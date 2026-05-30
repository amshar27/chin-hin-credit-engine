"""
main.py
-------
FastAPI entry point for the Autonomous Credit Scoring Engine.

Run locally:
    uvicorn app.main:app --reload
"""

import io
import logging

import pdfplumber
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.agents.agent_orchestrator import AgentOrchestrator, CreditDecision
from app.agents.chief_credit_officer_agent import generate_credit_decision
from app.agents.credit_form_extractor import extract_credit_scoring_form
from app.agents.ctos_extractor_agent import InvalidDocumentError
from app.agents.multi_agent_copilot import RefineDataRequest, execute_copilot_pipeline
from app.models.credit_scoring_form import CreditScoringDetailedForm

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Heuristic document-type gate — runs BEFORE any LLM call to save tokens
# ---------------------------------------------------------------------------

def _validate_ctos_markers(pdf_bytes: bytes) -> None:
    """
    Quick keyword check on raw PDF text. If neither 'CTOS' nor 'CCRIS'
    appears anywhere in the document, it is definitely not a CTOS credit
    report — reject immediately with HTTP 400.
    """
    try:
        pages: list[str] = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                pages.append(page.extract_text() or "")
        raw_text_upper = "\n".join(pages).upper()
    except Exception as exc:
        logger.warning("pdfplumber text extraction failed during marker check: %s", exc)
        return  # If we can't extract text, let the downstream agents handle it

    if "CTOS" not in raw_text_upper and "CCRIS" not in raw_text_upper:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Invalid document type. The uploaded PDF does not contain CTOS or CCRIS markers. "
                "Please upload a valid CTOS credit report."
            ),
        )
    logger.info("CTOS marker check passed — found CTOS/CCRIS keywords in document.")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Chin Hin Autonomous Credit Scoring Engine",
    description=(
        "Orchestrates four AI agents hosted on Microsoft Foundry to produce "
        "a structured credit decision from a CTOS PDF report."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_orchestrator = AgentOrchestrator()


# ---------------------------------------------------------------------------
# Recalculate-score helpers
# ---------------------------------------------------------------------------


class RecalculateScoreRequest(BaseModel):
    form: CreditScoringDetailedForm = Field(
        description="Officer-corrected CreditScoringDetailedForm (all 12 sections)."
    )
    requested_amount: float = Field(
        default=0.0,
        description="Customer's requested credit limit in MYR (0 if unspecified).",
    )


def _form_to_ctos_dict(form: CreditScoringDetailedForm) -> dict:
    """Convert the form into a flat CTOS-style dict the CCO agent understands."""
    ccris = form.ccris_for_company
    fin = form.financial_information
    bg = form.company_background
    info = form.customer_information
    add = form.additional_information
    profiles = form.guarantor_ccris_profiles or []

    spa_raw = (ccris.special_attention_account_spa or "").strip().lower()
    special_attention = spa_raw in ("yes", "y", "true", "1")

    directors_above_70 = [
        g.guarantor_info_pg or f"Guarantor No. {i + 1}"
        for i, g in enumerate(profiles)
        if g.guarantor_age_pg is not None and g.guarantor_age_pg >= 70
    ]
    has_director_above_70 = bool(directors_above_70)

    guarantors_list = [
        {
            "name": g.guarantor_info_pg,
            "age": g.guarantor_age_pg,
            "age_band": g.guarantor_range_age,
            "legal_cases": g.guarantor_legal_cases_unsettled,
            "blacklist": g.guarantor_blacklist_case,
            "repayment": g.repayment_to_banks,
            "utilisation": g.total_facilities_limit_vs_outstanding_utilisation_pct,
        }
        for g in profiles
    ]

    return {
        # Identity
        "company_name": info.company_name,
        "company_reg_no": info.company_business_registration_no,
        # Adverse flags (top-level — read directly by CCO agent instructions)
        "status_code_k": False,
        "status_code_10": False,
        "special_attention_accounts": special_attention,
        "has_director_above_70": has_director_above_70,
        "directors_above_70": directors_above_70,
        # CCRIS
        "legal_cases_unsettled": ccris.legal_cases_unsettled,
        "blacklist_cases": ccris.blacklist_cases,
        "special_attention_account_spa": ccris.special_attention_account_spa,
        "repayment_to_banks": ccris.repayment_to_banks,
        "facility_utilisation_pct": ccris.total_facilities_limit_vs_outstanding_utilisation_pct,
        # Financials
        "annual_revenue_myr": fin.turnover_specified_amount,
        "turnover_band": fin.turnover,
        "net_profit_loss": fin.net_profit_loss,
        "net_profit_myr": fin.net_profit_specified_amount,
        "net_worth_myr": fin.net_worth_specified_amount,
        "current_ratio": fin.current_ratio,
        "gearing_ratio": fin.gearing_ratio,
        "retained_profit_accumulated_losses": fin.retained_profit_accumulated_losses,
        # Company background
        "type_of_company": bg.type_of_company,
        "years_in_business": bg.years_in_business,
        "paid_up_capital_rm": bg.paid_up_capital_rm,
        "nature_of_business": add.nature_of_business_category,
        # Guarantors (list — one entry per guarantor)
        "guarantors": guarantors_list,
    }


def _form_to_erp_dict(form: CreditScoringDetailedForm) -> dict:
    """Derive an ERP-style dict from the Internal Information section."""
    ii = form.internal_information
    internal_pattern = ii.group_exposure_internal_payment_pattern
    external_pattern = ii.trade_reference_external_payment_pattern
    payment_conduct = internal_pattern or external_pattern or "Unknown"
    status = "Existing Customer" if internal_pattern else "New Customer"
    return {
        "status": status,
        "payment_conduct": payment_conduct,
        "trade_reference_payment_pattern": external_pattern,
        "group_exposure_with_other_subsidiaries": ii.group_exposure_with_other_subsidiaries,
        "common_director_or_shareholder_or_guarantor": ii.common_director_or_shareholder_or_guarantor,
        "existing_group_exposure_myr": 0.0,
        "relationship_years": 0,
    }


def _form_to_bank_dict(form: CreditScoringDetailedForm) -> dict:
    """Derive a bank-statement-style dict from the Financial Information section."""
    fin = form.financial_information
    provided = (fin.bank_statement_provided or "").strip().lower()
    if provided in ("yes", "y", "true", "1"):
        return {
            "summary": "Bank statement provided by officer.",
            "average_end_month_balance_myr": fin.bank_statement_end_month_balance_rm,
            "bounced_checks": 0,
        }
    return {"summary": "No bank statement provided."}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health", tags=["Health"])
def health_check() -> dict:
    """Simple liveness probe."""
    return {"status": "ok"}


@app.post(
    "/api/v1/process-credit-application",
    response_model=CreditDecision,
    status_code=status.HTTP_200_OK,
    tags=["Credit Engine"],
    summary="Submit a CTOS PDF for autonomous credit scoring",
    response_description="Structured credit decision produced by the Chief Credit Officer agent.",
)
async def process_credit_application(
    ctos_pdf: UploadFile = File(..., description="CTOS PDF report for the applicant company."),
    company_reg_no: str | None = Form(None, description="Company registration number (e.g. 202301012345). Optional — auto-extracted from CTOS PDF if omitted."),
    requested_amount: float = Form(0.0, description="Customer's requested credit limit in MYR (0 if unspecified)."),
    bank_statement_pdf: UploadFile | None = File(None, description="Optional bank statement PDF."),
) -> JSONResponse:
    """
    Accepts a CTOS PDF, a company registration number, an optional requested
    credit amount, and an optional bank statement PDF, then runs the full
    four-agent orchestration pipeline:

    1. **CTOSExtractorAgent**      — parses structured data from the CTOS PDF.
    2. **InternalERPAgent**        — fetches internal trade & credit history.
    3. **BankStatementAnalyst**    — analyses bank statement (if provided).
    4. **ChiefCreditOfficer**      — consolidates all inputs into a final decision,
                                     scoring against a 100-point scorecard and
                                     comparing the calculated limit to requested_amount.

    Returns a JSON credit decision including recommendation, proposed limit,
    final score, risk grade, guarantee type, and key reasoning.
    """
    # -- Validate CTOS file type -------------------------------------------
    if ctos_pdf.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Expected a PDF file for ctos_pdf, received: {ctos_pdf.content_type}",
        )

    logger.info(
        "Received credit application — company_reg_no=%s | requested=MYR %.2f | ctos=%s | bank=%s",
        company_reg_no or "(auto-detect from CTOS)",
        requested_amount,
        ctos_pdf.filename,
        bank_statement_pdf.filename if bank_statement_pdf else "not provided",
    )

    # -- Read CTOS PDF bytes -----------------------------------------------
    pdf_bytes = await ctos_pdf.read()
    if not pdf_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded CTOS PDF file is empty.",
        )

    # -- Heuristic gate: reject non-CTOS PDFs before burning LLM tokens ---
    _validate_ctos_markers(pdf_bytes)

    # -- Read bank statement bytes (optional) ------------------------------
    bank_pdf_bytes: bytes | None = None
    if bank_statement_pdf is not None:
        bank_pdf_bytes = await bank_statement_pdf.read() or None

    # -- Run agent pipeline ------------------------------------------------
    try:
        decision: CreditDecision = _orchestrator.run(
            pdf_bytes=pdf_bytes,
            company_reg_no=company_reg_no or "",
            requested_amount=requested_amount,
            bank_pdf_bytes=bank_pdf_bytes,
        )
    except InvalidDocumentError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Agent pipeline failed for %s", company_reg_no)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent pipeline error: {exc}",
        ) from exc

    return JSONResponse(content=decision.model_dump())


