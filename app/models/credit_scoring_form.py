"""
credit_scoring_form.py
----------------------
Pydantic v2 models that mirror the Chin Hin Credit Scoring Form Template.

Every leaf field is Optional so that missing CTOS data gracefully becomes null
in the structured output rather than causing a validation error.

All categorical / banded fields use typing.Literal to constrain the AI to the
exact option strings from the Credit Scoring Matrix.  The AI must analyse the
raw CTOS figures and select the correct band — it must never output a raw number
for a Literal field.

NOTE: All *_pct score-weighting fields have been intentionally removed.
      The React frontend computes all section scores via FIELD_SCORE_MAP.
      The AI must ONLY classify — never calculate scores.

Hierarchy
---------
CreditScoringDetailedForm
├── TypeOfCustomer
├── SalesmanProfile
├── CustomerInformation
├── CCRISForCompany
├── FinancialInformation
├── InternalInformation
├── PGBGCGObtained
├── PersonalGuarantee
├── GuarantorCCRISProfile  (List — one per guarantor)
├── CompanyBackground
├── AdditionalInformation
└── ProposedCreditLimit
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Shared Literal aliases — reused across multiple sections so the option
# strings are defined in exactly one place.
# ---------------------------------------------------------------------------

# Yes / No — used by every boolean scoring field
_YesNo = Literal['Yes', 'No']

# Legal cases — company and guarantor share the same bands
_LegalCasesLiteral = Literal[
    '0 ( Clean of legal action )',
    '1 ( 1 case still on-going or unsettled )',
    '2 ( 2 cases still on-going or unsettled )',
    '3 ( 3 cases still on-going or unsettled )',
    '>3 ( More than 3 cases still on-going or unsettled )',
]

# Blacklist cases — company and guarantor share the same bands
_BlacklistCasesLiteral = Literal[
    '0 ( no blacklist issue )',
    '1 ( 1 blacklist issue )',
    '2 ( 2 blacklist issue )',
    '3 ( 3 blacklist issue )',
    '>3 ( More than 3 blacklist issue )',
]

# Repayment conduct — company and guarantor share the same bands
_RepaymentLiteral = Literal[
    'Satisfactory ( Prompt payment or occasionally lapsed 1 month )',
    'Moderate ( Consistently lapsed 1-2 months )',
    'Unsatisfactory ( Under SPA or consistently lapsed 2 months and above )',
    'N/A',
]

# Bank facility utilisation — company and guarantor share the same bands
_UtilisationBandLiteral = Literal[
    '< 30%',
    '30% - 50%',
    '51% - 70%',
    '71% - 90%',
    '> 90%',
]


# ---------------------------------------------------------------------------
# 1. Type of Customer
# ---------------------------------------------------------------------------


class TypeOfCustomer(BaseModel):
    """Section 1 — classifies the account review type."""

    type: Optional[Literal['Review', 'Reactive']] = Field(
        None,
        description=(
            "Account review classification. "
            "Select exactly one of the allowed values: "
            "'Review' (scheduled periodic review) or "
            "'Reactive' (triggered by an event or request). "
            "Do not output any other string."
        ),
    )


# ---------------------------------------------------------------------------
# 2. Salesman Profile
# ---------------------------------------------------------------------------


class SalesmanProfile(BaseModel):
    """Section 2 — internal sales ownership of this credit application."""

    company: Optional[str] = Field(
        None,
        description="Chin Hin subsidiary or entity managing this account.",
    )
    branches: Optional[str] = Field(
        None,
        description="Branch name(s) responsible for this customer.",
    )
    salesman: Optional[str] = Field(
        None,
        description="Assigned salesman's name.",
    )
    head_of_branch: Optional[str] = Field(
        None,
        description="Head of branch overseeing this application.",
    )


# ---------------------------------------------------------------------------
# 3. Customer Information
# ---------------------------------------------------------------------------


class CustomerInformation(BaseModel):
    """Section 3 — applicant's basic business identity and contact details."""

    ref_no: Optional[str] = Field(
        None,
        description="Internal reference number for this credit application.",
    )
    company_business_registration_no: Optional[str] = Field(
        None,
        description=(
            "Company or business registration number (SSM / ROC / ROB). "
            "Extract from the CTOS report header or company profile section."
        ),
    )
    company_name: Optional[str] = Field(
        None,
        description="Full legal name of the applicant company or business.",
    )
    address: Optional[str] = Field(
        None,
        description="Registered or principal business address.",
    )
    phone_no: Optional[str] = Field(
        None,
        description="Primary telephone number of the business.",
    )
    fax_no: Optional[str] = Field(
        None,
        description="Fax number of the business, if listed.",
    )
    credit_terms: Optional[str] = Field(
        None,
        description=(
            "Requested or existing credit terms, e.g. '30 days', '60 days', 'COD'."
        ),
    )


# ---------------------------------------------------------------------------
# 4. CCRIS for Company
# ---------------------------------------------------------------------------


