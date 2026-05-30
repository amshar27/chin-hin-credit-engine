# Technology Stack

A full breakdown of every technology used in the **Intelligent Credit Assessment Copilot** — Chin Hin Group's autonomous credit scoring engine with an integrated Multi-Agent AI Data Copilot.

---

## Frontend — React Dashboard

### Core Framework

| Technology | Version | Role |
|-----------|---------|------|
| **React** | 19.2 | Component-based UI, hooks-driven state management |
| **Vite** | 7.3 | Build tool and dev server (sub-second HMR) |
| **Axios** | 1.13 | HTTP client for all API calls to FastAPI |
| **lucide-react** | 0.577 | Icon library (consistent, tree-shakeable SVG icons) |

### UI Architecture & Design System

The frontend uses **hand-crafted CSS** (no utility framework) to achieve a premium FinTech aesthetic:

- **Glassmorphism** — `backdrop-filter: blur()` with semi-transparent `rgba` backgrounds and subtle `border: 1px solid rgba(255,255,255,0.08)` on cards.
- **Animated gradient orbs** — Three `position: fixed` radial-gradient blobs with independent `@keyframes` float animations create a living, depth-rich background.
- **Gradient typography** — CSS `background-clip: text` with animated `background-position` for the hero title.
- **Staggered card entrance** — `animation-delay` via `nth-child` selectors for sequential feature card reveal.
- **Micro-interactions** — `translateY(-6px)` on hover, sliding `ArrowRight` on CTA, orange "modified" dot on officer-edited fields, blue "Suggested by AI" badge on auto-filled values.

### AI Data Copilot UI (`DataCopilot.jsx`)

A **minimisable sidebar** chat interface embedded directly in the dashboard:

- **Fixed-position architecture** — The chat bubble uses `position: fixed` and is rendered **outside** any animated or transformed parent containers to avoid CSS containing-block issues. The sidebar renders inside a flex layout with a draggable split handle.
- **Scroll-independent** — The chat area manages its own `scrollTop` (never uses `scrollIntoView` which propagates to ancestors). Focus events use `preventScroll: true`. Toggle between minimised/expanded preserves the main panel's scroll position via `requestAnimationFrame`.
- **Minimised state** — Collapses to a floating circular button (bottom-right corner, `z-index: 100`). Expanding restores the full sidebar without layout jumps.
- **Message rendering** — User messages (right-aligned, blue), assistant messages (left-aligned, grey), error states (red tint + AlertTriangle icon), success states (green tint + confirmation).

### Deterministic Rules Engine (`scoreMapping.js`)

The most architecturally significant frontend module — entirely decoupled from the AI pipeline:

- **`NEW_CUSTOMER_SCORE_MAP`** and **`EXISTING_CUSTOMER_SCORE_MAP`** — Two complete scoring matrices encoding the exact Chin Hin credit assessment tables. Keys are verbatim `Literal` strings from the Pydantic schema; values are numeric point allocations.
- **Virtual score keys** — `guarantor_repayment_to_banks` and `guarantor_utilisation_pct` are alias keys that map the same data fields to different point values (guarantor CCRIS uses different weights than company CCRIS in the Existing Customer matrix).
- **`calculateFinalScores(formData, customerType)`** — A pure function returning `{ ccris_company, financial_info, internal_info, guarantees, company_background, total }`. Handles guarantor CCRIS averaging across the array. Called directly in the React render cycle — no `useEffect`, no API call.
- **Hard-stop sanity gate** — If `company_name`, `company_business_registration_no`, and `reference_no` are all missing, returns `null` to force the UI to show "N/A — Missing Data" instead of phantom scores from empty default forms.

### Human-in-the-Loop Accordion (`CtosDetailedExtraction.jsx`)

