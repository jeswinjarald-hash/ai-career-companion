"""Milestone 3.1 — Skill Gap Analysis Agent.

Orchestrates the deterministic pipeline:

    structured resume + candidate profile
        -> evidence extraction (app.services.skill_gap_evidence)
        -> requirement classification (demonstrated / partial / learning_only / missing)
        -> deterministic readiness scoring
        -> template-based, job-grounded recommendations
        -> persisted SkillGapAnalysis

No LLM is used, matching this project's existing M2.3 job-matching convention
(app.services.job_matching): every explanation and recommendation is generated
from computed evidence, never inferred or guessed.
"""

import json
import logging
import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CandidateProfile, Resume, StructuredResume
from app.models.career_state import SkillGap as SkillGapRecord
from app.schemas.job_posting import JobPosting
from app.schemas.skill_gap import (
    EvidenceItem,
    GapItem,
    MatchType,
    Priority,
    RequirementType,
    ScoreComponent,
    SkillGapAnalysis,
    SkillGapSummary,
    StrengthItem,
)
from app.services.job_dataset_service import load_job_postings
from app.services.job_matching import normalize_term
from app.services.skill_gap_evidence import EvidenceUnit, build_evidence_units, evidence_item, match_requirement, mentions_term

logger = logging.getLogger(__name__)