class CCRISForCompany(BaseModel):
    """
    Section 4 — CCRIS (Central Credit Reference Information System) assessment
    for the applicant company.  All raw CTOS figures must be mapped to their
    scoring-matrix category string.  Do NOT output raw numbers or invent ranges.
    Do NOT output any score or percentage — the frontend handles all scoring.
    """

    legal_cases_unsettled: Optional[_LegalCasesLiteral] = Field(
        None,
        description=(
            "Unsettled legal cases against the company from the CTOS litigation section. "
            "Analyse the raw CTOS count and select the EXACT matching category — "
            "do NOT output a raw number: "
            "'0 ( Clean of legal action )', "
            "'1 ( 1 case still on-going or unsettled )', "
            "'2 ( 2 cases still on-going or unsettled )', "
            "'3 ( 3 cases still on-going or unsettled )', "
            "'>3 ( More than 3 cases still on-going or unsettled )'."
        ),
    )

    blacklist_cases: Optional[_BlacklistCasesLiteral] = Field(
        None,
        description=(
            "Blacklist / winding-up entries against the company from CTOS. "
            "Analyse the raw CTOS count and select the EXACT matching category — "
            "do NOT output a raw number: "
            "'0 ( no blacklist issue )', '1 ( 1 blacklist issue )', "
            "'2 ( 2 blacklist issue )', '3 ( 3 blacklist issue )', "
            "'>3 ( More than 3 blacklist issue )'."
        ),
    )

    special_attention_account_spa: Optional[_YesNo] = Field(
        None,
        description=(
            "Whether the company has a Special Attention Account (SPA / Pink Highlight) "
            "in CCRIS. Must be exactly 'Yes' or 'No'."
        ),
    )

    repayment_to_banks: Optional[_RepaymentLiteral] = Field(
        None,
        description=(
            "Overall CCRIS repayment conduct classification. "
            "Analyse the CCRIS payment history and select the EXACT matching category — "
            "do NOT output a free-text description: "
            "'Satisfactory ( Prompt payment or occasionally lapsed 1 month )', "
            "'Moderate ( Consistently lapsed 1-2 months )', "
            "'Unsatisfactory ( Under SPA or consistently lapsed 2 months and above )', "
            "'N/A' (if CCRIS data is unavailable)."
        ),
    )

    total_facilities_limit_vs_outstanding_utilisation_pct: Optional[_UtilisationBandLiteral] = Field(
        None,
        description=(
            "Bank facility utilisation band: total outstanding divided by total limit "
            "across all CCRIS facilities. Calculate the utilisation percentage, then map "
            "it to the EXACT band string — do NOT output the raw percentage. "
            "CRITICAL: Copy the exact string character-by-character. "
            "Do not correct capitalization or spacing — every character matters. "
            "STRICT VALIDATION — the ONLY accepted values are these 5 exact strings: "
            "'< 30%', '30% - 50%', '51% - 70%', '71% - 90%', '> 90%'. "
            "ANY other string (e.g., '62%', '45%', '80%', '0%') will cause a "
            "ValidationError crash. "
            "Mapping examples: 0%–29% → '< 30%'; 30%–50% → '30% - 50%'; "
            "51%–70% → '51% - 70%'; 71%–90% → '71% - 90%'; above 90% → '> 90%'. "
            "NEVER output a raw percentage like '62%'. ALWAYS output one of the 5 band strings."
        ),
    )


# ---------------------------------------------------------------------------
# 5. Financial Information
# ---------------------------------------------------------------------------


