"""Milestone 3.3 — grounded LLM interview-question enhancement.

Same architecture as `customization_llm.py`: the deterministic question/revision-plan
baseline (`interview_question_service.py`) is always computed first and is the
fallback. When an LLM provider is configured, it is given a restricted, structured
payload — the job, supported/partial/unsupported skill terms, the exact deterministic
questions to refine, and a fixed `allowed_evidence` list with stable `evidence_id`s —
never a free-form prompt. Its JSON response is validated against the same fabrication
checks (`customization_validator.check_fabrication`) plus evidence_id/requirement
existence checks; one repair attempt is made on failure; any further failure (or a
provider-level failure) falls back to the deterministic baseline unchanged.
"""

import logging

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.schemas.customization import EvidenceRecord
from app.schemas.interview_prep import InterviewQuestion, RevisionItem
from app.schemas.job_posting import JobPosting
from app.services.customization_validator import check_fabrication, check_fabrication_patterns
from app.services.llm_provider import LLMProvider, LLMUnavailableError, NullLLMProvider

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an interview-preparation assistant for a student job-application tool.

You are given: a target job, the candidate's supported/partial/unsupported skill classifications \
for that job, a list of deterministically-generated interview questions to refine, a revision plan \
to refine, a preparation summary to refine, and a restricted "allowed_evidence" list — each item has \
a stable evidence_id and real text taken directly from the candidate's own resume/profile.

