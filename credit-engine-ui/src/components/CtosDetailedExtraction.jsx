/**
 * CtosDetailedExtraction.jsx
 * --------------------------
 * Collapsible accordion rendering all 12 sections of CreditScoringDetailedForm.
 * All non-score fields are officer-editable via inline click-to-edit.
 *
 * Props
 * -----
 *   data         {object|null}    JSON from POST /api/v1/extract-credit-scoring-form.
 *   onDataChange {function|null}  Called with the updated data object on each edit.
 *   decision     {object|null}    Latest CreditDecision from the Chief Credit Officer AI.
 *                                 Used to auto-fill Section 12 (Proposed Credit Limit).
 */

import { useState, useEffect, useRef } from 'react'
import axios from 'axios'
import { NEW_CUSTOMER_SCORE_MAP, EXISTING_CUSTOMER_SCORE_MAP } from '../utils/scoreMapping'
import {
  ChevronDown, Pencil, RefreshCw, Loader2, CheckCircle,
  UserCheck, Users, Building2, ShieldCheck, BarChart2,
  Database, Lock, Shield, Briefcase, Info, DollarSign, ScanSearch,
  Sparkles,
} from 'lucide-react'
import './CtosDetailedExtraction.css'

// ─────────────────────────────────────────────────────────────────────────────
// Section schema
// ─────────────────────────────────────────────────────────────────────────────

const SECTIONS = [
  // ── 1. Type of Customer ──────────────────────────────────────────────────
  {
    key: 'type_of_customer',
    number: 1,
    title: 'Type of Customer',
    icon: <UserCheck size={14} />,
    scoreKey: null,
    rows: [
      [{ label: 'Customer Type', key: 'type', fmt: 'text' }],
    ],
  },

  // ── 2. Salesman Profile ───────────────────────────────────────────────────
  {
    key: 'salesman_profile',
    number: 2,
    title: 'Salesman Profile',
    icon: <Users size={14} />,
    scoreKey: null,
    rows: [
      [
        { label: 'Company', key: 'company', fmt: 'text' },
        { label: 'Branches', key: 'branches', fmt: 'text' },
      ],
      [
        { label: 'Salesman', key: 'salesman', fmt: 'text' },
        { label: 'Head of Branch', key: 'head_of_branch', fmt: 'text' },
      ],
    ],
  },

  // ── 3. Customer Information ───────────────────────────────────────────────
  {
    key: 'customer_information',
    number: 3,
    title: 'Customer Information',
    icon: <Building2 size={14} />,
    scoreKey: null,
    rows: [
      [
        { label: 'Reference No.', key: 'ref_no', fmt: 'text' },
        { label: 'Registration No.', key: 'company_business_registration_no', fmt: 'text' },
      ],
      [{ label: 'Company Name', key: 'company_name', fmt: 'text' }],
      [{ label: 'Address', key: 'address', fmt: 'text' }],
      [
        { label: 'Phone No.', key: 'phone_no', fmt: 'text' },
        { label: 'Fax No.', key: 'fax_no', fmt: 'text' },
      ],
      [{ label: 'Credit Terms', key: 'credit_terms', fmt: 'text' }],
    ],
  },

  // ── 4. CCRIS for Company ─────────────────────────────────────────────────
  {
    key: 'ccris_for_company',
    number: 4,
    title: 'CCRIS for Company',
    icon: <ShieldCheck size={14} />,
    scoreKey: 'ccris_pct',
    rows: [
      [
        { label: 'Legal Cases (Unsettled)', key: 'legal_cases_unsettled', fmt: 'text' },
        { label: 'Legal Cases Score', key: 'legal_cases_pct', fmt: 'score' },
      ],
      [
        { label: 'Blacklist Cases', key: 'blacklist_cases', fmt: 'text' },
        { label: 'Blacklist Score', key: 'blacklist_pct', fmt: 'score' },
      ],
      [{ label: 'Special Attention Account (SPA)', key: 'special_attention_account_spa', fmt: 'yesno' }],
      [
        { label: 'Repayment to Banks', key: 'repayment_to_banks', fmt: 'text' },
        { label: 'Repayment Score', key: 'repayment_to_banks_pct', fmt: 'score' },
      ],
      [
        { label: 'Total Facility Utilisation', key: 'total_facilities_limit_vs_outstanding_utilisation_pct', fmt: 'pct' },
        { label: 'Facility Score', key: 'facility_limit_vs_outstanding_pct', fmt: 'score' },
      ],
    ],
  },

  // ── 5. Financial Information ──────────────────────────────────────────────
  {
    key: 'financial_information',
    number: 5,
    title: 'Financial Information',
    icon: <BarChart2 size={14} />,
    scoreKey: 'financial_information_pct',
    rows: [
      [
        { label: 'Bank Statement Provided', key: 'bank_statement_provided', fmt: 'yesno' },
        { label: 'Bank Stmt Score', key: 'bank_statement_pct', fmt: 'score' },
      ],
      [{ label: 'Bank Statement End-Month Balance', key: 'bank_statement_end_month_balance_rm', fmt: 'currency' }],
      [
        { label: 'Audited Report Provided', key: 'financial_audited_report_provided', fmt: 'yesno' },
        { label: 'Report Date', key: 'financial_report_date', fmt: 'text' },
      ],
      [
        { label: 'Turnover (Band)', key: 'turnover', fmt: 'text' },
        { label: 'Turnover Specified Amount', key: 'turnover_specified_amount', fmt: 'currency' },
      ],
      [
        { label: 'Net Profit / Loss', key: 'net_profit_loss', fmt: 'text' },
        { label: 'Net Profit / Loss Score', key: 'net_profit_loss_pct', fmt: 'score' },
      ],
      [{ label: 'Net Profit Specified Amount', key: 'net_profit_specified_amount', fmt: 'currency' }],
      [
        { label: 'Retained Profit / Acc. Losses', key: 'retained_profit_accumulated_losses', fmt: 'text' },
        { label: 'Retained Profit Score', key: 'retained_profit_pct', fmt: 'score' },
      ],
      [{ label: 'Retained Profit Specified Amount', key: 'retained_profit_specified_amount', fmt: 'currency' }],
      [
        { label: 'Net Worth (Band)', key: 'net_worth', fmt: 'text' },
        { label: 'Net Worth Score', key: 'net_worth_pct', fmt: 'score' },
      ],
      [{ label: 'Net Worth Specified Amount', key: 'net_worth_specified_amount', fmt: 'currency' }],
      [
        { label: 'Net Current Assets / Liabilities', key: 'net_current_assets_liabilities', fmt: 'text' },
        { label: 'Net Current Assets Score', key: 'net_current_assets_pct', fmt: 'score' },
      ],
      [{ label: 'Net Current Assets Specified Amount', key: 'net_current_assets_specified_amount', fmt: 'currency' }],
      [
        { label: 'Current Ratio', key: 'current_ratio', fmt: 'ratio' },
        { label: 'Current Ratio Score', key: 'current_ratio_pct', fmt: 'score' },
      ],
      [
        { label: 'Gearing Ratio', key: 'gearing_ratio', fmt: 'ratio' },
        { label: 'Gearing Ratio Score', key: 'gearing_ratio_pct', fmt: 'score' },
      ],
    ],
  },

  // ── 6. Internal Information ───────────────────────────────────────────────
  {
    key: 'internal_information',
    number: 6,
    title: 'Internal Information',
    icon: <Database size={14} />,
    scoreKey: 'internal_information_pct',
    rows: [
      [{ label: 'Trade Ref. for Group Exposure Available', key: 'trade_reference_for_group_exposure_available', fmt: 'yesno' }],
      [{ label: 'Trade Ref. External Payment Pattern', key: 'trade_reference_external_payment_pattern', fmt: 'text' }],
      [{ label: 'Remark', key: 'remark', fmt: 'text' }],
      [{ label: 'Group Exposure Internal Payment Pattern', key: 'group_exposure_internal_payment_pattern', fmt: 'text' }],
      [{ label: 'Years in Relationship (Existing Customers)', key: 'years_in_relationship', fmt: 'text' }],
      [{ label: 'Group Exposure with Other Subsidiaries', key: 'group_exposure_with_other_subsidiaries', fmt: 'text' }],
      [{ label: 'Common Director / Shareholder / Guarantor', key: 'common_director_or_shareholder_or_guarantor', fmt: 'text' }],
    ],
  },

  // ── 7. PG / BG / CG Obtained ─────────────────────────────────────────────
  {
    key: 'pg_bg_cg_obtained',
    number: 7,
    title: 'PG / BG / CG Obtained',
    icon: <Lock size={14} />,
    scoreKey: 'pg_cg_bg_pct',
    linkedArrayKey: 'guarantor_ccris_profiles',
    maxScore: 30,
    rows: [
      [
        { label: 'Bank Guarantee (max 30%)', key: 'bank_guarantee_30_pct', fmt: 'yesno' },
        { label: 'Corporate Guarantee (max 18%)', key: 'corporate_guarantee_18_pct', fmt: 'yesno' },
      ],
      [{ label: 'Personal Guarantee (max 5%)', key: 'personal_guarantee_5_pct', fmt: 'yesno' }],
    ],
  },

  // ── 8. Personal Guarantee ────────────────────────────────────────────────
  {
    key: 'personal_guarantee',
    number: 8,
    title: 'Personal Guarantee',
    icon: <UserCheck size={14} />,
    scoreKey: null,
    rows: [
      [
        { label: 'Number of Guarantors', key: 'number_of_guarantor', fmt: 'count' },
        { label: 'Guarantee Amount', key: 'guarantee_amount', fmt: 'currency' },
      ],
    ],
  },

  // ── 10. Company Background ───────────────────────────────────────────────
  {
    key: 'company_background',
    number: 10,
    title: 'Company Background',
    icon: <Briefcase size={14} />,
    scoreKey: 'company_background_pct',
    rows: [
      [
        { label: 'Type of Company', key: 'type_of_company', fmt: 'text' },
        { label: 'Subsidiary of PLC', key: 'subsidiary_company_of_a_plc', fmt: 'yesno' },
      ],
      [
        { label: 'Years in Business', key: 'years_in_business', fmt: 'years' },
        { label: 'Years in Business Score', key: 'years_in_business_pct', fmt: 'score' },
      ],
      [
        { label: 'Paid-up Capital', key: 'paid_up_capital_rm', fmt: 'currency' },
        { label: 'Paid-up Capital Score', key: 'paid_up_capital_pct', fmt: 'score' },
      ],
    ],
  },

  // ── 11. Additional Information ───────────────────────────────────────────
  {
    key: 'additional_information',
    number: 11,
    title: 'Additional Information',
    icon: <Info size={14} />,
    scoreKey: null,
    rows: [
      [
        { label: 'No. of Directors / Partners', key: 'number_of_directors_partners', fmt: 'count' },
        { label: 'Nature of Business Category', key: 'nature_of_business_category', fmt: 'text' },
      ],
      [{ label: 'Others / Remarks', key: 'others', fmt: 'text' }],
    ],
  },

  // ── 12. Proposed Credit Limit ────────────────────────────────────────────
  {
    key: 'proposed_credit_limit',
    number: 12,
    title: 'Proposed Credit Limit',
    icon: <DollarSign size={14} />,
    scoreKey: null,
    rows: [
      [
        { label: 'Proposed Credit Limit', key: 'proposed_credit_limit_rm', fmt: 'currency' },
        { label: 'Total Credit Limit per Account', key: 'total_credit_limit_per_account', fmt: 'currency' },
      ],
      [{ label: 'Proposed CL + All Group Exposure CL', key: 'propose_cl_plus_all_group_exposure_cl', fmt: 'currency' }],
    ],
  },
]

