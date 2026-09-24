"""Milestone 3.2 — Resume & Cover Letter Customization Agent.

Orchestrates the deterministic pipeline:

    original resume + structured profile + selected job + M2 match (if available)
      -> evidence builder (app.services.customization_evidence)
      -> job keyword classification, reusing M3.1's matcher (app.services.customization_keywords)
      -> relevance-ranked, grounded resume customization (this module)
      -> grounded cover letter (app.services.cover_letter_service)
      -> unsupported claim validation (app.services.customization_validator)
      -> persisted, versioned ApplicationCustomization

No LLM is used, matching this project's M2/M3.1 convention. "Rewriting" a bullet
never invents new wording: `tailored_text` is always the original text with only
whitespace/punctuation normalization applied, so every resume claim is byte-for-byte
traceable to its `source_path` and `introduced_claims` is always empty for resume
content. The only places new sentences are composed (the professional summary and
the cover letter) are template-assembled strictly from known structured fields and
are the ones the claim validator actually has real work to do on.
"""

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import CandidateProfile, Resume, StructuredResume
from app.models.career_state import ApplicationCustomization as ApplicationCustomizationRecord
from app.schemas.customization import (
    ApplicationCustomization,
    ApplicationCustomizationEditPayload,
    ApplicationCustomizationSummary,
    CoverLetterSentence,
    EvidenceRecord,
    GenerationMetadata,
    KeywordClassification,
    TailoredBullet,
    TailoredEducationEntry,
    TailoredProject,
    TailoredResume,
    UserEdits,
    ValidationResult,
)
from app.schemas.job_posting import JobPosting
from app.services.cover_letter_service import build_cover_letter
from app.services.customization_evidence import build_evidence_records, is_category_label, join_terms, relevance_score, short_education_phrase, summarize_clause
from app.services.customization_keywords import classify_job_keywords, partial_terms, supported_terms, unsupported_terms
from app.services.customization_llm import LLMRewriteResponse, rewrite_with_llm
from app.services.customization_validator import build_validation_result, validate_cover_letter, validate_summary
from app.services.job_dataset_service import load_job_postings
from app.services.job_matching import normalize_term
from app.services.llm_provider import LLMProvider, get_llm_provider
from app.services.skill_gap_evidence import mentions_term

logger = logging.getLogger(__name__)

MIN_EVIDENCE_RECORDS = 3


class CustomizationError(Exception):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _get_job(job_id: str) -> JobPosting:
    job = next((job for job in load_job_postings() if job.job_id == job_id), None)
    if job is None:
        raise LookupError("Job posting not found.")
    return job


def _normalize_bullet(text: str) -> str:
    stripped = " ".join(text.split())
    if not stripped:
        return stripped
    if stripped[-1] not in ".!?":
        stripped += "."
    return stripped[0].upper() + stripped[1:]


def _keyword_display_map(classifications: list[KeywordClassification]) -> dict[str, str]:
    return {normalize_term(c.keyword): c.keyword for c in classifications}


def _keywords_used(text: str, term_pool: set[str], display: dict[str, str]) -> list[str]:
    normalized_text = normalize_term(text)
    found = [term for term in term_pool if mentions_term(term, normalized_text)]
    return sorted({display.get(term, term) for term in found})


def _build_summary(
    profile: CandidateProfile, structured_data: dict, priority_terms: list[str], top_project: TailoredProject | None,
) -> tuple[str, list[str]]:
    """A concise 2-3 sentence professional summary — never the raw education line
    (institution/CGPA/coursework), and never every extracted skill dumped in a row.
    Sentence 1 states education (degree/field only) + the top few job-relevant
    skills the student actually has. Sentence 2, when a relevant project exists,
    names it and states its most job-relevant technologies — never the full project
    description.
    """
    education_phrase, sources = short_education_phrase(profile, structured_data)

    sentences = [f"{education_phrase} student with hands-on experience in {join_terms(priority_terms)}." if priority_terms else f"{education_phrase} student."]

    if top_project is not None:
        project_skills = [kw for kw in top_project.job_keywords_used if normalize_term(kw) in {normalize_term(t) for t in priority_terms}] or top_project.job_keywords_used
        if project_skills:
            sentences.append(f"Applied {join_terms(project_skills[:3])} in building {top_project.title}.")
        else:
            sentences.append(f"Built {top_project.title} as a hands-on application of these skills.")
        sources.append(top_project.source_path)

    return " ".join(sentences), sources