class FinancialInformation(BaseModel):
    """
    Section 5 — financial strength assessment drawn from audited accounts
    and/or bank statements attached to the CTOS report.
    Do NOT output any score or percentage — the frontend handles all scoring.
    """

    bank_statement_provided: Optional[_YesNo] = Field(
        None,
        description=(
            "CRITICAL INSTRUCTION: Automatically detect from the document context whether "
            "bank statement information is present. "
            "If any bank statement data, transactions, account balances, or bank account "
            "summaries are visible in the provided text, you MUST output 'Yes'. "
            "If there is no bank statement data in the context at all, you MUST output 'No'. "
            "The ONLY accepted values are: 'Yes', 'No'. "
            "ANY other value will cause a ValidationError crash."
        ),
    )
    bank_statement_end_month_balance_rm: Optional[Literal[
        '> RM 500,000',
        'RM 200,001 - RM 500,000',
        'RM 50,001 - RM 200,000',
        'RM 10,001 - RM 50,000',
        '<= RM 10,000',
    ]] = Field(
        None,
        description=(
            "End-of-month closing balance band from the bank statement. "
            "Analyse the raw balance figure (MYR) and select the EXACT matching Literal string. "
            "CRITICAL INSTRUCTION: DO NOT output the raw MYR amount or a raw number. "
            "If the balance is RM 350,000, you MUST output 'RM 200,001 - RM 500,000', NOT 350000. "
            "CRITICAL: Copy the exact string character-by-character. "
            "Do not correct capitalization or spacing — every character matters. "
            "STRICT VALIDATION — the ONLY accepted values are these 5 exact strings: "
            "'> RM 500,000', 'RM 200,001 - RM 500,000', 'RM 50,001 - RM 200,000', "
            "'RM 10,001 - RM 50,000', '<= RM 10,000'. "
            "ANY other value will cause a ValidationError crash. "
            "Mapping examples (raw MYR balance → exact Literal to output): "
            "77490 → 'RM 50,001 - RM 200,000'; "
            "8000 → '<= RM 10,000'; "
            "25000 → 'RM 10,001 - RM 50,000'; "
            "120000 → 'RM 50,001 - RM 200,000'; "
            "350000 → 'RM 200,001 - RM 500,000'; "
            "600000 → '> RM 500,000'. "
            "NEVER output the raw balance figure (e.g., never output 77490.00 or 77490). "
            "ALWAYS output the matching band string."
        ),
    )

    financial_audited_report_provided: Optional[_YesNo] = Field(
        None,
        description=(
            "CRITICAL INSTRUCTION: Automatically detect from the document context whether "
            "an audited financial report is present. "
            "If any audited financial statements, balance sheets, income statements, or "
            "financial report data are visible in the provided text, you MUST output 'Yes'. "
            "If no financial report data is available in the context, you MUST output 'No'. "
            "The ONLY accepted values are: 'Yes', 'No'. "
            "ANY other value will cause a ValidationError crash."
        ),
    )
    financial_report_date: Optional[str] = Field(
        None,
        description=(
            "Date or financial year end of the most recent financial report, "
            "e.g. '31 Dec 2023' or 'FY2023'."
        ),
    )

    # Turnover
    turnover: Optional[Literal[
        '> 1 Mil',
        '501K - 999K',
        '301K - 500K',
        '0 - 300K',
        'Negative or N/A ( Make loss company or Not available)',
    ]] = Field(
        None,
        description=(
            "Annual turnover (revenue) band. Analyse the raw revenue figure (MYR) and "
            "select the EXACT matching Literal string. "
            "CRITICAL INSTRUCTION: DO NOT output the raw MYR amount or a raw number. "
            "If revenue is RM 750,000, you MUST output '501K - 999K', NOT 750000. "
            "CRITICAL: Copy the exact string character-by-character. "
            "Do not correct capitalization or spacing — every character matters. "
            "STRICT VALIDATION — the ONLY accepted values are these 5 exact strings: "
            "'> 1 Mil', '501K - 999K', '301K - 500K', '0 - 300K', "
            "'Negative or N/A ( Make loss company or Not available)'. "
            "ANY other value will cause a ValidationError crash. "
            "Mapping examples (all MYR): "
            "RM 0–RM 300,000 → '0 - 300K'; "
            "RM 301,001–RM 500,000 → '301K - 500K'; "
            "RM 501,001–RM 999,999 (e.g., 750,000) → '501K - 999K'; "
            "> RM 1,000,000 → '> 1 Mil'; "
            "zero revenue or net loss → 'Negative or N/A ( Make loss company or Not available)'. "
            "NEVER output the raw revenue figure. ALWAYS output the matching band string."
        ),
    )
    turnover_specified_amount: Optional[float] = Field(
        None,
        description=(
            "Actual annual turnover figure from the financial report (MYR). "
            "Use the most recent financial year. "
            "CRITICAL: Output a raw number only. DO NOT use commas as thousands separators "
            "(e.g., output 1500000.0, NOT 1,500,000.0)."
        ),
    )

    # Net Profit / Loss
    net_profit_loss: Optional[Literal[
        'Profit ( > RM 500,000 )',
        'Profit ( RM 100,001 - RM 500,000 )',
        'Profit ( RM 1 - RM 100,000 )',
        'Break-even',
        'Loss',
    ]] = Field(
        None,
        description=(
            "Net profit or loss band. Analyse the raw net profit/loss figure (MYR) and "
            "select the EXACT matching Literal string. "
            "CRITICAL INSTRUCTION: DO NOT output the raw MYR amount or a raw number. "
            "If net profit is RM 93,934, you MUST output 'Profit ( RM 1 - RM 100,000 )', "
            "NOT the number 93934. "
            "CRITICAL: Copy the exact string character-by-character. "
            "Do not correct capitalization or spacing — every character matters. "
            "STRICT VALIDATION — the ONLY accepted values are these 5 exact strings: "
            "'Profit ( > RM 500,000 )', 'Profit ( RM 100,001 - RM 500,000 )', "
            "'Profit ( RM 1 - RM 100,000 )', 'Break-even', 'Loss'. "
            "ANY other value will cause a ValidationError crash. "
            "Mapping examples: "
            "profit RM 1–RM 100,000 → 'Profit ( RM 1 - RM 100,000 )'; "
            "profit RM 100,001–RM 500,000 → 'Profit ( RM 100,001 - RM 500,000 )'; "
            "profit > RM 500,000 → 'Profit ( > RM 500,000 )'; "
            "exactly zero → 'Break-even'; any net loss → 'Loss'. "
            "NEVER output the raw figure. ALWAYS output the matching band string."
        ),
    )
    net_profit_specified_amount: Optional[float] = Field(
        None,
        description=(
            "Actual net profit (positive) or net loss (negative) figure (MYR). "
            "CRITICAL: Output a raw number only. DO NOT use commas as thousands separators "
            "(e.g., output 93934.6, NOT 93,934.6)."
        ),
    )

    # Retained Profit / Accumulated Losses
    retained_profit_accumulated_losses: Optional[Literal[
        'Retained Profit',
        'Accumulated Losses',
    ]] = Field(
        None,
        description=(
            "Retained earnings classification from the balance sheet. "
            "CRITICAL INSTRUCTION: DO NOT output a monetary amount or raw number. "
            "Select the EXACT Literal string based on the sign of retained earnings: "
            "if retained earnings are positive (e.g., RM 30,000), output 'Retained Profit'; "
            "if negative (e.g., -RM 15,000), output 'Accumulated Losses'. "
            "The ONLY accepted values are: 'Retained Profit', 'Accumulated Losses'. "
            "ANY other value will cause a ValidationError crash."
        ),
    )
    retained_profit_specified_amount: Optional[float] = Field(
        None,
        description=(
            "Actual retained profit (positive) or accumulated losses (negative) (MYR). "
            "CRITICAL: Output a raw number only. DO NOT use commas as thousands separators "
            "(e.g., output 250000.0, NOT 250,000.0)."
        ),
    )

    # Net Worth
    net_worth: Optional[Literal[
        '> RM 1 Mil',
        'RM 501K - RM 1 Mil',
        'RM 201K - RM 500K',
        'RM 1 - RM 200K',
        'Negative',
    ]] = Field(
        None,
        description=(
            "Net worth (shareholders' equity) band. Analyse the raw equity figure (MYR) "
            "and select the EXACT matching Literal string. "
            "CRITICAL INSTRUCTION: DO NOT output the raw MYR amount or a raw number. "
            "If net worth is RM 350,000, you MUST output 'RM 201K - RM 500K', NOT 350000. "
            "CRITICAL: Copy the exact string character-by-character. "
            "Do not correct capitalization or spacing — every character matters. "
            "STRICT VALIDATION — the ONLY accepted values are these 5 exact strings: "
            "'> RM 1 Mil', 'RM 501K - RM 1 Mil', 'RM 201K - RM 500K', "
            "'RM 1 - RM 200K', 'Negative'. "
            "ANY other value will cause a ValidationError crash. "
            "Mapping examples: "
            "negative equity → 'Negative'; "
            "RM 1–RM 200,000 → 'RM 1 - RM 200K'; "
            "RM 201,001–RM 500,000 (e.g., 350,000) → 'RM 201K - RM 500K'; "
            "RM 501,001–RM 1,000,000 → 'RM 501K - RM 1 Mil'; "
            "> RM 1,000,000 → '> RM 1 Mil'. "
            "NEVER output the raw equity figure. ALWAYS output the matching band string."
        ),
    )
    net_worth_specified_amount: Optional[float] = Field(
        None,
        description=(
            "Actual shareholders' equity / net worth from the balance sheet (MYR). "
            "CRITICAL: Output a raw number only. DO NOT use commas as thousands separators "
            "(e.g., output 750000.0, NOT 750,000.0)."
        ),
    )

    # Net Current Assets / Liabilities (Working Capital)
    net_current_assets_liabilities: Optional[Literal['Positive', 'Negative']] = Field(
        None,
        description=(
            "Working capital classification. "
            "CRITICAL INSTRUCTION: DO NOT output a monetary amount or raw number. "
            "Select the EXACT Literal string based on the sign of working capital: "
            "if current assets exceed current liabilities (positive working capital), "
            "output 'Positive'; if current liabilities exceed current assets, output 'Negative'. "
            "The ONLY accepted values are: 'Positive', 'Negative'. "
            "ANY other value (e.g., a MYR amount like 120000) will cause a ValidationError crash."
        ),
    )
    net_current_assets_specified_amount: Optional[float] = Field(
        None,
        description=(
            "Actual working capital: current assets minus current liabilities (MYR). "
            "Negative value if net current liabilities. "
            "CRITICAL: Output a raw number only. DO NOT use commas as thousands separators "
            "(e.g., output 120000.5, NOT 120,000.5)."
        ),
    )

    # Current Ratio
    current_ratio: Optional[Literal['> 2.00', '1.01 - 1.99', '< 1.00', 'N/A']] = Field(
        None,
        description=(
            "Current ratio band. Calculate current assets / current liabilities, "
            "then select the EXACT matching Literal string. "
            "CRITICAL INSTRUCTION: DO NOT output the raw decimal ratio (e.g., do NOT output "
            "1.5 or 2.3 — these are raw numbers and will crash the app). "
            "If the ratio is 1.5, you MUST output '1.01 - 1.99', NOT 1.5. "
            "CRITICAL: Copy the exact string character-by-character. "
            "Do not correct capitalization or spacing — every character matters. "
            "STRICT VALIDATION — the ONLY accepted values are these 4 exact strings: "
            "'> 2.00', '1.01 - 1.99', '< 1.00', 'N/A'. "
            "ANY other value will cause a ValidationError crash. "
            "Mapping examples: "
            "ratio < 1.00 (e.g., 0.8) → '< 1.00'; "
            "ratio 1.01–1.99 (e.g., 1.5, 1.8) → '1.01 - 1.99'; "
            "ratio > 2.00 (e.g., 2.1, 2.5, 3.0, 10.0) → '> 2.00'. "
            "NEVER invent new ranges. '> 2.00' is the ceiling for all ratios above 2.00."
        ),
    )

    # Gearing Ratio
    gearing_ratio: Optional[Literal[
        '( 0 - 0.99 )',
        '( 1.00 - 1.99 )',
        '( 2.00 - 2.99 )',
        '( 3.00 - 3.99 )',
        '> 4.00',
        'Negative',
        'N/A',
    ]] = Field(
        None,
        description=(
            "Gearing ratio band. Calculate total debt / shareholders' equity, "
            "then select the EXACT matching category. "
            "CRITICAL: Copy the exact string character-by-character. "
            "Do not correct capitalization or spacing — every character matters. "
            "STRICT VALIDATION — the ONLY accepted values are these 7 exact strings: "
            "'( 0 - 0.99 )', '( 1.00 - 1.99 )', '( 2.00 - 2.99 )', "
            "'( 3.00 - 3.99 )', '> 4.00', 'Negative', 'N/A'. "
            "ANY other string will cause a ValidationError crash. "
            "THIS MEANS: strings like '( 4.00 - 4.99 )', '( 5.00 - 5.99 )', "
            "'( 8.00 - 8.99 )', '( 7.00 - 7.99 )' ARE NOT VALID and will crash the app. "
            "If the gearing ratio is >= 4.00 (e.g., 4.0, 4.5, 5.5, 8.55, 10.0, 20.0), "
            "you MUST output '> 4.00' — this is the ONLY valid string for any ratio at "
            "or above 4.00. There are NO higher ranges. '> 4.00' is the ceiling. "
            "'Negative' is only for companies with negative shareholders equity. "
            "'N/A' is only if data is completely unavailable."
        ),
    )


