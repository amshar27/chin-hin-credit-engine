"""
ctos_extractor_agent.py
-----------------------
Extracts structured credit data from a CTOS PDF report.

Extraction strategy (with automatic fallback):
  1. PRIMARY — pdfplumber text extraction (fast, for digital PDFs).
  2. FALLBACK — PyMuPDF page-to-image rendering + vision API call
               (for scanned / image-only PDFs with no selectable text).
"""

import base64
import io
import logging
from typing import Any

import fitz          # PyMuPDF
import pdfplumber

from app.agents.foundry_client import CTOS_AGENT_ID, call_agent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Document-validation gate
# ---------------------------------------------------------------------------

class InvalidDocumentError(ValueError):
    """Raised when the uploaded PDF is not a valid CTOS credit report."""


# Keywords that strongly indicate a genuine CTOS credit report.
# We require >= 2 hits to allow for partial or reformatted reports while
# still rejecting menus, receipts, and random PDFs.
_CTOS_MARKERS = (
    "ctos",
    "ccris",
    "credit report",
    "company report",
    "company search",
    "litigation",
    "financial highlights",
    "financial summary",
    "directors",
    "shareholders",
    "paid-up capital",
    "paid up capital",
    "trade referees",
    "trade references",
    "special attention",
    "bank negara",
    "registration no",
    "ccris payment",
    "outstanding balance",
    "facilities",
)


def validate_is_ctos_report(text: str) -> None:
    """
    Pre-flight check: does the extracted text contain enough CTOS-specific
    markers to be a genuine credit report?

    Raises InvalidDocumentError if the document fails the check, preventing
    a wasted LLM call on garbage input.
    """
    text_lower = text.lower()
    hits = sum(1 for marker in _CTOS_MARKERS if marker in text_lower)
    if hits < 2:
        raise InvalidDocumentError(
            "The uploaded file does not appear to be a valid CTOS credit report. "
            "Please upload a genuine CTOS company or individual credit report PDF."
        )


# Minimum characters extracted before we consider text extraction successful.
_MIN_TEXT_LENGTH = 100

# Maximum pages to render as images to stay within vision token limits.
_MAX_IMAGE_PAGES = 10

# ---------------------------------------------------------------------------
# Extraction prompt — shared by both text and image paths
# ---------------------------------------------------------------------------

_EXTRACTION_PROMPT = """You are a CTOS Credit Report data extraction specialist. Extract ALL of the following fields from the raw CTOS report text below and return them as a single strict JSON object.

MANDATORY fields to extract (use null if not found):

COMPANY IDENTIFICATION:
- company_name (string)
- reg_no (string): the company's registration number
- incorporation_date (string)
- business_type (string): categorize as one of Dealer, Trader, Contractor, Manufacturer, Service Provider, or Other
- paid_up_capital_myr (number): paid-up capital in MYR

ADVERSE STATUS FLAGS (critical — read carefully):
- status_code_k (boolean): TRUE if you see "Status Code K", "Code K", "AKPK", or "Debt Management Counselling/Program" anywhere in the report
- status_code_10 (boolean): TRUE if you see "Status Code 10", "Code 10", or "Summons Filed" anywhere in the report
- special_attention_accounts (boolean): TRUE if you see "Pink Highlight", "SAA", or "Special Attention Account" anywhere in the report
- adverse_status_notes (string): verbatim excerpt(s) from the report that triggered any of the above flags; null if none

FINANCIAL SUMMARY (most recent year):
- annual_revenue_myr (number)
- net_profit_myr (number)
- total_assets_myr (number)
- total_liabilities_myr (number)
- outstanding_facilities (list of objects with keys: bank, facility_type, limit_myr, outstanding_myr)

FIVE-YEAR FINANCIAL TREND (critical — locate the "Financial Highlights", "5-Year Financial Summary", or equivalent table in the CTOS report and extract each year's figures):
  Look explicitly for rows or columns labeled: "Turnover", "Revenue", "Paid-up Capital", "Net Profit", "Profit After Tax", "Current Ratio", "Current Assets", "Current Liabilities", "Total Liabilities", "Shareholders Equity".
- financial_trend (list of objects, ordered OLDEST to NEWEST, each with keys:
    year (string e.g. "2020"),
    revenue_myr (number or null): from the "Turnover" or "Revenue" row — these are synonyms,
    net_profit_myr (number or null): from the "Net Profit" or "Profit After Tax" row,
    working_capital_myr (number or null): current_assets minus current_liabilities if both are available; else null,
    current_ratio (number or null): from the "Current Ratio" row directly, OR calculate as current_assets / current_liabilities; round to 2 decimal places,
    gearing_ratio (number or null): total_liabilities divided by total_equity, rounded to 2 decimal places
  )
  If fewer than 5 years are available, return only what is present. If no trend data is available, return an empty list [].

ADDITIONAL FINANCIAL METRICS (from the most recent year in the financial highlights table):
- paid_up_capital_myr (number): from the "Paid-up Capital" row — this is the registered share capital
- turnover_myr (number): same as annual_revenue_myr; from the "Turnover" row of the most recent year
- current_ratio (number): from the "Current Ratio" row of the most recent year, or null if not found

INDIVIDUAL APPLICANT (complete only if this report is for a Person/Individual, not a Company):
- is_individual_report (boolean): TRUE only if this is a personal CTOS report, not a business report
- other_businesses_owned (list of objects with keys: business_name, reg_no, role): businesses where this individual is a director/owner
- repayment_track_record_12m (list of objects with keys:
    facility (string),
    bank (string),
    status_per_month (list of 12 strings, index 0 = oldest month, each entry is "OK", "LATE", or "MISSED")
  ): extract from the CCRIS payment history table if available

LITIGATION & LEGAL:
- legal_cases (list of objects with keys: case_type, amount_myr, status, plaintiff)
- ccris_status (string)
- payment_history_notes (string)

DIRECTORS & SHAREHOLDERS (critical — check each person's age):
- directors (list of objects with keys: name, ic_no, age (number or null), designation, shareholding_pct)
- directors_above_70 (list of strings): full names of any director or shareholder whose age is 70 or above
- has_director_above_70 (boolean): TRUE if directors_above_70 is non-empty

TRADE REFERENCES:
- trade_referees (list of objects with keys: company, credit_limit_myr, payment_conduct)

Return ONLY the JSON object. Do not include any explanation, markdown, or code fences."""