// ─────────────────────────────────────────────────────────────────────────────
// Guarantor profile constants (dynamic sections — one per guarantor in the list)
// ─────────────────────────────────────────────────────────────────────────────

const GUARANTOR_PROFILE_ROWS = [
  [{ label: 'Guarantor Name / Info', key: 'guarantor_info_pg', fmt: 'text' }],
  [
    { label: 'Guarantor Age', key: 'guarantor_age_pg', fmt: 'age' },
    { label: 'Age Range', key: 'guarantor_range_age', fmt: 'text' },
  ],
  [
    { label: 'Legal Cases (Unsettled)', key: 'guarantor_legal_cases_unsettled', fmt: 'text' },
    { label: 'Legal Unsettled Score', key: 'legal_unsettled_pct', fmt: 'score' },
  ],
  [
    { label: 'Blacklist Cases', key: 'guarantor_blacklist_case', fmt: 'text' },
    { label: 'Blacklist Score', key: 'blacklist_pct', fmt: 'score' },
  ],
  [{ label: 'SPA Available', key: 'spa_available', fmt: 'yesno' }],
  [
    { label: 'Repayment to Banks', key: 'repayment_to_banks', fmt: 'text' },
    { label: 'Repayment Score', key: 'repayment_to_banks_pct', fmt: 'score' },
  ],
  [{ label: 'Total Facility Utilisation', key: 'total_facilities_limit_vs_outstanding_utilisation_pct', fmt: 'pct' }],
]