# ---------------------------------------------------------------------------
# Structured Extraction — Credit Scoring Form
# ---------------------------------------------------------------------------


@app.post(
    "/api/v1/extract-credit-scoring-form",
    response_model=CreditScoringDetailedForm,
    status_code=status.HTTP_200_OK,
    tags=["Credit Engine"],
    summary="Extract a structured Credit Scoring Form from a CTOS PDF",
    response_description=(
        "A fully structured CreditScoringDetailedForm populated by Azure OpenAI "
        "structured outputs — all 12 sections, guaranteed schema conformance."
    ),
)
async def extract_credit_scoring_form_endpoint(
    ctos_pdf: UploadFile = File(
        ...,
        description="CTOS PDF report for the applicant company or individual.",
    ),
    bank_statement_pdf: UploadFile | None = File(
        None,
        description="Optional bank statement PDF — when provided, its text is "
                    "concatenated with the CTOS text so the extractor can populate "
                    "bank_statement_provided and bank_statement_end_month_balance_rm.",
    ),
) -> JSONResponse:
    """
    Accepts a CTOS PDF (and an optional bank statement PDF) and runs them through
    the **Credit Scoring Form Extractor**, which uses Azure OpenAI **structured
    outputs** to guarantee that the response exactly matches the
    `CreditScoringDetailedForm` Pydantic schema.

    The 12 extracted sections are:

    | # | Section | Key data |
    |---|---------|----------|
    | 1 | Type of Customer | New / Existing / Potential |
    | 2 | Salesman Profile | Company, branch, salesman |
    | 3 | Customer Information | Reg no, name, address, credit terms |
    | 4 | CCRIS for Company | Legal cases, blacklist, repayment, utilisation |
    | 5 | Financial Information | Turnover, profit, ratios, bank statement |
    | 6 | Internal Information | Trade references, group exposure, payment pattern |
    | 7 | PG/BG/CG Obtained | Guarantee type obtained |
    | 8 | Personal Guarantee | Guarantor count and amount |
    | 9 | CCRIS for Guarantor No.1 | Age, legal cases, CCRIS conduct |
    | 10 | Company Background | Type, years, paid-up capital |
    | 11 | Additional Information | Directors, nature of business |
    | 12 | Proposed Credit Limit | Proposed limit and group exposure |

    Missing fields are returned as `null` — the endpoint never fails due to
    missing data, only due to file or API errors.
    """
    # -- Validate CTOS file type ------------------------------------------
    if ctos_pdf.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"Expected a PDF file, received content-type: {ctos_pdf.content_type}"
            ),
        )

    logger.info(
        "Credit scoring form extraction requested — ctos=%s bank=%s",
        ctos_pdf.filename,
        bank_statement_pdf.filename if bank_statement_pdf else "not provided",
    )

    # -- Read CTOS PDF bytes ----------------------------------------------
    pdf_bytes = await ctos_pdf.read()
    if not pdf_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded CTOS PDF file is empty.",
        )

    # -- Heuristic gate: reject non-CTOS PDFs before burning LLM tokens ---
    _validate_ctos_markers(pdf_bytes)

    # -- Read bank statement bytes (optional) -----------------------------
    bank_pdf_bytes: bytes | None = None
    if bank_statement_pdf is not None:
        bank_pdf_bytes = await bank_statement_pdf.read() or None

    # -- Run structured extraction ----------------------------------------
    try:
        form: CreditScoringDetailedForm = extract_credit_scoring_form(
            pdf_bytes, bank_pdf_bytes=bank_pdf_bytes
        )
    except InvalidDocumentError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        logger.exception("Credit form extraction failed for %s", ctos_pdf.filename)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Azure OpenAI extraction error: {exc}",
        ) from exc

    logger.info(
        "Credit scoring form extracted — company=%r reg_no=%r bank_provided=%s",
        form.customer_information.company_name,
        form.customer_information.company_business_registration_no,
        form.financial_information.bank_statement_provided,
    )

    # PDPA / Stateless Processing — bytes go out of scope here;
    # no raw personal data is persisted beyond this request.
    return JSONResponse(content=form.model_dump())


