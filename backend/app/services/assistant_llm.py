"""Milestone 3.4 — grounded LLM response synthesis for the Career Assistant.

Mirrors `app.services.interview_llm`/`customization_llm` exactly: the model is given
a restricted, structured payload (the intent, the already-computed grounded facts,
the deterministic baseline answer, recent conversation turns, and an explicit
unsupported-skills list) and may only reword/naturally phrase the baseline answer —
never invent a fact, score, or claim not present in `facts`. Validated with a
repair-once-then-fallback control flow identical to M3.2/M3.3's.
"""

import json
import logging

from pydantic import BaseModel, ConfigDict, ValidationError

from app.schemas.customization import GenerationMetadata
from app.services.customization_validator import check_fabrication, check_fabrication_patterns_excluding_metrics
from app.services.llm_provider import LLMProvider, LLMUnavailableError, NullLLMProvider

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the AI Career Companion's conversational career assistant, helping a student \
discuss career-opportunity recommendations (internships, entry-level jobs, graduate programs, trainee and \
apprenticeship roles), skill gaps, resume customization, and interview preparation.

You are given: the detected intent, a "baseline_answer" (an already-correct, fully grounded answer \
computed deterministically from real data), a "facts" object (the only real data you may reference), \
the student's message, and recent conversation turns for continuity.

Rules you must follow exactly:
- You may reword/rephrase/naturally connect baseline_answer to the conversation. You may NOT change what \
it claims, add a fact not present in "facts", invent a skill, score, job detail, or candidate experience, \
or contradict baseline_answer.
- Never state or imply that the student has demonstrated a skill listed in \
"unsupported_skills_do_not_use" — if you mention one of these skills, phrase it explicitly as a gap, \
never as something the student already has.
- Never invent a numeric score, percentage, or metric not present in "facts".
- Never declare one job "better" than another — you may only state which one aligns with more of the \
student's currently-demonstrated requirements, and only if "facts" actually shows that.
- Never change or assume an opportunity's type (internship, entry-level job, graduate role, trainee, \
apprenticeship) — use exactly what "facts" states, and never call an opportunity an "internship" unless \
"facts" says it actually is one.
- Respond with ONLY a single JSON object, no prose, no markdown code fences, in exactly this shape:
{"message": "..."}"""


class LLMAssistantResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    message: str = ""


def build_grounded_llm_input(
    intent: str, facts: dict, baseline_answer: str, user_message: str,
    recent_messages: list[dict], unsupported_terms: set[str],
) -> dict:
    return {
        "intent": intent,
        "baseline_answer": baseline_answer,
        "facts": facts,
        "unsupported_skills_do_not_use": sorted(unsupported_terms),
        "student_message": user_message,
        "recent_messages": recent_messages[-6:],
    }


def _validate(message: str, grounding_mode: str, unsupported_terms: set[str]) -> str | None:
    if not message.strip():
        return "empty message"
    if grounding_mode == "scored":
        return check_fabrication_patterns_excluding_metrics(message)
    return check_fabrication(message, unsupported_terms)


def _parse_and_validate(raw: dict, grounding_mode: str, unsupported_terms: set[str]) -> tuple[LLMAssistantResponse | None, str | None]:
    try:
        parsed = LLMAssistantResponse.model_validate(raw)
    except ValidationError as exc:
        return None, f"schema validation failed: {exc}"
    violation = _validate(parsed.message, grounding_mode, unsupported_terms)
    if violation:
        return None, violation
    return parsed, None


def synthesize_response(
    provider: LLMProvider, intent: str, facts: dict, baseline_answer: str, user_message: str,
    recent_messages: list[dict], unsupported_terms: set[str], grounding_mode: str,
) -> tuple[str | None, dict]:
    """Returns (synthesized_message_or_None, generation_meta). `None` means: use
    `baseline_answer` as-is (the caller sets `mode="deterministic_fallback"`).
    """
    meta: dict = {
        "attempted_llm": not isinstance(provider, NullLLMProvider),
        "provider": provider.name, "model": provider.model,
        "repair_attempted": False, "fallback_reason": None,
    }
    if isinstance(provider, NullLLMProvider):
        meta["fallback_reason"] = "no_provider_configured"
        return None, meta

    payload = build_grounded_llm_input(intent, facts, baseline_answer, user_message, recent_messages, unsupported_terms)
    try:
        raw = provider.generate_json(SYSTEM_PROMPT, payload)
    except LLMUnavailableError as exc:
        logger.warning("assistant_llm_provider_failed provider=%s error=%s", provider.name, exc)
        meta["fallback_reason"] = f"provider_failed: {exc}"
        return None, meta

    parsed, violation = _parse_and_validate(raw, grounding_mode, unsupported_terms)
    if parsed is not None:
        return parsed.message, meta

    meta["repair_attempted"] = True
    repair_payload = {**payload, "previous_response": raw, "violations": [violation]}
    try:
        raw_repair = provider.generate_json(SYSTEM_PROMPT, repair_payload)
    except LLMUnavailableError as exc:
        logger.warning("assistant_llm_repair_failed provider=%s error=%s", provider.name, exc)
        meta["fallback_reason"] = f"provider_failed_on_repair: {exc}"
        return None, meta

    parsed_repair, violation_repair = _parse_and_validate(raw_repair, grounding_mode, unsupported_terms)
    if parsed_repair is not None:
        return parsed_repair.message, meta

    meta["fallback_reason"] = f"repair_failed: {violation_repair}"
    return None, meta
