/**
 * scoreMapping.js
 * ---------------
 * Two separate scoring matrices — one per customer type — sourced directly
 * from the Credit Scoring Matrix CSVs.
 *
 * Keys must match the exact Literal strings defined in credit_scoring_form.py
 * (i.e. what the AI outputs), so the frontend lookup is deterministic.
 *
 * NOTE: `guarantor_repayment_to_banks` and `guarantor_utilisation_pct` are
 * virtual score-map keys (not Pydantic field names).  The guarantor scoring
 * code maps these back to the actual data fields `repayment_to_banks` and
 * `total_facilities_limit_vs_outstanding_utilisation_pct` respectively.
 * This is necessary because the company-CCRIS and guarantor sections share
 * the same field names but have different point values in some matrices.
 */

// ─────────────────────────────────────────────────────────────────────────────
// Shared sub-maps (identical in both matrices)
// ─────────────────────────────────────────────────────────────────────────────

const _LEGAL_CASES = {
  '0 ( Clean of legal action )': 5,
  '1 ( 1 case still on-going or unsettled )': 3,
  '2 ( 2 cases still on-going or unsettled )': 2,
  '3 ( 3 cases still on-going or unsettled )': 1,
  '>3 ( More than 3 cases still on-going or unsettled )': 0,
}

const _BLACKLIST_CASES = {
  '0 ( no blacklist issue )': 5,
  '1 ( 1 blacklist issue )': 3,
  '2 ( 2 blacklist issue )': 2,
  '3 ( 3 blacklist issue )': 1,
  '>3 ( More than 3 blacklist issue )': 0,
}

const _REPAYMENT_COMPANY = {
  'Satisfactory ( Prompt payment or occasionally lapsed 1 month )': 10,
  'Moderate ( Consistently lapsed 1-2 months )': 6,
  'Unsatisfactory ( Under SPA or consistently lapsed 2 months and above )': 0,
  'N/A': 0,
}

// Company-level facility utilisation (same in both matrices)
const _UTILISATION_COMPANY = {
  '< 30%': 5,
  '30% - 50%': 4,
  '51% - 70%': 2,
  '71% - 90%': 1,
  '> 90%': 0,
  'N/A': 0,
}

const _FINANCIAL_SHARED = {
  bank_statement_end_month_balance_rm: {
    '> RM 500,000': 5,
    'RM 200,001 - RM 500,000': 4,
    'RM 50,001 - RM 200,000': 3,
    'RM 10,001 - RM 50,000': 2,
    '<= RM 10,000': 0,
    'N/A': 0,
  },
  net_profit_loss: {
    'Profit ( > RM 500,000 )': 5,
    'Profit ( RM 100,001 - RM 500,000 )': 4,
    'Profit ( RM 1 - RM 100,000 )': 2,
    'Break-even': 2,
    'Loss': 0,
  },
  retained_profit_accumulated_losses: {
    'Retained Profit': 2.5,
    'Accumulated Losses': 0,
  },
  net_worth: {
    '> RM 1 Mil': 5,
    'RM 501K - RM 1 Mil': 5,
    'RM 201K - RM 500K': 5,
    'RM 1 - RM 200K': 5,
    'Negative': 0,
  },
  net_current_assets_liabilities: {
    'Positive': 2.5,
    'Negative': 0,
  },
  current_ratio: {
    '> 2.00': 2.5,
    '1.01 - 1.99': 1.5,
    '< 1.00': 0,
    'N/A': 0,
  },
  gearing_ratio: {
    '( 0 - 0.99 )': 2.5,
    '( 1.00 - 1.99 )': 2,
    '( 2.00 - 2.99 )': 1.5,
    '( 3.00 - 3.99 )': 1,
    '> 4.00': 0,
    'Negative': 0,
    'N/A': 0,
  },
}

const _TRADE_REF_PAYMENT = {
  '< 90 days': 5,
  '91 - 120 days': 4,
  '121 - 150 days': 2,
  '151 - 180 days': 1,
  '> 180 days': 0,
  'N/A': 0,
}