READINESS_WEIGHTS: dict[str, float] = {
    "required_skills": 0.40,
    "preferred_skills": 0.15,
    "experience": 0.20,
    "education": 0.10,
    "qualifications": 0.15,
}
COMPONENT_LABELS: dict[str, str] = {
    "required_skills": "Required skills",
    "preferred_skills": "Preferred skills",
    "experience": "Experience",
    "education": "Education",
    "qualifications": "Qualifications",
}
_PARTIAL_CREDIT: dict[MatchType, float] = {"demonstrated": 1.0, "partial": 0.5, "learning_only": 0.1, "missing": 0.0}
_PRIORITY_ORDER: dict[Priority, int] = {"high": 0, "medium": 1, "low": 2}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    # SQLite drops tzinfo on round-trip even for DateTime(timezone=True) columns,
    # so a value read back from the database is naive UTC in practice — treat it
    # as such rather than crashing on naive/aware datetime comparisons.
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _unique_preserve(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = normalize_term(value)
        if key and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _importance_for(requirement: str, requirement_type: RequirementType, job: JobPosting) -> str:
    if requirement_type == "required_skill":
        base = f'"{requirement}" is listed as a required skill for the {job.job_title} role at {job.company}.'
    elif requirement_type == "preferred_skill":
        base = f'"{requirement}" is listed as a preferred (non-mandatory) skill for the {job.job_title} role at {job.company}.'
    elif requirement_type == "qualification":
        base = f'"{requirement}" is listed as an expected qualification for the {job.job_title} role at {job.company}.'
    elif requirement_type == "experience":
        base = f'The role states this experience expectation: "{job.experience_requirements}"'
    else:
        base = f'The role states this education expectation: "{job.education_requirements}"'
    norm = normalize_term(requirement)
    if requirement_type in ("required_skill", "preferred_skill") and any(mentions_term(norm, normalize_term(item)) for item in job.responsibilities):
        base += " It also appears directly in the role's stated responsibilities."
    return base


def _recommendation_for(requirement: str, requirement_type: RequirementType, job: JobPosting) -> tuple[str, str]:
    if requirement_type == "education":
        return (
            f'If your current or planned degree does not clearly align with "{job.education_requirements}", '
            "emphasize relevant coursework, certifications, or self-study that bridges the gap in your application materials.",
            "Coursework, an online certification, or a project that demonstrates the expected academic background.",
        )
    if requirement_type == "experience":
        return (
            "Build a portfolio entry that speaks directly to this expectation — an internship, freelance work, "
            "or a deployed, production-style personal project with a short write-up of your specific role in it.",
            "An internship, freelance engagement, or a deployed personal project with a documented write-up of your contribution.",
        )
    if requirement_type == "qualification":
        return (
            f'This is a behavioral/soft expectation ("{requirement}") that a resume rarely demonstrates directly — '
            "prepare a concrete example (a project decision, a debugging story, a team situation) you can describe in your application or interview.",
            "A specific, concrete example ready to cite in your cover letter or interview that illustrates this quality.",
        )
    norm = normalize_term(requirement)
    if norm in {"docker", "kubernetes"}:
        return (
            f"Containerize one of your existing backend projects with {requirement}, add a deployment/compose file, and document the setup in the project README.",
            "A Dockerfile (and docker-compose.yml if applicable) committed to an existing project repository.",
        )
    if norm in {"aws", "azure", "gcp"}:
        return (
            f"Deploy one existing project to {requirement} (e.g. a free-tier VM, storage bucket, or managed database) and document the deployment architecture.",
            f"A deployed, publicly reachable version of an existing project hosted on {requirement}, with a short architecture write-up.",
        )
    if norm in {"fastapi", "flask", "django", "spring boot", "express", "node.js"}:
        return (
            f"Build or extend a REST API using {requirement} and connect it to a real database.",
            f"A working {requirement} service with at least two endpoints and a database integration, pushed to a public repository.",
        )
    if norm in {"react", "angular", "vue"}:
        return (
            f"Build or extend a frontend project using {requirement} that consumes a real or mock API.",
            f"A deployed {requirement} application with at least two connected views.",
        )
    if norm in {"pytorch", "tensorflow", "scikit-learn", "machine learning", "deep learning"}:
        return (
            f"Complete a small applied project using {requirement} on a public dataset, and document the approach and results.",
            f"A notebook or repository showing a {requirement} model trained and evaluated on a real dataset.",
        )
    if norm in {"sql", "postgresql", "mysql", "mongodb", "dbms"}:
        return (
            f"Design and query a normalized schema in {requirement} for one of your existing or new projects.",
            f"A project with a documented {requirement} schema and several non-trivial queries.",
        )
    if norm in {"git", "github", "ci/cd"}:
        return (
            f"Use {requirement} actively on an existing project: a meaningful commit history, branches, and (for CI/CD) an automated pipeline.",
            f"A public repository showing active {requirement} usage over multiple commits.",
        )
    return (
        f"Learn the fundamentals of {requirement} and apply it directly in a small, focused project so you have concrete evidence to show.",
        f"A small project or contribution that clearly demonstrates {requirement} in practice.",
    )


def _gap_item(requirement: str, requirement_type: RequirementType, match_type: MatchType, confidence: float, evidence: list[EvidenceItem], reason: str, job: JobPosting, priority: Priority) -> GapItem:
    recommendation, suggested_evidence = _recommendation_for(requirement, requirement_type, job)
    return GapItem(
        requirement=requirement,
        requirement_type=requirement_type,
        match_type=match_type,
        priority=priority,
        confidence=confidence,
        importance=_importance_for(requirement, requirement_type, job),
        student_evidence=evidence,
        reason=reason,
        recommendation=recommendation,
        suggested_evidence_to_build=suggested_evidence,
    )


_NO_EXPERIENCE_MARKERS = ("no prior", "no experience", "entry-level", "entry level", "not required", "not mandatory")
_YEAR_PATTERN = re.compile(r"(\d+)\s*(?:-|to)?\s*\+?\s*years?")


def assess_experience(job: JobPosting, units: list[EvidenceUnit]) -> tuple[MatchType, float, list[EvidenceItem], str]:
    requirement = job.experience_requirements
    norm_req = normalize_term(requirement)
    professional_units = [unit for unit in units if unit.source in ("experience", "internship")]
    project_units = [unit for unit in units if unit.source == "project"]

    if any(marker in norm_req for marker in _NO_EXPERIENCE_MARKERS):
        return "demonstrated", 0.9, [], f'The role does not strictly require prior professional experience ("{requirement}").'

    year_match = _YEAR_PATTERN.search(norm_req)
    if year_match:
        required_years = int(year_match.group(1))
        for unit in professional_units:
            years_found = [int(value) for value in re.findall(r"(\d+)\s*years?", unit.normalized_text)]
            if years_found and max(years_found) >= required_years:
                return "demonstrated", 0.9, [evidence_item(unit)], f"Documented experience meets the required {required_years}+ years."
        if professional_units:
            return "partial", 0.6, [evidence_item(professional_units[0])], f"Internship/professional evidence exists but does not clearly document {required_years}+ years of experience."
        if project_units:
            return "partial", 0.5, [evidence_item(project_units[0])], f"Only academic/personal project evidence was found; the role expects around {required_years}+ years of professional experience."
        return "missing", 0.9, [], f"No experience evidence was found for the required {required_years}+ years."

    if "intern" in norm_req:
        internship_units = [unit for unit in professional_units if unit.source == "internship"]
        if internship_units:
            return "demonstrated", 0.85, [evidence_item(internship_units[0])], "Internship experience relevant to the requirement was found."
    if professional_units:
        return "partial", 0.65, [evidence_item(professional_units[0])], "Some relevant experience evidence is present, but the requirement is not clearly quantified or fully confirmed."
    if project_units:
        return "partial", 0.5, [evidence_item(project_units[0])], "Only academic/personal project evidence was found for this experience expectation."
    return "missing", 0.85, [], "No experience evidence was found for this requirement."


_DEGREE_FIELD_TERMS = ("b.tech", "b.e", "bca", "b.sc", "m.tech", "mca", "m.sc", "computer", "information technology", "data science", "engineering", "mathematics", "statistics", "electronics")


def assess_education(job: JobPosting, units: list[EvidenceUnit]) -> tuple[MatchType, float, list[EvidenceItem], str, bool]:
    education_units = [unit for unit in units if unit.source == "education"]
    if not education_units:
        return "missing", 0.6, [], "No education evidence is available in your profile/resume yet.", False

    norm_req = normalize_term(job.education_requirements)
    combined = " ".join(unit.normalized_text for unit in education_units)
    has_relevant_field = any(term in combined for term in _DEGREE_FIELD_TERMS)
    accepts_related = "related" in norm_req or "any discipline" in norm_req
    if has_relevant_field and (("computer" in norm_req) or ("information technology" in norm_req) or accepts_related):
        return "demonstrated", 0.85, [evidence_item(education_units[0])], "Education evidence satisfies the stated or related-field requirement.", True
    if has_relevant_field:
        return "partial", 0.6, [evidence_item(education_units[0])], "Available education is technical but does not clearly match the specific discipline stated in the requirement.", True
    return "missing", 0.75, [evidence_item(education_units[0])], "Available education does not clearly satisfy the stated requirement.", True


def _score_component(component: str, matched: int, total: int, included: bool) -> ScoreComponent:
    score = (matched / total) if included and total else (1.0 if included else None)
    return ScoreComponent(component=component, label=COMPONENT_LABELS[component], weight=READINESS_WEIGHTS[component], included=included, score=score, matched=matched, total=total)


def _compute_summary(
    required_matches: list[MatchType],
    preferred_matches: list[MatchType],
    qualification_matches: list[MatchType],
    experience_match: MatchType,
    education_match: MatchType,
    education_evidence_available: bool,
    critical_gap_count: int,
    partial_gap_count: int,
    preferred_gap_count: int,
    experience_gap_count: int,
    qualification_gap_count: int,
) -> SkillGapSummary:
    components: list[ScoreComponent] = []

    required_score = sum(_PARTIAL_CREDIT[m] for m in required_matches) / len(required_matches) if required_matches else None
    components.append(ScoreComponent(
        component="required_skills", label=COMPONENT_LABELS["required_skills"], weight=READINESS_WEIGHTS["required_skills"],
        included=bool(required_matches), score=required_score,
        matched=sum(1 for m in required_matches if m == "demonstrated"), total=len(required_matches),
    ))

    preferred_score = sum(_PARTIAL_CREDIT[m] for m in preferred_matches) / len(preferred_matches) if preferred_matches else None
    components.append(ScoreComponent(
        component="preferred_skills", label=COMPONENT_LABELS["preferred_skills"], weight=READINESS_WEIGHTS["preferred_skills"],
        included=bool(preferred_matches), score=preferred_score,
        matched=sum(1 for m in preferred_matches if m == "demonstrated"), total=len(preferred_matches),
    ))

    qual_score = sum(_PARTIAL_CREDIT[m] for m in qualification_matches) / len(qualification_matches) if qualification_matches else None
    components.append(ScoreComponent(
        component="qualifications", label=COMPONENT_LABELS["qualifications"], weight=READINESS_WEIGHTS["qualifications"],
        included=bool(qualification_matches), score=qual_score,
        matched=sum(1 for m in qualification_matches if m == "demonstrated"), total=len(qualification_matches),
    ))

    components.append(ScoreComponent(
        component="experience", label=COMPONENT_LABELS["experience"], weight=READINESS_WEIGHTS["experience"],
        included=True, score=_PARTIAL_CREDIT[experience_match], matched=1 if experience_match == "demonstrated" else 0, total=1,
    ))

    components.append(ScoreComponent(
        component="education", label=COMPONENT_LABELS["education"], weight=READINESS_WEIGHTS["education"],
        included=education_evidence_available, score=_PARTIAL_CREDIT[education_match] if education_evidence_available else None,
        matched=1 if education_evidence_available and education_match == "demonstrated" else 0, total=1 if education_evidence_available else 0,
    ))

    included_components = [c for c in components if c.included and c.score is not None]
    total_weight = sum(c.weight for c in included_components)
    weighted = sum(c.score * c.weight for c in included_components if c.score is not None)
    overall = round((weighted / total_weight) * 100) if total_weight else 0

    return SkillGapSummary(
        overall_readiness=overall,
        required_requirements_met=sum(1 for m in required_matches if m == "demonstrated"),
        required_requirements_total=len(required_matches),
        preferred_requirements_met=sum(1 for m in preferred_matches if m == "demonstrated"),
        preferred_requirements_total=len(preferred_matches),
        critical_gap_count=critical_gap_count,
        partial_gap_count=partial_gap_count,
        preferred_gap_count=preferred_gap_count,
        experience_gap_count=experience_gap_count,
        qualification_gap_count=qualification_gap_count,
        score_breakdown=components,
    )


def _get_job(job_id: str) -> JobPosting:
    job = next((job for job in load_job_postings() if job.job_id == job_id), None)
    if job is None:
        raise LookupError("Internship not found.")
    return job


def analyze_skill_gap(db: Session, resume_id: int, job_id: str, user_id: int) -> SkillGapAnalysis:
    resume = db.get(Resume, resume_id)
    if resume is None:
        raise LookupError("Resume not found.")
    profile = db.get(CandidateProfile, resume.candidate_profile_id)
    if profile is None or profile.user_id != user_id:
        raise LookupError("Resume not found.")
    structured = db.scalar(select(StructuredResume).where(StructuredResume.resume_id == resume_id))
    if structured is None:
        raise ValueError("A structured student profile is required before skill gap analysis.")
    job = _get_job(job_id)

    logger.info("skill_gap_analysis_started profile_id=%s job_id=%s", profile.id, job.job_id)

    units = build_evidence_units(profile, structured.data)

    strengths: list[StrengthItem] = []
    critical_gaps: list[GapItem] = []
    partial_gaps: list[GapItem] = []
    preferred_gaps: list[GapItem] = []
    qualification_gaps: list[GapItem] = []
    experience_gaps: list[GapItem] = []

    required_matches: list[MatchType] = []
    for skill in _unique_preserve(job.required_skills):
        match_type, confidence, evidence, reason = match_requirement(skill, units)
        required_matches.append(match_type)
        if match_type == "demonstrated":
            strengths.append(StrengthItem(requirement=skill, requirement_type="required_skill", evidence=evidence, reason=reason))
        elif match_type in ("partial", "learning_only"):
            # Learning-only exposure for a required skill is a real gap, but a
            # meaningfully smaller one than no evidence at all — grouped with partial
            # matches (distinguished by `match_type`) rather than the critical list.
            partial_gaps.append(_gap_item(skill, "required_skill", match_type, confidence, evidence, reason, job, "medium"))
        else:
            critical_gaps.append(_gap_item(skill, "required_skill", match_type, confidence, evidence, reason, job, "high"))

    preferred_matches: list[MatchType] = []
    for skill in _unique_preserve(job.preferred_skills):
        match_type, confidence, evidence, reason = match_requirement(skill, units)
        preferred_matches.append(match_type)
        if match_type == "demonstrated":
            strengths.append(StrengthItem(requirement=skill, requirement_type="preferred_skill", evidence=evidence, reason=reason))
        else:
            preferred_gaps.append(_gap_item(skill, "preferred_skill", match_type, confidence, evidence, reason, job, "low"))

    qualification_matches: list[MatchType] = []
    for qualification in _unique_preserve(job.qualifications):
        match_type, confidence, evidence, reason = match_requirement(qualification, units)
        qualification_matches.append(match_type)
        if match_type == "demonstrated":
            strengths.append(StrengthItem(requirement=qualification, requirement_type="qualification", evidence=evidence, reason=reason))
        else:
            display_reason = "Insufficient evidence to confirm this from the current resume/profile." if match_type == "missing" else reason
            qualification_gaps.append(_gap_item(qualification, "qualification", match_type, confidence, evidence, display_reason, job, "low"))

    edu_match_type, edu_confidence, edu_evidence, edu_reason, edu_evidence_available = assess_education(job, units)
    if edu_match_type == "demonstrated":
        strengths.append(StrengthItem(requirement=job.education_requirements, requirement_type="education", evidence=edu_evidence, reason=edu_reason))
    else:
        priority: Priority = "high" if edu_match_type == "missing" else "medium"
        qualification_gaps.append(_gap_item(job.education_requirements, "education", edu_match_type, edu_confidence, edu_evidence, edu_reason, job, priority))

    exp_match_type, exp_confidence, exp_evidence, exp_reason = assess_experience(job, units)
    if exp_match_type == "demonstrated":
        strengths.append(StrengthItem(requirement=job.experience_requirements, requirement_type="experience", evidence=exp_evidence, reason=exp_reason))
    else:
        exp_priority: Priority = "high" if exp_match_type == "missing" else "medium"
        experience_gaps.append(_gap_item(job.experience_requirements, "experience", exp_match_type, exp_confidence, exp_evidence, exp_reason, job, exp_priority))

    summary = _compute_summary(
        required_matches, preferred_matches, qualification_matches, exp_match_type, edu_match_type, edu_evidence_available,
        critical_gap_count=len(critical_gaps), partial_gap_count=len(partial_gaps), preferred_gap_count=len(preferred_gaps),
        experience_gap_count=len(experience_gaps), qualification_gap_count=len(qualification_gaps),
    )

    recommendations = sorted(
        critical_gaps + experience_gaps + partial_gaps + preferred_gaps + qualification_gaps,
        key=lambda gap: _PRIORITY_ORDER[gap.priority],
    )

    analysis = SkillGapAnalysis(
        job_id=job.job_id, job_title=job.job_title, company=job.company, domain=job.domain, location=job.location,
        resume_id=resume.id, profile_id=profile.id,
        generated_at=_utc_now(), resume_updated_at=_as_utc(structured.updated_at), stale=False,
        summary=summary, strengths=strengths, critical_gaps=critical_gaps, partial_gaps=partial_gaps,
        preferred_gaps=preferred_gaps, experience_gaps=experience_gaps, qualification_gaps=qualification_gaps,
        recommendations=recommendations,
    )

    _persist(db, user_id, job.job_id, analysis)
    logger.info(
        "skill_gap_analysis_completed profile_id=%s job_id=%s required_skills=%s critical_gaps=%s partial_gaps=%s readiness=%s",
        profile.id, job.job_id, len(required_matches), len(critical_gaps), len(partial_gaps), summary.overall_readiness,
    )
    return analysis


def _persist(db: Session, user_id: int, job_id: str, analysis: SkillGapAnalysis) -> None:
    payload = json.loads(analysis.model_dump_json())
    record = db.scalar(select(SkillGapRecord).where(SkillGapRecord.user_id == user_id, SkillGapRecord.job_id == job_id))
    if record is None:
        record = SkillGapRecord(user_id=user_id, job_id=job_id, data=payload)
        db.add(record)
    else:
        record.data = payload
    db.commit()


def get_persisted_skill_gap(db: Session, user_id: int, job_id: str, current_resume_updated_at: datetime) -> SkillGapAnalysis | None:
    record = db.scalar(select(SkillGapRecord).where(SkillGapRecord.user_id == user_id, SkillGapRecord.job_id == job_id))
    if record is None:
        return None
    analysis = SkillGapAnalysis.model_validate(record.data)
    analysis.stale = _as_utc(analysis.resume_updated_at) < _as_utc(current_resume_updated_at)
    return analysis