def _build_tailored_resume(
    profile: CandidateProfile,
    structured_data: dict,
    classifications: list[KeywordClassification],
) -> TailoredResume:
    supported = supported_terms(classifications)
    partial = partial_terms(classifications)
    display = _keyword_display_map(classifications)
    relevant_pool = supported | partial

    # Skills: reorder only — never add a job's missing skill to the list. A stable
    # sort keeps the student's original relative ordering within each relevance tier.
    # Category-header labels (e.g. "Programming", "Backend") that M1's intentionally
    # permissive Skills-section parser can preserve verbatim (see
    # `customization_evidence.CATEGORY_LABEL_TERMS`) are excluded here — the
    # unfiltered original list is still visible via the "original order" display,
    # so nothing about the source resume itself is hidden, only this tailored/
    # exported view is cleaned up.
    original_skills = [str(s) for s in structured_data.get("skills", []) or [] if not is_category_label(str(s))]
    ranked_skills = sorted(
        enumerate(original_skills),
        key=lambda pair: (0 if normalize_term(pair[1]) in supported else 1 if normalize_term(pair[1]) in partial else 2, pair[0]),
    )
    skills = [name for _index, name in ranked_skills]

    priority_skill_names = [name for _index, name in ranked_skills if normalize_term(name) in supported][:4]
    if not priority_skill_names:
        priority_skill_names = skills[:3]

    education = [
        TailoredEducationEntry(raw_text=str(entry.get("raw_text") or ""), source_path=f"structured_resume.education[{index}].raw_text")
        for index, entry in enumerate(structured_data.get("education", []) or []) if isinstance(entry, dict) and entry.get("raw_text")
    ]

    projects_raw = [p for p in structured_data.get("projects", []) or [] if isinstance(p, dict)]
    scored_projects = [
        (index, project, relevance_score(str(project.get("raw_text") or project.get("description") or ""), project.get("technologies", []) or [], supported, partial))
        for index, project in enumerate(projects_raw)
    ]
    scored_projects.sort(key=lambda item: (-item[2], item[0]))
    projects: list[TailoredProject] = []
    for rank, (index, project, _score) in enumerate(scored_projects, start=1):
        # `raw_text` on a project is "{title} - {description}" (see
        # structured_resume.py) — since `title` is rendered separately here,
        # `description` (the body alone) is used to avoid duplicating the title.
        raw_text = str(project.get("description") or project.get("raw_text") or project.get("title") or "").strip()
        projects.append(TailoredProject(
            title=str(project.get("title") or "Project").strip() or "Project",
            original_text=raw_text,
            tailored_text=_normalize_bullet(raw_text),
            technologies=[str(t) for t in project.get("technologies", []) or []],
            source_path=f"structured_resume.projects[{index}].raw_text",
            relevance_rank=rank,
            job_keywords_used=_keywords_used(raw_text, relevant_pool, display),
        ))

    summary, summary_sources = _build_summary(profile, structured_data, priority_skill_names, projects[0] if projects else None)

    def _bullets(key: str) -> list[TailoredBullet]:
        bullets: list[TailoredBullet] = []
        for index, item in enumerate(structured_data.get(key, []) or []):
            if not isinstance(item, dict):
                continue
            raw_text = str(item.get("raw_text") or "").strip()
            if not raw_text:
                continue
            bullets.append(TailoredBullet(
                original_text=raw_text, tailored_text=_normalize_bullet(raw_text),
                source_path=f"structured_resume.{key}[{index}].raw_text",
                job_keywords_used=_keywords_used(raw_text, relevant_pool, display),
            ))
        return bullets

    certifications = [str(item.get("raw_text") or "").strip() for item in structured_data.get("certifications", []) or [] if isinstance(item, dict) and item.get("raw_text")]
    achievements = [str(item.get("raw_text") or "").strip() for item in structured_data.get("achievements", []) or [] if isinstance(item, dict) and item.get("raw_text")]

    return TailoredResume(
        header=str(structured_data.get("header") or ""),
        summary=summary, summary_sources=summary_sources,
        skills=skills, education=education, projects=projects,
        experience=_bullets("experience"), internships=_bullets("internships"),
        certifications=certifications, achievements=achievements,
    )


def _parser_warning_notice(structured_data: dict) -> str | None:
    warnings = structured_data.get("parser_warnings") or []
    if not warnings:
        return None
    return "Resume structure contains parsing warnings. Review extracted profile before customization."


