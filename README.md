# Intelligent Credit Assessment Copilot

> **A hybrid AI + Deterministic Rules Engine that automates B2B credit scoring for Chin Hin Group.**
>
> Ingests CTOS reports and bank statements, extracts structured data via a multi-agent LLM pipeline, calculates scores against a 100% deterministic matrix, and surfaces a Human-in-the-Loop dashboard with an integrated **AI Data Copilot** so Credit Officers retain full, auditable control.

---

## The Problem

Manual credit assessment at Chin Hin Group requires officers to:

1. Read dense CTOS PDF reports by hand
2. Transcribe data into a 12-section scoring form
3. Apply a weighted scorecard across 5 risk categories
4. Write a credit narrative and propose a credit limit

This process takes **hours per application**, is prone to transcription errors, and produces inconsistent decisions across officers. Officers have no conversational way to query or correct extracted data — they must manually locate and edit each field.

---

## The Solution

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                   INTELLIGENT CREDIT ASSESSMENT COPILOT                      │
│                                                                              │
│  PDF Upload                       Azure AI Foundry — Multi-Agent             │
│  ──────────                       ─────────────────────────────              │
│  CTOS PDF  ──▶  ┌──────────┐   ┌─────────┐   ┌──────────┐                 │
│                  │  CTOS    │   │  Bank   │   │ Internal │                  │
│  Bank Stmt ──▶  │ Extractor│   │ Analyst │   │   ERP    │   [parallel]     │
│                  └────┬─────┘   └────┬────┘   └────┬─────┘                 │
│                       └──────────────┴──────────────┘                        │
│                                      │                                        │
│  ┌─────────────────┐                 ▼                                        │
│  │ Document        │     ┌─────────────────────┐                             │
│  │ Validation Gate │────▶│ Chief Credit Officer │  GPT-4o                    │
│  │ (CTOS/CCRIS     │     │       Agent          │                             │
│  │  markers)       │     └──────────┬──────────┘                             │
│  └─────────────────┘                │  CreditDecision (JSON)                  │
│                                      ▼                                        │
│  ┌───────────────────────────────────────────────────────────────────┐       │
│  │                     React Dashboard                                │       │
│  │  ✦ Deterministic 100-pt score     ✦ Officer edits → AI re-eval   │       │
│  │  ✦ AI Data Copilot (chat)         ✦ Audit trail & final sign-off │       │
│  └───────────────────────────────────────────────────────────────────┘       │
│                                      │                                        │
│           ┌──────────────────────────┘                                        │
│           ▼                                                                   │
│  ┌─────────────────────────────────────────┐                                 │
│  │     AI Data Copilot Pipeline            │                                 │
│  │                                         │                                 │
│  │  Officer ──▶ Planner ──▶ Specialists ──▶ Merge ──▶ Patch Form            │
│  │  "Change      (routes)   (bank/erp/     (synth-   (Pydantic              │
│  │   gearing                 ctos, run      esises    validated)             │
│  │   ratio..."               in parallel)   patches)                        │
│  └─────────────────────────────────────────┘                                 │
└──────────────────────────────────────────────────────────────────────────────┘
```

Assessment time: **hours → under 30 seconds.** Every score remains 100% auditable. Every decision stays under officer authority.

---

## Key Features

### Multi-Agent Credit Pipeline
Four specialised agents on **Microsoft Azure AI Foundry** (Agents 1-3 execute in parallel; Agent 4 consumes all outputs):

| # | Agent | Responsibility |
|---|-------|----------------|
| 1 | **CTOS Extractor** | Parses raw CTOS PDF text. Uses Azure OpenAI **Structured Outputs** to populate all 12 sections of the `CreditScoringDetailedForm` Pydantic schema with guaranteed schema conformance. Implements two-pass graceful degradation — invalid fields are nullified and retried rather than crashing the pipeline. |
| 2 | **Bank Statement Analyst** | Analyses the optional bank statement PDF. Extracts average end-of-month balances, flags bounced cheques, and summarises payment conduct for the Chief Officer. |
| 3 | **Internal ERP Agent** | Cross-references the applicant against Chin Hin's internal trade records to determine payment history, relationship tenure, and existing group exposure. |
| 4 | **Chief Credit Officer** | Synthesises all upstream outputs to produce a structured `CreditDecision`: recommendation (`APPROVE / MANUAL_REVIEW / REJECT`), proposed credit limit (MYR), risk grade, key reasons, conditions, and a formal credit narrative memo. |

### AI Data Copilot — Conversational Form Editing

A natural-language chat sidebar embedded directly in the dashboard. Officers can **talk** to their data instead of hunting through dropdowns.

```
Officer types:  "Change blacklist cases to 1"
                "What is the current net profit?"
                "The gearing ratio looks wrong, recalculate from the balance sheet"

