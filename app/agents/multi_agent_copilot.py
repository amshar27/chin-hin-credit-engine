"""
multi_agent_copilot.py
----------------------
Planner → Specialists (parallel) → Merge → Patch pipeline for the
Data Copilot natural-language editing feature.

Architecture
------------
                  ┌─────────────────┐
  user_prompt ──▶ │  Planner Agent  │ ──▶ PlannerOutput (which specialists + focus)
  form_summary    └─────────────────┘
                          │
           ┌──────────────┼──────────────┐   asyncio.gather()
           ▼              ▼              ▼
      [Bank Agent]  [ERP Agent]  [CTOS Agent]   (only those requested by Planner)
           │              │              │       (each receives only its data slice)
           └──────────────┴──────────────┘
                          │  free-text analyses
                          ▼
                  ┌─────────────────┐
  full_form  ──▶  │  Merge Agent   │ ──▶ MergeResult (list of MergeActions)
                  └─────────────────┘
                          │
                          ▼
               _apply_merge_actions()
                          │
                          ▼
               CreditScoringDetailedForm  (patched copy)

Guarantees
----------
- Never raises from execute_copilot_pipeline().  Any failure at any step
  returns the original form unchanged so the UI never crashes.
- call_agent() is synchronous; every call is offloaded to a thread-pool
  worker via asyncio.to_thread() so the FastAPI event loop is never blocked.
- Specialist agents run concurrently via asyncio.gather().
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import typing
from typing import Any, List, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.agents.foundry_client import call_agent
from app.models.credit_scoring_form import CreditScoringDetailedForm

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Agent IDs — read from .env; sensible defaults match existing Foundry agents
# ---------------------------------------------------------------------------

_PLANNER_AGENT_ID = os.environ.get("PLANNER_AGENT_ID", "Planner-Agent:1")
_MERGE_AGENT_ID   = os.environ.get("MERGE_AGENT_ID",   "Merge-Agent:1")

# Re-use existing specialist Foundry agents (same IDs as the extraction pipeline)
_SPECIALIST_AGENT_IDS: dict[str, str] = {
    "bank": os.environ.get("BANK_AGENT_ID",  "Bank-Statement-Analyst:2"),
    "erp":  os.environ.get("ERP_AGENT_ID",   "Internal-ERP-Agent:2"),
    "ctos": os.environ.get("CTOS_AGENT_ID",  "CTOS-Extractor:2"),
}

# ---------------------------------------------------------------------------
# Pipeline Pydantic models
# ---------------------------------------------------------------------------


class SpecialistTask(BaseModel):
    """A single specialist assignment produced by the Planner Agent."""

    model_config = ConfigDict(extra="forbid")

    specialist: Literal["bank", "erp", "ctos"] = Field(
        description="Which specialist to invoke."
    )
    focus_area: str = Field(
        description="Concise sentence describing what this specialist should analyse or correct."
    )


class PlannerOutput(BaseModel):
    """Structured output of the Planner Agent."""

    model_config = ConfigDict(extra="forbid")

    tasks: List[SpecialistTask] = Field(
        description="Ordered list of specialist tasks required to fulfil the user's request."
    )


class MergeAction(BaseModel):
    """A single field patch produced by the Merge Agent."""

    model_config = ConfigDict(extra="forbid")

    field: str = Field(
        description=(
            "Dot-separated path to the target field inside CreditScoringDetailedForm. "
            "Supported formats:\n"
            "  • 'customer_type'                               (top-level scalar)\n"
            "  • 'financial_information.net_profit_loss'       (section.field)\n"
            "  • 'guarantor_ccris_profiles.0.guarantor_age_pg' (list.index.field)"
        )
    )
    value: Any = Field(
        description=(
            "New value to set.  For Literal fields use the exact band string "
            "from the CreditScoringDetailedForm schema (e.g. '( 1.00 - 1.99 )' "
            "for gearing_ratio).  Use null to clear a field."
        )
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence in this patch (0.0 – 1.0).  Use 1.0 only when certain.",
    )
    reason: str = Field(description="One-sentence explanation for this change.")


class MergeResult(BaseModel):
    """Structured output of the Merge Agent — patch list + conversational message."""

    model_config = ConfigDict(extra="forbid")

    actions: List[MergeAction] = Field(
        default_factory=list,
        description="Patches to apply in order.  Empty list means no changes are needed.",
    )
    message: str = Field(
        default="",
        description=(
            "Conversational response to the officer.  For mutations: explain what "
            "was changed.  For read-only questions: answer directly from the form data.  "
            "If you cannot help: explain why politely."
        ),
    )


class RefineDataRequest(BaseModel):
    """Request body for POST /api/refine-data."""

    current_data: CreditScoringDetailedForm = Field(
        description="The current state of the credit scoring form (all 12 sections)."
    )
    user_prompt: str = Field(
        min_length=1,
        max_length=2_000,
        description="Natural language instruction from the credit officer.",
    )


# ---------------------------------------------------------------------------
# JSON schema strings — generated once at import time, injected into prompts
# ---------------------------------------------------------------------------

_PLANNER_SCHEMA_STR: str = json.dumps(PlannerOutput.model_json_schema(), indent=2)
_MERGE_SCHEMA_STR: str   = json.dumps(MergeResult.model_json_schema(), indent=2)

# ---------------------------------------------------------------------------
# Helper: lightweight form summary for the Planner
# ---------------------------------------------------------------------------

def _build_form_summary(form: CreditScoringDetailedForm) -> str:
    """
    Produce a compact text summary of the form's current state.

    Intentionally terse — the Planner only needs to decide *which* specialists
    to invoke, not to perform analysis itself.  Sending the full 50-field form
    to the Planner wastes tokens and degrades routing accuracy.
    """
    data = form.model_dump(exclude_none=True)
    lines: list[str] = []

    if ci := data.get("customer_information"):
        lines.append(
            f"Company: {ci.get('company_name', '—')} "
            f"(Reg: {ci.get('company_business_registration_no', '—')})"
        )

    lines.append(f"Customer type: {data.get('customer_type', '—')}")

    if ccris := data.get("ccris_for_company"):
        lines.append(
            f"CCRIS — legal cases: {ccris.get('legal_cases_unsettled', '—')}, "
            f"blacklist: {ccris.get('blacklist_cases', '—')}, "
            f"repayment: {ccris.get('repayment_to_banks', '—')}"
        )

    if fin := data.get("financial_information"):
        lines.append(
            f"Financials — turnover band: {fin.get('turnover', '—')}, "
            f"net profit/loss: {fin.get('net_profit_loss', '—')}, "
            f"bank statement: {fin.get('bank_statement_provided', 'N/A')}"
        )

    if ii := data.get("internal_information"):
        lines.append(
            f"Internal — payment pattern: {ii.get('group_exposure_internal_payment_pattern', '—')}, "
            f"relationship: {ii.get('years_in_relationship', '—')}"
        )

    if bg := data.get("company_background"):
        lines.append(
            f"Background — type: {bg.get('type_of_company', '—')}, "
            f"years: {bg.get('years_in_business', '—')}, "
            f"paid-up capital: {bg.get('paid_up_capital_rm', '—')}"
        )

    guarantors: list = data.get("guarantor_ccris_profiles") or []
    if guarantors:
        lines.append(f"Guarantors: {len(guarantors)} profile(s) present.")

    return "\n".join(lines) if lines else "Form is currently empty."


# ---------------------------------------------------------------------------
# Helper: relevant data slice per specialist (saves tokens)
# ---------------------------------------------------------------------------

_SPECIALIST_SECTIONS: dict[str, list[str]] = {
    "bank": [
        "financial_information",
    ],
    "erp": [
        "internal_information",
    ],
    "ctos": [
        "customer_information",
        "ccris_for_company",
        "company_background",
        "guarantor_ccris_profiles",
        "additional_information",
        "proposed_credit_limit",
    ],
}


def _build_data_slice(form: CreditScoringDetailedForm, specialist: str) -> dict[str, Any]:
    """Return only the form sections relevant to the given specialist."""
    full: dict[str, Any] = form.model_dump(exclude_none=False)
    keys = _SPECIALIST_SECTIONS.get(specialist, list(full.keys()))
    return {k: full[k] for k in keys if k in full}


# ---------------------------------------------------------------------------
# Literal introspection + fuzzy matching
# ---------------------------------------------------------------------------


def _extract_literal_args(annotation: Any) -> list[str] | None:
    """
    Recursively unwrap Optional / Union wrappers to find Literal[...] args.
    Returns the list of allowed string values, or None if not a Literal field.
    """
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)

    if origin is Literal:
        return [a for a in args if isinstance(a, str)]

    # Optional[X] is Union[X, None] — unwrap and recurse
    if origin is typing.Union:
        for arg in args:
            if arg is type(None):
                continue
            result = _extract_literal_args(arg)
            if result is not None:
                return result

    return None


def _unwrap_to_basemodel(annotation: Any) -> type[BaseModel] | None:
    """
    Given a type annotation, unwrap Optional / List layers to find a
    BaseModel subclass.  Returns None if none is found.
    """
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation

    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)

    if origin is typing.Union:
        for arg in args:
            if arg is type(None):
                continue
            result = _unwrap_to_basemodel(arg)
            if result is not None:
                return result

    if origin is list:
        for arg in args:
            result = _unwrap_to_basemodel(arg)
            if result is not None:
                return result

    return None


def _get_literal_options(field_path: str) -> list[str] | None:
    """
    Given a dot-separated field path (e.g. 'ccris_for_company.blacklist_cases'),
    introspect CreditScoringDetailedForm to find the Literal constraints.

    Handles depth-1 (top-level), depth-2 (section.field), and depth-3
    (list.index.field) paths.  Returns None if the field is not a Literal.
    """
    parts = field_path.strip().split(".")
    model: type[BaseModel] = CreditScoringDetailedForm

    for i, part in enumerate(parts):
        if part.isdigit():
            continue  # Skip list indices (e.g. '0' in 'guarantor_ccris_profiles.0.field')

        field_info = model.model_fields.get(part)
        if field_info is None:
            return None

        annotation = field_info.annotation

        if i == len(parts) - 1:
            # Leaf field — extract Literal options
            return _extract_literal_args(annotation)
        else:
            # Intermediate — resolve to nested BaseModel and continue
            inner = _unwrap_to_basemodel(annotation)
            if inner is None:
                return None
            model = inner

    return None


def _fuzzy_match_literal(value: str, allowed: list[str]) -> str | None:
    """
    Attempt to match a potentially hallucinated LLM value to an exact
    allowed Literal string.

    Matching cascade (first unique hit wins):
      1. Case-insensitive exact match
      2. Prefix-before-parenthesis match  (e.g. "1" matches "1 ( 1 blacklist issue )")
      3. Normalised substring match       (value contained in one option)
      4. Starts-with match                (one option starts with the value)
    """
    if not isinstance(value, str) or not allowed:
        return None

    def _norm(s: str) -> str:
        return re.sub(r"\s+", " ", s.strip().lower())

    val_norm = _norm(value)

    # 1. Case-insensitive exact match
    for opt in allowed:
        if _norm(opt) == val_norm:
            return opt

    # 2. Prefix-before-parenthesis match
    val_prefix = _norm(value.split("(")[0])
    if val_prefix:
        candidates = [opt for opt in allowed if _norm(opt.split("(")[0]) == val_prefix]
        if len(candidates) == 1:
            return candidates[0]

    # 3. Value (normalised) is a substring of exactly one option
    candidates = [opt for opt in allowed if val_norm in _norm(opt)]
    if len(candidates) == 1:
        return candidates[0]

    # 4. One option starts with the normalised value
    candidates = [opt for opt in allowed if _norm(opt).startswith(val_norm)]
    if len(candidates) == 1:
        return candidates[0]

    return None


# ---------------------------------------------------------------------------
# Helper: apply MergeResult actions to a deep copy of the form
# ---------------------------------------------------------------------------

def _apply_merge_actions(
    form: CreditScoringDetailedForm,
    actions: list[MergeAction],
) -> CreditScoringDetailedForm:
    """
    Navigate each MergeAction's dot-path, set the value in a dict copy of
    the form, then re-validate through CreditScoringDetailedForm.

    Returns the original form unchanged if post-patch validation fails.

    Supported path formats
    ----------------------
    Depth 1  — top-level scalar:
                 'customer_type'
    Depth 2  — section.field (most common):
                 'financial_information.net_profit_loss'
    Depth 3a — list[index].field:
                 'guarantor_ccris_profiles.0.guarantor_age_pg'
    Depth 3b — section.sub_object.field (rare):
                 'ccris_for_company.some_nested.field'
    """
    data: dict[str, Any] = form.model_dump()
    applied: list[str] = []
    skipped: list[str] = []

    for action in actions:
        parts = action.field.strip().split(".")

        # ── Fuzzy-match Literal values before applying ────────────────
        resolved_value = action.value
        literal_options = _get_literal_options(action.field)
        if literal_options and isinstance(resolved_value, str) and resolved_value not in literal_options:
            matched = _fuzzy_match_literal(resolved_value, literal_options)
            if matched is not None:
                logger.info(
                    "Fuzzy-matched Literal: '%s' → '%s' (field: %s)",
                    resolved_value, matched, action.field,
                )
                resolved_value = matched
            else:
                skipped.append(
                    f"{action.field} (value '{resolved_value}' does not match "
                    f"any allowed option)"
                )
                continue

        try:
            if len(parts) == 1:
                # ── top-level field ────────────────────────────────────────
                if parts[0] in data:
                    data[parts[0]] = resolved_value
                    applied.append(action.field)
                else:
                    skipped.append(f"{action.field} (unknown top-level key)")

            elif len(parts) == 2:
                # ── section.field ──────────────────────────────────────────
                section, field = parts
                target = data.get(section)
                if isinstance(target, dict):
                    target[field] = resolved_value
                    applied.append(action.field)
                else:
                    skipped.append(f"{action.field} (section '{section}' not a dict)")

            elif len(parts) == 3:
                section, middle, field = parts
                if middle.isdigit():
                    # ── list[index].field ──────────────────────────────────
                    idx = int(middle)
                    lst = data.get(section)
                    if isinstance(lst, list) and idx < len(lst) and isinstance(lst[idx], dict):
                        lst[idx][field] = resolved_value
                        applied.append(action.field)
                    else:
                        skipped.append(f"{action.field} (list index {idx} out of range or not a list)")
                else:
                    # ── section.sub_object.field ───────────────────────────
                    section_data = data.get(section)
                    if isinstance(section_data, dict):
                        sub = section_data.get(middle)
                        if isinstance(sub, dict):
                            sub[field] = resolved_value
                            applied.append(action.field)
                        else:
                            skipped.append(f"{action.field} (sub-key '{middle}' not a dict)")
                    else:
                        skipped.append(f"{action.field} (section '{section}' not a dict)")

            else:
                skipped.append(f"{action.field} (path depth > 3 not supported)")

        except Exception as exc:
            logger.warning("Patch error for field '%s': %s", action.field, exc)
            skipped.append(f"{action.field} (exception: {exc})")

    if applied:
        logger.info("Patch: %d action(s) applied — %s", len(applied), applied)
    if skipped:
        logger.warning("Patch: %d action(s) skipped — %s", len(skipped), skipped)

    try:
        return CreditScoringDetailedForm.model_validate(data)
    except ValidationError as exc:
        logger.error(
            "Post-patch validation failed (%d error(s)) — returning original form unchanged.",
            exc.error_count(),
        )
        return form


# ---------------------------------------------------------------------------
# Async agent call wrappers
# call_agent() is synchronous; asyncio.to_thread() offloads each call to the
# default ThreadPoolExecutor so the FastAPI event loop is never blocked.
# ---------------------------------------------------------------------------


async def _call_planner(user_prompt: str, form_summary: str) -> PlannerOutput:
    """
    Ask the Planner Agent which specialists to invoke and what to focus on.

    Falls back to a single all-coverage CTOS task if the agent call fails
    or returns malformed output — ensuring the pipeline always continues.
    """
    payload = (
        "You are a credit form planning agent for Chin Hin Group.\n"
        "Your job: decide which specialist agents are needed to fulfil the officer's request.\n\n"
        "AVAILABLE SPECIALISTS:\n"
        "  bank  — Bank statement fields: end-month balances, deposit patterns, banking conduct.\n"
        "  erp   — Internal trade fields: payment pattern, relationship years, group exposure.\n"
        "  ctos  — CTOS fields: CCRIS, legal cases, blacklist, financials, company background, guarantors.\n\n"
        f"OFFICER REQUEST:\n{user_prompt}\n\n"
        f"CURRENT FORM STATE (summary):\n{form_summary}\n\n"
        "OUTPUT SCHEMA — return STRICT JSON matching this exactly:\n"
        f"{_PLANNER_SCHEMA_STR}\n\n"
        "RULES:\n"
        "- Only include specialists that are genuinely relevant to the officer's request.\n"
        "- Do not include the same specialist more than once.\n"
        "- Each focus_area must be one concise sentence.\n"
        "- Return ONLY the JSON object. No markdown, no explanation text."
    )

    try:
        raw: dict = await asyncio.to_thread(call_agent, _PLANNER_AGENT_ID, payload, True)
        output = PlannerOutput.model_validate(raw)
        logger.info(
            "Planner assigned %d specialist(s): %s",
            len(output.tasks),
            [t.specialist for t in output.tasks],
        )
        return output
    except Exception as exc:
        logger.warning(
            "Planner agent failed (%s) — defaulting to full CTOS specialist.", exc
        )
        return PlannerOutput(
            tasks=[
                SpecialistTask(
                    specialist="ctos",
                    focus_area="Full form review based on the officer's request.",
                )
            ]
        )


async def _call_specialist(
    specialist: str,
    focus_area: str,
    data_slice: dict[str, Any],
    user_prompt: str,
) -> str:
    """
    Call one specialist agent with its focused data slice.

    Specialists return free-text analysis that the Merge Agent interprets.
    Using free text here keeps specialist prompts simple and lets the more
    capable Merge Agent make the final structured decisions.

    Returns an empty string on failure so the Merge Agent can still run
    with whatever other specialists succeeded.
    """
    agent_id = _SPECIALIST_AGENT_IDS.get(specialist, _SPECIALIST_AGENT_IDS["ctos"])
    slice_json = json.dumps(data_slice, indent=2, default=str)

    payload = (
        f"You are a specialist credit analyst for Chin Hin Group.\n"
        f"Your focus area for this task: {focus_area}\n\n"
        f"OFFICER REQUEST:\n{user_prompt}\n\n"
        f"RELEVANT FORM DATA (your section only):\n{slice_json}\n\n"
        "TASK:\n"
        "Analyse the data above in the context of the officer's request.\n"
        "Identify fields that appear incorrect, inconsistent, outdated, or that "
        "the officer is likely asking to change.\n"
        "Be specific: name the exact field paths (using dot notation) and "
        "the values you would recommend.\n\n"
        "Respond with a concise plain-text analysis. Do not output JSON at this stage."
    )

    try:
        result: str = await asyncio.to_thread(call_agent, agent_id, payload, False)
        logger.info(
            "Specialist '%s' completed analysis (%d chars).", specialist, len(str(result))
        )
        return str(result)
    except Exception as exc:
        logger.warning("Specialist '%s' failed: %s", specialist, exc)
        return ""


async def _call_merge(
    user_prompt: str,
    current_data: CreditScoringDetailedForm,
    specialist_reports: dict[str, str],
) -> MergeResult:
    """
    Ask the Merge Agent to synthesise specialist analyses into a patch list.

    The Merge Agent receives:
      - The officer's original request (ground truth for intent)
      - All specialist free-text analyses
      - The full current form (for context on what to leave unchanged)
      - The MergeResult JSON schema (for structured output)

    Returns an empty MergeResult on any failure (safe no-op).
    """
    reports_block = "\n\n".join(
        f"=== {name.upper()} SPECIALIST ===\n{report}"
        for name, report in specialist_reports.items()
        if report.strip()
    ) or "No specialist analyses available."

    full_form_json = json.dumps(
        current_data.model_dump(exclude_none=True), indent=2, default=str
    )

    payload = (
        "You are the Merge Agent for Chin Hin Group's Credit Copilot.\n"
        "Synthesise the specialist analyses below into a minimal, precise patch list "
        "that exactly fulfils the officer's request.\n\n"
        f"OFFICER REQUEST:\n{user_prompt}\n\n"
        f"SPECIALIST ANALYSES:\n{reports_block}\n\n"
        f"FULL CURRENT FORM DATA:\n{full_form_json}\n\n"
        "OUTPUT SCHEMA — return STRICT JSON matching this exactly:\n"
        f"{_MERGE_SCHEMA_STR}\n\n"
        "RULES:\n"
        "1. Only patch fields that directly address the officer's request.\n"
        "2. Field paths must use dot notation — e.g. 'financial_information.net_profit_loss'.\n"
        "   For guarantor lists use: 'guarantor_ccris_profiles.0.guarantor_age_pg'.\n"
        "3. For Literal/banded fields, the value MUST be the exact band string from the schema "
        "   (e.g. '( 1.00 - 1.99 )' not '1.5'). Copy the string character-for-character.\n"
        "4. Set confidence=1.0 only when certain. Use 0.7–0.9 for inferences.\n"
        "5. If nothing needs to change, return {\"actions\": [], \"message\": \"your answer\"}.\n"
        "6. ALWAYS include a 'message' field with a brief, conversational response:\n"
        "   - For data mutations: explain what was changed (e.g. 'Updated the gearing ratio to ...').\n"
        "   - For read-only questions: answer directly from the form data.\n"
        "   - If you cannot help: explain why politely.\n"
        "7. Return ONLY the JSON object. No markdown fences, no explanation text."
    )

    try:
        raw: dict = await asyncio.to_thread(call_agent, _MERGE_AGENT_ID, payload, True)
        result = MergeResult.model_validate(raw)
        logger.info("Merge Agent produced %d action(s).", len(result.actions))
        return result
    except ValidationError as exc:
        logger.warning(
            "Merge Agent output failed validation (%d error(s)) — no changes applied.",
            exc.error_count(),
        )
        return MergeResult()
    except Exception as exc:
        logger.warning("Merge Agent failed (%s) — no changes applied.", exc)
        return MergeResult()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def execute_copilot_pipeline(
    current_data: CreditScoringDetailedForm,
    user_prompt: str,
) -> tuple[CreditScoringDetailedForm, str]:
    """
    Execute the full Planner → Specialists → Merge → Patch pipeline.

    This is the only public entry point for the Data Copilot feature.

    Args:
        current_data: The current state of the credit scoring form (all 12 sections).
        user_prompt:  Natural language instruction from the credit officer.

    Returns:
        A ``(form, message)`` tuple.  ``form`` is a new CreditScoringDetailedForm
        with the Merge Agent's patches applied (or the original if nothing changed).
        ``message`` is a conversational response from the AI explaining what it did
        or answering the officer's question.  The caller is guaranteed a valid form.
    """
    logger.info(
        "=== Copilot pipeline starting — prompt=%r ===", user_prompt[:80]
    )

    try:
        # ── Step 1: Planner ────────────────────────────────────────────────
        form_summary = _build_form_summary(current_data)
        planner_output = await _call_planner(user_prompt, form_summary)

        if not planner_output.tasks:
            logger.info("Planner returned no tasks — form returned unchanged.")
            return current_data, "I wasn't able to determine how to help with that request. Could you rephrase it?"

        # ── Step 2: Parallel specialist execution ──────────────────────────
        # asyncio.gather() runs all specialist coroutines concurrently.
        # Each specialist receives only the slice of data it needs (token-efficient).
        coroutines = [
            _call_specialist(
                specialist=task.specialist,
                focus_area=task.focus_area,
                data_slice=_build_data_slice(current_data, task.specialist),
                user_prompt=user_prompt,
            )
            for task in planner_output.tasks
        ]
        analyses: list[str] = await asyncio.gather(*coroutines)

        specialist_reports: dict[str, str] = {
            task.specialist: analysis
            for task, analysis in zip(planner_output.tasks, analyses)
        }

        # ── Step 3: Merge ──────────────────────────────────────────────────
        merge_result = await _call_merge(user_prompt, current_data, specialist_reports)

        if not merge_result.actions:
            logger.info("Merge Agent produced no actions — form returned unchanged.")
            return current_data, merge_result.message or "No changes were needed for this request."

        # ── Step 4: Patch ──────────────────────────────────────────────────
        updated_form = _apply_merge_actions(current_data, merge_result.actions)

        # If post-patch validation failed, _apply_merge_actions returns the
        # original form object unchanged (same identity).  Override the AI's
        # success message so the officer knows the update didn't stick.
        if updated_form is current_data:
            logger.warning("Patch validation failed — overriding AI success message.")
            return current_data, (
                "\u26a0\ufe0f I attempted to update the field, but the value didn't match "
                "the required dropdown options. Please try again using the exact "
                "option from the dropdown menu."
            )

        logger.info("=== Copilot pipeline complete ===")
        return updated_form, merge_result.message or "Done — form data has been updated."

    except Exception as exc:
        logger.exception(
            "Copilot pipeline encountered an unexpected error (%s) — "
            "returning original form unchanged.",
            exc,
        )
        return current_data, "Sorry, I encountered an error processing your request. Please try again."