// CCRIS fields scored per guarantor for the PG/BG/CG bucket.
// dataKey = actual field name on the guarantor profile object.
// scoreKey = key to look up in the active score map (may differ — the guarantor
// section uses matrix-specific guarantor point values, not company-CCRIS ones).
const GUARANTOR_SCORED_FIELDS = [
  { dataKey: 'guarantor_legal_cases_unsettled',                       scoreKey: 'guarantor_legal_cases_unsettled' },
  { dataKey: 'guarantor_blacklist_case',                              scoreKey: 'guarantor_blacklist_case' },
  { dataKey: 'repayment_to_banks',                                    scoreKey: 'guarantor_repayment_to_banks' },
  { dataKey: 'total_facilities_limit_vs_outstanding_utilisation_pct', scoreKey: 'guarantor_utilisation_pct' },
]

// ─────────────────────────────────────────────────────────────────────────────
// Field input config
// Maps each field key to the control type and options it should render in
// edit mode.  Fields not listed here fall back to a plain text/number <input>.
// ─────────────────────────────────────────────────────────────────────────────

const FIELD_INPUT_CONFIG = {

  // ── Yes / No radio fields ─────────────────────────────────────────────────
  // Option strings match the _YesNo Literal alias in credit_scoring_form.py
  special_attention_account_spa:                { type: 'radio', options: ['Yes', 'No'] },
  bank_statement_provided:                      { type: 'radio', options: ['Yes', 'No'] },
  financial_audited_report_provided:            { type: 'radio', options: ['Yes', 'No'] },
  trade_reference_for_group_exposure_available: { type: 'radio', options: ['Yes', 'No'] },
  group_exposure_with_other_subsidiaries:       { type: 'radio', options: ['Yes', 'No'] },
  common_director_or_shareholder_or_guarantor:  { type: 'radio', options: ['Yes', 'No'] },
  spa_available:                                { type: 'radio', options: ['Yes', 'No'] },
  subsidiary_company_of_a_plc:                  { type: 'radio', options: ['Yes', 'No'] },
  bank_guarantee_30_pct:                        { type: 'radio', options: ['Yes', 'No'] },
  corporate_guarantee_18_pct:                   { type: 'radio', options: ['Yes', 'No'] },
  personal_guarantee_5_pct:                     { type: 'radio', options: ['Yes', 'No'] },

  // ── Custom radio fields ───────────────────────────────────────────────────
  type: { type: 'radio', options: ['Review', 'Reactive'] },

  // ── Binary classification radios ─────────────────────────────────────────
  retained_profit_accumulated_losses: {
    type: 'radio',
    options: ['Retained Profit', 'Accumulated Losses'],
  },
  net_current_assets_liabilities: {
    type: 'radio',
    options: ['Positive', 'Negative'],
  },

  // ── Dropdown fields — options are EXACT Literal strings from credit_scoring_form.py ──

  // _LegalCasesLiteral
  legal_cases_unsettled: {
    type: 'dropdown',
    options: [
      '0 ( Clean of legal action )',
      '1 ( 1 case still on-going or unsettled )',
      '2 ( 2 cases still on-going or unsettled )',
      '3 ( 3 cases still on-going or unsettled )',
      '>3 ( More than 3 cases still on-going or unsettled )',
    ],
  },
  guarantor_legal_cases_unsettled: {
    type: 'dropdown',
    options: [
      '0 ( Clean of legal action )',
      '1 ( 1 case still on-going or unsettled )',
      '2 ( 2 cases still on-going or unsettled )',
      '3 ( 3 cases still on-going or unsettled )',
      '>3 ( More than 3 cases still on-going or unsettled )',
    ],
  },

  // _BlacklistCasesLiteral
  blacklist_cases: {
    type: 'dropdown',
    options: [
      '0 ( no blacklist issue )',
      '1 ( 1 blacklist issue )',
      '2 ( 2 blacklist issue )',
      '3 ( 3 blacklist issue )',
      '>3 ( More than 3 blacklist issue )',
    ],
  },
  guarantor_blacklist_case: {
    type: 'dropdown',
    options: [
      '0 ( no blacklist issue )',
      '1 ( 1 blacklist issue )',
      '2 ( 2 blacklist issue )',
      '3 ( 3 blacklist issue )',
      '>3 ( More than 3 blacklist issue )',
    ],
  },

  // _RepaymentLiteral
  repayment_to_banks: {
    type: 'dropdown',
    options: [
      'Satisfactory ( Prompt payment or occasionally lapsed 1 month )',
      'Moderate ( Consistently lapsed 1-2 months )',
      'Unsatisfactory ( Under SPA or consistently lapsed 2 months and above )',
      'N/A',
    ],
  },

  // _UtilisationBandLiteral
  total_facilities_limit_vs_outstanding_utilisation_pct: {
    type: 'dropdown',
    options: [
      '< 30%',
      '30% - 50%',
      '51% - 70%',
      '71% - 90%',
      '> 90%',
    ],
  },

  // bank_statement_end_month_balance_rm Literal
  bank_statement_end_month_balance_rm: {
    type: 'dropdown',
    options: [
      '> RM 500,000',
      'RM 200,001 - RM 500,000',
      'RM 50,001 - RM 200,000',
      'RM 10,001 - RM 50,000',
      '<= RM 10,000',
    ],
  },

  // turnover Literal (5-band dropdown, not a binary radio)
  turnover: {
    type: 'dropdown',
    options: [
      '> 1 Mil',
      '501K - 999K',
      '301K - 500K',
      '0 - 300K',
      'Negative or N/A ( Make loss company or Not available)',
    ],
  },

  // net_profit_loss Literal
  net_profit_loss: {
    type: 'dropdown',
    options: [
      'Profit ( > RM 500,000 )',
      'Profit ( RM 100,001 - RM 500,000 )',
      'Profit ( RM 1 - RM 100,000 )',
      'Break-even',
      'Loss',
    ],
  },

  // net_worth Literal
  net_worth: {
    type: 'dropdown',
    options: [
      '> RM 1 Mil',
      'RM 501K - RM 1 Mil',
      'RM 201K - RM 500K',
      'RM 1 - RM 200K',
      'Negative',
    ],
  },

  // current_ratio Literal
  current_ratio: {
    type: 'dropdown',
    options: [
      '> 2.00',
      '1.01 - 1.99',
      '< 1.00',
      'N/A',
    ],
  },

  // gearing_ratio Literal — preserves exact bracket/spacing from Pydantic model
  gearing_ratio: {
    type: 'dropdown',
    options: [
      '( 0 - 0.99 )',
      '( 1.00 - 1.99 )',
      '( 2.00 - 2.99 )',
      '( 3.00 - 3.99 )',
      '> 4.00',
      'Negative',
      'N/A',
    ],
  },

  // guarantor_range_age Literal
  guarantor_range_age: {
    type: 'dropdown',
    options: [
      'Below 40',
      '40 - 49',
      '50 - 59',
      '60 - 64',
      '65 - 69',
      '70 and above',
    ],
  },

  // years_in_business Literal
  years_in_business: {
    type: 'dropdown',
    options: [
      '> 10 Years',
      '7.1 - 10 Years',
      '5.1 - 7 Years',
      '2.1 - 5 Years',
      '< 2 Years',
    ],
  },

  // paid_up_capital_rm Literal
  paid_up_capital_rm: {
    type: 'dropdown',
    options: [
      '> RM 750K',
      'RM 301K - 750K',
      'RM 151K - 300K',
      'RM 2.01 - 150K',
      '< RM 2',
    ],
  },

  // years_in_relationship Literal (Existing Customers only)
  years_in_relationship: {
    type: 'dropdown',
    options: [
      '> 10 Years',
      '7.1 Years - 10 Years',
      '5.1 Years - 7 Years',
      '2.1 Years - 5 Years',
      '< 2 Years',
    ],
  },

  // ── Checkbox (multi-select) ───────────────────────────────────────────────
  nature_of_business_category: {
    type: 'checkbox',
    options: ['Trading', 'Manufacturing', 'Services', 'Construction', 'Agriculture', 'Others'],
  },
}

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