Copilot:        Routes → Analyses → Patches → Confirms
```

**Architecture: Planner → Specialists (parallel) → Merge → Patch**

| Stage | Agent | What it does |
|-------|-------|-------------|
| 1. Plan | **Planner Agent** | Reads the officer's prompt + a compact form summary. Decides which specialist(s) to invoke (bank, erp, ctos). |
| 2. Analyse | **Specialist Agents** | Run **concurrently** via `asyncio.gather()`. Each receives only its relevant data slice (token-efficient). Returns free-text analysis. |
| 3. Merge | **Merge Agent** | Receives all specialist analyses + the full form. Produces a list of `MergeAction` patches (field path + new value + confidence + reason) and a conversational message. |
| 4. Patch | **`_apply_merge_actions()`** | Navigates dot-paths, fuzzy-matches hallucinated Literal values to exact schema strings, validates through Pydantic, returns the patched form. |

**Fuzzy Literal Matching** — When the Merge Agent outputs `"1 ( blacklisted )"` instead of `"1 ( 1 blacklist issue )"`, the engine introspects the Pydantic schema at runtime, extracts the allowed `Literal` options for the target field, and applies a 4-step cascade (case-insensitive → prefix-before-paren → substring → starts-with) to resolve the exact match. No silent failures.

**Fake Success Prevention** — If post-patch Pydantic validation fails despite fuzzy matching, the pipeline detects it via identity check and overrides the AI's success message with a clear warning. The officer always knows whether their edit actually landed.

### Document Validation Gate

A multi-layered defence that rejects non-CTOS PDFs **before** any LLM call:

| Layer | Location | Check | Response |
|-------|----------|-------|----------|
| 1 | `main.py` | Raw text must contain `"CTOS"` or `"CCRIS"` | HTTP 400 — saves LLM tokens |
| 2 | `ctos_extractor_agent.py` | 20+ keyword marker check (requires >= 2 hits) | `InvalidDocumentError` → HTTP 400 |
| 3 | `scoreMapping.js` | Company name + reg no + reference no all missing | Returns `null` → UI shows "N/A — Missing Data" |

### Deterministic Rules Engine

Scoring is computed **100% client-side** — no API call, no LLM involvement:

- `src/utils/scoreMapping.js` encodes the exact Chin Hin credit matrices for both **New** and **Existing** customers.
- `calculateFinalScores(formData, customerType)` returns live sub-totals for all 5 categories.
- Scores **update in real-time** as the officer edits any field in the form.
- The AI's `score_breakdown` is intentionally **ignored** to eliminate hallucination from the final score.

#### 5-Category Scorecard (100 Points)

| Category | New Customer | Existing Customer |
|----------|:-----------:|:-----------------:|
| CCRIS for Company | 25 pts | 25 pts |
| Financial Information | 25 pts | 25 pts |
| Trade Reference / Group Exposure | 10 pts | 30 pts |
| PG / CG / BG + Guarantor CCRIS | 30 pts | 20 pts |
| Company Background | 10 pts | — |
| **Total** | **100 pts** | **100 pts** |

#### 5-Tier Risk Matrix

| Score | Credit Rating | Risk Grade | Prob. of Default |
|-------|--------------|------------|:----------------:|
| 81-100 | Extremely Strong | Low Risk — Approve | 0%-5% |
| 61-80 | Strong | Moderate Risk — Approve with Conditions | 5.1%-15% |
| 41-60 | Average | Medium Risk — Manual Review Required | 15.1%-30% |
| 21-40 | Weak | High Risk — Reject | 30.1%-60% |
| 0-20 | Very Weak | Extremely High Risk — Reject Immediately | >60% |

#### Hard-Stop Business Rules

Regardless of score, the following trigger an immediate dashboard flag:

- **Status Code K** — Applicant is under AKPK / Debt Management Counselling
- **Status Code 10** — Summons filed against the applicant
- **Special Attention Account (SAA)** — Pink-highlighted CCRIS facility
- **Director / Guarantor Age >= 70** — Non-actionable for legal recovery

---

## Human-in-the-Loop Workflow

```
AI Extracts → Human Corrects (with Copilot) → AI Re-evaluates → Officer Signs Off
```

1. **AI Extracts** — CTOS PDF + optional bank statement uploaded. All 12 form sections auto-populated in ~30 seconds.
2. **Human Corrects** — Every field is click-to-edit. Scores update live. AI-auto-filled fields in Section 12 carry a *Suggested by AI* badge that clears on manual edit. The **AI Data Copilot** sidebar provides natural-language editing ("change the gearing ratio to 1.5") and Q&A ("what is the company's net profit?").
3. **AI Re-evaluates** — Officer clicks **"Update AI Credit Decision"** to send corrected data back to the Chief Credit Officer agent for a fresh narrative, limit, and recommendation — without re-running PDF extraction.
4. **Officer Signs Off** — Final Approve / Conditional Approve / Reject is recorded with officer name, staff ID, designation, and remarks. A timestamped audit reference (`CH-YYYYMMDD-XXXX`) is generated.

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Liveness probe |
| `POST` | `/api/v1/process-credit-application` | Full pipeline: CTOS PDF + optional bank statement → `CreditDecision` |
| `POST` | `/api/v1/extract-credit-scoring-form` | Extraction only: PDF(s) → structured `CreditScoringDetailedForm` |
| `POST` | `/api/v1/recalculate-score` | Re-runs Chief Credit Officer on officer-corrected form data |
| `POST` | `/api/refine-data` | **AI Data Copilot**: natural-language form editing and Q&A via the Planner → Specialists → Merge pipeline |

Interactive docs at `http://localhost:8000/docs` (Swagger UI).