- **Click-to-edit fields** — `EditableFieldCell` supports `text`, `number`, `dropdown`, `radio`, `checkbox`, and `date` edit modes with automatic format conversion.
- **Dynamic guarantor sections** — A `useEffect` watching `personal_guarantee.number_of_guarantor` auto-resizes the `guarantor_ccris_profiles` array, spawning or destroying CCRIS sections in real-time.
- **AI suggestion badges** — Auto-fills Section 12 credit limit fields (only when `null`) and marks them with a "Suggested by AI" badge that clears on manual edit.
- **`localDataRef`** pattern — A `useRef` updated via a no-dependency `useEffect` allows the decision effect to read latest state without dependency loops.

---

## Backend — FastAPI Service

### Core Framework

| Technology | Version | Role |
|-----------|---------|------|
| **Python** | 3.11+ | Runtime |
| **FastAPI** | Latest | Async REST API framework with automatic OpenAPI docs |
| **Uvicorn** | Latest | ASGI server |
| **pdfplumber** | Latest | Primary PDF text extraction (layer-based) |
| **PyMuPDF (fitz)** | Latest | OCR fallback — renders PDF pages as 144-DPI PNG images for vision API |

### Data Modelling — Pydantic v2

Pydantic is not just a data class library here — it is the **LLM output enforcement layer**.

**`CreditScoringDetailedForm`** is a 12-section, 13-class Pydantic model with:

- **`Optional[Literal[...]]` fields** — Every banded score field (e.g. `gearing_ratio`, `years_in_business`, `repayment_to_banks`) is typed as a `Literal` of the exact string values from the scoring matrix. The LLM cannot hallucinate a value not in the enumeration.
- **`model_config = ConfigDict(extra='forbid')`** — Any unrecognised key causes an immediate `ValidationError`, preventing the LLM from silently inventing parallel schema keys.
- **Anti-hallucination descriptions** — Every Literal field's `Field(description=...)` includes: *"CRITICAL: Copy the exact string character-by-character."*

**Graceful degradation in `_validate(raw, mode)`:**

1. First pass: `model_validate(raw)` — if it passes, done.
2. On `ValidationError`: traverse each `error['loc']` path (including nested lists for guarantor arrays), **nullify only the offending fields** (or **delete** for `extra_forbidden` errors), and retry.
3. A `RuntimeError` is only raised if the second pass also fails.

### Document Validation Gate

A multi-layered defence that rejects non-CTOS PDFs **before** any LLM call:

| Layer | File | Mechanism | Outcome |
|-------|------|-----------|---------|
| **1. Heuristic gate** | `main.py` | `_validate_ctos_markers()` — extracts raw text via pdfplumber, checks for `"CTOS"` or `"CCRIS"` in uppercase | HTTP 400 immediately — zero LLM tokens burned |
| **2. Keyword gate** | `ctos_extractor_agent.py` | `validate_is_ctos_report()` — checks 20+ domain-specific markers, requires >= 2 hits | `InvalidDocumentError` → HTTP 400 |
| **3. Scoring gate** | `scoreMapping.js` | Checks company_name + reg_no + reference_no | Returns `null` → UI renders "N/A — Missing Data" |

### Multi-Agent Orchestration — Credit Pipeline (`agent_orchestrator.py`)

- Three upstream agents (CTOS, Bank, ERP) dispatched via `ThreadPoolExecutor` — truly parallel, not sequential.
- The Chief Credit Officer agent receives a merged context dict built from all three outputs.
- `CreditDecision` is a 21-field Pydantic model with `Optional` fields for all AI-produced values, making partial responses safe.

### Multi-Agent Data Copilot Pipeline (`multi_agent_copilot.py`)

The conversational form-editing engine uses a **4-stage architecture**:

