"""Milestone 3.3 — optional mock interview answer evaluation.

Stateless by design: each answer is evaluated independently against the question it
answers (no persisted session/answer history — the "mock interview session" is a
frontend-only loop over the already-generated, already-persisted question set).
Deterministic by default (heuristic: does the answer engage with the question's own
`topics_to_review`/evidence, is it substantive); an LLM path is used when configured,
producing richer feedback but validated for fabricated metric/leadership/years-of-
experience patterns (the same check M3.2/M3.3 use elsewhere for those specific
patterns) — the unsupported-keyword check is deliberately not applied here, since
feedback legitimately discusses whatever skills the student's own free-text answer
mentions, including a gap skill a `skill_gap`-category question explicitly asked
about.
"""

import logging

from pydantic import BaseModel, ConfigDict, ValidationError

from app.schemas.customization import GenerationMetadata
from app.schemas.interview_prep import InterviewQuestion, MockAnswerEvaluation
from app.services.customization_validator import check_fabrication_patterns
from app.services.job_matching import normalize_term
from app.services.llm_provider import LLMProvider, LLMUnavailableError, NullLLMProvider
from app.services.skill_gap_evidence import mentions_term

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are giving a student feedback on their answer to a single mock interview question.

You are given the question (with why it's asked and what the interviewer is testing), any real evidence \
that backs the question, and the student's own typed answer. Give constructive, honest feedback.

Rules you must follow exactly:
- Evaluate only what the student actually wrote. Do not invent facts about their skills, projects, or \
experience beyond what is in their answer or the provided evidence.
- Do not assess personality, intelligence, or "fit" — assess the answer's relevance, technical \
correctness (where applicable), structure, use of concrete evidence/examples, and clarity only.
- Do not assign a numeric score.
- Respond with ONLY a single JSON object, no prose, no markdown code fences, in exactly this shape:
{
  "strengths": ["..."],
  "improvements": ["..."],
  "missing_points": ["..."],
  "suggested_structure": "...",
  "grounded_feedback": "..."
}"""


class LLMMockEvaluation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    strengths: list[str] = []
    improvements: list[str] = []
    missing_points: list[str] = []
    suggested_structure: str = ""
    grounded_feedback: str = ""


def _deterministic_evaluation(question: InterviewQuestion, answer: str) -> tuple[list[str], list[str], list[str], str, str]:
    words = answer.split()
    normalized_answer = normalize_term(answer)

    mentioned = [topic for topic in question.topics_to_review if mentions_term(normalize_term(topic), normalized_answer)]
    missing = [topic for topic in question.topics_to_review if topic not in mentioned]

    strengths: list[str] = []
    improvements: list[str] = []

    if len(words) >= 40:
        strengths.append("Your answer is detailed and substantive.")
    elif len(words) < 15:
        improvements.append("Your answer is quite brief — add more specific detail so the interviewer can assess your depth.")

    if mentioned:
        strengths.append(f"You directly addressed: {', '.join(mentioned)}.")
    if missing:
        improvements.append(f"Consider explicitly addressing: {', '.join(missing)}.")

    if question.category in ("hr",):
        suggested_structure = "Structure your answer with STAR: Situation, Task, Action, Result."
    elif question.category in ("technical", "project"):
        suggested_structure = "Structure your answer as: context -> your approach -> outcome -> what you'd do differently."
    else:
        suggested_structure = "Lead with a direct answer, then support it with a specific, concrete example."

    if not strengths:
        strengths.append("You engaged with the question directly.")
    if not improvements:
        improvements.append("Consider adding a concrete example to make your answer more memorable.")

    feedback = (
        f"This question tests: {question.what_interviewer_is_testing} "
        f"Your answer {'covers the key topics well' if not missing else 'could more directly address ' + ', '.join(missing)}."
    )
    return strengths, improvements, missing, suggested_structure, feedback


def evaluate_mock_answer(provider: LLMProvider, question: InterviewQuestion, answer: str) -> MockAnswerEvaluation:
    strengths, improvements, missing, structure, feedback = _deterministic_evaluation(question, answer)
    meta: dict = {"attempted_llm": not isinstance(provider, NullLLMProvider), "provider": provider.name, "model": provider.model, "repair_attempted": False, "fallback_reason": None}

    if isinstance(provider, NullLLMProvider):
        meta["fallback_reason"] = "no_provider_configured"
        return MockAnswerEvaluation(strengths=strengths, improvements=improvements, missing_points=missing, suggested_structure=structure, grounded_feedback=feedback, generation=GenerationMetadata(mode="deterministic_fallback", **meta))

    payload = {
        "question": question.question, "category": question.category,
        "why_asked": question.why_asked, "what_interviewer_is_testing": question.what_interviewer_is_testing,
        "topics_to_review": question.topics_to_review, "student_answer": answer,
    }
    try:
        raw = provider.generate_json(SYSTEM_PROMPT, payload)
        parsed = LLMMockEvaluation.model_validate(raw)
    except (LLMUnavailableError, ValidationError) as exc:
        logger.warning("interview_mock_llm_failed provider=%s error=%s", provider.name, exc)
        meta["fallback_reason"] = f"provider_or_validation_failed: {exc}"
        return MockAnswerEvaluation(strengths=strengths, improvements=improvements, missing_points=missing, suggested_structure=structure, grounded_feedback=feedback, generation=GenerationMetadata(mode="deterministic_fallback", **meta))

    fabrication_hit = check_fabrication_patterns(parsed.grounded_feedback) or next((h for s in parsed.strengths if (h := check_fabrication_patterns(s))), None)
    if fabrication_hit or not parsed.grounded_feedback.strip():
        meta["fallback_reason"] = f"llm_feedback_failed_validation: {fabrication_hit}"
        return MockAnswerEvaluation(strengths=strengths, improvements=improvements, missing_points=missing, suggested_structure=structure, grounded_feedback=feedback, generation=GenerationMetadata(mode="deterministic_fallback", **meta))

    return MockAnswerEvaluation(
        strengths=parsed.strengths or strengths, improvements=parsed.improvements or improvements,
        missing_points=parsed.missing_points or missing, suggested_structure=parsed.suggested_structure or structure,
        grounded_feedback=parsed.grounded_feedback, generation=GenerationMetadata(mode="llm", **meta),
    )
