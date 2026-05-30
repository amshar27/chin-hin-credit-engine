import { useState, useEffect, useRef } from 'react'
import axios from 'axios'
import {
  FileText, Upload, CheckCircle, AlertTriangle, DollarSign,
  Loader2, Building2, ChevronRight, ShieldAlert, XCircle,
  ClipboardCheck, TrendingUp, BarChart2, BookOpen, UserCheck,
  MessageCircle,
} from 'lucide-react'
import './App.css'
import CtosDetailedExtraction from './components/CtosDetailedExtraction'
import DataCopilot from './components/DataCopilot'
import WelcomePage from './components/WelcomePage'
import { calculateFinalScores } from './utils/scoreMapping'

// ---------------------------------------------------------------------------
// Pure helpers
// ---------------------------------------------------------------------------

function getRecommendationConfig(recommendation) {
  switch (recommendation) {
    case 'APPROVE':
      return { className: 'badge badge-approve', icon: <CheckCircle size={20} />, label: 'APPROVED' }
    case 'REJECT':
      return { className: 'badge badge-reject', icon: <XCircle size={20} />, label: 'REJECTED' }
    case 'MANUAL_REVIEW':
      return { className: 'badge badge-review', icon: <AlertTriangle size={20} />, label: 'MANUAL REVIEW' }
    default:
      return { className: 'badge badge-review', icon: <AlertTriangle size={20} />, label: recommendation }
  }
}

function getRiskTierClass(riskGrade) {
  if (!riskGrade) return ''
  const g = riskGrade.toLowerCase()
  if (g.includes('extremely high')) return 'risk-extremely-high'
  if (g.includes('high'))           return 'risk-high'
  if (g.includes('medium'))         return 'risk-medium'
  if (g.includes('moderate'))       return 'risk-moderate'
  if (g.includes('low'))            return 'risk-low'
  return ''
}

function getScoreBarClass(score) {
  if (score >= 81) return 'score-bar-fill--high'
  if (score >= 61) return 'score-bar-fill--moderate'
  if (score >= 41) return 'score-bar-fill--medium'
  return 'score-bar-fill--low'
}

function formatCurrency(amount) {
  if (amount == null) return 'N/A'
  return `MYR ${Number(amount).toLocaleString('en-MY')}`
}

function formatNumber(n) {
  if (n == null) return '—'
  return Number(n).toLocaleString('en-MY')
}

function getLoadingLabel(pct) {
  if (pct < 20) return 'Extracting CTOS Data...'
  if (pct < 50) return 'Analyzing Financials & Bank Statements...'
  if (pct < 90) return 'Chief Credit Officer evaluating...'
  return 'Finalizing decision...'
}