# ---------------------------------------------------------------------------
# 6. Internal Information
# ---------------------------------------------------------------------------


class InternalInformation(BaseModel):
    """
    Section 6 — internal Chin Hin ERP data: trade references, group exposure,
    and payment history from existing accounts.
    Do NOT output any score or percentage — the frontend handles all scoring.
    """

    years_in_relationship: Optional[Literal[
        '> 10 Years',
        '7.1 Years - 10 Years',
        '5.1 Years - 7 Years',
        '2.1 Years - 5 Years',
        '< 2 Years',
    ]] = Field(
        None,
        description=(
            "Years the applicant has been a customer of Chin Hin (relationship duration). "
            "APPLICABLE TO EXISTING CUSTOMERS ONLY — leave null for New Customers. "
            "CRITICAL INSTRUCTION: DO NOT output a raw integer or number. "
            "CRITICAL: Copy the exact string character-by-character. "
            "Do not correct capitalization or spacing — every character matters. "
            "If the relationship has lasted 3 years, you MUST output '2.1 Years - 5 Years', "
            "NOT the integer 3. "
            "STRICT VALIDATION — the ONLY accepted values are these 5 exact strings: "
            "'> 10 Years', '7.1 Years - 10 Years', '5.1 Years - 7 Years', "
            "'2.1 Years - 5 Years', '< 2 Years'. "
            "ANY other value (including raw integers) will cause a ValidationError crash. "
            "Mapping examples: "
            "< 2 yrs → '< 2 Years'; "
            "2.1–5 yrs (e.g., 3, 4) → '2.1 Years - 5 Years'; "
            "5.1–7 yrs (e.g., 6) → '5.1 Years - 7 Years'; "
            "7.1–10 yrs (e.g., 8, 9) → '7.1 Years - 10 Years'; "
            "> 10 yrs → '> 10 Years'. "
            "NEVER output the raw number. ALWAYS output the matching band string."
        ),
    )

    trade_reference_for_group_exposure_available: Optional[_YesNo] = Field(
        None,
        description=(
            "Whether a trade reference for group exposure is available in the "
            "internal ERP system. Must be 'Yes' or 'No'."
        ),
    )
    trade_reference_external_payment_pattern: Optional[str] = Field(
        None,
        description=(
            "External trade reference payment behaviour classification. "
            "E.g. 'Prompt', 'Slow 30', 'Slow 60', 'COD'."
        ),
    )
    remark: Optional[str] = Field(
        None,
        description="Free-text remark from the internal credit officer or ERP entry.",
    )
    group_exposure_internal_payment_pattern: Optional[str] = Field(
        None,
        description=(
            "Internal payment pattern for this company within the Chin Hin group. "
            "E.g. 'Prompt', 'Slow 30', 'Irregular'."
        ),
    )
    group_exposure_with_other_subsidiaries: Optional[_YesNo] = Field(
        None,
        description=(
            "Whether this applicant has existing credit exposure across other "
            "Chin Hin subsidiaries. Must be 'Yes' or 'No'."
        ),
    )
    common_director_or_shareholder_or_guarantor: Optional[_YesNo] = Field(
        None,
        description=(
            "Whether this applicant shares a director, shareholder, or guarantor "
            "with any existing Chin Hin customer. Must be 'Yes' or 'No'."
        ),
    )


