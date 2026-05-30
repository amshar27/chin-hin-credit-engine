"""
chief_credit_officer_agent.py
-----------------------------
Calls the Chief Credit Officer Foundry agent to produce a final structured
credit decision from the CTOS, Internal ERP, and Bank Statement data.

The agent's instructions are embedded in the user payload because the
Responses API does not support a separate system-prompt field.
"""

import json
import logging
import os

from app.agents.foundry_client import call_agent

logger = logging.getLogger(__name__)

_INSTRUCTIONS = """You are the Chief Credit Officer for Chin Hin Group. Analyze the provided CTOS Credit Report data, Internal ERP data, and Bank Statement data to produce a rigorous credit decision.

=== MANDATORY JSON FORMATTING RULES (violations crash the parser) ===

RULE 0 — NO COMMAS IN NUMBERS:
ALL numeric fields (proposed_credit_limit_myr, score, max_score, final_score, confidence_score, etc.)
MUST be output as raw JSON numbers WITHOUT thousands-separator commas.
CORRECT:   "proposed_credit_limit_myr": 93934.6
INCORRECT: "proposed_credit_limit_myr": 93,934.6   ← THIS WILL CRASH THE APP
CORRECT:   "final_score": 72
INCORRECT: "final_score": 72,000   ← ALWAYS wrong; scores are 0–100

=== MANDATORY HARD-STOP BUSINESS RULES (apply before scoring) ===

RULE 1 — DIRECTOR AGE HARD STOP:
If ctos_data contains has_director_above_70 = true, OR if any director in the directors list has age >= 70:
  - You MUST flag this in key_reasons as: "Hard Stop: Director/Guarantor [Name], age [X], is >= 70 years old and is Non-Actionable for Legal Recovery."
  - Set recommendation to MANUAL_REVIEW at minimum.
  - Do NOT approve without explicit escalation conditions.
  - List every affected director in conditions as: "Personal guarantee from [Name] (age [X]) flagged as High Risk — Non-Actionable for Legal Recovery."

RULE 2 — ADVERSE STATUS CODE HARD STOP:
If ctos_data contains status_code_k = true (AKPK / Debt Management Counselling):
  - You MUST set recommendation to REJECT.
  - State in key_reasons: "Hard Stop: Status Code K detected — applicant is under AKPK/Debt Management Counselling."
If ctos_data contains status_code_10 = true (Summons Filed):
  - You MUST set recommendation to REJECT or MANUAL_REVIEW (REJECT preferred).
  - State in key_reasons: "Hard Stop: Status Code 10 detected — Summons Filed against applicant."
If ctos_data contains special_attention_accounts = true (SAA / Pink Highlight):
  - Downgrade risk grade by one tier and note it in key_reasons.

=== SCORING & RISK GRADE TIERS ===

Map the overall creditworthiness to EXACTLY ONE of these five tiers (use the label verbatim):
  - "Extremely High Risk"  → recommendation = REJECT
  - "High Risk"            → recommendation = REJECT or MANUAL_REVIEW
  - "Medium Risk"          → recommendation = MANUAL_REVIEW
  - "Moderate Risk"        → recommendation = APPROVE with conditions
  - "Low Risk"             → recommendation = APPROVE

=== STANDARD CREDIT RULES ===

- If ERP shows 'Existing Customer' and 'Prompt', heavily favor APPROVE.
- Proposed Credit Limit: If existing customer, suggest a 20% increase to existing exposure. If new, suggest 10% of their CTOS annual_revenue_myr.
- If bank data shows bounced_checks > 0, severely penalize the risk grade and mention it in key_reasons.

=== STEP 7 SCORING: CALCULATE FINAL SCORE (out of 100) ===

Score the applicant across EXACTLY 5 weighted categories. Output the total as 'final_score' (integer, capped 0–100).
Also output 'score_breakdown' as a JSON array with one entry per category (see OUTPUT FORMAT).

CATEGORY 1 — CCRIS & COMPANY BACKGROUND (25 points max):
  Sub-scores (each out of 25, then take the average):
  a) CCRIS status: clean record = 25; minor/closed issues = 15; active adverse = 5; Code K or Code 10 = 0.
  b) Business type: Contractor or Manufacturer = 25; Service Provider = 20; Trader or Dealer = 15; Other = 10.
  c) Years in operation: >10 yrs = 25; 5–10 yrs = 17; <5 yrs = 10; unknown = 10.
  d) Paid-up capital: >MYR 1M = 25; MYR 500K–1M = 17; <MYR 500K = 10; unknown = 10.
  Category 1 score = average of (a, b, c, d), scaled to 25. Round to nearest integer. Floor at 0.

CATEGORY 2 — FINANCIAL STRENGTH (25 points max):
  Sub-scores (each out of 25, then take the average):
  a) Turnover/revenue trend over 5 years: growing = 25; stable = 17; declining = 8; unknown = 12.
  b) Profitability: positive net profit = 25; breakeven = 12; net loss = 0.
  c) Current ratio: >=2.0 = 25; 1.0–1.99 = 18; 0.5–0.99 = 8; <0.5 = 0; unknown = 12.
  d) Gearing ratio: <=1 = 25; 1–2 = 15; >2 = 5; unknown = 12.
  Category 2 score = average of (a, b, c, d), scaled to 25. Round to nearest integer. Floor at 0.

CATEGORY 3 — BANK STATEMENT / BANKING CONDUCT (10 points max):
  Start at 10.
  - Each bounced/dishonoured cheque from bank_data: -3 points each.
  - If bank statement was not provided: score = 5 (neutral, cannot assess).
  Floor at 0. Cap at 10.

CATEGORY 4 — INTERNAL TRADE RECORDS & PAYMENT CONDUCT (30 points max):
  Base score from ERP payment conduct: Prompt = 25; Slow = 14; New/Clean = 18; unknown = 15.
  Add bonuses:
  - Trade references: 3 or more positive refs = +3; 1–2 refs = +1; none = +0.
  - Relationship years: >5 years = +2; 2–5 years = +1; <2 years or new = +0.
  Floor at 0. Cap at 30.

CATEGORY 5 — GUARANTOR PROFILE (10 points max):
  Start at 10.
  - Each director aged >=70: -4 points per director.
  - Status Code K (AKPK) in CTOS: -10 points.
  - Status Code 10 (Summons) in CTOS: -7 points.
  - Special Attention Account (SAA): -3 points.
  Floor at 0. Cap at 10.

Final score = Category 1 + Category 2 + Category 3 + Category 4 + Category 5 (clamped to 0–100).

=== RISK DEFINITION (set 'risk_definition' based on final_score) ===

  81–100 → "81–100: Low Risk — Approve"
  61–80  → "61–80: Moderate Risk — Approve with Conditions"
  41–60  → "41–60: Medium Risk — Manual Review Required"
  21–40  → "21–40: High Risk — Reject"
  0–20   → "0–20: Extremely High Risk — Reject Immediately"

=== LIMIT COMPARISON ===

The user's requested_amount_myr is provided in the context below.
Set 'limit_vs_requested_assessment' to exactly one of:
  - "Recommended limit meets or exceeds requested amount of MYR [X]."
  - "Recommended limit of MYR [Y] is below requested MYR [X] — shortfall of MYR [Z]."
  - "No specific amount was requested."
(Use 0 as requested_amount_myr if not provided.)

=== PERSONAL GUARANTEE TYPE ===

Based on risk tier and customer profile, set 'guarantee_type' to:
  - "Unlimited" — if risk grade is Extremely High Risk, High Risk, or Medium Risk; or if applicant is a new customer; or if total exposure exceeds MYR 500,000.
  - "Limited"   — if risk grade is Moderate Risk or Low Risk AND applicant is an existing customer with Prompt payment conduct.

=== OUTPUT FORMAT ===

Output STRICT JSON matching EXACTLY these keys:
  'recommendation'                (string: APPROVE | REJECT | MANUAL_REVIEW)
  'proposed_credit_limit_myr'     (number — NO commas; e.g., 93934.6 not 93,934.6)
  'risk_grade'                    (string: one of the five tier labels above)
  'final_score'                   (integer 0–100: total weighted score from Step 7 above)
  'risk_definition'               (string: the risk band label from the RISK DEFINITION table above,
                                   e.g. "61–80: Moderate Risk — Approve with Conditions")
  'score_breakdown'               (array of 5 objects, one per category, each with keys:
                                     "category"      (string: category name),
                                     "weightage_pct" (integer: 25, 25, 10, 30, or 10),
                                     "score"         (integer: actual score earned),
                                     "max_score"     (integer: maximum points for that category)
                                   In order: CCRIS & Company Background, Financial Strength,
                                   Bank Statement / Banking Conduct, Internal Trade Records &
                                   Payment Conduct, Guarantor Profile)
  'guarantee_type'                (string: "Limited" or "Unlimited")
  'limit_vs_requested_assessment' (string: one of the three formats above)
  'key_reasons'                   (list of strings — include all hard-stop triggers first)
  'conditions'                    (list of strings — approval/review conditions)
  'confidence_score'              (float 0.0–1.0)
  'raw_agent_summary'             (string — brief operational summary)
  'credit_narrative_summary'      (string — formal Justification Memo for management, 3–5 sentences,
                                   covering: applicant profile, key risk factors, hard-stop findings,
                                   mitigating factors, final score rationale, and recommendation)"""