function extractHighRiskFlags(result) {
  const flags = []
  if (result.status_code_k)
    flags.push('Status Code K detected — Applicant is under AKPK / Debt Management Counselling.')
  if (result.status_code_10)
    flags.push('Status Code 10 detected — Summons Filed against applicant.')
  if (result.special_attention_accounts)
    flags.push('Special Attention Account (SAA / Pink Highlight) detected.')
  if (result.has_director_above_70) {
    const names = Array.isArray(result.directors_above_70) && result.directors_above_70.length
      ? result.directors_above_70.join(', ')
      : 'one or more directors'
    flags.push(`Director/Guarantor Age ≥ 70 flagged: ${names} — Non-Actionable for Legal Recovery.`)
  }
  return flags
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ScoreBar({ score }) {
  const isNA = score === null || score === undefined
  const pct = isNA ? 0 : Math.max(0, Math.min(100, score))
  const fillClass = isNA ? '' : getScoreBarClass(pct)
  return (
    <div className="score-bar-section">
      <div className="score-bar-header">
        <span className="score-bar-label">Final Credit Score</span>
        <span className="score-bar-value">
          {isNA
            ? <span style={{ color: '#9ca3af', fontStyle: 'italic' }}>N/A — Missing Data</span>
            : <>{pct}<span className="score-bar-max">/100</span></>}
        </span>
      </div>
      <div className="score-bar-track">
        <div className={`score-bar-fill ${fillClass}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

// Hardcoded row definitions — scoreKey maps to the calculateFinalScores return object.
const RESULT_ROWS = [
  { label: 'CCRIS for Company',               weightage: '25%', scoreKey: 'ccris_company' },
  { label: 'Financial Information',            weightage: '25%', scoreKey: 'financial_info' },
  { label: 'Trade Reference/ Group Exposure',  weightage: '10%', scoreKey: 'internal_info' },
  { label: 'PG/ CG/ BG (Personal CCRIS)',     weightage: '30%', scoreKey: 'guarantees' },
  { label: 'Company Background',               weightage: '10%', scoreKey: 'company_background' },
]

function ResultTable({ scores, finalScore }) {
  const cellStyle   = { border: '1px solid #ddd', padding: '10px', textAlign: 'center' }
  const headerStyle = { ...cellStyle, fontWeight: 'bold', background: '#f5f5f5' }

  return (
    <div className="results-section">
      <h3 className="results-section-title">
        <BarChart2 size={14} style={{ display: 'inline', marginRight: '0.35rem', verticalAlign: 'middle' }} />
        Result
      </h3>
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr>
            <th style={headerStyle}>Categories</th>
            <th style={headerStyle}>Weightage</th>
            <th style={headerStyle}>Current Score (%)</th>
          </tr>
        </thead>
        <tbody>
          {RESULT_ROWS.map(row => (
            <tr key={row.label}>
              <td style={cellStyle}>{row.label}</td>
              <td style={cellStyle}>{row.weightage}</td>
              <td style={cellStyle}>{scores?.[row.scoreKey] ?? '—'}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr style={{ fontWeight: 'bold' }}>
            <td style={cellStyle}>Total</td>
            <td style={cellStyle}>100%</td>
            <td style={cellStyle}>{finalScore != null ? finalScore : <span style={{ color: '#9ca3af', fontStyle: 'italic' }}>N/A</span>}</td>
          </tr>
        </tfoot>
      </table>
    </div>
  )
}

const CREDIT_MATRIX_ROWS = [
  { min: 81, max: 100, range: '81 - 100', creditRating: 'Extremely Strong', riskGrade: 'Low Risk — Approve',                        pod: '0% - 5%'     },
  { min: 61, max: 80,  range: '61 - 80',  creditRating: 'Strong',           riskGrade: 'Moderate Risk — Approve with Conditions',    pod: '5.1% - 15%'  },
  { min: 41, max: 60,  range: '41 - 60',  creditRating: 'Average',          riskGrade: 'Medium Risk — Manual Review Required',       pod: '15.1% - 30%' },
  { min: 21, max: 40,  range: '21 - 40',  creditRating: 'Weak',             riskGrade: 'High Risk — Reject',                        pod: '30.1% - 60%' },
  { min: 0,  max: 20,  range: '0 - 20',   creditRating: 'Very Weak',        riskGrade: 'Extremely High Risk — Reject Immediately',   pod: '> 60%'       },
]

function CreditRatingMatrix({ finalScore }) {
  const cellStyle   = { border: '1px solid #ddd', padding: '10px', textAlign: 'center' }
  const headerStyle = { ...cellStyle, fontWeight: 'bold', background: '#f5f5f5' }
  return (
    <div className="results-section">
      <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: '20px' }}>
        <thead>
          <tr>
            <th style={headerStyle} colSpan={2}>Credit Scoring</th>
            <th style={headerStyle}>Credit Rating &amp; Risk Grade</th>
            <th style={headerStyle}>Probability of Default %</th>
          </tr>
        </thead>
        <tbody>
          {CREDIT_MATRIX_ROWS.map((row) => {
            const isActive = finalScore != null && finalScore >= row.min && finalScore <= row.max
            return (
              <tr key={row.range} style={isActive ? { backgroundColor: 'yellow' } : {}}>
                <td style={cellStyle}>{row.range}</td>
                <td style={cellStyle}>{row.creditRating}</td>
                <td style={cellStyle}>{row.riskGrade}</td>
                <td style={cellStyle}>{row.pod}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function FinancialTrendTable({ trend }) {
  if (!Array.isArray(trend) || trend.length === 0) return null
  const hasCR = trend.some(r => r.current_ratio != null)
  return (
    <div className="results-section">
      <h3 className="results-section-title">
        <TrendingUp size={14} style={{ display: 'inline', marginRight: '0.35rem', verticalAlign: 'middle' }} />
        5-Year Financial Trend
      </h3>
      <div className="trend-table-wrapper">
        <table className="trend-table">
          <thead>
            <tr>
              <th>Year</th>
              <th>Turnover (MYR)</th>
              <th>Net Profit (MYR)</th>
              <th>Working Capital (MYR)</th>
              {hasCR && <th>Current Ratio</th>}
              <th>Gearing Ratio</th>
            </tr>
          </thead>
          <tbody>
            {trend.map((row, i) => (
              <tr key={i}>
                <td className="trend-year">{row.year || '—'}</td>
                <td>{row.revenue_myr != null ? formatNumber(row.revenue_myr) : '—'}</td>
                <td className={row.net_profit_myr != null && row.net_profit_myr < 0 ? 'trend-negative' : ''}>
                  {row.net_profit_myr != null ? formatNumber(row.net_profit_myr) : '—'}
                </td>
                <td className={row.working_capital_myr != null && row.working_capital_myr < 0 ? 'trend-negative' : ''}>
                  {row.working_capital_myr != null ? formatNumber(row.working_capital_myr) : '—'}
                </td>
                {hasCR && (
                  <td>{row.current_ratio != null ? Number(row.current_ratio).toFixed(2) : '—'}</td>
                )}
                <td>{row.gearing_ratio != null ? Number(row.gearing_ratio).toFixed(2) : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

function App() {
  // ── Welcome gate ──────────────────────────────────────────────────────────
  const [hasStarted, setHasStarted] = useState(false)

  // ── Form state ────────────────────────────────────────────────────────────
  const [regNo, setRegNo]                     = useState('')
  const [requestedAmount, setRequestedAmount] = useState('')
  const [ctosFile, setCtosFile]               = useState(null)
  const [bankFile, setBankFile]               = useState(null)
  const [pdpaConsent, setPdpaConsent]         = useState(false)
  const [isLoading, setIsLoading]             = useState(false)
  const [result, setResult]                   = useState(null)
  const [ctosFormData, setCtosFormData]       = useState(null)
  const [error, setError]                     = useState('')

  // ── Loading progress state ────────────────────────────────────────────────
  const [loadingProgress, setLoadingProgress] = useState(0)
  const [loadingLabel, setLoadingLabel]       = useState('')
  const progressRef                           = useRef(0)
  const intervalRef                           = useRef(null)

  // ── Officer decision state ────────────────────────────────────────────────
  const [humanDecision, setHumanDecision]           = useState(null)
  const [officerName, setOfficerName]               = useState('')
  const [officerStaffId, setOfficerStaffId]         = useState('')
  const [officerDesignation, setOfficerDesignation] = useState('Branch Credit Officer')
  const [overrideCreditLimit, setOverrideCreditLimit] = useState('')
  const [decisionRemarks, setDecisionRemarks]       = useState('')
  const [decisionSubmitted, setDecisionSubmitted]   = useState(false)
  const [submittedAt, setSubmittedAt]               = useState(null)
  const [decisionRef, setDecisionRef]               = useState('')

  // ── Sidebar state ──────────────────────────────────────────────────────────
  const [copilotWidth, setCopilotWidth]             = useState(400)
  const [isDragging, setIsDragging]                 = useState(false)
  const [isCopilotMinimized, setIsCopilotMinimized] = useState(false)
  const mainPanelRef  = useRef(null)
  const pendingScroll = useRef(null)

  useEffect(() => {
    if (!isDragging) return
    const onMove = (e) => {
      const w = window.innerWidth - e.clientX
      setCopilotWidth(Math.min(800, Math.max(300, w)))
    }
    const onUp = () => setIsDragging(false)
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [isDragging])

  // Restore scroll position after sidebar layout toggle
  useEffect(() => {
    if (pendingScroll.current == null) return
    const scrollTop = pendingScroll.current
    pendingScroll.current = null

    requestAnimationFrame(() => {
      if (isCopilotMinimized) {
        // Sidebar just closed — transfer panel scroll → document scroll
        window.scrollTo(0, scrollTop)
      } else {
        // Sidebar just opened — transfer document scroll → panel scroll
        if (mainPanelRef.current) mainPanelRef.current.scrollTop = scrollTop
      }
    })
  }, [isCopilotMinimized])

  const handleCopilotMinimize = () => {
    pendingScroll.current = mainPanelRef.current?.scrollTop || 0
    setIsCopilotMinimized(true)
  }

  const handleCopilotExpand = (e) => {
    e.preventDefault()
    e.stopPropagation()
    pendingScroll.current = window.scrollY || document.documentElement.scrollTop
    setIsCopilotMinimized(false)
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setResult(null)
    setCtosFormData(null)
    // reset officer decision
    setHumanDecision(null)
    setOfficerName('')
    setOfficerStaffId('')
    setOfficerDesignation('Branch Credit Officer')
    setOverrideCreditLimit('')
    setDecisionRemarks('')
    setDecisionSubmitted(false)
    setSubmittedAt(null)
    setDecisionRef('')
    // reset progress
    progressRef.current = 0
    setLoadingProgress(0)
    setLoadingLabel('Extracting CTOS Data...')
    setIsLoading(true)

    const formData = new FormData()
    if (regNo.trim()) formData.append('company_reg_no', regNo.trim())
    formData.append('requested_amount', requestedAmount ? String(parseFloat(requestedAmount)) : '0')
    formData.append('ctos_pdf', ctosFile)
    if (bankFile) formData.append('bank_statement_pdf', bankFile)

    const extractFormData = new FormData()
    extractFormData.append('ctos_pdf', ctosFile)
    if (bankFile) extractFormData.append('bank_statement_pdf', bankFile)

    try {
      const [decisionRes, extractRes] = await Promise.allSettled([
        axios.post(
          'http://localhost:8000/api/v1/process-credit-application',
          formData,
          { headers: { 'Content-Type': 'multipart/form-data' } }
        ),
        axios.post(
          'http://localhost:8000/api/v1/extract-credit-scoring-form',
          extractFormData,
          { headers: { 'Content-Type': 'multipart/form-data' } }
        ),
      ])

      // API resolved — snap progress to 100%
      if (intervalRef.current) { clearInterval(intervalRef.current); intervalRef.current = null }
      setLoadingProgress(100)
      setLoadingLabel('Complete!')

      if (decisionRes.status === 'fulfilled') {
        setResult(decisionRes.value.data)
      } else {
        throw decisionRes.reason
      }

      if (extractRes.status === 'fulfilled') {
        setCtosFormData(extractRes.value.data)
      }

      // Brief pause so the user sees 100% before the dashboard reveals
      await new Promise(r => setTimeout(r, 500))
    } catch (err) {
      if (intervalRef.current) { clearInterval(intervalRef.current); intervalRef.current = null }

      // Document validation rejection (HTTP 400) — do NOT populate formData
      if (err.response?.status === 400) {
        setError(
          'Upload Rejected: ' +
          (err.response.data?.detail || 'Please ensure you are uploading a valid CTOS credit report PDF.')
        )
      } else {
        setError(err.response?.data?.detail || err.message || 'An unexpected error occurred.')
      }
    } finally {
      setIsLoading(false)
    }
  }

  // Simulate progress while loading; pauses at 90% until API resolves
  useEffect(() => {
    if (!isLoading) return
    intervalRef.current = setInterval(() => {
      const curr = progressRef.current
      if (curr >= 90) return
      const step = curr < 20 ? 2.5 : curr < 50 ? 0.8 : curr < 85 ? 0.35 : 0.1
      const next = Math.min(90, curr + step)
      progressRef.current = next
      setLoadingProgress(next)
      setLoadingLabel(getLoadingLabel(next))
    }, 200)
    return () => { if (intervalRef.current) clearInterval(intervalRef.current) }
  }, [isLoading])

  const handleReset = () => {
    setResult(null)
    setCtosFormData(null)
    setRegNo('')
    setRequestedAmount('')
    setCtosFile(null)
    setBankFile(null)
    setError('')
    setPdpaConsent(false)
    setHumanDecision(null)
    setOfficerName('')
    setOfficerStaffId('')
    setOfficerDesignation('Branch Credit Officer')
    setOverrideCreditLimit('')
    setDecisionRemarks('')
    setDecisionSubmitted(false)
    setSubmittedAt(null)
    setDecisionRef('')
  }

  const handleDecisionSubmit = () => {
    const now     = new Date()
    const dateStr = now.toISOString().slice(0, 10).replace(/-/g, '')
    const seq     = String(Math.floor(Math.random() * 9000) + 1000)
    setDecisionRef(`CH-${dateStr}-${seq}`)
    setDecisionSubmitted(true)
    setSubmittedAt(now)
  }

  const canSubmitDecision =
    humanDecision &&
    officerName.trim() &&
    officerStaffId.trim() &&
    !(humanDecision === 'REJECTED' && !decisionRemarks.trim())

  if (!hasStarted) {
    return <WelcomePage onStart={() => setHasStarted(true)} />
  }

  const hasSidebar = !!ctosFormData && !isCopilotMinimized

  return (
    <>
    <div
      className={`app-container app-fadein${hasSidebar ? ' app-with-sidebar' : ''}`}
      style={isDragging ? { userSelect: 'none', cursor: 'col-resize' } : undefined}
    >
      <div className="app-main-panel" ref={mainPanelRef}>
      {/* Header */}
      <header className="app-header">
        <div className="header-inner">
          <div className="header-brand">
            <Building2 size={28} className="header-icon" />
            <div>
              <h1 className="header-title">Chin Hin Credit Engine</h1>
              <p className="header-subtitle">AI-Powered Credit Decision Platform</p>
            </div>
          </div>
        </div>
      </header>

      <main className="main-content">
        {/* ---------------------------------------------------------------- */}
        {/* Form Card                                                         */}
        {/* ---------------------------------------------------------------- */}
        <div className="card form-card">
          <div className="card-header">
            <FileText size={20} className="card-header-icon" />
            <h2 className="card-title">New Credit Application</h2>
          </div>

          <form onSubmit={handleSubmit} className="application-form">
            <div className="form-row">
              <div className="form-group">
                <label className="form-label" htmlFor="regNo">
                  Company Registration No.{' '}
                  <span className="optional">Optional – Auto-extracted from CTOS</span>
                </label>
                <input
                  id="regNo"
                  type="text"
                  className="form-input"
                  placeholder="e.g., 202301012345 (leave blank to auto-detect)"
                  value={regNo}
                  onChange={(e) => setRegNo(e.target.value)}
                />
              </div>

              <div className="form-group">
                <label className="form-label" htmlFor="requestedAmount">
                  Requested Credit Limit (MYR) <span className="optional">Optional</span>
                </label>
                <input
                  id="requestedAmount"
                  type="number"
                  min="0"
                  step="1000"
                  className="form-input"
                  placeholder="e.g., 250000"
                  value={requestedAmount}
                  onChange={(e) => setRequestedAmount(e.target.value)}
                />
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label className="form-label" htmlFor="ctosFile">
                  CTOS Report (PDF) <span className="required">*</span>
                </label>
                <div className={`file-input-wrapper ${ctosFile ? 'has-file' : ''}`}>
                  <label htmlFor="ctosFile" className="file-input-label">
                    <Upload size={16} />
                    <span>{ctosFile ? ctosFile.name : 'Click to upload CTOS PDF'}</span>
                  </label>
                  <input
                    id="ctosFile"
                    type="file"
                    accept=".pdf"
                    className="file-input-hidden"
                    onChange={(e) => setCtosFile(e.target.files[0] || null)}
                    required
                  />
                </div>
              </div>

              <div className="form-group">
                <label className="form-label" htmlFor="bankFile">
                  Bank Statement (PDF) <span className="optional">Optional</span>
                </label>
                <div className={`file-input-wrapper ${bankFile ? 'has-file' : ''}`}>
                  <label htmlFor="bankFile" className="file-input-label">
                    <Upload size={16} />
                    <span>{bankFile ? bankFile.name : 'Click to upload Bank Statement'}</span>
                  </label>
                  <input
                    id="bankFile"
                    type="file"
                    accept=".pdf"
                    className="file-input-hidden"
                    onChange={(e) => setBankFile(e.target.files[0] || null)}
                  />
                </div>
              </div>
            </div>

            <div className="pdpa-consent-group">
              <label className="pdpa-consent-label">
                <input
                  type="checkbox"
                  className="pdpa-checkbox"
                  checked={pdpaConsent}
                  onChange={(e) => setPdpaConsent(e.target.checked)}
                  required
                />
                <span>
                  I confirm that explicit customer consent has been obtained under the{' '}
                  <strong>Personal Data Protection Act (PDPA)</strong> for this credit assessment.
                </span>
              </label>
            </div>

            {error && (
              <div className="error-box">
                <AlertTriangle size={16} />
                <span>{error}</span>
              </div>
            )}

            {isLoading ? (
              <div className="loading-progress-panel">
                <div className="loading-progress-label-row">
                  <Loader2 size={15} className="spin loading-progress-icon" />
                  <span className="loading-progress-label-text">{loadingLabel}</span>
                  <span className="loading-progress-pct">
                    {loadingProgress === 100 ? '100' : Math.floor(loadingProgress)}%
                  </span>
                </div>
                <div className="loading-bar-track">
                  <div
                    className={`loading-bar-fill${loadingProgress === 100 ? ' loading-bar-fill--complete' : ''}`}
                    style={{ width: `${loadingProgress}%` }}
                  />
                </div>
              </div>
            ) : (
              <button
                type="submit"
                className="submit-btn"
                disabled={!pdpaConsent}
              >
                <ChevronRight size={18} />Submit Application
              </button>
            )}
          </form>
        </div>

        {/* ---------------------------------------------------------------- */}
        {/* Results Card — Digital Credit Scoring Form + Data Copilot         */}
        {/* ---------------------------------------------------------------- */}
        {result && (() => {
          const recConfig     = getRecommendationConfig(result.recommendation)
          const riskClass     = getRiskTierClass(result.risk_grade)
          const highRiskFlags = extractHighRiskFlags(result)
          const narrative       = result.credit_narrative_summary || result.raw_agent_summary || ''
          const computedScores = calculateFinalScores(ctosFormData, ctosFormData?.customer_type)
          // Kill switch: if sanity check returned null, force score to null.
          // Only fall back to the AI's final_score when computation ran but yielded no total.
          const score = computedScores === null
            ? null
            : (computedScores.total ?? result.final_score ?? null)
          const scoreIsInvalid = score === null
          const trend          = result.financial_trend || []
          const aiLimit        = result.proposed_credit_limit_myr

          return (
            <div className="card results-card">
              <div className="card-header">
                <DollarSign size={20} className="card-header-icon" />
                <h2 className="card-title">Digital Credit Scoring Form</h2>
              </div>

              {/* AI Recommendation Badge */}
              <div className="decision-hero">
                <div className={recConfig.className}>
                  {recConfig.icon}
                  <span>{recConfig.label}</span>
                </div>
              </div>

              {/* Company Reg No */}
              {result.company_reg_no && (
                <div className="company-reg-row">
                  <span className="company-reg-label">Company Reg No.</span>
                  <span className="company-reg-value">{result.company_reg_no}</span>
                </div>
              )}

              {/* Score Bar */}
              <div className="score-bar-wrapper">
                <ScoreBar score={score} />
              </div>

              {/* Key Metrics Grid */}
              <div className="metrics-grid metrics-grid--3">
                <div className="metric-card">
                  <p className="metric-label">Risk Grade</p>
                  <p className={`metric-value metric-risk ${scoreIsInvalid ? '' : riskClass}`}>
                    {scoreIsInvalid ? 'Pending Data' : (result.risk_grade || 'N/A')}
                  </p>
                </div>
                <div className="metric-card">
                  <p className="metric-label">Proposed Credit Limit</p>
                  <p className="metric-value metric-currency">
                    {formatCurrency(aiLimit)}
                  </p>
                </div>
                <div className="metric-card">
                  <p className="metric-label">Guarantee Type</p>
                  <p className={`metric-value metric-guarantee ${result.guarantee_type === 'Limited' ? 'guarantee-limited' : 'guarantee-unlimited'}`}>
                    {result.guarantee_type || 'N/A'}
                  </p>
                </div>
              </div>

              {/* Limit vs Requested Assessment */}
              {result.limit_vs_requested_assessment && (
                <div className="limit-assessment-row">
                  <span className="limit-assessment-icon">⇄</span>
                  <span className="limit-assessment-text">{result.limit_vs_requested_assessment}</span>
                </div>
              )}

              <div className="results-body">
                {/* High Risk Flags */}
                {highRiskFlags.length > 0 && (
                  <div className="high-risk-flags-box">
                    <div className="high-risk-flags-header">
                      <ShieldAlert size={16} />
                      <span>High Risk Flags Detected</span>
                    </div>
                    <ul className="high-risk-flags-list">
                      {highRiskFlags.map((flag, i) => (
                        <li key={i} className="high-risk-flag-item">{flag}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Result Table */}
                <ResultTable scores={computedScores} finalScore={score} />

                {/* Credit Rating & Risk Grade Matrix */}
                <CreditRatingMatrix finalScore={score} />

                {/* 5-Year Financial Trend */}
                <FinancialTrendTable trend={trend} />

                {/* Key Reasons */}
                {result.key_reasons && result.key_reasons.length > 0 && (
                  <div className="results-section">
                    <h3 className="results-section-title">Key Reasons</h3>
                    <ul className="bullet-list">
                      {result.key_reasons.map((reason, i) => (
                        <li key={i} className="bullet-item">
                          <span className="bullet-dot" />
                          {reason}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Conditions */}
                {result.conditions && result.conditions.length > 0 && (
                  <div className="results-section">
                    <h3 className="results-section-title">Conditions</h3>
                    <ul className="bullet-list">
                      {result.conditions.map((condition, i) => (
                        <li key={i} className="bullet-item bullet-item-condition">
                          <span className="bullet-dot bullet-dot-condition" />
                          {condition}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Credit Narrative Summary */}
                {narrative && (
                  <div className="ai-summary-box">
                    <div className="ai-summary-header">
                      <BookOpen size={14} style={{ display: 'inline', marginRight: '0.4rem', verticalAlign: 'middle', color: '#2563eb' }} />
                      <span className="ai-summary-tag">
                        Credit Narrative Summary — Justification Memo
                      </span>
                    </div>
                    <p className="ai-summary-text">{narrative}</p>
                  </div>
                )}

                {/* -------------------------------------------------------- */}
                {/* Extracted CTOS Form Data (editable accordion)             */}
                {/* -------------------------------------------------------- */}
                <CtosDetailedExtraction
                  data={ctosFormData}
                  onDataChange={setCtosFormData}
                  onResult={setResult}
                  requestedAmount={parseFloat(requestedAmount) || 0}
                  decision={result}
                />

                {/* -------------------------------------------------------- */}
                {/* Human Officer Decision — Enterprise Panel                 */}
                {/* -------------------------------------------------------- */}
                <div className="officer-decision-panel">
                  {/* Panel header */}
                  <div className="officer-panel-header">
                    <UserCheck size={18} className="officer-header-icon" />
                    <div className="officer-header-text">
                      <span className="officer-panel-title">Human Officer Decision</span>
                      <span className="officer-panel-subtitle">
                        Final credit authority — generates compliance &amp; audit record
                      </span>
                    </div>
                    {decisionSubmitted
                      ? <span className="officer-recorded-badge">RECORDED</span>
                      : <span className="officer-required-badge">ACTION REQUIRED</span>
                    }
                  </div>

                  {decisionSubmitted ? (
                    /* ── Decision Receipt ─────────────────────────────── */
                    <div className="decision-receipt">
                      <div className={`receipt-status ${
                        humanDecision === 'APPROVED'      ? 'receipt-status--approved'
                        : humanDecision === 'REJECTED'    ? 'receipt-status--rejected'
                        : 'receipt-status--review'
                      }`}>
                        {humanDecision === 'APPROVED'      && <CheckCircle  size={20} />}
                        {humanDecision === 'REJECTED'      && <XCircle      size={20} />}
                        {humanDecision === 'MANUAL_REVIEW' && <AlertTriangle size={20} />}
                        <span className="receipt-decision-label">
                          {humanDecision.replace('_', ' ')}
                        </span>
                        <span className="receipt-ref">{decisionRef}</span>
                      </div>

                      <div className="receipt-details-grid">
                        <span className="receipt-key">Officer</span>
                        <span className="receipt-val">
                          <strong>{officerName}</strong> ({officerStaffId}) · {officerDesignation}
                        </span>

                        <span className="receipt-key">AI Limit</span>
                        <span className="receipt-val">{formatCurrency(aiLimit)}</span>

                        {overrideCreditLimit && (
                          <>
                            <span className="receipt-key">Override Limit</span>
                            <span className="receipt-val receipt-val--override">
                              MYR {Number(overrideCreditLimit).toLocaleString('en-MY')}
                            </span>
                          </>
                        )}

                        <span className="receipt-key">Timestamp</span>
                        <span className="receipt-val">
                          {submittedAt?.toLocaleString('en-MY', {
                            dateStyle: 'medium',
                            timeStyle: 'medium',
                          })}
                        </span>

                        {decisionRemarks && (
                          <>
                            <span className="receipt-key">Remarks</span>
                            <span className="receipt-val receipt-val--remarks">
                              &ldquo;{decisionRemarks}&rdquo;
                            </span>
                          </>
                        )}
                      </div>

                      <div className="receipt-actions">
                        <button
                          type="button"
                          className="receipt-modify-btn"
                          onClick={() => setDecisionSubmitted(false)}
                        >
                          Modify Decision
                        </button>
                        <p className="receipt-finality-note">
                          This decision has been logged to the audit trail.
                        </p>
                      </div>
                    </div>
                  ) : (
                    /* ── Decision Form ────────────────────────────────── */
                    <div className="officer-form-body">
                      {/* Officer identification */}
                      <div className="officer-id-grid">
                        <div className="officer-form-group">
                          <label className="officer-form-label">
                            Officer Name <span className="required">*</span>
                          </label>
                          <input
                            type="text"
                            className="officer-form-input"
                            value={officerName}
                            onChange={e => setOfficerName(e.target.value)}
                            placeholder="Full legal name"
                          />
                        </div>
                        <div className="officer-form-group">
                          <label className="officer-form-label">
                            Staff ID <span className="required">*</span>
                          </label>
                          <input
                            type="text"
                            className="officer-form-input"
                            value={officerStaffId}
                            onChange={e => setOfficerStaffId(e.target.value)}
                            placeholder="e.g. EMP-0123"
                          />
                        </div>
                        <div className="officer-form-group">
                          <label className="officer-form-label">Designation</label>
                          <select
                            className="officer-form-select"
                            value={officerDesignation}
                            onChange={e => setOfficerDesignation(e.target.value)}
                          >
                            <option>Branch Credit Officer</option>
                            <option>Senior Credit Officer</option>
                            <option>Regional Credit Manager</option>
                            <option>Head of Credit</option>
                            <option>Chief Financial Officer</option>
                            <option>Credit Committee</option>
                          </select>
                        </div>
                      </div>

                      {/* Decision selection */}
                      <div className="officer-decision-select">
                        <p className="officer-section-label">
                          Credit Decision <span className="required">*</span>
                        </p>
                        <div className="odso-buttons">
                          <button
                            type="button"
                            className={`odso-btn odso-approve ${humanDecision === 'APPROVED' ? 'odso-active' : ''}`}
                            onClick={() => setHumanDecision('APPROVED')}
                          >
                            <CheckCircle size={18} />
                            <span>Approve</span>
                          </button>
                          <button
                            type="button"
                            className={`odso-btn odso-review ${humanDecision === 'MANUAL_REVIEW' ? 'odso-active' : ''}`}
                            onClick={() => setHumanDecision('MANUAL_REVIEW')}
                          >
                            <AlertTriangle size={18} />
                            <span>Refer to Committee</span>
                          </button>
                          <button
                            type="button"
                            className={`odso-btn odso-reject ${humanDecision === 'REJECTED' ? 'odso-active' : ''}`}
                            onClick={() => setHumanDecision('REJECTED')}
                          >
                            <XCircle size={18} />
                            <span>Reject</span>
                          </button>
                        </div>
                      </div>

                      {/* Override credit limit */}
                      <div className="officer-override-section">
                        <div className="officer-form-group">
                          <label className="officer-form-label">Override Credit Limit (MYR)</label>
                          <p className="officer-field-hint">
                            AI recommendation: <strong>{formatCurrency(aiLimit)}</strong> — leave blank to accept.
                          </p>
                          <input
                            type="number"
                            className="officer-form-input"
                            value={overrideCreditLimit}
                            onChange={e => setOverrideCreditLimit(e.target.value)}
                            placeholder="Enter override amount, e.g. 500000"
                            min="0"
                            step="1000"
                          />
                        </div>
                      </div>

                      {/* Decision remarks */}
                      <div className="officer-remarks-section">
                        <div className="officer-form-group">
                          <label className="officer-form-label">
                            Decision Remarks
                            {humanDecision === 'REJECTED' && (
                              <span className="required"> · Required for rejection</span>
                            )}
                          </label>
                          <textarea
                            className="officer-form-textarea"
                            rows={3}
                            value={decisionRemarks}
                            onChange={e => setDecisionRemarks(e.target.value)}
                            placeholder="Document your rationale for this credit decision (for compliance and audit purposes)…"
                          />
                        </div>
                      </div>

                      {/* Submit row */}
                      <div className="officer-submit-row">
                        <button
                          type="button"
                          className="officer-submit-btn"
                          disabled={!canSubmitDecision}
                          onClick={handleDecisionSubmit}
                        >
                          <ClipboardCheck size={16} />
                          Record Decision &amp; Generate Audit Entry
                        </button>
                        {!humanDecision && (
                          <span className="officer-submit-hint">Select a decision above to continue</span>
                        )}
                        {humanDecision && (!officerName.trim() || !officerStaffId.trim()) && (
                          <span className="officer-submit-hint">Officer name and Staff ID are required</span>
                        )}
                        {humanDecision === 'REJECTED' && officerName.trim() && officerStaffId.trim() && !decisionRemarks.trim() && (
                          <span className="officer-submit-hint officer-submit-hint--error">
                            Remarks are required when rejecting
                          </span>
                        )}
                      </div>
                    </div>
                  )}
                </div>

                {/* Start New Application */}
                <div className="results-footer">
                  <button type="button" className="new-application-btn" onClick={handleReset}>
                    + Start New Application
                  </button>
                </div>
              </div>
            </div>

          )
        })()}
      </main>

      <footer className="app-footer">
        <p>Chin Hin Group &copy; {new Date().getFullYear()} &mdash; Internal Credit Assessment Tool</p>
      </footer>
      </div>{/* end app-main-panel */}

      {/* Draggable divider + Copilot sidebar */}
      {hasSidebar && (
        <div
          className={`split-handle${isDragging ? ' split-handle--active' : ''}`}
          onMouseDown={() => setIsDragging(true)}
        />
      )}
      {hasSidebar && (
        <div className="copilot-panel" style={{ width: copilotWidth }}>
          <DataCopilot
            currentData={ctosFormData}
            onDataUpdated={setCtosFormData}
            onMinimize={handleCopilotMinimize}
          />
        </div>
      )}

    </div>

    {/* Minimized bubble — OUTSIDE app-container to avoid containing-block from animation */}
    {ctosFormData && isCopilotMinimized && (
      <button
        type="button"
        className="copilot-expand-bubble"
        onClick={handleCopilotExpand}
        title="Open AI Data"
      >
        <MessageCircle size={22} />
        <span className="copilot-expand-badge" />
      </button>
    )}
    </>
  )
}

export default App