# ---------------------------------------------------------------------------
# 7. PG / BG / CG Obtained
# ---------------------------------------------------------------------------


class PGBGCGObtained(BaseModel):
    """
    Section 7 — type of guarantee obtained from the applicant.
    Do NOT output any score or percentage — the frontend handles all scoring.
    """

    bank_guarantee_30_pct: Optional[_YesNo] = Field(
        None,
        description=(
            "Whether a Bank Guarantee (BG) is obtained. "
            "Must be 'Yes' or 'No'."
        ),
    )
    corporate_guarantee_18_pct: Optional[_YesNo] = Field(
        None,
        description=(
            "Whether a Corporate Guarantee (CG) is obtained. "
            "Must be 'Yes' or 'No'."
        ),
    )
    personal_guarantee_5_pct: Optional[_YesNo] = Field(
        None,
        description=(
            "Whether a Personal Guarantee (PG) is obtained. "
            "Must be 'Yes' or 'No'."
        ),
    )


# ---------------------------------------------------------------------------
# 8. Personal Guarantee (summary)
# ---------------------------------------------------------------------------


class PersonalGuarantee(BaseModel):
    """Section 8 — summary of personal guarantee arrangement."""

    number_of_guarantor: Optional[int] = Field(
        None,
        description=(
            "Total number of personal guarantors for this credit facility. "
            "CRITICAL: Output a plain integer only, no commas (e.g., output 2, NOT 2,000)."
        ),
    )
    guarantee_amount: Optional[float] = Field(
        None,
        description=(
            "Total guarantee amount (MYR) covered by all personal guarantors combined. "
            "CRITICAL: Output a raw number only. DO NOT use commas as thousands separators "
            "(e.g., output 500000.0, NOT 500,000.0)."
        ),
    )


