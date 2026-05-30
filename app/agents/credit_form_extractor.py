"""
credit_form_extractor.py
------------------------
Extracts a fully-structured CreditScoringDetailedForm from CTOS PDF bytes by
routing through the project's shared Foundry agent utility (call_agent).

Architecture
------------
• Zero-credential policy — no AZURE_OPENAI_API_KEY, no direct openai client.
• All model calls go through call_agent() in foundry_client.py, which uses
  DefaultAzureCredential via azure-ai-projects (AIProjectClient).
• The CreditScoringDetailedForm JSON Schema is injected verbatim into the
  user_message so the CTOS-Extractor agent knows the exact keys to return.
• The raw dict returned by call_agent(expect_json=True) is validated through
  CreditScoringDetailedForm.model_validate() before being returned to the router.

Flow
----
1. PDF bytes → plain text via pdfplumber  (primary path).
2. If text < _MIN_TEXT_LENGTH chars      → render pages as base64 PNGs (OCR fallback).
3. Build user_message: extraction rules + injected JSON Schema + CTOS content.
4. call_agent("CTOS-Extractor:2", user_message, expect_json=True, images=...)
   returns a dict.
5. CreditScoringDetailedForm.model_validate(dict) → validated Pydantic instance.
"""

from __future__ import annotations

import base64
import copy
import io
import json
import logging

import fitz        # PyMuPDF — image fallback for scanned PDFs
import pdfplumber
from pydantic import ValidationError

from app.agents.ctos_extractor_agent import InvalidDocumentError, validate_is_ctos_report
from app.agents.foundry_client import CTOS_AGENT_ID, call_agent
from app.models.credit_scoring_form import CreditScoringDetailedForm

logger = logging.getLogger(__name__)

# Minimum characters pdfplumber must return before we trust text extraction.
_MIN_TEXT_LENGTH = 100

# Maximum PDF pages rendered as images to stay within vision token limits.
_MAX_IMAGE_PAGES = 10

# ---------------------------------------------------------------------------
# Schema — generated once at import time, injected into every user_message.
# model_json_schema() produces the full JSON Schema including all nested
# $defs and field descriptions, which guides the model on keys + value types.
# ---------------------------------------------------------------------------

_FORM_SCHEMA: dict = CreditScoringDetailedForm.model_json_schema()
_FORM_SCHEMA_STR: str = json.dumps(_FORM_SCHEMA, indent=2)

# ---------------------------------------------------------------------------
# Extraction instructions — embedded in user_message (the Foundry Responses
# API has no separate system-prompt field; all instructions go in user turn).
# ---------------------------------------------------------------------------

