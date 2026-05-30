/**
 * WelcomePage.jsx
 * ---------------
 * Premium FinTech landing page shown before the user enters the dashboard.
 * Uses glassmorphism, animated gradient orbs, and gradient typography.
 *
 * Props
 * -----
 *   onStart  {function}  Called when the user clicks "Start New Application".
 */

import { ArrowRight, ScanSearch, BarChart2, UserCheck, ShieldCheck, Zap } from 'lucide-react'
import './WelcomePage.css'

// ─────────────────────────────────────────────────────────────────────────────
// Feature cards data
// ─────────────────────────────────────────────────────────────────────────────

const FEATURES = [
  {
    icon: <ScanSearch size={26} />,
    color: 'blue',
    title: 'AI Document Extraction',
    desc: 'Upload any CTOS PDF and bank statement. Azure OpenAI reads every field and maps it into the structured 12-section Credit Scoring Form in seconds.',
    points: [
      'CTOS PDF parsing with OCR fallback',
      'Bank statement auto-detection',
      'Graceful field recovery on validation errors',
    ],
  },
  {
    icon: <Zap size={26} />,
    color: 'emerald',
    title: 'Deterministic Rules Engine',
    desc: 'Every score is computed client-side from the exact Chin Hin credit matrices. Zero AI hallucination in scoring — fully transparent and auditable.',
    points: [
      '100-point weighted scorecard',
      'New & Existing customer matrices',
      'Live score updates as you edit',
    ],
  },
  {
    icon: <UserCheck size={26} />,
    color: 'violet',
    title: 'Human-in-the-Loop Control',
    desc: 'Credit officers review and correct every extracted field inline. Request a fresh AI narrative, limit recommendation, and approval decision on demand.',
    points: [
      'Click-to-edit all 12 form sections',
      '"Update AI Credit Decision" on demand',
      'Officer decision recorded with full audit trail',
    ],
  },
]

// ─────────────────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────────────────

export default function WelcomePage({ onStart }) {
  return (
    <div className="wp-root">

      {/* ── Animated background ── */}
      <div className="wp-bg" aria-hidden="true">
        <div className="wp-orb wp-orb--1" />
        <div className="wp-orb wp-orb--2" />
        <div className="wp-orb wp-orb--3" />
        <div className="wp-grid-mesh" />
      </div>

      {/* ── Navigation ── */}
      <nav className="wp-nav">
        <div className="wp-nav-brand">
          <div className="wp-nav-logo">CH</div>
          <div className="wp-nav-brand-text">
            <span className="wp-nav-name">Chin Hin Group</span>
            <span className="wp-nav-sub">Credit &amp; Risk Division</span>
          </div>
        </div>
        <span className="wp-nav-pill">
          <ShieldCheck size={12} />
          PDPA Compliant · Azure OpenAI
        </span>
      </nav>

      {/* ── Hero ── */}
      <section className="wp-hero">
        <div className="wp-hero-eyebrow">
          <span className="wp-eyebrow-dot" />
          Autonomous Credit Scoring Engine · v0.1
        </div>

        <h1 className="wp-hero-title">
          Intelligent Credit<br />
          <span className="wp-gradient-text">Assessment Copilot</span>
        </h1>

        <p className="wp-hero-sub">
          Automate CTOS extraction, analyse bank statements, and generate
          deterministic credit scores with full officer oversight — in seconds.
        </p>

        <button className="wp-cta" onClick={onStart}>
          Start New Application
          <ArrowRight size={18} className="wp-cta-arrow" />
        </button>

        {/* Stats row */}
        <div className="wp-stats">
          <div className="wp-stat">
            <span className="wp-stat-num">&lt;&nbsp;30s</span>
            <span className="wp-stat-lbl">Processing Time</span>
          </div>
          <div className="wp-stat-divider" />
          <div className="wp-stat">
            <span className="wp-stat-num">100pt</span>
            <span className="wp-stat-lbl">Scorecard</span>
          </div>
          <div className="wp-stat-divider" />
          <div className="wp-stat">
            <span className="wp-stat-num">12</span>
            <span className="wp-stat-lbl">Extracted Sections</span>
          </div>
          <div className="wp-stat-divider" />
          <div className="wp-stat">
            <span className="wp-stat-num">4</span>
            <span className="wp-stat-lbl">AI Agents</span>
          </div>
        </div>
      </section>

      {/* ── Section divider ── */}
      <div className="wp-divider" role="presentation">
        <span className="wp-divider-label">
          <BarChart2 size={12} />
          Core Capabilities
        </span>
      </div>

      {/* ── Feature cards ── */}
      <section className="wp-features" aria-label="Core capabilities">
        {FEATURES.map((f) => (
          <article key={f.title} className={`wp-card wp-card--${f.color}`}>
            <div className={`wp-card-icon wp-card-icon--${f.color}`}>
              {f.icon}
            </div>
            <h3 className="wp-card-title">{f.title}</h3>
            <p className="wp-card-desc">{f.desc}</p>
            <ul className="wp-card-points">
              {f.points.map((p) => (
                <li key={p} className="wp-card-point">
                  <span className={`wp-point-dot wp-point-dot--${f.color}`} />
                  {p}
                </li>
              ))}
            </ul>
          </article>
        ))}
      </section>

      {/* ── Footer ── */}
      <footer className="wp-footer">
        <span>© 2025 Chin Hin Group Berhad · Autonomous Credit Scoring Engine</span>
        <span className="wp-footer-sep">·</span>
        <span>Built on Azure OpenAI · FastAPI · React</span>
      </footer>

    </div>
  )
}