// ─────────────────────────────────────────────────────────────────────────────
// NEW CUSTOMER Score Map  (CCRIS 25% | Financial 25% | Internal 10% | PG 30% | Background 10%)
// ─────────────────────────────────────────────────────────────────────────────

export const NEW_CUSTOMER_SCORE_MAP = {

  // ── CCRIS for Company (25%) ───────────────────────────────────────────────
  legal_cases_unsettled: { ..._LEGAL_CASES },
  blacklist_cases: { ..._BLACKLIST_CASES },
  repayment_to_banks: { ..._REPAYMENT_COMPANY },
  total_facilities_limit_vs_outstanding_utilisation_pct: { ..._UTILISATION_COMPANY },

  // ── Financial Information (25%) ───────────────────────────────────────────
  ..._FINANCIAL_SHARED,

  // ── Internal Information (10%) ────────────────────────────────────────────
  trade_reference_external_payment_pattern: { ..._TRADE_REF_PAYMENT },
  group_exposure_internal_payment_pattern: {
    '< 90 days': 5,
    '91 - 120 days': 4,
    '121 - 150 days': 2,
    '151 - 180 days': 1,
    '> 180 days': 0,
    'N/A': 0,
  },
  // years_in_relationship is NOT scored for New Customers

  // ── PG / BG / CG Obtained (30%) ───────────────────────────────────────────
  bank_guarantee_30_pct: { 'Yes': 30, 'No': 0 },
  corporate_guarantee_18_pct: { 'Yes': 18, 'No': 0 },
  personal_guarantee_5_pct: { 'Yes': 5, 'No': 0 },

  // Guarantor-specific score keys (virtual — mapped from actual data fields)
  guarantor_legal_cases_unsettled: { ..._LEGAL_CASES },
  guarantor_blacklist_case: { ..._BLACKLIST_CASES },
  guarantor_repayment_to_banks: {
    'Satisfactory ( Prompt payment or occasionally lapsed 1 month )': 10,
    'Moderate ( Consistently lapsed 1-2 months )': 6,
    'Unsatisfactory ( Under SPA or consistently lapsed 2 months and above )': 0,
    'N/A': 0,
  },
  guarantor_utilisation_pct: {
    '< 30%': 5,
    '30% - 50%': 4,
    '51% - 70%': 3,
    '71% - 90%': 2,
    '> 90%': 0,
    'N/A': 0,
  },

  // ── Company Background (10%) ──────────────────────────────────────────────
  years_in_business: {
    '> 10 Years': 5,
    '7.1 - 10 Years': 4,
    '5.1 - 7 Years': 3,
    '2.1 - 5 Years': 1,
    '< 2 Years': 0,
  },
  paid_up_capital_rm: {
    '> RM 750K': 5,
    'RM 301K - 750K': 4,
    'RM 151K - 300K': 3,
    'RM 2.01 - 150K': 2,
    '< RM 2': 0,
  },
}

// ─────────────────────────────────────────────────────────────────────────────
// EXISTING CUSTOMER Score Map  (CCRIS 25% | Financial 25% | Internal 30% | PG 20%)
// Note: Company Background section is NOT scored for Existing Customers.
// ─────────────────────────────────────────────────────────────────────────────