_INSTRUCTIONS = """\
!!!CRITICAL DIRECTIVE FOR ALL ENUM/LITERAL FIELDS!!!
=====================================================
Your output is validated by a STRICT CODE PARSER that performs exact string
matching. Whenever a field expects a specific string option (an enum/Literal),
you MUST copy that string EXACTLY, character-by-character.

DO NOT change capitalization (e.g. 'Years' must stay 'Years', not 'years').
DO NOT add or remove spaces (e.g. '( 2.00 - 2.99 )' must stay exactly that).
DO NOT add extra words or punctuation.
DO NOT "correct" what looks like a typo — the strings are intentionally formatted.

If you alter even a single character of a Literal option string, the system
will crash with a ValidationError and the entire extraction will fail.
=====================================================

You are a credit scoring form extraction specialist for Chin Hin Group, a \
Malaysian building materials distributor.

TASK
====
Read the CTOS credit report supplied below and extract structured data to \
populate the Chin Hin Credit Scoring Form. Return ONLY a single JSON object \
that strictly conforms to the OUTPUT SCHEMA section — no extra keys, no \
markdown fences, no explanation text.

TOP-LEVEL STRUCTURE (MANDATORY)
================================
The JSON object you return MUST have EXACTLY these top-level keys — no more,
no fewer. Do NOT invent alternative key names (e.g. "financials" is wrong;
"financial_information" is correct):

  customer_type
  type_of_customer
  salesman_profile
  customer_information
  ccris_for_company
  financial_information
  internal_information
  pg_bg_cg_obtained
  personal_guarantee
  guarantor_ccris_profiles
  company_background
  additional_information
  proposed_credit_limit

Each value must be a nested JSON object (or list for guarantor_ccris_profiles)
whose sub-keys match the OUTPUT SCHEMA exactly. If an entire section is absent
from the report, still include its key and set all sub-fields to null.

EXTRACTION RULES
================

GENERAL
-------
- All monetary amounts in MYR as plain numbers (e.g. 1500000.0 for MYR 1.5 M).
  DO NOT use commas as thousands separators (output 1500000.0, NOT 1,500,000.0).
- Dates: ISO 8601 (YYYY-MM-DD) where possible; else "FY2023" / "31 Dec 2023".
- Yes/No fields: return the string "Yes" or "No" — not true/false booleans.
- Fields not determinable from the report: return null — do NOT guess.
- Nested sections that are entirely absent: return their object with all
  fields set to null; do NOT omit the section key.
- BANDED / LITERAL FIELDS: Many fields require you to compute a raw figure
  and then map it to an EXACT band string. NEVER output the raw number for
  a banded field — always output the matching band string from the schema.

CCRIS FOR COMPANY (ccris_for_company)
--------------------------------------
- legal_cases_unsettled : select the exact Literal band based on the count
  of active/unsettled litigation from the CTOS Legal section.
- blacklist_cases : select the exact Literal band based on the count of
  winding-up / bankruptcy / blacklist entries.
- special_attention_account_spa : "Yes" if "SAA", "Pink Highlight", or
  "Special Attention Account" appears anywhere; otherwise "No".
- repayment_to_banks : select the exact Literal from the schema based on
  the overall CCRIS repayment pattern across all facilities.
- total_facilities_limit_vs_outstanding_utilisation_pct : first compute the
  raw utilisation as (Σ Outstanding / Σ Limit) × 100, then map to the exact
  Literal band in the schema (e.g. 62% → '51% - 70%'). Output the band
  string, NOT the raw percentage.

FINANCIAL INFORMATION (financial_information)
---------------------------------------------
- Prefer the most recent year in "Financial Highlights" / "5-Year Financial
  Summary" table (rows: Turnover, Net Profit, Paid-up Capital, Current Ratio,
  Gearing Ratio, Net Worth, Working Capital / Net Current Assets).
- current_ratio : from "Current Ratio" row, or Current Assets / Current
  Liabilities. Round to 2 decimal places. Then map to the exact Literal band.
- gearing_ratio : from "Gearing Ratio" row, or Total Liabilities / Equity.
  Round to 2 decimal places. Then map to the exact Literal band.
- retained_profit_specified_amount : "Retained Earnings" / "Accumulated
  Losses" from balance sheet; negative if accumulated losses.
- net_worth_specified_amount : Shareholders' Equity / Total Equity.
- All turnover, net_profit_loss, net_worth, bank_statement_end_month_balance_rm
  fields require the exact Literal band string — never the raw MYR number.

COMPANY BACKGROUND (company_background)
----------------------------------------
- years_in_business : compute years from incorporation date to today, then
  map to the exact Literal band (e.g. 3 years → '2.1 - 5 Years').
- type_of_company : infer from name suffix ("Sdn Bhd", "Bhd", "Enterprise",
  "Partnership", "Sole Proprietor").
- paid_up_capital_rm : extract from CTOS company profile, then map to the
  exact Literal band.

GUARANTORS (guarantor_ccris_profiles)
--------------------------------------
- This key holds a JSON ARRAY — one object per guarantor found in the report.
- Extract from the personal CTOS / director section of the report.
- If two guarantors are present, output a list with two objects.
- If no guarantors are found, output an empty list [].
- guarantor_age_pg : compute from IC number if not explicit
  (YYMMDD-##-####; first 6 digits = birthdate).
- guarantor_range_age : map the computed age to the exact Literal band
  (e.g. age 45 → '40 - 49'; age >= 70 → '70 and above').
"""

# ---------------------------------------------------------------------------
# user_message builders
# ---------------------------------------------------------------------------

def _build_text_message(combined_text: str) -> str:
    """
    Construct the full user_message for digital (text-based) input.

    combined_text may contain both the CTOS report and the bank statement,
    already labelled with section headers by the caller.
    """
    return (
        f"{_INSTRUCTIONS}\n\n"
        "OUTPUT SCHEMA\n"
        "=============\n"
        "Return ONLY a JSON object whose top-level keys and nested structure\n"
        "match this JSON Schema exactly. Every section key must be present;\n"
        "use null for any field that cannot be determined.\n\n"
        f"{_FORM_SCHEMA_STR}\n\n"
        f"{combined_text}"
    )