# ---------------------------------------------------------------------------
# 9. CCRIS for Guarantor (one instance per guarantor)
# ---------------------------------------------------------------------------


class GuarantorCCRISProfile(BaseModel):
    """
    CCRIS profile for a single personal guarantor.
    Mirrors the same structure as CCRISForCompany but applied to an individual.
    One instance must be created for EVERY guarantor listed in the CTOS report.
    Do NOT output any score or percentage — the frontend handles all scoring.
    """

    guarantor_info_pg: Optional[str] = Field(
        None,
        description=(
            "Full name or identification of Guarantor No. 1 as listed in CTOS. "
            "E.g. 'TAN AH KOW (900101-14-1234)'."
        ),
    )
    guarantor_age_pg: Optional[int] = Field(
        None,
        description=(
            "Age of the guarantor in years. Critical flag: age >= 70 triggers a "
            "Hard Stop — Non-Actionable for Legal Recovery. "
            "CRITICAL: Output a plain integer only, no commas (e.g., output 45, NOT 45,000)."
        ),
    )
    guarantor_range_age: Optional[Literal[
        'Below 40',
        '40 - 49',
        '50 - 59',
        '60 - 64',
        '65 - 69',
        '70 and above',
    ]] = Field(
        None,
        description=(
            "Age band of the guarantor. Derive from guarantor_age_pg and select the "
            "EXACT matching Literal string. "
            "CRITICAL INSTRUCTION: DO NOT output the raw age integer. "
            "If the guarantor is 45 years old, you MUST output '40 - 49', NOT 45. "
            "CRITICAL: Copy the exact string character-by-character. "
            "Do not correct capitalization or spacing — every character matters. "
            "STRICT VALIDATION — the ONLY accepted values are these 6 exact strings: "
            "'Below 40', '40 - 49', '50 - 59', '60 - 64', '65 - 69', '70 and above'. "
            "ANY other value (including raw integers like 45, 55) will cause a "
            "ValidationError crash. "
            "Mapping examples: "
            "age < 40 → 'Below 40'; "
            "age 40–49 (e.g., 45) → '40 - 49'; "
            "age 50–59 (e.g., 55) → '50 - 59'; "
            "age 60–64 → '60 - 64'; "
            "age 65–69 → '65 - 69'; "
            "age >= 70 → '70 and above'. "
            "NEVER output the raw age. ALWAYS output the matching band string."
        ),
    )

    guarantor_legal_cases_unsettled: Optional[_LegalCasesLiteral] = Field(
        None,
        description=(
            "Unsettled legal cases against the guarantor from their personal CTOS report. "
            "Analyse the raw count and select the EXACT matching category — "
            "do NOT output a raw number: "
            "'0 ( Clean of legal action )', "
            "'1 ( 1 case still on-going or unsettled )', "
            "'2 ( 2 cases still on-going or unsettled )', "
            "'3 ( 3 cases still on-going or unsettled )', "
            "'>3 ( More than 3 cases still on-going or unsettled )'."
        ),
    )

    guarantor_blacklist_case: Optional[_BlacklistCasesLiteral] = Field(
        None,
        description=(
            "Blacklist entries against the guarantor from CTOS. "
            "Analyse the raw count and select the EXACT matching category — "
            "do NOT output a raw number: "
            "'0 ( no blacklist issue )', '1 ( 1 blacklist issue )', "
            "'2 ( 2 blacklist issue )', '3 ( 3 blacklist issue )', "
            "'>3 ( More than 3 blacklist issue )'."
        ),
    )

    spa_available: Optional[_YesNo] = Field(
        None,
        description=(
            "Whether the guarantor has a Special Attention Account (SPA) flag. "
            "Must be 'Yes' or 'No'."
        ),
    )

    repayment_to_banks: Optional[_RepaymentLiteral] = Field(
        None,
        description=(
            "Guarantor's CCRIS repayment conduct. Analyse the payment history and "
            "select the EXACT matching category — do NOT output a free-text description: "
            "'Satisfactory ( Prompt payment or occasionally lapsed 1 month )', "
            "'Moderate ( Consistently lapsed 1-2 months )', "
            "'Unsatisfactory ( Under SPA or consistently lapsed 2 months and above )', "
            "'N/A'."
        ),
    )

    total_facilities_limit_vs_outstanding_utilisation_pct: Optional[_UtilisationBandLiteral] = Field(
        None,
        description=(
            "Guarantor's bank facility utilisation band. Calculate the utilisation "
            "percentage, then map it to the EXACT band string — do NOT output the raw percentage. "
            "CRITICAL: Copy the exact string character-by-character. "
            "Do not correct capitalization or spacing — every character matters. "
            "STRICT VALIDATION — the ONLY accepted values are these 5 exact strings: "
            "'< 30%', '30% - 50%', '51% - 70%', '71% - 90%', '> 90%'. "
            "ANY other string (e.g., '62%', '45%', '80%', '0%') will cause a "
            "ValidationError crash. "
            "Mapping examples: 0%–29% → '< 30%'; 30%–50% → '30% - 50%'; "
            "51%–70% → '51% - 70%'; 71%–90% → '71% - 90%'; above 90% → '> 90%'. "
            "NEVER output a raw percentage like '62%'. ALWAYS output one of the 5 band strings."
        ),
    )