export const EXISTING_CUSTOMER_SCORE_MAP = {

  // ── CCRIS for Company (25%) — identical to New Customer ───────────────────
  legal_cases_unsettled: { ..._LEGAL_CASES },
  blacklist_cases: { ..._BLACKLIST_CASES },
  repayment_to_banks: { ..._REPAYMENT_COMPANY },
  total_facilities_limit_vs_outstanding_utilisation_pct: { ..._UTILISATION_COMPANY },

  // ── Financial Information (25%) — identical to New Customer ──────────────
  ..._FINANCIAL_SHARED,

  // ── Internal Information (30%) — higher weight & different scores ─────────
  trade_reference_external_payment_pattern: { ..._TRADE_REF_PAYMENT },
  group_exposure_internal_payment_pattern: {
    '< 90 days': 20,
    '91 - 120 days': 17,
    '121 - 150 days': 11,
    '151 - 180 days': 8,
    '> 180 days': 5,
    'N/A': 5,
  },
  years_in_relationship: {
    '> 10 Years': 5,
    '7.1 Years - 10 Years': 4,
    '5.1 Years - 7 Years': 3,
    '2.1 Years - 5 Years': 2,
    '< 2 Years': 0,
  },

  // ── PG / BG / CG Obtained (20%) — lower max scores ───────────────────────
  bank_guarantee_30_pct: { 'Yes': 20, 'No': 0 },
  corporate_guarantee_18_pct: { 'Yes': 8, 'No': 0 },
  personal_guarantee_5_pct: { 'Yes': 5, 'No': 0 },

  // Guarantor-specific score keys — lower values for Existing Customers
  guarantor_legal_cases_unsettled: {
    '0 ( Clean of legal action )': 3,
    '1 ( 1 case still on-going or unsettled )': 1.8,
    '2 ( 2 cases still on-going or unsettled )': 1.2,
    '3 ( 3 cases still on-going or unsettled )': 0.6,
    '>3 ( More than 3 cases still on-going or unsettled )': 0,
  },
  guarantor_blacklist_case: {
    '0 ( no blacklist issue )': 3,
    '1 ( 1 blacklist issue )': 1.8,
    '2 ( 2 blacklist issue )': 1.2,
    '3 ( 3 blacklist issue )': 0.6,
    '>3 ( More than 3 blacklist issue )': 0,
  },
  guarantor_repayment_to_banks: {
    'Satisfactory ( Prompt payment or occasionally lapsed 1 month )': 6,
    'Moderate ( Consistently lapsed 1-2 months )': 3.6,
    'Unsatisfactory ( Under SPA or consistently lapsed 2 months and above )': 0,
    'N/A': 0,
  },
  guarantor_utilisation_pct: {
    '< 30%': 3,
    '30% - 50%': 2.4,
    '51% - 70%': 1.8,
    '71% - 90%': 1.2,
    '> 90%': 0,
    'N/A': 0,
  },

  // Company Background: NOT scored for Existing Customers.
  // years_in_business and paid_up_capital_rm intentionally omitted.
}

// ─────────────────────────────────────────────────────────────────────────────
// Backward-compat alias — new code should use NEW_CUSTOMER_SCORE_MAP directly
// ─────────────────────────────────────────────────────────────────────────────
export const FIELD_SCORE_MAP = NEW_CUSTOMER_SCORE_MAP

// ─────────────────────────────────────────────────────────────────────────────
// calculateFinalScores
// ─────────────────────────────────────────────────────────────────────────────
// Deterministically computes the 5-category score breakdown from formData.
// Mirrors the SectionCard logic in CtosDetailedExtraction.jsx exactly so the
// ResultTable and ScoreBar always agree with the per-section scores displayed
// in the accordion.
//
// Parameters:
//   formData     {object}  Full CreditScoringDetailedForm (from ctosFormData state)
//   customerType {string}  'Existing Customer' | anything else → New Customer
//
// Returns:
//   { ccris_company, financial_info, internal_info, guarantees, company_background, total }
//   All values are numbers (rounded to 2 dp).
// ─────────────────────────────────────────────────────────────────────────────

const _GUARANTOR_SCORED_FIELDS = [
  { dataKey: 'guarantor_legal_cases_unsettled',                       scoreKey: 'guarantor_legal_cases_unsettled' },
  { dataKey: 'guarantor_blacklist_case',                              scoreKey: 'guarantor_blacklist_case' },
  { dataKey: 'repayment_to_banks',                                    scoreKey: 'guarantor_repayment_to_banks' },
  { dataKey: 'total_facilities_limit_vs_outstanding_utilisation_pct', scoreKey: 'guarantor_utilisation_pct' },
]