def _build_ocr_message(bank_text: str = "") -> str:
    """
    Construct the text portion of the user_message for a scanned (image) PDF.
    The base64 page images are passed separately via the `images` kwarg.
    If bank_text is provided it is appended so the model can read it alongside
    the OCR'd CTOS images.
    """
    bank_section = (
        f"\n\n--- BANK STATEMENT TEXT ---\n{bank_text}" if bank_text.strip() else ""
    )
    return (
        "NOTE: This is a SCANNED document (image-based PDF). Perform OCR on\n"
        "the attached page images to read all visible text, then apply the\n"
        "extraction rules below.\n\n"
        f"{_INSTRUCTIONS}\n\n"
        "OUTPUT SCHEMA\n"
        "=============\n"
        "Return ONLY a JSON object whose top-level keys and nested structure\n"
        "match this JSON Schema exactly. Every section key must be present;\n"
        "use null for any field that cannot be determined.\n\n"
        f"{_FORM_SCHEMA_STR}\n\n"
        f"--- EXTRACT FROM THE ATTACHED PAGE IMAGES ---{bank_section}"
    )


# ---------------------------------------------------------------------------
# Pydantic validation helper
# ---------------------------------------------------------------------------

def _nullify_invalid_fields(raw: dict, errors: list) -> dict:
    """
    Deep-copy *raw* and set every field named in *errors* to None.

    Handles:
    - Nested dicts  (e.g. loc = ('financial_information', 'gearing_ratio'))
    - List elements (e.g. loc = ('guarantor_ccris_profiles', 0, 'guarantor_range_age'))
    - Extra keys at the top level (type == 'extra_forbidden') → deleted, not nulled

    Returns the cleaned copy.
    """
    clean = copy.deepcopy(raw)

    for error in errors:
        loc = error.get("loc", ())
        if not loc:
            continue

        # Traverse to the parent container of the offending field
        container = clean
        for key in loc[:-1]:
            if isinstance(container, dict) and key in container:
                container = container[key]
            elif isinstance(container, list) and isinstance(key, int) and key < len(container):
                container = container[key]
            else:
                container = None
                break

        if container is None:
            continue

        last = loc[-1]
        if error.get("type") == "extra_forbidden":
            # Extra keys must be deleted — setting them to None still violates forbid
            if isinstance(container, dict) and last in container:
                del container[last]
        else:
            # Nullify the invalid leaf so the Optional[Literal[...]] accepts None
            if isinstance(container, dict) and last in container:
                container[last] = None
            elif isinstance(container, list) and isinstance(last, int) and last < len(container):
                container[last] = None

    return clean


