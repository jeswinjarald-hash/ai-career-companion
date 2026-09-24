"""Milestone 3.3 — Interview Preparation Agent.

Orchestrates the deterministic pipeline (always computed first, and the fallback):

    selected job + structured resume/profile + M3.1 skill gap (reused, not re-scored)
    + best-effort M2 match
      -> evidence builder (app.services.interview_evidence, reuses
         customization_evidence.build_evidence_records)
      -> categorized question generation + revision plan
         (app.services.interview_question_service)
      -> optional grounded LLM refinement (app.services.interview_llm), validated
         against the same fabrication checks M3.2 already uses, with a repair
         attempt and a fallback to the deterministic baseline
      -> persisted, versioned InterviewPreparation

No LLM is required — every question the deterministic generator produces already
cites real evidence_ids/job requirements. The LLM path only ever refines wording;
it cannot add, remove, or reclassify questions.
"""

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import CandidateProfile, Resume, StructuredResume
from app.models.career_state import InterviewPreparation as InterviewPreparationRecord
from app.schemas.customization import EvidenceRecord, GenerationMetadata, ValidationResult
from app.schemas.interview_prep import InterviewPreparation, InterviewPreparationSummary, InterviewQuestion, RevisionItem
from app.services.customization_evidence import build_evidence_records
from app.services.customization_validator import check_fabrication, check_fabrication_patterns
from app.services.interview_evidence import InterviewContext, best_effort_m2_match
from app.services.interview_llm import LLMInterviewPrepResponse, rewrite_with_llm
from app.services.interview_question_service import build_preparation_summary, build_revision_plan, generate_questions
from app.services.job_dataset_service import load_job_postings
from app.services.llm_provider import LLMProvider, get_llm_provider
from app.services.skill_gap_service import analyze_skill_gap

logger = logging.getLogger(__name__)

MIN_EVIDENCE_RECORDS = 3


def _get_job(job_id: str):
    job = next((j for j in load_job_postings() if j.job_id == job_id), None)
    if job is None:
        raise LookupError("Job posting not found.")
    return job


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _parser_warning_notice(structured_data: dict) -> str | None:
    warnings = structured_data.get("parser_warnings") or []
    if not warnings:
        return None
    return "Resume structure contains parsing warnings. Review extracted profile before generating interview preparation."


def _apply_llm_refinement(
    questions: list[InterviewQuestion], revision_plan: list[RevisionItem], preparation_summary: str, llm_response: LLMInterviewPrepResponse,
) -> tuple[list[InterviewQuestion], list[RevisionItem], str]:
    refinements_by_index = {r.index: r for r in llm_response.questions}
    for i, question in enumerate(questions):
        refinement = refinements_by_index.get(i)
        if refinement is None:
            continue
        if refinement.question.strip():
            question.question = refinement.question
        if refinement.why_asked.strip():
            question.why_asked = refinement.why_asked
        if refinement.what_interviewer_is_testing.strip():
            question.what_interviewer_is_testing = refinement.what_interviewer_is_testing
        if refinement.preparation_guidance.strip():
            question.preparation_guidance = refinement.preparation_guidance
        if refinement.evidence_ids:
            question.source_evidence_ids = refinement.evidence_ids

    if llm_response.revision_plan and len(llm_response.revision_plan) == len(revision_plan):
        for item, refinement in zip(revision_plan, llm_response.revision_plan, strict=True):
            item.reason = refinement.reason or item.reason
            item.suggested_revision = refinement.suggested_revision or item.suggested_revision
            item.estimated_focus = refinement.estimated_focus or item.estimated_focus

    new_summary = llm_response.preparation_summary.strip() or preparation_summary
    return questions, revision_plan, new_summary