def _backfill_evidence_ids(
    tailored_resume: TailoredResume, cover_letter_sentences: list[CoverLetterSentence], evidence_records: list[EvidenceRecord],
) -> None:
    """Fills in `evidence_ids` for the deterministic baseline, before any LLM rewrite
    runs: a deterministic bullet's text *is* its own evidence record (same
    `source_path`), so the frontend's "Supported by" provenance UI has real data to
    show even when no LLM is configured. The LLM path overwrites these with its own
    (already-validated) citations for whatever it actually rewrites.
    """
    ids_by_path: dict[str, list[str]] = {}
    for record in evidence_records:
        ids_by_path.setdefault(record.source_path, []).append(record.evidence_id)

    for project in tailored_resume.projects:
        project.evidence_ids = ids_by_path.get(project.source_path, [])
    for bullet in tailored_resume.experience + tailored_resume.internships:
        bullet.evidence_ids = ids_by_path.get(bullet.source_path, [])
    for sentence in cover_letter_sentences:
        ids: list[str] = []
        for path in sentence.sources:
            ids.extend(ids_by_path.get(path, []))
        sentence.evidence_ids = ids


def _apply_llm_rewrite(
    tailored_resume: TailoredResume,
    cover_letter_sentences: list[CoverLetterSentence],
    llm_response: LLMRewriteResponse,
    evidence_records: list[EvidenceRecord],
) -> tuple[TailoredResume, list[CoverLetterSentence]]:
    """Merges a validated LLM rewrite onto the deterministic baseline. Only
    `tailored_text`/`summary`/cover-letter text and their cited evidence change —
    `original_text`, `source_path`, `technologies`, and `relevance_rank` are always
    kept from the deterministic pass, so provenance and ranking stay intact even
    when the wording is LLM-rewritten.
    """
    path_by_evidence_id = {e.evidence_id: e.source_path for e in evidence_records}

    def _to_source_paths(evidence_ids: list[str]) -> list[str]:
        return [path_by_evidence_id[eid] for eid in evidence_ids if eid in path_by_evidence_id]

    bullet_map = {b.source_path: b for b in llm_response.bullets}
    for project in tailored_resume.projects:
        rewrite = bullet_map.get(project.source_path)
        if rewrite is None or not rewrite.rewritten_text.strip():
            continue
        project.tailored_text = rewrite.rewritten_text
        project.evidence_ids = rewrite.evidence_ids
        if rewrite.job_keywords_used:
            project.job_keywords_used = sorted(set(project.job_keywords_used) | set(rewrite.job_keywords_used))
    for bullet in tailored_resume.experience + tailored_resume.internships:
        rewrite = bullet_map.get(bullet.source_path)
        if rewrite is None or not rewrite.rewritten_text.strip():
            continue
        bullet.tailored_text = rewrite.rewritten_text
        bullet.evidence_ids = rewrite.evidence_ids
        if rewrite.job_keywords_used:
            bullet.job_keywords_used = sorted(set(bullet.job_keywords_used) | set(rewrite.job_keywords_used))

    if llm_response.summary.strip():
        tailored_resume.summary = llm_response.summary
        tailored_resume.summary_sources = _to_source_paths(llm_response.summary_evidence_ids) or tailored_resume.summary_sources

    new_cover_letter = [
        CoverLetterSentence(text=p.text, sources=_to_source_paths(p.evidence_ids), evidence_ids=p.evidence_ids)
        for p in llm_response.cover_letter_paragraphs if p.text.strip()
    ] or cover_letter_sentences

    return tailored_resume, new_cover_letter