def _validate(raw: dict, mode: str) -> CreditScoringDetailedForm:
    """
    Validate the raw dict returned by call_agent against CreditScoringDetailedForm.

    Graceful-degradation strategy
    ------------------------------
    First attempt  — strict model_validate.  If it succeeds, return immediately.
    On ValidationError  — log the offending fields, nullify them in a deep copy of
                          the raw dict, and retry validation once.
    Second failure — raise RuntimeError so FastAPI surfaces a clean 500.  This
                     only happens when the model structure itself is wrong (e.g.
                     the LLM returned a completely different JSON shape), not when
                     individual Literal values are hallucinated.
    """
    try:
        form = CreditScoringDetailedForm.model_validate(raw)
    except ValidationError as first_exc:
        errors = first_exc.errors(include_url=False)
        nullified_paths = [
            ".".join(str(k) for k in e["loc"]) for e in errors
        ]
        logger.warning(
            "Credit form validation failed (%s mode) — %d error(s): [%s]. "
            "Nullifying invalid fields and retrying…",
            mode,
            len(errors),
            ", ".join(nullified_paths),
        )

        clean = _nullify_invalid_fields(raw, errors)

        try:
            form = CreditScoringDetailedForm.model_validate(clean)
            logger.info(
                "Credit form recovered after nullifying %d field(s): [%s]",
                len(nullified_paths),
                ", ".join(nullified_paths),
            )
        except ValidationError as second_exc:
            raise RuntimeError(
                f"Credit form schema validation failed ({mode} mode) after nullifying "
                f"{len(errors)} field(s) — {second_exc.error_count()} error(s) remain: "
                f"{second_exc.errors(include_url=False)}"
            ) from second_exc

    logger.info(
        "Credit form validated (%s mode) — company=%r reg_no=%r",
        mode,
        form.customer_information.company_name,
        form.customer_information.company_business_registration_no,
    )
    return form


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_credit_scoring_form(
    pdf_bytes: bytes,
    bank_pdf_bytes: bytes | None = None,
) -> CreditScoringDetailedForm:
    """
    Extract a validated CreditScoringDetailedForm from raw CTOS PDF bytes,
    optionally enriched with a bank statement PDF.

    Routes through call_agent() — DefaultAzureCredential, zero API-key policy.

    Primary path  : pdfplumber text extraction → call_agent (text message).
    Fallback path : PyMuPDF page images        → call_agent (OCR message + images).

    When bank_pdf_bytes is supplied its text is extracted and concatenated with
    the CTOS text under a '--- BANK STATEMENT ---' header so the model can
    populate financial_information.bank_statement_provided and
    financial_information.bank_statement_end_month_balance_rm.

    Args:
        pdf_bytes:      Raw bytes of the uploaded CTOS PDF.
        bank_pdf_bytes: Optional raw bytes of the bank statement PDF.

    Returns:
        A validated CreditScoringDetailedForm Pydantic model instance.

    Raises:
        ValueError:   PDF yields neither text nor renderable images.
        RuntimeError: call_agent fails, returns invalid JSON, or Pydantic
                      validation cannot reconcile the agent's response with
                      the schema.
    """
    # ── Step 1: extract bank statement text (if provided) ─────────────────
    bank_text = ""
    if bank_pdf_bytes:
        bank_text = _extract_text(bank_pdf_bytes)
        logger.info(
            "Credit form extractor — bank statement text: %d chars extracted.",
            len(bank_text),
        )

    # ── Step 2: attempt CTOS text extraction ──────────────────────────────
    raw_text = _extract_text(pdf_bytes)

    if len(raw_text.strip()) >= _MIN_TEXT_LENGTH:
        logger.info(
            "Credit form extractor — text path: %d chars extracted from CTOS.",
            len(raw_text),
        )
        validate_is_ctos_report(raw_text)
        combined_text = (
            f"--- CTOS REPORT ---\n{raw_text}"
            + (f"\n\n--- BANK STATEMENT ---\n{bank_text}" if bank_text.strip() else "")
        )
        user_message = _build_text_message(combined_text)
        raw_dict = call_agent(CTOS_AGENT_ID, user_message, expect_json=True)
        return _validate(raw_dict, mode="text")

    # ── Step 3: fallback to image-based OCR for CTOS ──────────────────────
    logger.info(
        "Credit form extractor — text path yielded %d chars (below threshold %d); "
        "falling back to image OCR.",
        len(raw_text.strip()),
        _MIN_TEXT_LENGTH,
    )
    images = _pdf_to_base64_images(pdf_bytes)
    if not images:
        raise ValueError(
            "CTOS PDF contains no extractable text and could not be rendered "
            "as images. Verify the file is a valid, non-corrupted PDF."
        )

    logger.info(
        "Credit form extractor — OCR path: %d page image(s) being sent to agent.",
        len(images),
    )
    user_message = _build_ocr_message(bank_text=bank_text)
    raw_dict = call_agent(
        CTOS_AGENT_ID,
        user_message,
        expect_json=True,
        images=images,
    )
    return _validate(raw_dict, mode="ocr")


# ---------------------------------------------------------------------------
# PDF utilities
# ---------------------------------------------------------------------------

def _extract_text(pdf_bytes: bytes) -> str:
    """Concatenate selectable text from all pages using pdfplumber."""
    pages: list[str] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            pages.append(text)
            logger.debug("Page %d: %d chars.", i + 1, len(text))
    return "\n".join(pages)


def _pdf_to_base64_images(pdf_bytes: bytes) -> list[str]:
    """
    Render each PDF page to a 2× PNG (≈144 DPI) and return base64 strings.
    Capped at _MAX_IMAGE_PAGES to stay within vision token limits.
    """
    images: list[str] = []
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page_count = min(len(doc), _MAX_IMAGE_PAGES)
    if len(doc) > _MAX_IMAGE_PAGES:
        logger.warning(
            "PDF has %d pages; only first %d sent as images.",
            len(doc), _MAX_IMAGE_PAGES,
        )
    zoom = fitz.Matrix(2, 2)
    for i in range(page_count):
        pix = doc[i].get_pixmap(matrix=zoom)
        images.append(base64.b64encode(pix.tobytes("png")).decode("utf-8"))
        logger.debug("Page %d rendered — %d bytes.", i + 1, len(images[-1]))
    doc.close()
    return images