```
                  ┌─────────────────┐
  user_prompt ──> │  Planner Agent  │ ──> PlannerOutput (which specialists + focus)
  form_summary    └─────────────────┘
                          │
           ┌──────────────┼──────────────┐   asyncio.gather()
           v              v              v
      [Bank Agent]  [ERP Agent]  [CTOS Agent]   (only those requested by Planner)
           │              │              │       (each receives only its data slice)
           └──────────────┴──────────────┘
                          │  free-text analyses
                          v
                  ┌─────────────────┐
  full_form  ──>  │  Merge Agent   │ ──> MergeResult (list of MergeActions + message)
                  └─────────────────┘
                          │
                          v
               _apply_merge_actions()        ← fuzzy Literal matching here
                          │
                          v
               CreditScoringDetailedForm  (patched copy, Pydantic-validated)
```

**Key implementation details:**

- **`asyncio.gather()` for parallel specialists** — All specialist coroutines run concurrently. Each specialist receives only its relevant data slice (token-efficient). `asyncio.to_thread()` offloads the synchronous `call_agent()` calls to the default thread-pool so the FastAPI event loop is never blocked.
- **Token-efficient data slicing** — `_build_data_slice(form, specialist)` routes only relevant form sections to each specialist (e.g. the Bank specialist only sees `financial_information`), reducing prompt sizes by ~70%.
- **MergeAction patches** — Each patch specifies a dot-separated field path (e.g. `ccris_for_company.blacklist_cases`), the new value, confidence (0.0-1.0), and a reason. Supports depth-1 (top-level scalar), depth-2 (section.field), and depth-3 (list.index.field) paths.
- **Never raises** — `execute_copilot_pipeline()` catches all exceptions and returns the original form unchanged, ensuring the UI never crashes from a Copilot error.

### Fuzzy Literal Matching (`_apply_merge_actions`)

When the Merge Agent hallucinates a Literal value (e.g. `"1 ( blacklisted )"` instead of `"1 ( 1 blacklist issue )"`), the engine:

1. **Introspects the Pydantic schema at runtime** — `_get_literal_options(field_path)` walks the `CreditScoringDetailedForm` model hierarchy using `typing.get_origin()` / `typing.get_args()`, unwrapping `Optional`, `Union`, and `List` layers to find the `Literal[...]` constraints.
2. **Applies a 4-step fuzzy matching cascade** — `_fuzzy_match_literal(value, allowed)`:
   - Case-insensitive exact match
   - Prefix-before-parenthesis match (e.g. `"1"` uniquely matches `"1 ( 1 blacklist issue )"`)
   - Normalised substring match
   - Starts-with match
3. **Resolves or skips** — If a unique match is found, the corrected value is used. If not, the action is skipped and logged as a warning.
4. **Prevents fake success** — If post-patch Pydantic validation still fails, the pipeline detects it via object identity check and overrides the AI's success message with a clear warning to the officer.

### Route Layer (`main.py`)

Five routes serving the full credit workflow:

| Route | Purpose |
|-------|---------|
| `GET /health` | Liveness probe |
| `POST /api/v1/process-credit-application` | Full 4-agent pipeline (PDF → CreditDecision) |
| `POST /api/v1/extract-credit-scoring-form` | Extraction only (PDF → CreditScoringDetailedForm) |
| `POST /api/v1/recalculate-score` | Re-score with officer-corrected form (Chief Officer agent only) |
| `POST /api/refine-data` | AI Data Copilot (Planner → Specialists → Merge → Patch) |

Three helper converters (`_form_to_ctos_dict`, `_form_to_erp_dict`, `_form_to_bank_dict`) translate the officer's corrected `CreditScoringDetailedForm` back into the flat dicts each agent expects.

---

## AI / LLM Platform — Microsoft Azure AI Foundry

| Component | Technology |
|-----------|-----------|
| **Platform** | Microsoft Azure AI Foundry (formerly Azure AI Studio) |
| **SDK** | `azure-ai-projects` + `azure-identity` |
| **Authentication** | `DefaultAzureCredential` (supports `az login` locally, Managed Identity in production) |
| **Models** | GPT-4o (Chief Credit Officer + CTOS Extractor), GPT-4o-mini (Bank Analyst, Internal ERP) |
| **Output mode** | Azure OpenAI Structured Outputs — JSON schema enforced at the API level |
| **Agent deployment** | Each agent is a separately deployed, versioned Azure AI Agent with its own system prompt, tools, and model configuration |
| **Copilot agents** | Planner Agent + Merge Agent — dedicated agents for the Data Copilot pipeline |