def generate_customization(
    db: Session, resume_id: int, job_id: str, user_id: int, llm_provider: LLMProvider | None = None,
) -> ApplicationCustomization:
    resume = db.get(Resume, resume_id)
    if resume is None:
        raise LookupError("Resume not found.")
    profile = db.get(CandidateProfile, resume.candidate_profile_id)
    if profile is None or profile.user_id != user_id:
        raise LookupError("Resume not found.")
    structured = db.scalar(select(StructuredResume).where(StructuredResume.resume_id == resume_id))
    if structured is None:
        raise ValueError("A structured student profile is required before generating application materials.")
    job = _get_job(job_id)

    logger.info("customization_started user_id=%s resume_id=%s job_id=%s", user_id, resume_id, job.job_id)

    evidence_records = build_evidence_records(profile, structured.data)
    parser_notice = _parser_warning_notice(structured.data)
    if len(evidence_records) < MIN_EVIDENCE_RECORDS:
        raise ValueError("Not enough grounded evidence in this resume/profile to generate application materials yet.")

    classifications = classify_job_keywords(profile, structured.data, job, evidence_records)
    tailored_resume = _build_tailored_resume(profile, structured.data, classifications)
    cover_letter_sentences = build_cover_letter(profile, structured.data, job, evidence_records, classifications)
    _backfill_evidence_ids(tailored_resume, cover_letter_sentences, evidence_records)
    unsupported = unsupported_terms(classifications)

    # The deterministic pipeline above is always computed in full first — the LLM is
    # strictly an optional enhancement layer applied on top of it, never a
    # replacement the request depends on. A repair-failed/unavailable/misconfigured
    # provider always leaves the fully-grounded deterministic result in place.
    provider = llm_provider if llm_provider is not None else get_llm_provider(get_settings())
    llm_response, generation_meta = rewrite_with_llm(provider, job, classifications, evidence_records, tailored_resume, unsupported)
    if llm_response is not None:
        tailored_resume, cover_letter_sentences = _apply_llm_rewrite(tailored_resume, cover_letter_sentences, llm_response, evidence_records)
        generation = GenerationMetadata(mode="llm", **generation_meta)
    else:
        generation = GenerationMetadata(mode="deterministic_fallback", **generation_meta)

    # The existing validator always runs last, over whichever text is actually being
    # shipped (deterministic or LLM-rewritten) — a genuine final safety net, not
    # bypassed just because the LLM path claims to have already checked itself.
    validated_summary, summary_warnings, summary_removed = validate_summary(tailored_resume.summary, unsupported)
    tailored_resume.summary = validated_summary
    validated_letter, letter_warnings, letter_removed = validate_cover_letter(cover_letter_sentences, unsupported)
    validation = build_validation_result(summary_warnings, summary_removed, letter_warnings, letter_removed, parser_notice)

    cover_letter_text = "\n\n".join(sentence.text for sentence in validated_letter)
    status = "ready" if validation.passed else "validation_warning"

    version = (db.scalar(select(func.max(ApplicationCustomizationRecord.version)).where(
        ApplicationCustomizationRecord.resume_id == resume_id, ApplicationCustomizationRecord.job_id == job.job_id,
    )) or 0) + 1

    payload = {
        "job_title": job.job_title,
        "company": job.company,
        "evidence": [json.loads(e.model_dump_json()) for e in evidence_records],
        "keyword_classification": [json.loads(c.model_dump_json()) for c in classifications],
        "tailored_resume": json.loads(tailored_resume.model_dump_json()),
        "cover_letter": [json.loads(s.model_dump_json()) for s in validated_letter],
        "cover_letter_text": cover_letter_text,
        "validation": json.loads(validation.model_dump_json()),
        "generation": json.loads(generation.model_dump_json()),
        "user_edits": json.loads(UserEdits().model_dump_json()),
        "parser_warning_notice": parser_notice,
    }
    record = ApplicationCustomizationRecord(
        user_id=user_id, resume_id=resume_id, job_id=job.job_id, version=version, status=status,
        source_resume_updated_at=_as_utc(structured.updated_at), data=payload,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    logger.info(
        "customization_completed user_id=%s resume_id=%s job_id=%s customization_id=%s generation_mode=%s supported_keyword_count=%s warning_count=%s",
        user_id, resume_id, job.job_id, record.id, generation.mode, len(supported_terms(classifications)), len(validation.warnings),
    )
    return _to_response(record, structured.updated_at)


# Records written before this LLM-layer upgrade have no "generation" key at all —
# they were produced entirely by the (still-existing) deterministic pipeline.
_LEGACY_GENERATION_METADATA = {
    "mode": "deterministic_fallback", "attempted_llm": False,
    "provider": None, "model": None, "repair_attempted": False,
    "fallback_reason": "generated_before_llm_layer_existed",
}


def _to_response(record: ApplicationCustomizationRecord, current_resume_updated_at: datetime) -> ApplicationCustomization:
    data = record.data
    stale = _as_utc(record.source_resume_updated_at) < _as_utc(current_resume_updated_at)
    return ApplicationCustomization(
        id=record.id, resume_id=record.resume_id, job_id=record.job_id,
        job_title=data.get("job_title", ""), company=data.get("company", ""),
        version=record.version, status=record.status, stale=stale,
        parser_warning_notice=data.get("parser_warning_notice"),
        evidence=[EvidenceRecord.model_validate(e) for e in data.get("evidence", [])],
        keyword_classification=[KeywordClassification.model_validate(c) for c in data.get("keyword_classification", [])],
        tailored_resume=TailoredResume.model_validate(data.get("tailored_resume", {})),
        cover_letter=[CoverLetterSentence.model_validate(s) for s in data.get("cover_letter", [])],
        cover_letter_text=data.get("cover_letter_text", ""),
        validation=ValidationResult.model_validate(data.get("validation", {"passed": True, "warnings": [], "removed_claims": []})),
        generation=GenerationMetadata.model_validate(data.get("generation") or _LEGACY_GENERATION_METADATA),
        user_edits=UserEdits.model_validate(data.get("user_edits", {})),
        created_at=record.created_at, updated_at=record.updated_at,
    )


def get_customization(db: Session, resume_id: int, customization_id: int, current_resume_updated_at: datetime | None) -> ApplicationCustomization | None:
    record = db.get(ApplicationCustomizationRecord, customization_id)
    if record is None or record.resume_id != resume_id:
        return None
    reference = current_resume_updated_at if current_resume_updated_at is not None else record.source_resume_updated_at
    return _to_response(record, reference)


def list_customizations(db: Session, resume_id: int, job_id: str | None) -> list[ApplicationCustomizationSummary]:
    statement = select(ApplicationCustomizationRecord).where(ApplicationCustomizationRecord.resume_id == resume_id)
    if job_id is not None:
        statement = statement.where(ApplicationCustomizationRecord.job_id == job_id)
    statement = statement.order_by(ApplicationCustomizationRecord.job_id, ApplicationCustomizationRecord.version.desc())
    records = list(db.scalars(statement))
    structured = db.scalar(select(StructuredResume).where(StructuredResume.resume_id == resume_id))
    current_updated_at = structured.updated_at if structured is not None else None
    summaries: list[ApplicationCustomizationSummary] = []
    for record in records:
        reference = current_updated_at if current_updated_at is not None else record.source_resume_updated_at
        stale = _as_utc(record.source_resume_updated_at) < _as_utc(reference)
        generation_mode = (record.data.get("generation") or _LEGACY_GENERATION_METADATA).get("mode", "deterministic_fallback")
        summaries.append(ApplicationCustomizationSummary(
            id=record.id, resume_id=record.resume_id, job_id=record.job_id,
            job_title=record.data.get("job_title", ""), company=record.data.get("company", ""),
            version=record.version, status=record.status, stale=stale, generation_mode=generation_mode,
            created_at=record.created_at, updated_at=record.updated_at,
        ))
    return summaries


def apply_user_edits(db: Session, resume_id: int, customization_id: int, payload: ApplicationCustomizationEditPayload) -> ApplicationCustomization | None:
    record = db.get(ApplicationCustomizationRecord, customization_id)
    if record is None or record.resume_id != resume_id:
        return None

    data = dict(record.data)
    user_edits = dict(data.get("user_edits") or {})
    edited_fields = set(user_edits.get("edited_fields") or [])

    if payload.summary is not None:
        data["tailored_resume"] = {**data.get("tailored_resume", {}), "summary": payload.summary}
        user_edits["summary"] = payload.summary
        edited_fields.add("summary")
    if payload.cover_letter_text is not None:
        data["cover_letter_text"] = payload.cover_letter_text
        user_edits["cover_letter_text"] = payload.cover_letter_text
        edited_fields.add("cover_letter_text")
    if payload.bullet_edits:
        bullet_edits = dict(user_edits.get("bullet_edits") or {})
        bullet_edits.update(payload.bullet_edits)
        user_edits["bullet_edits"] = bullet_edits
        tailored = dict(data.get("tailored_resume", {}))
        for section in ("projects", "experience", "internships"):
            items = tailored.get(section)
            if not isinstance(items, list):
                continue
            for item in items:
                if isinstance(item, dict) and item.get("source_path") in payload.bullet_edits:
                    item["tailored_text"] = payload.bullet_edits[item["source_path"]]
        data["tailored_resume"] = tailored
        edited_fields.update(payload.bullet_edits.keys())

    user_edits["edited_fields"] = sorted(edited_fields)
    data["user_edits"] = user_edits
    record.data = data
    db.add(record)
    db.commit()
    db.refresh(record)

    structured = db.scalar(select(StructuredResume).where(StructuredResume.resume_id == resume_id))
    return _to_response(record, structured.updated_at if structured is not None else record.source_resume_updated_at)