_OCR_PROMPT_PREFIX = """NOTE: This is a SCANNED document (image-based PDF with no selectable text).
Perform OCR-style reading of the page images attached and extract all visible text before applying the instructions below.

""" + _EXTRACTION_PROMPT + "\n\n--- EXTRACT FROM THE ATTACHED PAGE IMAGES ---"

_TEXT_PROMPT_PREFIX = _EXTRACTION_PROMPT + "\n\n--- RAW CTOS REPORT TEXT BEGINS ---\n"


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------

def extract_ctos_data(pdf_bytes: bytes) -> dict[str, Any]:
    """
    Extract structured CTOS data from PDF bytes.

    Tries text extraction first; falls back to image-based OCR if the PDF
    contains no selectable text (e.g. a scanned document).

    Args:
        pdf_bytes: Raw bytes of the uploaded CTOS PDF.

    Returns:
        Structured dict with all CTOS fields.

    Raises:
        ValueError:   If neither text nor images can be extracted.
        RuntimeError: If the Foundry agent call fails.
    """
    # --- Primary path: text extraction ------------------------------------
    try:
        raw_text = _extract_text(pdf_bytes)
    except Exception as exc:
        logger.warning("pdfplumber text extraction failed: %s — trying image fallback.", exc)
        raw_text = ""

    if len(raw_text.strip()) >= _MIN_TEXT_LENGTH:
        logger.info("Text path — %d characters extracted.", len(raw_text))
        validate_is_ctos_report(raw_text)
        payload = _TEXT_PROMPT_PREFIX + raw_text
        logger.info("Calling CTOS Extractor agent (text mode, agent_id=%s) …", CTOS_AGENT_ID)
        result = call_agent(CTOS_AGENT_ID, payload, expect_json=True)

    else:
        # --- Fallback path: image-based OCR -------------------------------
        logger.info(
            "Text extraction returned %d chars (below threshold of %d) — "
            "falling back to image-based OCR.",
            len(raw_text.strip()),
            _MIN_TEXT_LENGTH,
        )
        images = _pdf_to_base64_images(pdf_bytes)
        if not images:
            raise ValueError(
                "PDF contains no extractable text and could not be rendered as images. "
                "Please ensure the file is a valid, non-corrupted PDF."
            )
        logger.info(
            "Calling CTOS Extractor agent (OCR/image mode, %d page(s), agent_id=%s) …",
            len(images),
            CTOS_AGENT_ID,
        )
        result = call_agent(CTOS_AGENT_ID, _OCR_PROMPT_PREFIX, expect_json=True, images=images)

    logger.info(
        "CTOS extraction complete — status_code_k=%s status_code_10=%s has_director_above_70=%s",
        result.get("status_code_k"),
        result.get("status_code_10"),
        result.get("has_director_above_70"),
    )
    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_text(pdf_bytes: bytes) -> str:
    """Use pdfplumber to concatenate text from all pages of a PDF."""
    pages: list[str] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            pages.append(text)
            logger.debug("Page %d: %d chars extracted.", i + 1, len(text))
    return "\n".join(pages)


def _pdf_to_base64_images(pdf_bytes: bytes) -> list[str]:
    """
    Render each PDF page to a PNG image using PyMuPDF and return as
    a list of base64-encoded strings.

    Pages are rendered at 2× zoom (144 DPI) for legibility. Capped at
    _MAX_IMAGE_PAGES to avoid exceeding the vision token limit.
    """
    images: list[str] = []
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    page_count = min(len(doc), _MAX_IMAGE_PAGES)
    if len(doc) > _MAX_IMAGE_PAGES:
        logger.warning(
            "PDF has %d pages; only the first %d will be sent as images.",
            len(doc),
            _MAX_IMAGE_PAGES,
        )

    zoom = fitz.Matrix(2, 2)  # 2× = ~144 DPI — readable without excess tokens
    for i in range(page_count):
        pix = doc[i].get_pixmap(matrix=zoom)
        png_bytes = pix.tobytes("png")
        images.append(base64.b64encode(png_bytes).decode("utf-8"))
        logger.debug("Page %d rendered — %d bytes as PNG.", i + 1, len(png_bytes))

    doc.close()
    return images