# ---------------------------------------------------------------------------
# Recalculate Score — officer-corrected form → Chief Credit Officer agent
# ---------------------------------------------------------------------------


@app.post(
    "/api/v1/recalculate-score",
    response_model=CreditDecision,
    status_code=status.HTTP_200_OK,
    tags=["Credit Engine"],
    summary="Re-score using officer-corrected CTOS form data",
    response_description=(
        "A new CreditDecision produced by the Chief Credit Officer agent "
        "from officer-corrected form data, without re-running PDF extraction."
    ),
)
async def recalculate_score(body: RecalculateScoreRequest) -> JSONResponse:
    """
    Accepts an officer-corrected **CreditScoringDetailedForm** and
    re-runs only the **Chief Credit Officer** agent to produce a fresh
    credit decision — no PDF extraction agents are invoked.

    The form data is converted into structured CTOS, ERP, and bank dicts
    and passed directly to the CCO agent via the existing `call_agent()`
    utility.  All adverse-flag hard-stop rules (Status Code K/10, SAA,
    director age ≥ 70) are derived from the corrected form fields.
    """
    form = body.form
    company_reg_no = form.customer_information.company_business_registration_no or ""

    logger.info(
        "Recalculate-score requested — company_reg_no=%s requested_amount=MYR %.2f",
        company_reg_no,
        body.requested_amount,
    )

    ctos_data = _form_to_ctos_dict(form)
    erp_data = _form_to_erp_dict(form)
    bank_data = _form_to_bank_dict(form)

    try:
        decision_raw: dict = generate_credit_decision(
            ctos_data=ctos_data,
            erp_data=erp_data,
            bank_data=bank_data,
            requested_amount=body.requested_amount,
        )
    except Exception as exc:
        logger.exception("Recalculate-score CCO agent failed for %s", company_reg_no)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chief Credit Officer agent error: {exc}",
        ) from exc

    # Merge fields the CCO agent doesn't return but CreditDecision requires.
    decision_raw.setdefault("company_reg_no", company_reg_no)
    decision_raw.setdefault("financial_trend", [])
    decision_raw.setdefault("status_code_k", ctos_data["status_code_k"])
    decision_raw.setdefault("status_code_10", ctos_data["status_code_10"])
    decision_raw.setdefault("special_attention_accounts", ctos_data["special_attention_accounts"])
    decision_raw.setdefault("has_director_above_70", ctos_data["has_director_above_70"])
    decision_raw.setdefault("directors_above_70", ctos_data["directors_above_70"])
    decision_raw.setdefault("score_breakdown", [])
    decision_raw.setdefault("conditions", [])
    decision_raw.setdefault("key_reasons", [])

    decision = CreditDecision(**decision_raw)
    logger.info(
        "Recalculate-score complete — company=%s score=%s/100 recommendation=%s",
        company_reg_no,
        decision.final_score,
        decision.recommendation,
    )
    return JSONResponse(content=decision.model_dump())