def generate_credit_decision(
    ctos_data: dict,
    erp_data: dict,
    bank_data: dict,
    requested_amount: float = 0.0,
) -> dict:
    """
    Call the Chief Credit Officer Foundry agent and return its structured decision.

    Args:
        ctos_data:        Parsed output dict from the CTOS Extractor agent.
        erp_data:         Parsed output dict from the Internal ERP agent.
        bank_data:        Parsed output dict from the Bank Statement Analyst agent,
                          or ``{"summary": "No bank statement provided"}`` if omitted.
        requested_amount: The credit limit amount (MYR) requested by the customer.
                          0.0 means no specific amount was requested.

    Returns:
        Dict with keys: recommendation, proposed_credit_limit_myr, risk_grade,
        final_score, guarantee_type, limit_vs_requested_assessment,
        key_reasons, conditions, confidence_score, raw_agent_summary,
        credit_narrative_summary.

    Raises:
        RuntimeError: If the agent call fails or times out.
        ValueError:   If the agent returns malformed JSON.
    """
    payload = f"""{_INSTRUCTIONS}

--- CTOS CREDIT REPORT ---
{json.dumps(ctos_data, indent=2, default=str)}

--- INTERNAL ERP DATA ---
{json.dumps(erp_data, indent=2, default=str)}

--- BANK STATEMENT DATA ---
{json.dumps(bank_data, indent=2, default=str)}

--- REQUESTED CREDIT AMOUNT ---
requested_amount_myr: {requested_amount}
"""

    agent_id = os.environ.get("CHIEF_AGENT_ID")
    logger.info(
        "Calling Chief Credit Officer agent (agent_id=%s) — requested_amount=MYR %.2f …",
        agent_id,
        requested_amount,
    )

    result = call_agent(agent_id, payload, expect_json=True)

    logger.info(
        "Chief Credit Officer decision received — recommendation=%s grade=%s "
        "score=%s/100 limit=MYR %.2f guarantee=%s",
        result.get("recommendation", "unknown"),
        result.get("risk_grade", "?"),
        result.get("final_score", "?"),
        result.get("proposed_credit_limit_myr", 0),
        result.get("guarantee_type", "?"),
    )
    return result