Rules you must follow exactly:
- You may improve wording, clarity, specificity, and professional tone of questions, guidance text, \
the preparation summary, and revision-plan entries.
- You may NOT invent or imply that the candidate has any skill, technology, tool, metric/percentage, \
year of experience, team size, leadership role, company name, certification, or achievement that is \
not explicitly present in the allowed_evidence text you were given.
- You may NOT phrase a question or its guidance as presupposing hands-on experience with a skill in \
unsupported_skills_do_not_use — those may only be asked about conceptually, or explicitly framed as \
a gap the candidate should prepare for (never as something they already have hands-on experience with).
- Every question and revision-plan entry that cites specific evidence must include the evidence_id(s) \
(from allowed_evidence only) that support it — do not cite an evidence_id that wasn't offered.
- You must keep the exact same set of questions (by index) and the exact same category/difficulty for \
each — you are refining wording and guidance quality, not changing which questions exist or reclassifying them.
- Respond with ONLY a single JSON object, no prose, no markdown code fences, in exactly this shape:
{
  "preparation_summary": "...",
  "questions": [
    {"index": 0, "question": "...", "why_asked": "...", "what_interviewer_is_testing": "...", "preparation_guidance": "...", "evidence_ids": ["EV-001"]}
  ],
  "revision_plan": [
    {"topic": "...", "reason": "...", "suggested_revision": "...", "estimated_focus": "..."}
  ]
}
- "questions" must contain exactly one entry per index in the input questions list, using the \
identical index number.
- "revision_plan" must contain one entry per input revision-plan topic, in the same order."""


class LLMQuestionRefinement(BaseModel):
    model_config = ConfigDict(extra="ignore")

    index: int
    question: str
    why_asked: str
    what_interviewer_is_testing: str
    preparation_guidance: str
    evidence_ids: list[str] = Field(default_factory=list)


class LLMRevisionRefinement(BaseModel):
    model_config = ConfigDict(extra="ignore")

    topic: str
    reason: str
    suggested_revision: str
    estimated_focus: str


class LLMInterviewPrepResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    preparation_summary: str
    questions: list[LLMQuestionRefinement] = Field(default_factory=list)
    revision_plan: list[LLMRevisionRefinement] = Field(default_factory=list)


def build_grounded_llm_input(
    job: JobPosting,
    questions: list[InterviewQuestion],
    revision_plan: list[RevisionItem],
    preparation_summary: str,
    evidence_records: list[EvidenceRecord],
    supported_terms: set[str],
    partial_terms: set[str],
    unsupported_terms: set[str],
) -> tuple[dict, set[str]]:
    allowed_evidence = [
        {"evidence_id": e.evidence_id, "source_path": e.source_path, "source_type": e.source_type, "text": e.raw_text, "confidence": e.confidence_type}
        for e in evidence_records
    ]
    allowed_ids = {e.evidence_id for e in evidence_records}

    payload = {
        "job": {"title": job.job_title, "company": job.company, "domain": job.domain, "required_skills": job.required_skills, "preferred_skills": job.preferred_skills},
        "supported_skills": sorted(supported_terms),
        "partial_or_learning_skills": sorted(partial_terms),
        "unsupported_skills_do_not_use": sorted(unsupported_terms),
        "preparation_summary": preparation_summary,
        "questions": [
            {
                "index": i, "category": q.category, "difficulty": q.difficulty, "question": q.question,
                "why_asked": q.why_asked, "what_interviewer_is_testing": q.what_interviewer_is_testing,
                "preparation_guidance": q.preparation_guidance, "existing_evidence_ids": q.source_evidence_ids,
            }
            for i, q in enumerate(questions)
        ],
        "revision_plan": [{"topic": r.topic, "reason": r.reason, "suggested_revision": r.suggested_revision, "estimated_focus": r.estimated_focus} for r in revision_plan],
        "allowed_evidence": allowed_evidence,
    }
    return payload, allowed_ids


# Categories whose entire purpose is to discuss a real job requirement or an
# explicitly-named skill gap — merely mentioning a job-required/preferred or gap
# skill by name is expected and correct here, not a fabrication. Only categories
# describing the candidate's own claims (resume/project/hr) get the stricter
# unsupported-keyword check; the revision plan is inherently about topics/skills to
# study, so it uses the same relaxed check as those categories.
_UNRESTRICTED_CATEGORIES = {"technical", "role", "skill_gap"}


def validate_llm_response(
    response: LLMInterviewPrepResponse,
    allowed_evidence_ids: set[str],
    original_questions: list[InterviewQuestion],
    unsupported_terms: set[str],
) -> list[str]:
    violations: list[str] = []
    expected_question_count = len(original_questions)

    if not response.preparation_summary.strip():
        violations.append("preparation_summary must not be empty")
    else:
        hit = check_fabrication(response.preparation_summary, unsupported_terms)
        if hit:
            violations.append(f"preparation_summary: {hit}")

    seen_indices = {q.index for q in response.questions}
    expected_indices = set(range(expected_question_count))
    if seen_indices != expected_indices:
        violations.append(f"questions must cover exactly indices 0..{expected_question_count - 1}, got {sorted(seen_indices)}")

    for q in response.questions:
        category = original_questions[q.index].category if 0 <= q.index < expected_question_count else None
        unrestricted = category in _UNRESTRICTED_CATEGORIES
        for field_name, value in (("question", q.question), ("why_asked", q.why_asked), ("what_interviewer_is_testing", q.what_interviewer_is_testing), ("preparation_guidance", q.preparation_guidance)):
            if not value.strip():
                violations.append(f"question[{q.index}].{field_name} must not be empty")
                continue
            hit = check_fabrication_patterns(value) if unrestricted else check_fabrication(value, unsupported_terms)
            if hit:
                violations.append(f"question[{q.index}].{field_name}: {hit}")
        unknown = [i for i in q.evidence_ids if i not in allowed_evidence_ids]
        if unknown:
            violations.append(f"question[{q.index}] cites unknown evidence_ids: {unknown}")

    for i, r in enumerate(response.revision_plan):
        for field_name, value in (("reason", r.reason), ("suggested_revision", r.suggested_revision), ("estimated_focus", r.estimated_focus)):
            hit = check_fabrication_patterns(value)
            if hit:
                violations.append(f"revision_plan[{i}].{field_name}: {hit}")

    return violations


def rewrite_with_llm(
    provider: LLMProvider,
    job: JobPosting,
    questions: list[InterviewQuestion],
    revision_plan: list[RevisionItem],
    preparation_summary: str,
    evidence_records: list[EvidenceRecord],
    supported_terms: set[str],
    partial_terms: set[str],
    unsupported_terms: set[str],
) -> tuple[LLMInterviewPrepResponse | None, dict]:
    meta: dict = {
        "attempted_llm": not isinstance(provider, NullLLMProvider),
        "provider": provider.name, "model": provider.model,
        "repair_attempted": False, "fallback_reason": None,
    }
    if isinstance(provider, NullLLMProvider):
        meta["fallback_reason"] = "no_provider_configured"
        return None, meta

    payload, allowed_ids = build_grounded_llm_input(job, questions, revision_plan, preparation_summary, evidence_records, supported_terms, partial_terms, unsupported_terms)

    try:
        raw = provider.generate_json(SYSTEM_PROMPT, payload)
    except LLMUnavailableError as exc:
        logger.warning("interview_llm_provider_unavailable provider=%s error=%s", provider.name, exc)
        meta["fallback_reason"] = f"provider_unavailable: {exc}"
        return None, meta

    response, violations = _parse_and_validate(raw, allowed_ids, questions, unsupported_terms)

    if violations:
        meta["repair_attempted"] = True
        logger.info("interview_llm_repair_attempted provider=%s violation_count=%s", provider.name, len(violations))
        try:
            repaired_raw = provider.generate_json(SYSTEM_PROMPT, {**payload, "previous_response": raw, "violations_to_fix": violations})
        except LLMUnavailableError as exc:
            meta["fallback_reason"] = f"repair_call_failed: {exc}"
            return None, meta
        response, violations = _parse_and_validate(repaired_raw, allowed_ids, questions, unsupported_terms)

    if violations:
        logger.warning("interview_llm_validation_failed_after_repair provider=%s violation_count=%s", provider.name, len(violations))
        meta["fallback_reason"] = f"validation_failed: {violations[:5]}"
        return None, meta

    return response, meta


def _parse_and_validate(
    raw: dict, allowed_ids: set[str], original_questions: list[InterviewQuestion], unsupported_terms: set[str]
) -> tuple[LLMInterviewPrepResponse | None, list[str]]:
    try:
        response = LLMInterviewPrepResponse.model_validate(raw)
    except ValidationError as exc:
        return None, [f"response did not match the required JSON schema: {exc}"]
    return response, validate_llm_response(response, allowed_ids, original_questions, unsupported_terms)
