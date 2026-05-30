"""
agent_orchestrator.py
---------------------
Defines the AgentOrchestrator service class which coordinates the four AI agents
in the credit scoring pipeline:

    1. CTOSExtractorAgent   – Extracts structured data from the CTOS PDF.
    2. InternalERPAgent     – Fetches & analyses internal ERP/trade records.
    3. BankStatementAgent   – Analyses bank statement data (optional / mocked).
    4. ChiefCreditOfficer   – Consolidates all inputs into a final credit decision.

Each agent call is currently backed by a STUB that returns dummy JSON so that the
orchestration flow can be validated end-to-end before heavy logic is wired in.
"""

import json
import logging

from pydantic import BaseModel, Field

from app.agents.ctos_extractor_agent import extract_ctos_data
from app.agents.internal_erp_agent import query_internal_erp
from app.agents.bank_statement_analyst_agent import analyze_bank_statement
from app.agents.chief_credit_officer_agent import generate_credit_decision

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pydantic output schemas
# ---------------------------------------------------------------------------



class InternalERPOutput(BaseModel):
    """Internal ERP / trade record summary for the applicant."""

    status: str = Field(description="e.g. 'Existing Customer' or 'New Customer'")
    payment_conduct: str = Field(description="e.g. 'Prompt', 'Slow', 'New/Clean'")
    existing_group_exposure: float = Field(description="Total group exposure in MYR")
    relationship_years: int



class CreditDecision(BaseModel):
    """Final structured credit decision produced by the Chief Credit Officer agent."""

    company_reg_no: str
    recommendation: str = Field(description="APPROVE | REJECT | MANUAL_REVIEW")
    proposed_credit_limit_myr: float
    risk_grade: str = Field(
        description=(
            "One of: Extremely High Risk, High Risk, Medium Risk, "
            "Moderate Risk, Low Risk"
        )
    )
    final_score: int = Field(
        default=0,
        ge=0,
        le=100,
        description="Weighted credit score out of 100 (Step 7 scorecard).",
    )
    risk_definition: str = Field(
        default="",
        description="Risk band definition label, e.g. '81–100: Low Risk — Approve'.",
    )
    guarantee_type: str = Field(
        default="",
        description="'Limited' or 'Unlimited' personal guarantee recommendation.",
    )
    limit_vs_requested_assessment: str = Field(
        default="",
        description="Comparison of AI-calculated limit against the customer's requested amount.",
    )
    key_reasons: list[str]
    conditions: list[str] = Field(default_factory=list, description="Conditions if approved")
    confidence_score: float = Field(ge=0.0, le=1.0)
    raw_agent_summary: str = Field(default="")
    credit_narrative_summary: str = Field(
        default="",
        description="Formal Justification Memo for management review.",
    )
    # Passed through from CTOS extractor so the UI can render the trend table.
    financial_trend: list[dict] = Field(
        default_factory=list,
        description="5-year financial trend extracted from the CTOS report.",
    )
    # Per-category score breakdown for the Digital Credit Scoring Form table.
    score_breakdown: list[dict] = Field(
        default_factory=list,
        description=(
            "List of {category, weightage_pct, score, max_score} dicts "
            "for the 5-category scorecard."
        ),
    )
    # Adverse flags passed through from CTOS so the UI can render high-risk alerts.
    status_code_k: bool = Field(default=False)
    status_code_10: bool = Field(default=False)
    special_attention_accounts: bool = Field(default=False)
    has_director_above_70: bool = Field(default=False)
    directors_above_70: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# Stub helpers  (replace with real logic / tool calls as development progresses)
# ---------------------------------------------------------------------------





# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------