### Why Structured Outputs Over Plain JSON Mode?

`response_format={"type": "json_schema", "json_schema": {...}}` (Structured Outputs) enforces schema conformance at the **Azure API level** — the model is constrained during token generation, not just post-hoc parsed. Combined with Pydantic's two-pass graceful degradation, the pipeline has defence-in-depth against malformed LLM responses.

### Prompt Engineering Highlights

- **Global Literal directive** — Injected at the top of the CTOS Extractor system prompt, instructing the model to treat Literal enum strings as byte-for-byte constants.
- **Explicit top-level key list** — The prompt enumerates all 13 root keys of `CreditScoringDetailedForm` to prevent the model from inventing a shorter or renamed schema.
- **Combined document context** — When a bank statement PDF is uploaded alongside the CTOS report, both are concatenated with section headers (`--- CTOS REPORT ---` / `--- BANK STATEMENT ---`).
- **Copilot specialist focus** — Each specialist agent receives a one-sentence `focus_area` from the Planner, constraining its analysis to the officer's actual intent rather than reviewing the entire form.

---

## Infrastructure & Tooling

| Tool | Purpose |
|------|---------|
| **Azure AI Foundry Portal** | Agent deployment, system prompt management, model versioning |
| **Azure Developer CLI (`azd`)** | Environment provisioning and configuration |
| **ESLint** | JavaScript linting (react-hooks, react-refresh plugins) |
| **python-dotenv** | Local environment variable loading |
| **CORS middleware (FastAPI)** | Configured for open origins during development |

---

## Architecture Decision Record — Key Choices

### Why deterministic scoring in the frontend?

The LLM's `score_breakdown` field is populated by the Chief Credit Officer agent — but the agent has no reliable way to apply a weighted matrix accurately under token constraints. Early testing showed hallucinated sub-scores (e.g. 18/25 when the correct answer was 14/25). Moving the scoring computation to the client, encoded as a lookup table in `scoreMapping.js`, gave us **zero-error, zero-latency, always-auditable scores** that update as the officer types.

### Why Pydantic `extra='forbid'` instead of `extra='ignore'`?

`extra='ignore'` silently dropped unrecognised keys, masking the problem of the LLM inventing `"financials"` instead of `"financial_information"`. With `extra='forbid'`, the key mismatch surfaces immediately as a `ValidationError`, triggering graceful degradation.

### Why a 4-stage Copilot pipeline instead of a single LLM call?

A single call with the full 12-section form + user prompt would:
1. **Burn excessive tokens** — sending the entire form (50+ fields) every time.
2. **Reduce accuracy** — the model struggles to locate the right field in a large context.
3. **Eliminate parallelism** — a single call is inherently sequential.

The Planner → Specialists → Merge architecture routes the right data to the right expert, runs specialists concurrently, and lets the Merge Agent make the final structured decision with full context. The Planner often routes to a single specialist for simple requests, saving ~70% of tokens.

### Why fuzzy matching instead of strict validation?

The Merge Agent must produce exact Literal strings like `'1 ( 1 blacklist issue )'`. In practice, it occasionally paraphrases (e.g. `'1 ( blacklisted )'`). Without fuzzy matching, these near-misses silently fail Pydantic validation and the original form is returned unchanged — creating a confusing user experience where the Copilot says "Updated!" but nothing changed. The fuzzy matcher resolves ~95% of these hallucinations automatically.

### Why render the chat bubble outside animated containers?

CSS `transform` (even `translateY(0)`) creates a new **containing block**, breaking `position: fixed` on child elements. The chat bubble is rendered as a sibling of `.app-container` via a React Fragment, ensuring it always positions relative to the viewport.