# ---------------------------------------------------------------------------
# 10. Company Background
# ---------------------------------------------------------------------------


class CompanyBackground(BaseModel):
    """
    Section 10 — structural and operational profile of the applicant company,
    used to assess business stability and credibility.
    Do NOT output any score or percentage — the frontend handles all scoring.
    """

    type_of_company: Optional[str] = Field(
        None,
        description=(
            "Legal structure of the company. "
            "E.g. 'Sdn Bhd', 'Bhd (PLC)', 'Enterprise', 'Partnership', 'Sole Proprietor'."
        ),
    )
    subsidiary_company_of_a_plc: Optional[_YesNo] = Field(
        None,
        description=(
            "Whether this company is a subsidiary of a Public Listed Company. "
            "Must be 'Yes' or 'No'."
        ),
    )

    years_in_business: Optional[Literal[
        '> 10 Years',
        '7.1 - 10 Years',
        '5.1 - 7 Years',
        '2.1 - 5 Years',
        '< 2 Years',
    ]] = Field(
        None,
        description=(
            "Calculate years in business from incorporation date to today. "
            "CRITICAL INSTRUCTION: You MUST output ONLY one of the provided exact strings. "
            "CRITICAL: Copy the exact string character-by-character. "
            "Do not correct capitalization or spacing — every character matters. "
            "DO NOT invent your own ranges (e.g., never output '0.1 - 2 Years', "
            "'1 - 3 Years', '2 - 4 Years', or any other invented range). "
            "Use this exact mapping: "
            "If < 2.0 years (e.g., 0.5, 1, 1.8), output '< 2 Years'. "
            "If 2.1 to 5.0 years (e.g., 2.7, 3, 4, 5), output '2.1 - 5 Years'. "
            "If 5.1 to 7.0 years (e.g., 6, 6.5), output '5.1 - 7 Years'. "
            "If 7.1 to 10.0 years (e.g., 8, 9, 10), output '7.1 - 10 Years'. "
            "If > 10 years (e.g., 11, 15, 20), output '> 10 Years'. "
            "ANY other string will cause a ValidationError crash."
        ),
    )

    paid_up_capital_rm: Optional[Literal[
        '> RM 750K',
        'RM 301K - 750K',
        'RM 151K - 300K',
        'RM 2.01 - 150K',
        '< RM 2',
    ]] = Field(
        None,
        description=(
            "Paid-up capital band. Extract the registered paid-up capital (MYR) from "
            "the CTOS company profile and select the EXACT matching Literal string. "
            "CRITICAL INSTRUCTION: DO NOT output the raw MYR amount or a raw number. "
            "If capital is RM 60,000, you MUST output 'RM 2.01 - 150K', NOT 60000. "
            "CRITICAL: Copy the exact string character-by-character. "
            "Do not correct capitalization or spacing — every character matters. "
            "STRICT VALIDATION — the ONLY accepted values are these 5 exact strings: "
            "'> RM 750K', 'RM 301K - 750K', 'RM 151K - 300K', "
            "'RM 2.01 - 150K', '< RM 2'. "
            "ANY other value (including raw amounts like 60000, 500000) will cause a "
            "ValidationError crash. "
            "Mapping examples: "
            "< RM 2 → '< RM 2'; "
            "RM 2.01–RM 150,000 (e.g., 60,000; 100,000) → 'RM 2.01 - 150K'; "
            "RM 151,001–RM 300,000 → 'RM 151K - 300K'; "
            "RM 301,001–RM 750,000 → 'RM 301K - 750K'; "
            "> RM 750,000 → '> RM 750K'. "
            "NEVER output the raw capital figure. ALWAYS output the matching band string."
        ),
    )


# ---------------------------------------------------------------------------
# 11. Additional Information
# ---------------------------------------------------------------------------


class AdditionalInformation(BaseModel):
    """Section 11 — supplementary details not captured in other sections."""

    number_of_directors_partners: Optional[int] = Field(
        None,
        description=(
            "Total number of directors (for Sdn Bhd/Bhd) or partners "
            "(for partnership / enterprise) as listed in CTOS. "
            "CRITICAL: Output a plain integer only, no commas."
        ),
    )
    nature_of_business_category: Optional[str] = Field(
        None,
        description=(
            "Business activity category or categories. "
            "Select one or more from: 'Trading', 'Manufacturing', 'Services', "
            "'Construction', 'Agriculture', 'Others'. "
            "If multiple categories apply, output them as a comma-separated string, "
            "e.g. 'Trading, Manufacturing'."
        ),
    )
    others: Optional[str] = Field(
        None,
        description=(
            "Any other relevant information or observations not captured elsewhere, "
            "such as market reputation, group affiliation, or special notes."
        ),
    )