# ---------------------------------------------------------------------------
# Data Copilot — natural language form refinement
# ---------------------------------------------------------------------------


class RefineDataResponse(BaseModel):
    """Response body for POST /api/refine-data."""

    updated_data: dict = Field(description="The (possibly modified) CreditScoringDetailedForm.")
    message: str = Field(description="Conversational AI response explaining changes or answering the query.")


@app.post(
    "/api/refine-data",
    response_model=RefineDataResponse,
    status_code=status.HTTP_200_OK,
    tags=["Credit Engine"],
    summary="Refine credit scoring form data or answer questions via natural language",
    response_description=(
        "The updated CreditScoringDetailedForm together with a conversational AI "
        "message.  If the pipeline fails at any stage, the original form is "
        "returned unchanged — this endpoint never errors on pipeline faults."
    ),
)
async def refine_data(body: RefineDataRequest) -> JSONResponse:
    """
    Accepts an officer's natural language instruction and the current state of
    the **CreditScoringDetailedForm**, then runs the four-stage Data Copilot
    pipeline.

    Returns ``{ updated_data, message }`` — the AI can both mutate form data
    **and** answer read-only questions about the current application.
    """
    logger.info(
        "Refine-data request — prompt=%r",
        body.user_prompt[:80],
    )

    updated_form, message = await execute_copilot_pipeline(
        current_data=body.current_data,
        user_prompt=body.user_prompt,
    )

    logger.info("Refine-data complete — message=%r", message[:80])
    return JSONResponse(content={
        "updated_data": updated_form.model_dump(),
        "message": message,
    })