function scoreTheme(score) {
  if (score == null) return { color: '#94a3b8', bg: '#f8fafc', border: '#e2e8f0' }
  if (score >= 80)   return { color: '#16a34a', bg: '#f0fdf4', border: '#bbf7d0' }
  if (score >= 60)   return { color: '#ca8a04', bg: '#fefce8', border: '#fef08a' }
  if (score >= 40)   return { color: '#ea580c', bg: '#fff7ed', border: '#fed7aa' }
  return               { color: '#dc2626', bg: '#fef2f2', border: '#fecaca' }
}

function renderValue(value, fmt) {
  if (value === null || value === undefined) {
    return <span className="ctos-val ctos-val--null">—</span>
  }

  switch (fmt) {
    case 'currency': {
      const num = Number(value)
      // Band labels (e.g. '> RM 500,000') are stored as strings after dropdown edit
      if (isNaN(num)) return <span className="ctos-val">{String(value)}</span>
      const isNeg = num < 0
      const abs = Math.abs(num).toLocaleString('en-MY', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      })
      return (
        <span className={`ctos-val ctos-val--currency${isNeg ? ' ctos-val--neg' : ''}`}>
          {isNeg ? `(MYR ${abs})` : `MYR ${abs}`}
        </span>
      )
    }

    case 'score': {
      const num = Number(value)
      const theme = scoreTheme(num)
      return (
        <div className="ctos-score-wrap">
          <span
            className="ctos-score-chip"
            style={{ color: theme.color, background: theme.bg, borderColor: theme.border }}
          >
            {num.toFixed(0)}
          </span>
          <div className="ctos-score-bar">
            <div
              className="ctos-score-bar-fill"
              style={{ width: `${Math.max(0, Math.min(100, num))}%`, background: theme.color }}
            />
          </div>
        </div>
      )
    }

    case 'pct': {
      const num = Number(value)
      if (isNaN(num)) return <span className="ctos-val">{String(value)}</span>
      return <span className="ctos-val ctos-val--mono">{num.toFixed(1)}%</span>
    }

    case 'ratio': {
      const num = Number(value)
      if (isNaN(num)) return <span className="ctos-val">{String(value)}</span>
      return <span className="ctos-val ctos-val--mono">{num.toFixed(2)}&times;</span>
    }

    case 'years': {
      const n = Number(value)
      if (isNaN(n)) return <span className="ctos-val">{String(value)}</span>
      return <span className="ctos-val">{n} {n === 1 ? 'yr' : 'yrs'}</span>
    }

    case 'age':
      return <span className="ctos-val">{value} yrs old</span>

    case 'count':
      return <span className="ctos-val">{value}</span>

    case 'yesno': {
      const s = String(value).trim()
      const isYes = /^yes$/i.test(s)
      const isNo  = /^no$/i.test(s)
      if (isYes) return <span className="ctos-badge ctos-badge--yes">{s}</span>
      if (isNo)  return <span className="ctos-badge ctos-badge--no">{s}</span>
      return <span className="ctos-val">{s}</span>
    }

    default:
      return <span className="ctos-val">{String(value)}</span>
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Date helpers
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Convert any date value the AI might return (ISO string, "31 Dec 2022", etc.)
 * into the YYYY-MM-DD format required by <input type="date">.
 * Returns '' if the value cannot be parsed.
 */
function toDateInputValue(val) {
  if (!val) return ''
  const s = String(val).trim()
  // Already YYYY-MM-DD — pass straight through
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s
  const d = new Date(s)
  if (isNaN(d.getTime())) return ''
  const yyyy = d.getFullYear()
  const mm   = String(d.getMonth() + 1).padStart(2, '0')
  const dd   = String(d.getDate()).padStart(2, '0')
  return `${yyyy}-${mm}-${dd}`
}

// ─────────────────────────────────────────────────────────────────────────────
// EditableFieldCell
// ─────────────────────────────────────────────────────────────────────────────

function EditableFieldCell({ field, value, scoreLabel, isFull, isModified, isAiSuggested, onCommit, inputTypeConfig, scoreMap }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft]     = useState('')
  const inputRef              = useRef(null)

  // Score fields are AI-computed — not officer-editable
  const isReadOnly = field.fmt === 'score'

  // Deterministic score derived from the committed value via the active scoring matrix.
  // Backend scoreValue is intentionally ignored to prevent AI hallucination.
  const currentScore = scoreMap[field.key]?.[value]
  const hasScore     = currentScore !== undefined

  function buildScoreRight(score) {
    if (score === undefined) return null
    return (
      <div className="ctos-score-right">
        {scoreLabel && <span className="ctos-score-right-label">{scoreLabel}</span>}
        <span className="ctos-score-right-value">{score}</span>
      </div>
    )
  }
  const scoreRight = buildScoreRight(currentScore)

  useEffect(() => {
    if (editing && inputRef.current) {
      inputRef.current.focus()
      inputRef.current.select?.()
    }
  }, [editing])

  const isDateField = field.key.toLowerCase().includes('date')

  function startEdit() {
    if (isReadOnly) return
    if (inputTypeConfig?.type === 'checkbox') {
      // Initialise draft as an array by splitting the stored comma-separated string
      const existing = value
        ? (Array.isArray(value)
            ? value
            : String(value).split(',').map(s => s.trim()).filter(Boolean))
        : []
      setDraft(existing)
    } else if (isDateField) {
      setDraft(toDateInputValue(value))
    } else {
      setDraft(value == null ? '' : String(value))
    }
    setEditing(true)
  }

  function commitEdit() {
    setEditing(false)
    // Config-driven dropdowns always store the option label as a plain string
    if (inputTypeConfig?.type === 'dropdown') {
      onCommit(field.key, draft.trim() === '' ? null : draft.trim())
      return
    }
    const isNumeric = ['currency', 'pct', 'ratio', 'years', 'age', 'count'].includes(field.fmt)
    let parsed
    if (isNumeric) {
      const t = draft.trim()
      parsed = t === '' ? null : Number(t)
      if (isNaN(parsed)) parsed = null
    } else {
      parsed = draft.trim() === '' ? null : draft.trim()
    }
    onCommit(field.key, parsed)
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter')  commitEdit()
    if (e.key === 'Escape') setEditing(false)
  }

  // ── Edit mode ────────────────────────────────────────────────────────────
  if (editing) {
    const cfg       = inputTypeConfig
    const wrapClass = `ctos-field ctos-field--editing${isFull ? ' ctos-field--full' : ''}${hasScore ? ' ctos-field--has-score' : ''}`

    // ── Radio buttons ─────────────────────────────────────────────────────
    if (cfg?.type === 'radio') {
      return (
        <div className={wrapClass}>
          <div className="ctos-field-left">
            <span className="ctos-field-label">{field.label}</span>
            <div
              className="ctos-field-radio-group"
              onKeyDown={e => { if (e.key === 'Escape') setEditing(false) }}
              onBlur={e => { if (!e.currentTarget.contains(e.relatedTarget)) setEditing(false) }}
            >
              <div className="ctos-radio-options" role="radiogroup">
                {cfg.options.map(opt => (
                  <label key={opt} className="ctos-radio-label">
                    <input
                      type="radio"
                      name={`ctos-radio-${field.key}`}
                      value={opt}
                      checked={draft === opt}
                      onChange={() => { setEditing(false); onCommit(field.key, opt) }}
                      className="ctos-radio-input"
                    />
                    {opt}
                  </label>
                ))}
              </div>
            </div>
          </div>
          {scoreRight}
        </div>
      )
    }

    // ── Config-driven dropdown ────────────────────────────────────────────
    if (cfg?.type === 'dropdown') {
      // Derive score live from draft so it updates as the user picks an option
      const liveScore     = scoreMap[field.key]?.[draft]
      const hasLiveScore  = liveScore !== undefined
      const dropWrapClass = `ctos-field ctos-field--editing${isFull ? ' ctos-field--full' : ''}${hasLiveScore ? ' ctos-field--has-score' : ''}`
      return (
        <div className={dropWrapClass}>
          <div className="ctos-field-left">
            <span className="ctos-field-label">{field.label}</span>
            <div className="ctos-field-value">
              <select
                ref={inputRef}
                className="ctos-field-edit-select"
                value={draft}
                onChange={e => setDraft(e.target.value)}
                onBlur={commitEdit}
                onKeyDown={handleKeyDown}
              >
                <option value="">— Select —</option>
                {cfg.options.map(opt => (
                  <option key={opt} value={opt}>{opt}</option>
                ))}
              </select>
            </div>
          </div>
          {buildScoreRight(liveScore)}
        </div>
      )
    }

    // ── Checkbox (multi-select) ───────────────────────────────────────────
    if (cfg?.type === 'checkbox') {
      const selectedSet = new Set(Array.isArray(draft) ? draft : [])
      function commitCheckbox() {
        setEditing(false)
        // Preserve config order in the committed string
        const joined = cfg.options.filter(o => selectedSet.has(o)).join(', ')
        onCommit(field.key, joined || null)
      }
      return (
        <div className={wrapClass}>
          <div className="ctos-field-left">
            <span className="ctos-field-label">{field.label}</span>
            <div
              className="ctos-checkbox-group"
              tabIndex={-1}
              onBlur={e => { if (!e.currentTarget.contains(e.relatedTarget)) commitCheckbox() }}
            >
              {cfg.options.map(opt => (
                <label key={opt} className="ctos-checkbox-label">
                  <input
                    type="checkbox"
                    className="ctos-checkbox-input"
                    value={opt}
                    checked={selectedSet.has(opt)}
                    onChange={e => {
                      const next = new Set(selectedSet)
                      if (e.target.checked) next.add(opt)
                      else next.delete(opt)
                      setDraft([...next])
                    }}
                  />
                  {opt}
                </label>
              ))}
            </div>
          </div>
          {scoreRight}
        </div>
      )
    }

    // ── Legacy yesno fallback (no config entry) ───────────────────────────
    if (field.fmt === 'yesno') {
      return (
        <div className={wrapClass}>
          <div className="ctos-field-left">
            <span className="ctos-field-label">{field.label}</span>
            <div className="ctos-field-value">
              <select
                ref={inputRef}
                className="ctos-field-edit-select"
                value={draft}
                onChange={e => setDraft(e.target.value)}
                onBlur={commitEdit}
                onKeyDown={handleKeyDown}
              >
                <option value="">— Select —</option>
                <option value="Yes">Yes</option>
                <option value="No">No</option>
              </select>
            </div>
          </div>
          {scoreRight}
        </div>
      )
    }

    // ── Date picker ───────────────────────────────────────────────────────
    if (isDateField) {
      return (
        <div className={wrapClass}>
          <div className="ctos-field-left">
            <span className="ctos-field-label">{field.label}</span>
            <div className="ctos-field-value">
              <input
                ref={inputRef}
                type="date"
                className="ctos-field-edit-input"
                value={draft}
                onChange={e => setDraft(e.target.value)}
                onBlur={commitEdit}
                onKeyDown={handleKeyDown}
              />
            </div>
          </div>
          {scoreRight}
        </div>
      )
    }

    // ── Default: text / numeric <input> ───────────────────────────────────
    const isNumeric = ['currency', 'pct', 'ratio', 'years', 'age', 'count'].includes(field.fmt)
    return (
      <div className={wrapClass}>
        <div className="ctos-field-left">
          <span className="ctos-field-label">{field.label}</span>
          <div className="ctos-field-value">
            <input
              ref={inputRef}
              type={isNumeric ? 'number' : 'text'}
              className="ctos-field-edit-input"
              value={draft}
              onChange={e => setDraft(e.target.value)}
              onBlur={commitEdit}
              onKeyDown={handleKeyDown}
              placeholder={value == null ? 'Enter value…' : ''}
            />
          </div>
        </div>
        {scoreRight}
      </div>
    )
  }

  // ── Display mode ─────────────────────────────────────────────────────────
  const isEmpty = value === null || value === undefined
  const cellClass = [
    'ctos-field',
    isFull        ? 'ctos-field--full'     : '',
    !isReadOnly   ? 'ctos-field--editable' : '',
    isEmpty && !isReadOnly ? 'ctos-field--empty' : '',
    isModified    ? 'ctos-field--modified' : '',
    hasScore      ? 'ctos-field--has-score' : '',
  ].filter(Boolean).join(' ')

  return (
    <div
      className={cellClass}
      onClick={isReadOnly ? undefined : startEdit}
      title={isReadOnly ? 'AI-computed — not editable' : 'Click to edit'}
      role={isReadOnly ? undefined : 'button'}
      tabIndex={isReadOnly ? undefined : 0}
      onKeyDown={isReadOnly ? undefined : e => e.key === 'Enter' && startEdit()}
    >
      <div className="ctos-field-left">
        <span className="ctos-field-label">
          {field.label}
          {isModified && <span className="ctos-modified-dot" title="Edited by officer" />}
        </span>
        {isAiSuggested && (
          <span className="ctos-ai-badge" title="This value was auto-filled by the Chief Credit Officer AI. Click to override.">
            <Sparkles size={9} />
            Suggested by AI
          </span>
        )}
        <div className="ctos-field-value">
          {renderValue(value, field.fmt)}
          {!isReadOnly && (
            <span className="ctos-edit-hint" aria-hidden="true">
              <Pencil size={10} />
            </span>
          )}
        </div>
      </div>
      {scoreRight}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// SectionCard
// ─────────────────────────────────────────────────────────────────────────────

function SectionCard({ section, sectionData, allSectionData, onFieldCommit, modifiedKeys, scoreMap, aiSuggestedFields }) {
  // Derive section subtotal deterministically from the active scoreMap.
  // Backend subtotal fields (e.g. ccris_pct, financial_information_pct) are
  // intentionally ignored — the AI hallucinates them.
  const allFields    = section.rows.flat()
  const mappedFields = allFields.filter(f => f.key in scoreMap)

  const ownScore = mappedFields.reduce((sum, field) => {
    const score = scoreMap[field.key]?.[sectionData?.[field.key]]
    return score !== undefined ? sum + score : sum
  }, 0)

  // For sections linked to a guarantor profile array, average CCRIS scores
  // across all guarantors so the per-guarantor max stays consistent.
  const linkedProfiles = section.linkedArrayKey
    ? (allSectionData?.[section.linkedArrayKey] ?? [])
    : []

  const linkedArrayScore = (() => {
    if (!section.linkedArrayKey || linkedProfiles.length === 0) return 0
    const perGuarantor = linkedProfiles.map(profile =>
      GUARANTOR_SCORED_FIELDS.reduce((sum, { dataKey, scoreKey }) => {
        const score = scoreMap[scoreKey]?.[profile[dataKey]]
        return score !== undefined ? sum + score : sum
      }, 0)
    )
    return perGuarantor.reduce((a, b) => a + b, 0) / perGuarantor.length
  })()

  const displayScore = ownScore + linkedArrayScore

  const ownMax = mappedFields.reduce((total, field) => {
    const vals = Object.values(scoreMap[field.key] ?? {})
    return total + (vals.length ? Math.max(...vals) : 0)
  }, 0)

  // Use explicit maxScore override when the section aggregates multiple sub-sections
  const sectionMax = section.maxScore ?? ownMax

  const hasScore = mappedFields.length > 0 || !!section.linkedArrayKey

  const theme = hasScore ? scoreTheme(sectionMax > 0 ? (displayScore / sectionMax) * 100 : 0) : null

  return (
    <div className="ctos-section">
      {/* Section header */}
      <div className="ctos-section-hd">
        <div className="ctos-section-hd-left">
          <span className="ctos-section-num">{section.number}</span>
          <span className="ctos-section-icon" aria-hidden="true">{section.icon}</span>
          <span className="ctos-section-title">{section.title}</span>
        </div>

        {hasScore && (
          <div
            className="ctos-section-score"
            style={{ color: theme.color, background: theme.bg, borderColor: theme.border }}
            title={`Section score: ${displayScore} / ${sectionMax} pts`}
          >
            <span className="ctos-section-score-lbl">Score</span>
            <span className="ctos-section-score-val">{displayScore}</span>
            <span className="ctos-section-score-max">/ {sectionMax}</span>
          </div>
        )}
      </div>

      {/* Fields grid — score fields are folded into their paired data field as badges */}
      <div className="ctos-grid">
        {section.rows.flatMap((row, ri) => {
          const scoreField = row.find(f => f.fmt === 'score')
          const dataFields = row.filter(f => f.fmt !== 'score')
          return dataFields.map((field, ci) => {
            const isPaired = scoreField != null && ci === 0
            return (
              <EditableFieldCell
                key={`${ri}-${ci}`}
                field={field}
                value={sectionData?.[field.key]}
                isFull={dataFields.length === 1}
                scoreLabel={isPaired ? scoreField.label : undefined}
                isModified={modifiedKeys?.has(field.key)}
                isAiSuggested={!!aiSuggestedFields?.[field.key]}
                onCommit={onFieldCommit}
                inputTypeConfig={FIELD_INPUT_CONFIG[field.key]}
                scoreMap={scoreMap}
              />
            )
          })
        })}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// CtosDetailedExtraction — main export
// ─────────────────────────────────────────────────────────────────────────────

export default function CtosDetailedExtraction({ data, onDataChange, onResult, requestedAmount, decision }) {
  const [open, setOpen]               = useState(false)
  const [localData, setLocalData]     = useState(data)

  // Select the correct scoring matrix based on the ERP agent's determination.
  // Defaults to New Customer if the field is absent.
  const activeScoreMap = localData?.customer_type === 'Existing Customer'
    ? EXISTING_CUSTOMER_SCORE_MAP
    : NEW_CUSTOMER_SCORE_MAP
  const [modifiedPaths, setModifiedPaths] = useState(new Set())
  const [guarantorModifiedKeys, setGuarantorModifiedKeys] = useState({})

  // Recalculate state
  const [recalcLoading, setRecalcLoading] = useState(false)
  const [recalcError, setRecalcError]     = useState('')
  const [recalcSuccess, setRecalcSuccess] = useState(false)

  // Tracks which Section 12 fields were auto-filled by the AI decision.
  // Cleared per-field when the officer manually edits that field.
  const [aiSuggestedFields, setAiSuggestedFields] = useState({})

  // Always-current ref for localData — lets the decision effect read the latest
  // state without adding localData to its dependency array (which would loop).
  const localDataRef = useRef(localData)
  useEffect(() => { localDataRef.current = localData })

  // ── Helper: apply AI limit to proposed_credit_limit section ───────────────
  // Returns { mergedSection, suggested } where suggested lists the keys filled.
  function _applyAiLimit(currentSection, limit) {
    const updates  = {}
    const suggested = {}
    if (currentSection.proposed_credit_limit_rm == null) {
      updates.proposed_credit_limit_rm       = limit
      suggested.proposed_credit_limit_rm     = true
    }
    if (currentSection.total_credit_limit_per_account == null) {
      updates.total_credit_limit_per_account = limit
      suggested.total_credit_limit_per_account = true
    }
    return { updates, suggested }
  }

  // Sync when a fresh extraction arrives.
  // Also attempts to auto-fill Section 12 from the current decision if a limit
  // already exists (e.g. pipeline ran → extraction and decision arrive together).
  useEffect(() => {
    const limit   = decision?.proposed_credit_limit_myr
    const base    = data ?? null
    const current = base?.proposed_credit_limit ?? {}

    let merged   = base
    let suggested = {}

    if (base && limit) {
      const { updates, suggested: s } = _applyAiLimit(current, limit)
      if (Object.keys(updates).length) {
        merged    = { ...base, proposed_credit_limit: { ...current, ...updates } }
        suggested = s
      }
    }

    setLocalData(merged)
    setAiSuggestedFields(suggested)
    setModifiedPaths(new Set())
    setGuarantorModifiedKeys({})
    setRecalcError('')
    setRecalcSuccess(false)
  }, [data]) // eslint-disable-line react-hooks/exhaustive-deps

  // Fires when only the decision changes (e.g. "Update AI Credit Decision" button).
  // Reads localDataRef for the current live values so we never overwrite an
  // officer-edited field.
  useEffect(() => {
    const limit = decision?.proposed_credit_limit_myr
    if (!limit) return

    const snap    = localDataRef.current
    if (!snap) return

    const current = snap.proposed_credit_limit ?? {}
    const { updates, suggested } = _applyAiLimit(current, limit)
    if (!Object.keys(updates).length) return

    setLocalData(prev => {
      if (!prev) return prev
      const c = prev.proposed_credit_limit ?? {}
      const m = {}
      if (c.proposed_credit_limit_rm       == null) m.proposed_credit_limit_rm       = limit
      if (c.total_credit_limit_per_account == null) m.total_credit_limit_per_account = limit
      if (!Object.keys(m).length) return prev
      return { ...prev, proposed_credit_limit: { ...c, ...m } }
    })
    setAiSuggestedFields(prev => ({ ...prev, ...suggested }))
  }, [decision?.proposed_credit_limit_myr]) // eslint-disable-line react-hooks/exhaustive-deps

  // Resize guarantor_ccris_profiles whenever number_of_guarantor changes
  useEffect(() => {
    const raw = localData?.personal_guarantee?.number_of_guarantor
    const desired = parseInt(raw, 10)
    if (!localData || isNaN(desired) || desired < 0) return

    const current = localData.guarantor_ccris_profiles ?? []
    if (current.length === desired) return

    const resized = desired > current.length
      ? [...current, ...Array(desired - current.length).fill(null).map(() => ({}))]
      : current.slice(0, desired)

    const updated = { ...localData, guarantor_ccris_profiles: resized }
    setLocalData(updated)
    onDataChange?.(updated)
  }, [localData?.personal_guarantee?.number_of_guarantor]) // eslint-disable-line react-hooks/exhaustive-deps

  function handleFieldCommit(sectionKey, fieldKey, newValue) {
    const updated = {
      ...localData,
      [sectionKey]: { ...(localData?.[sectionKey] ?? {}), [fieldKey]: newValue },
    }
    setLocalData(updated)
    setModifiedPaths(prev => new Set([...prev, `${sectionKey}.${fieldKey}`]))
    // Clear AI suggestion badge when the officer manually edits the field
    if (aiSuggestedFields[fieldKey]) {
      setAiSuggestedFields(prev => { const n = { ...prev }; delete n[fieldKey]; return n })
    }
    onDataChange?.(updated)
  }

  function handleGuarantorFieldCommit(index, fieldKey, newValue) {
    const profiles = [...(localData?.guarantor_ccris_profiles ?? [])]
    profiles[index] = { ...(profiles[index] ?? {}), [fieldKey]: newValue }
    const updated = { ...localData, guarantor_ccris_profiles: profiles }
    setLocalData(updated)
    setGuarantorModifiedKeys(prev => ({
      ...prev,
      [index]: new Set([...(prev[index] ?? []), fieldKey]),
    }))
    onDataChange?.(updated)
  }

  async function handleRecalculate() {
    setRecalcLoading(true)
    setRecalcError('')
    setRecalcSuccess(false)
    try {
      const res = await axios.post(
        'http://localhost:8000/api/v1/recalculate-score',
        { form: localData, requested_amount: requestedAmount ?? 0 }
      )
      onResult?.(res.data)
      setModifiedPaths(new Set())
      setGuarantorModifiedKeys({})
      setRecalcSuccess(true)
      setTimeout(() => setRecalcSuccess(false), 4000)
    } catch (err) {
      setRecalcError(err.response?.data?.detail || err.message || 'Recalculation failed.')
    } finally {
      setRecalcLoading(false)
    }
  }

  const guarantorModifiedCount = Object.values(guarantorModifiedKeys).reduce((n, s) => n + s.size, 0)
  const modifiedCount = modifiedPaths.size + guarantorModifiedCount

  return (
    <div className="ctos-accordion">
      {/* Trigger */}
      <button
        type="button"
        className={`ctos-trigger${open ? ' ctos-trigger--open' : ''}`}
        onClick={() => setOpen(v => !v)}
        aria-expanded={open}
        aria-controls="ctos-body"
      >
        <div className="ctos-trigger-left">
          <ScanSearch size={17} className="ctos-trigger-icon" aria-hidden="true" />
          <div className="ctos-trigger-text">
            <span className="ctos-trigger-title">Extracted CTOS Form Data</span>
            <span className="ctos-trigger-sub">
              12 sections · AI-extracted · Click any field to edit
            </span>
          </div>
        </div>

        <div className="ctos-trigger-right">
          {modifiedCount > 0 && (
            <span className="ctos-trigger-badge ctos-trigger-badge--modified">
              {modifiedCount} edited
            </span>
          )}
          {localData && modifiedCount === 0 && (
            <span className="ctos-trigger-badge">{SECTIONS.length} sections</span>
          )}
          <ChevronDown
            size={19}
            className={`ctos-chevron${open ? ' ctos-chevron--open' : ''}`}
            aria-hidden="true"
          />
        </div>
      </button>

      {/* Animated body */}
      <div
        id="ctos-body"
        className={`ctos-body${open ? ' ctos-body--open' : ''}`}
        role="region"
        aria-labelledby="ctos-trigger"
      >
        <div className="ctos-body-inner">
          {!localData ? (
            <div className="ctos-empty">
              <ScanSearch size={32} className="ctos-empty-icon" />
              <p className="ctos-empty-title">No extraction data available</p>
              <p className="ctos-empty-sub">
                The CTOS extraction did not return data for this application.
              </p>
            </div>
          ) : (
            <div className="ctos-sections">
              <div className="ctos-edit-notice">
                <Pencil size={11} />
                <span>
                  AI-extracted data — click any field to correct or complete missing values.
                  Score fields (coloured chips) are AI-computed and read-only.
                </span>
                {localData?.customer_type && (
                  <span
                    className="ctos-customer-type-badge"
                    style={{
                      marginLeft: '10px',
                      padding: '2px 8px',
                      borderRadius: '4px',
                      fontSize: '11px',
                      fontWeight: 600,
                      background: localData.customer_type === 'Existing Customer' ? '#eff6ff' : '#f0fdf4',
                      color:      localData.customer_type === 'Existing Customer' ? '#1d4ed8' : '#15803d',
                      border:     `1px solid ${localData.customer_type === 'Existing Customer' ? '#bfdbfe' : '#bbf7d0'}`,
                    }}
                  >
                    {localData.customer_type === 'Existing Customer' ? 'Existing Customer Matrix (20% PG)' : 'New Customer Matrix (30% PG)'}
                  </span>
                )}
              </div>

              {/* ── Sections up to and including Personal Guarantee (8) ── */}
              {SECTIONS.filter(s =>
                SECTIONS.indexOf(s) <= SECTIONS.findIndex(x => x.key === 'personal_guarantee')
              ).map(s => (
                <SectionCard
                  key={s.key}
                  section={s}
                  sectionData={localData[s.key]}
                  allSectionData={localData}
                  onFieldCommit={(fieldKey, newValue) =>
                    handleFieldCommit(s.key, fieldKey, newValue)
                  }
                  modifiedKeys={
                    new Set(
                      [...modifiedPaths]
                        .filter(p => p.startsWith(`${s.key}.`))
                        .map(p => p.slice(s.key.length + 1))
                    )
                  }
                  scoreMap={activeScoreMap}
                  aiSuggestedFields={aiSuggestedFields}
                />
              ))}

              {/* ── Dynamic guarantor sections (one per guarantor, Section 9.x) ── */}
              {(localData.guarantor_ccris_profiles ?? []).map((guarantor, i) => {
                const name = guarantor?.guarantor_info_pg
                const syntheticSection = {
                  key: `guarantor_${i}`,
                  number: `9.${i + 1}`,
                  title: `CCRIS for Guarantor No. ${i + 1}${name ? ` — ${name}` : ''}`,
                  icon: <Shield size={14} />,
                  scoreKey: null,
                  rows: GUARANTOR_PROFILE_ROWS,
                }
                return (
                  <SectionCard
                    key={`guarantor-${i}`}
                    section={syntheticSection}
                    sectionData={guarantor}
                    allSectionData={localData}
                    onFieldCommit={(fieldKey, newValue) =>
                      handleGuarantorFieldCommit(i, fieldKey, newValue)
                    }
                    modifiedKeys={guarantorModifiedKeys[i] ?? new Set()}
                    scoreMap={activeScoreMap}
                    aiSuggestedFields={aiSuggestedFields}
                  />
                )
              })}

              {/* ── Remaining sections from Company Background (10) onward ── */}
              {SECTIONS.filter(s =>
                SECTIONS.indexOf(s) > SECTIONS.findIndex(x => x.key === 'personal_guarantee')
              ).map(s => (
                <SectionCard
                  key={s.key}
                  section={s}
                  sectionData={localData[s.key]}
                  allSectionData={localData}
                  onFieldCommit={(fieldKey, newValue) =>
                    handleFieldCommit(s.key, fieldKey, newValue)
                  }
                  modifiedKeys={
                    new Set(
                      [...modifiedPaths]
                        .filter(p => p.startsWith(`${s.key}.`))
                        .map(p => p.slice(s.key.length + 1))
                    )
                  }
                  scoreMap={activeScoreMap}
                  aiSuggestedFields={aiSuggestedFields}
                />
              ))}

              {/* ── Update AI Credit Decision bar ───────────────────── */}
              <div className="ctos-recalc-bar">
                <div className="ctos-recalc-feedback">
                  {recalcError && (
                    <span className="ctos-recalc-msg ctos-recalc-msg--error">
                      {recalcError}
                    </span>
                  )}
                  {recalcSuccess && (
                    <span className="ctos-recalc-msg ctos-recalc-msg--success">
                      <CheckCircle size={13} />
                      AI decision updated — narrative, limit &amp; recommendation refreshed.
                    </span>
                  )}
                </div>
                <div className="ctos-recalc-btn-group">
                  <button
                    type="button"
                    className={`ctos-recalc-btn${modifiedCount > 0 ? ' ctos-recalc-btn--highlight' : ''}`}
                    disabled={recalcLoading}
                    onClick={handleRecalculate}
                    title="Sends your corrected form data to the Chief Credit Officer AI to regenerate the narrative, credit limit recommendation, and approval decision. Mathematical scores update instantly as you edit."
                  >
                    {recalcLoading ? (
                      <><Loader2 size={15} className="spin" />Updating AI Decision…</>
                    ) : (
                      <>
                        <RefreshCw size={15} />
                        Update AI Credit Decision
                        {modifiedCount > 0 && (
                          <span className="ctos-recalc-badge">{modifiedCount} change{modifiedCount !== 1 ? 's' : ''}</span>
                        )}
                      </>
                    )}
                  </button>
                  <span className="ctos-recalc-hint">
                    Updates AI narrative, credit limit &amp; recommendation from your corrected inputs.
                    Scores update instantly.
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