# ---------------------------------------------------------------------------
# 12. Proposed Credit Limit
# ---------------------------------------------------------------------------


class ProposedCreditLimit(BaseModel):
    """Section 12 — credit limit recommendation for this applicant."""

    proposed_credit_limit_rm: Optional[float] = Field(
        None,
        description=(
            "AI-calculated or officer-proposed credit limit (MYR). "
            "CRITICAL: Output a raw number only. DO NOT use commas as thousands separators "
            "(e.g., output 93934.6, NOT 93,934.6)."
        ),
    )
    total_credit_limit_per_account: Optional[float] = Field(
        None,
        description=(
            "Total credit limit allocated to this single account (MYR). "
            "CRITICAL: Output a raw number only. DO NOT use commas as thousands separators "
            "(e.g., output 150000.0, NOT 150,000.0)."
        ),
    )
    propose_cl_plus_all_group_exposure_cl: Optional[float] = Field(
        None,
        description=(
            "Combined total: proposed credit limit for this account plus all existing "
            "credit limits across the entire group / related companies (MYR). "
            "CRITICAL: Output a raw number only. DO NOT use commas as thousands separators "
            "(e.g., output 250000.0, NOT 250,000.0)."
        ),
    )


# ---------------------------------------------------------------------------
# Root model — the full Credit Scoring Detailed Form
# ---------------------------------------------------------------------------


class CreditScoringDetailedForm(BaseModel):
    """
    Complete structured representation of the Chin Hin Credit Scoring Form Template.

    All 12 sections are captured as nested Pydantic models.  Categorical fields
    use Literal types so the AI is forced to select from the exact scoring-matrix
    option strings rather than outputting raw numbers.  Every field is Optional so
    that a partial CTOS report does not cause validation failures.

    IMPORTANT: This model contains NO score/percentage fields.  All weighted
    scoring is computed by the React frontend via FIELD_SCORE_MAP.  The AI's
    sole responsibility is classification — never calculation.

    extra='forbid' ensures that if the AI returns wrong top-level keys
    (e.g. "financials" instead of "financial_information") a ValidationError
    is raised immediately rather than silently filling sections with None.
    """

    model_config = ConfigDict(extra='forbid')

    customer_type: Optional[Literal['New Customer', 'Existing Customer']] = Field(
        None,
        description=(
            "Whether this applicant is a New Customer or an Existing Customer of Chin Hin. "
            "CRITICAL — this field controls which scoring matrix the frontend uses. "
            "Determine this from the ERP agent findings or the 'Type of Customer' section: "
            "if the applicant has no prior trading history with Chin Hin, output 'New Customer'; "
            "if they have an established account or trade history, output 'Existing Customer'. "
            "STRICT VALIDATION — the ONLY accepted values are 'New Customer' and 'Existing Customer'. "
            "ANY other string will cause a ValidationError crash."
        ),
    )

    type_of_customer: TypeOfCustomer = Field(
        default_factory=TypeOfCustomer,
        description="Section 1 — Review / Reactive classification.",
    )
    salesman_profile: SalesmanProfile = Field(
        default_factory=SalesmanProfile,
        description="Section 2 — Internal sales ownership.",
    )
    customer_information: CustomerInformation = Field(
        default_factory=CustomerInformation,
        description="Section 3 — Company identity and contact details.",
    )
    ccris_for_company: CCRISForCompany = Field(
        default_factory=CCRISForCompany,
        description="Section 4 — CCRIS assessment for the applicant company.",
    )
    financial_information: FinancialInformation = Field(
        default_factory=FinancialInformation,
        description="Section 5 — Financial strength from audited accounts / bank statements.",
    )
    internal_information: InternalInformation = Field(
        default_factory=InternalInformation,
        description="Section 6 — Internal ERP trade records and group exposure.",
    )
    pg_bg_cg_obtained: PGBGCGObtained = Field(
        default_factory=PGBGCGObtained,
        description="Section 7 — Type of guarantee secured.",
    )
    personal_guarantee: PersonalGuarantee = Field(
        default_factory=PersonalGuarantee,
        description="Section 8 — Personal guarantee summary.",
    )
    guarantor_ccris_profiles: List[GuarantorCCRISProfile] = Field(
        default_factory=list,
        description=(
            "Section 9 — CCRIS profiles for ALL personal guarantors. "
            "Extract a separate GuarantorCCRISProfile object for EVERY guarantor "
            "found in the CTOS report. If the document lists two guarantors, "
            "this list must contain exactly two entries. "
            "Do NOT merge multiple guarantors into a single entry."
        ),
    )
    company_background: CompanyBackground = Field(
        default_factory=CompanyBackground,
        description="Section 10 — Company structural profile.",
    )
    additional_information: AdditionalInformation = Field(
        default_factory=AdditionalInformation,
        description="Section 11 — Supplementary details.",
    )
    proposed_credit_limit: ProposedCreditLimit = Field(
        default_factory=ProposedCreditLimit,
        description="Section 12 — Credit limit recommendation.",
    )