class AgentOrchestrator:
    """
    Coordinates all AI agents in sequence and returns a final CreditDecision.

    Usage:
        orchestrator = AgentOrchestrator()
        decision = await orchestrator.run(pdf_bytes=..., company_reg_no=...)
    """

    def run(
        self,
        *,
        pdf_bytes: bytes,
        company_reg_no: str | None = None,
        requested_amount: float = 0.0,
        bank_pdf_bytes: bytes | None = None,
    ) -> CreditDecision:
        """
        Execute the full agent pipeline synchronously.

        Args:
            pdf_bytes:        Raw bytes of the uploaded CTOS PDF.
            company_reg_no:   Company registration number supplied by the user.
                              If omitted or empty, it is auto-extracted from the
                              CTOS PDF by the CTOS Extractor agent in Step 1.
            requested_amount: Customer's requested credit limit in MYR (0 = unspecified).
            bank_pdf_bytes:   Raw bytes of the optional bank statement PDF.

        Returns:
            A validated CreditDecision Pydantic model.
        """
        logger.info(
            "=== Starting credit pipeline for %s ===",
            company_reg_no or "(reg no will be auto-extracted from CTOS PDF)",
        )

        # ------------------------------------------------------------------
        # Step 1 — CTOS Extractor Agent (live)
        # ------------------------------------------------------------------
        ctos_raw = extract_ctos_data(pdf_bytes)

        # PDPA / Stateless Processing — purge raw CTOS PDF bytes from memory
        # immediately after extraction so sensitive personal data is not retained.
        del pdf_bytes
        pdf_bytes = b""
        logger.info("PDPA: CTOS PDF bytes purged from memory after extraction.")

        # Print extracted data to console for inspection during development
        print("\n" + "=" * 60)
        print("CTOS EXTRACTOR — AI OUTPUT")
        print("=" * 60)
        print(json.dumps(ctos_raw, indent=2, default=str))
        print(f"  [keys returned: {list(ctos_raw.keys())}]")
        print("=" * 60 + "\n")

        # Pull reg no and company name from the AI response, trying every key
        # variant the model might use, then fall back to the user-supplied value.
        _REG_KEYS  = ["reg_no", "Reg No", "registration_no", "Registration No",
                      "company_reg_no", "Company Reg No", "reg_number", "Registration Number"]
        _NAME_KEYS = ["company_name", "Company Name", "name", "Name"]

        ai_reg_no: str = next(
            (str(ctos_raw[k]).strip() for k in _REG_KEYS if ctos_raw.get(k)),
            ""
        ) or company_reg_no or ""

        ai_company_name: str = next(
            (str(ctos_raw[k]).strip() for k in _NAME_KEYS if ctos_raw.get(k)),
            ""
        )

        logger.info("Step 1 complete — reg_no=%s company=%s", ai_reg_no, ai_company_name)

        # ------------------------------------------------------------------
        # Step 2 — Internal ERP Agent
        # Use AI-extracted reg no and company name for the best chance of a match.
        # ------------------------------------------------------------------
        erp_raw = query_internal_erp(ai_company_name or None, ai_reg_no)
        erp_data = InternalERPOutput(**erp_raw)
        logger.info(
            "Step 2 complete — ERP status: %s | conduct: %s | exposure: MYR %.2f",
            erp_data.status,
            erp_data.payment_conduct,
            erp_data.existing_group_exposure,
        )

        # ------------------------------------------------------------------
        # Step 3 — Bank Statement Analyst Agent (optional)
        # ------------------------------------------------------------------
        if bank_pdf_bytes:
            bank_data = analyze_bank_statement(bank_pdf_bytes)
            # PDPA / Stateless Processing — purge raw bank PDF bytes immediately
            # after extraction so sensitive financial data is not retained.
            del bank_pdf_bytes
            bank_pdf_bytes = b""
            logger.info(
                "Step 3 complete — Bank analysis done | bounced_checks=%s. "
                "PDPA: Bank PDF bytes purged from memory.",
                bank_data.get("bounced_checks", "?"),
            )
        else:
            bank_data = {"summary": "No bank statement provided"}
            logger.info("Step 3 skipped — no bank statement uploaded.")

        # ------------------------------------------------------------------
        # Step 4 — Chief Credit Officer Agent (live)
        # ------------------------------------------------------------------
        logger.info("Step 4 — Calling Chief Credit Officer agent …")

        decision_raw = generate_credit_decision(
            ctos_data=ctos_raw,
            erp_data=erp_data.model_dump(),
            bank_data=bank_data,
            requested_amount=requested_amount,
        )

        # Use the reg no the AI extracted from the PDF; fall back to user input
        decision_raw["company_reg_no"] = ai_reg_no or company_reg_no or ""

        # Pass the 5-year financial trend through to the response so the UI
        # can render it without a separate API call.
        decision_raw.setdefault("financial_trend", ctos_raw.get("financial_trend", []))

        # Pass CTOS adverse flags through so the UI can render high-risk alerts.
        decision_raw.setdefault("status_code_k", bool(ctos_raw.get("status_code_k", False)))
        decision_raw.setdefault("status_code_10", bool(ctos_raw.get("status_code_10", False)))
        decision_raw.setdefault(
            "special_attention_accounts",
            bool(ctos_raw.get("special_attention_accounts", False)),
        )
        decision_raw.setdefault(
            "has_director_above_70",
            bool(ctos_raw.get("has_director_above_70", False)),
        )
        decision_raw.setdefault(
            "directors_above_70",
            ctos_raw.get("directors_above_70", []),
        )

        decision = CreditDecision(**decision_raw)
        logger.info(
            "=== Pipeline complete — Recommendation: %s | Limit: MYR %.2f ===",
            decision.recommendation,
            decision.proposed_credit_limit_myr,
        )
        return decision