---

## Project Structure

```
chin-hin-credit-engine/
│
├── app/
│   ├── main.py                              # FastAPI app, routes, document validation gate
│   ├── agents/
│   │   ├── agent_orchestrator.py            # Parallel pipeline coordinator + Pydantic output models
│   │   ├── foundry_client.py                # Azure AI Foundry client wrapper (call_agent)
│   │   ├── credit_form_extractor.py         # Structured-output 12-section extractor + graceful degradation
│   │   ├── ctos_extractor_agent.py          # Agent 1: CTOS PDF + document validation
│   │   ├── bank_statement_analyst_agent.py  # Agent 2: Bank statement
│   │   ├── internal_erp_agent.py            # Agent 3: ERP trade records
│   │   ├── chief_credit_officer_agent.py    # Agent 4: Final decision
│   │   └── multi_agent_copilot.py           # AI Data Copilot: Planner → Specialists → Merge → Patch
│   └── models/
│       └── credit_scoring_form.py           # Pydantic v2 schema — 12 sections, strict Literals
│
├── credit-engine-ui/
│   └── src/
│       ├── App.jsx                          # Dashboard shell, state, submit flow, score rendering
│       ├── components/
│       │   ├── WelcomePage.jsx              # Premium FinTech landing page
│       │   ├── CtosDetailedExtraction.jsx   # Editable 12-section accordion + live scoring
│       │   ├── DataCopilot.jsx              # Floating chat sidebar — natural language form editing
│       │   └── DataCopilot.css
│       └── utils/
│           └── scoreMapping.js              # New/Existing customer matrices + calculateFinalScores()
│
├── data/
│   ├── matrices/                            # Credit scoring lookup tables
│   ├── mock_erp/mock_erp_data.json          # Mock internal trade records
│   └── sample_pdfs/                         # Sample CTOS test files
│
├── Credit Scoring Matrix(New Customer).csv
├── Credit Scoring Matrix(Existing Customer).csv
├── requirements.txt
├── .env.example                             # Copy to .env and fill in values
├── README.md
├── TECH_STACK.md
└── PRESENTATION_CHEATSHEET.md
```

---

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- An **Azure AI Foundry** project with deployed agents (see `.env.example` for required IDs)
- `az login` completed locally (uses `DefaultAzureCredential`)

### 1 — Clone & configure

```bash
git clone https://github.com/your-org/chin-hin-credit-engine.git
cd chin-hin-credit-engine

cp .env.example .env
# Open .env and fill in your Azure credentials and agent IDs
```

### 2 — Start the FastAPI backend

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

pip install -r requirements.txt

uvicorn app.main:app --reload --port 8000
```

API → `http://localhost:8000` | Swagger → `http://localhost:8000/docs`

### 3 — Start the React frontend

```bash
cd credit-engine-ui
npm install
npm run dev
```

UI → `http://localhost:5173`

---

## Environment Variables

Copy `.env.example` → `.env` and set:

| Variable | Description |
|----------|-------------|
| `AZURE_EXISTING_AIPROJECT_ENDPOINT` | Azure AI Foundry project endpoint URL |
| `AZURE_EXISTING_AIPROJECT_RESOURCE_ID` | Full ARM resource ID of the AI project |
| `AZURE_EXISTING_RESOURCE_ID` | ARM resource ID of the Azure AI account |
| `AZURE_SUBSCRIPTION_ID` | Your Azure subscription ID |
| `AZURE_LOCATION` | Azure region (e.g. `eastus2`) |
| `CTOS_AGENT_ID` | Deployed agent ID for the CTOS Extractor |
| `ERP_AGENT_ID` | Deployed agent ID for the Internal ERP Agent |
| `BANK_AGENT_ID` | Deployed agent ID for the Bank Statement Analyst |
| `CHIEF_AGENT_ID` | Deployed agent ID for the Chief Credit Officer |
| `PLANNER_AGENT_ID` | *(Optional)* Agent ID for the Data Copilot Planner (default: `Planner-Agent:1`) |
| `MERGE_AGENT_ID` | *(Optional)* Agent ID for the Data Copilot Merge Agent (default: `Merge-Agent:1`) |

---

## PDPA Compliance

- **No raw document data is persisted.** PDF bytes are processed in-memory and go out of scope at the end of each request.
- The UI gate requires officers to confirm explicit **PDPA consent** before submitting an application.
- The system is **stateless by design** — no applicant PII is stored server-side.
- The Data Copilot pipeline follows the same stateless principle — form data exists only in the browser session and the in-flight API request.

---

## License

Developed for the **Chin Hin Group Hackathon 2025**. All rights reserved.