export function calculateFinalScores(formData, customerType) {
  // ── Hard-stop sanity gate ──────────────────────────────────────────────
  // If the AI couldn't even find a company name, registration number, OR
  // reference number, the form is invalid — return null to force the UI to
  // show "N/A" instead of a fake score.  This is the last line of defence
  // against phantom marks from empty/default Pydantic forms.
  const custInfo = formData?.customer_information || {}
  if (!custInfo.company_name && !custInfo.company_business_registration_no && !custInfo.reference_no) {
    console.warn('Sanity check failed: Missing core company identifiers. Halting scoring.')
    return null
  }

  const scoreMap = customerType === 'Existing Customer'
    ? EXISTING_CUSTOMER_SCORE_MAP
    : NEW_CUSTOMER_SCORE_MAP

  function pts(key, val) {
    const p = scoreMap[key]?.[val]
    return p !== undefined ? p : 0
  }

  // 1. CCRIS for Company (max 25)
  const ccris = formData?.ccris_for_company ?? {}
  const ccris_company =
    pts('legal_cases_unsettled',                              ccris.legal_cases_unsettled) +
    pts('blacklist_cases',                                    ccris.blacklist_cases) +
    pts('repayment_to_banks',                                 ccris.repayment_to_banks) +
    pts('total_facilities_limit_vs_outstanding_utilisation_pct',
        ccris.total_facilities_limit_vs_outstanding_utilisation_pct)

  // 2. Financial Information (max 25)
  const fin = formData?.financial_information ?? {}
  const financial_info =
    pts('bank_statement_end_month_balance_rm',  fin.bank_statement_end_month_balance_rm) +
    pts('net_profit_loss',                      fin.net_profit_loss) +
    pts('retained_profit_accumulated_losses',   fin.retained_profit_accumulated_losses) +
    pts('net_worth',                            fin.net_worth) +
    pts('net_current_assets_liabilities',       fin.net_current_assets_liabilities) +
    pts('current_ratio',                        fin.current_ratio) +
    pts('gearing_ratio',                        fin.gearing_ratio)

  // 3. Internal Information (max 10 new / max 30 existing)
  const ii = formData?.internal_information ?? {}
  const internal_info =
    pts('trade_reference_external_payment_pattern', ii.trade_reference_external_payment_pattern) +
    pts('group_exposure_internal_payment_pattern',  ii.group_exposure_internal_payment_pattern) +
    pts('years_in_relationship',                    ii.years_in_relationship)

  // 4. PG / BG / CG + Guarantor CCRIS average (max 30 new / max 20 existing)
  const pg = formData?.pg_bg_cg_obtained ?? {}
  const pgBase =
    pts('bank_guarantee_30_pct',      pg.bank_guarantee_30_pct) +
    pts('corporate_guarantee_18_pct', pg.corporate_guarantee_18_pct) +
    pts('personal_guarantee_5_pct',   pg.personal_guarantee_5_pct)

  const profiles = formData?.guarantor_ccris_profiles ?? []
  const guarantorArrayScore = (() => {
    if (profiles.length === 0) return 0
    const perGuarantor = profiles.map(profile =>
      _GUARANTOR_SCORED_FIELDS.reduce((sum, { dataKey, scoreKey }) => {
        const p = scoreMap[scoreKey]?.[profile[dataKey]]
        return p !== undefined ? sum + p : sum
      }, 0)
    )
    return perGuarantor.reduce((a, b) => a + b, 0) / perGuarantor.length
  })()
  const guarantees = pgBase + guarantorArrayScore

  // 5. Company Background (max 10 — New Customers only; omitted from Existing map)
  const bg = formData?.company_background ?? {}
  const company_background =
    pts('years_in_business',   bg.years_in_business) +
    pts('paid_up_capital_rm',  bg.paid_up_capital_rm)

  const total = ccris_company + financial_info + internal_info + guarantees + company_background

  const round2 = v => Math.round(v * 100) / 100
  return {
    ccris_company:      round2(ccris_company),
    financial_info:     round2(financial_info),
    internal_info:      round2(internal_info),
    guarantees:         round2(guarantees),
    company_background: round2(company_background),
    total:              round2(total),
  }
}