def generate_interview_preparation(
    db: Session, resume_id: int, job_id: str, user_id: int, llm_provider: LLMProvider | None = None,
) -> InterviewPreparation:
    resume = db.get(Resume, resume_id)
    if resume is None:
        raise LookupError("Resume not found.")
    profile = db.get(CandidateProfile, resume.candidate_profile_id)
    if profile is None or profile.user_id != user_id:
        raise LookupError("Resume not found.")
    structured = db.scalar(select(StructuredResume).where(StructuredResume.resume_id == resume_id))
    if structured is None:
        raise ValueError("A structured student profile is required before generating interview preparation.")

    logger.info("interview_prep_started user_id=%s resume_id=%s job_id=%s", user_id, resume_id, job_id)

    evidence_records = build_evidence_records(profile, structured.data)
    parser_notice = _parser_warning_notice(structured.data)
    if len(evidence_records) < MIN_EVIDENCE_RECORDS:
        raise ValueError("Not enough grounded evidence in this resume/profile to generate interview preparation yet.")

    # M3.1's skill gap analysis is reused directly (never re-scored) — this both
    # grounds the skill_gap-category questions and persists as this milestone's
    # normal side effect (matching skill_gap_service's own upsert behavior).
    skill_gap = analyze_skill_gap(db, resume_id, job_id, user_id)
    job = _get_job(job_id)
    m2_match = best_effort_m2_match(db, resume_id, job_id)

    context = InterviewContext(profile, structured.data, job, skill_gap, m2_match, evidence_records)

    questions = generate_questions(context)
    revision_plan = build_revision_plan(context)
    preparation_summary = build_preparation_summary(context)

    unsupported_terms = {item.requirement.lower() for item in (skill_gap.critical_gaps + skill_gap.preferred_gaps) if item.match_type == "missing"}

    provider = llm_provider if llm_provider is not None else get_llm_provider(get_settings())
    llm_response, generation_meta = rewrite_with_llm(
        provider, job, questions, revision_plan, preparation_summary, evidence_records,
        context.supported_terms, context.partial_terms, unsupported_terms,
    )
    if llm_response is not None:
        questions, revision_plan, preparation_summary = _apply_llm_refinement(questions, revision_plan, preparation_summary, llm_response)
        generation = GenerationMetadata(mode="llm", **generation_meta)
    else:
        generation = GenerationMetadata(mode="deterministic_fallback", **generation_meta)

    # Final safety net over whichever text is actually being shipped, regardless of
    # path. Categories whose entire purpose is to discuss a real job requirement or
    # an explicitly-named skill gap (technical/role/skill_gap) are checked only for
    # fabricated metric/leadership/years-of-experience patterns — merely mentioning
    # a job-required or gap skill by name is expected there, not a fabrication.
    # Categories about the candidate's own claims (resume/project/hr) get the full
    # check, including the unsupported-keyword scan.
    warnings: list[str] = []
    removed: list[str] = []
    hit = check_fabrication(preparation_summary, unsupported_terms)
    if hit:
        warnings.append(f'Removed preparation summary: "{preparation_summary}" ({hit}).')
        removed.append(preparation_summary)
        preparation_summary = build_preparation_summary(context)
    kept_questions: list[InterviewQuestion] = []
    for question in questions:
        if question.category in ("technical", "role", "skill_gap"):
            hit = check_fabrication_patterns(question.question) or check_fabrication_patterns(question.preparation_guidance)
        else:
            hit = check_fabrication(question.question, unsupported_terms) or check_fabrication(question.preparation_guidance, unsupported_terms)
        if hit:
            warnings.append(f'Removed question: "{question.question}" ({hit}).')
            removed.append(question.question)
            continue
        kept_questions.append(question)
    questions = kept_questions
    if parser_notice:
        warnings.append(parser_notice)
    validation = ValidationResult(passed=not removed, warnings=warnings, removed_claims=removed)
    status = "ready" if validation.passed else "validation_warning"

    version = (db.scalar(select(func.max(InterviewPreparationRecord.version)).where(
        InterviewPreparationRecord.resume_id == resume_id, InterviewPreparationRecord.job_id == job.job_id,
    )) or 0) + 1

    payload = {
        "job_title": job.job_title, "company": job.company,
        "preparation_summary": preparation_summary,
        "questions": [json.loads(q.model_dump_json()) for q in questions],
        "revision_plan": [json.loads(r.model_dump_json()) for r in revision_plan],
        "evidence": [json.loads(e.model_dump_json()) for e in evidence_records],
        "validation": json.loads(validation.model_dump_json()),
        "generation": json.loads(generation.model_dump_json()),
        "parser_warning_notice": parser_notice,
    }
    record = InterviewPreparationRecord(
        user_id=user_id, resume_id=resume_id, job_id=job.job_id, version=version, status=status,
        source_resume_updated_at=_as_utc(structured.updated_at), data=payload,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    logger.info(
        "interview_prep_completed user_id=%s resume_id=%s job_id=%s prep_id=%s generation_mode=%s question_count=%s warning_count=%s",
        user_id, resume_id, job.job_id, record.id, generation.mode, len(questions), len(validation.warnings),
    )
    return _to_response(record, structured.updated_at)


_LEGACY_GENERATION_METADATA = {
    "mode": "deterministic_fallback", "attempted_llm": False,
    "provider": None, "model": None, "repair_attempted": False,
    "fallback_reason": "generated_before_llm_layer_existed",
}


def _to_response(record: InterviewPreparationRecord, current_resume_updated_at: datetime) -> InterviewPreparation:
    data = record.data
    stale = _as_utc(record.source_resume_updated_at) < _as_utc(current_resume_updated_at)
    return InterviewPreparation(
        id=record.id, resume_id=record.resume_id, job_id=record.job_id,
        job_title=data.get("job_title", ""), company=data.get("company", ""),
        version=record.version, status=record.status, stale=stale,
        parser_warning_notice=data.get("parser_warning_notice"),
        preparation_summary=data.get("preparation_summary", ""),
        questions=[InterviewQuestion.model_validate(q) for q in data.get("questions", [])],
        revision_plan=[RevisionItem.model_validate(r) for r in data.get("revision_plan", [])],
        evidence=[EvidenceRecord.model_validate(e) for e in data.get("evidence", [])],
        validation=ValidationResult.model_validate(data.get("validation", {"passed": True, "warnings": [], "removed_claims": []})),
        generation=GenerationMetadata.model_validate(data.get("generation") or _LEGACY_GENERATION_METADATA),
        created_at=record.created_at, updated_at=record.updated_at,
    )


def get_interview_preparation(db: Session, resume_id: int, prep_id: int, current_resume_updated_at: datetime | None) -> InterviewPreparation | None:
    record = db.get(InterviewPreparationRecord, prep_id)
    if record is None or record.resume_id != resume_id:
        return None
    reference = current_resume_updated_at if current_resume_updated_at is not None else record.source_resume_updated_at
    return _to_response(record, reference)


def list_interview_preparations(db: Session, resume_id: int, job_id: str | None) -> list[InterviewPreparationSummary]:
    statement = select(InterviewPreparationRecord).where(InterviewPreparationRecord.resume_id == resume_id)
    if job_id is not None:
        statement = statement.where(InterviewPreparationRecord.job_id == job_id)
    statement = statement.order_by(InterviewPreparationRecord.job_id, InterviewPreparationRecord.version.desc())
    records = list(db.scalars(statement))
    structured = db.scalar(select(StructuredResume).where(StructuredResume.resume_id == resume_id))
    current_updated_at = structured.updated_at if structured is not None else None
    summaries: list[InterviewPreparationSummary] = []
    for record in records:
        reference = current_updated_at if current_updated_at is not None else record.source_resume_updated_at
        stale = _as_utc(record.source_resume_updated_at) < _as_utc(reference)
        generation_mode = (record.data.get("generation") or _LEGACY_GENERATION_METADATA).get("mode", "deterministic_fallback")
        summaries.append(InterviewPreparationSummary(
            id=record.id, resume_id=record.resume_id, job_id=record.job_id,
            job_title=record.data.get("job_title", ""), company=record.data.get("company", ""),
            version=record.version, status=record.status, stale=stale, generation_mode=generation_mode,
            created_at=record.created_at, updated_at=record.updated_at,
        ))
    return summaries
