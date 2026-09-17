import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CandidateProfile, Resume, StructuredResume
from app.schemas.job_match import JobMatchResult
from app.schemas.job_posting import JobPosting
from app.schemas.job_chunk import JobSearchResult
from app.services.job_dataset_service import load_job_postings
from app.services.job_search_service import search_jobs

MATCH_WEIGHTS = {
    "required_skills": 0.35,
    "preferred_skills": 0.15,
    "experience": 0.15,
    "education": 0.10,
    "project_relevance": 0.15,
    "qualifications": 0.10,
}

ALIASES = {
    "react.js": "react",
    "node.js": "nodejs",
    "node js": "nodejs",
    "js": "javascript",
    "ts": "typescript",
    "postgres": "postgresql",
    "postgres sql": "postgresql",
    "ml": "machine learning",
    "ai/ml": "machine learning",
    "rest api": "rest apis",
    "restful api": "rest apis",
    "fast api": "fastapi",
    "scikit learn": "scikit-learn",
}


@dataclass(frozen=True)
class MatchingProfile:
    skills: list[str]
    education_text: str
    experience_text: str
    project_texts: list[str]
    project_skills: list[str]
    qualification_text: str
    retrieval_terms: list[str]
    project_evidence: list[tuple[str, list[str]]] = field(default_factory=list)


@dataclass(frozen=True)
class ComponentResult:
    score: float | None
    matched: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


def normalize_term(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9+#./ -]", "", value.casefold()).strip()
    return ALIASES.get(normalized, normalized)


def _unique_terms(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        term = normalize_term(value)
        if term and term not in seen:
            seen.add(term)
            result.append(term)
    return result


def _text_values(value: object) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        values: list[str] = []
        for item in value:
            if isinstance(item, str) and item.strip():
                values.append(item)
            elif isinstance(item, dict):
                values.extend(
                    str(item[key])
                    for key in ("raw_text", "description", "title")
                    if isinstance(item.get(key), str) and item[key].strip()
                )
        return values
    return []


def normalize_profile(profile: CandidateProfile, structured_data: dict) -> MatchingProfile:
    education_entries = _text_values(profile.education) + _text_values(profile.degree)
    education_entries += _text_values(profile.specialization) + _text_values(structured_data.get("education", []))
    experience_entries = _text_values(profile.experience_level)
    experience_entries += _text_values(structured_data.get("experience", []))
    experience_entries += _text_values(structured_data.get("internships", []))
    project_items = structured_data.get("projects", [])
    project_texts = _text_values(project_items)
    project_evidence = [
        (
            str(item.get("raw_text") or item.get("title") or "").strip(),
            _unique_terms([str(skill) for skill in item.get("technologies", [])]),
        )
        for item in project_items
        if isinstance(item, dict) and str(item.get("raw_text") or item.get("title") or "").strip()
    ]
    project_skills = _unique_terms(
        [skill for item in project_items if isinstance(item, dict) for skill in item.get("technologies", [])]
    )
    skills = _unique_terms(list(profile.skills) + structured_data.get("skills", []) + project_skills)
    qualification_text = " ".join(
        _text_values(structured_data.get("certifications", []))
        + _text_values(structured_data.get("achievements", []))
        + _text_values(structured_data.get("qualifications", []))
        + _text_values(profile.career_goals)
    )
    retrieval_terms = _unique_terms(
        skills
        + list(profile.target_roles)
        + list(profile.career_interests)
        + education_entries
        + project_texts
    )
    return MatchingProfile(
        skills=skills,
        education_text=" ".join(education_entries),
        experience_text=" ".join(experience_entries),
        project_texts=project_texts,
        project_skills=project_skills,
        qualification_text=qualification_text,
        retrieval_terms=retrieval_terms,
        project_evidence=project_evidence,
    )


def _matched_terms(student_terms: list[str], job_terms: list[str]) -> ComponentResult:
    student_set = set(student_terms)
    matched = [term for term in job_terms if normalize_term(term) in student_set]
    missing = [term for term in job_terms if normalize_term(term) not in student_set]
    score = len(matched) / len(job_terms) if job_terms else 1.0
    return ComponentResult(score=score, matched=matched, missing=missing)


def score_required_skills(profile: MatchingProfile, job: JobPosting) -> ComponentResult:
    return _matched_terms(profile.skills, job.required_skills)


def score_preferred_skills(profile: MatchingProfile, job: JobPosting) -> ComponentResult:
    return _matched_terms(profile.skills, job.preferred_skills)


def score_education(profile: MatchingProfile, job: JobPosting) -> ComponentResult:
    student = normalize_term(profile.education_text)
    requirement = normalize_term(job.education_requirements)
    if not student:
        return ComponentResult(None, reasons=["Education evidence is unavailable."])
    degree_terms = ("b.tech", "b.e", "bca", "b.sc", "m.tech", "mca", "m.sc", "computer", "information technology", "data science", "engineering", "mathematics", "statistics", "electronics")
    student_has_field = any(term in student for term in degree_terms)
    requirement_accepts_related = "related" in requirement or "any discipline" in requirement
    if student_has_field and ("computer" in requirement or "information technology" in requirement or requirement_accepts_related):
        return ComponentResult(1.0, reasons=["Education evidence satisfies the stated or related-field requirement."])
    return ComponentResult(0.0, reasons=["Available education does not clearly satisfy the stated requirement."])


def score_experience(profile: MatchingProfile, job: JobPosting) -> ComponentResult:
    requirement = normalize_term(job.experience_requirements)
    evidence = normalize_term(profile.experience_text)
    if any(term in requirement for term in ("no prior", "no experience", "entry-level", "entry level", "not required")):
        return ComponentResult(1.0, reasons=["The job does not require prior professional experience."])
    if not evidence:
        return ComponentResult(0.0, reasons=["No experience evidence is available for this requirement."])
    if "intern" in requirement and "intern" in evidence:
        return ComponentResult(1.0, reasons=["The profile includes internship experience relevant to the requirement."])
    year_match = re.search(r"(\d+)\s*(?:-|to)?\s*\+?\s*years?", requirement)
    if year_match:
        required_years = int(year_match.group(1))
        evidence_years = [int(value) for value in re.findall(r"(\d+)\s*years?", evidence)]
        if evidence_years and max(evidence_years) >= required_years:
            return ComponentResult(1.0, reasons=["Documented experience meets the stated duration."])
        return ComponentResult(0.6 if "intern" in evidence or "project" in evidence else 0.0, reasons=["Experience evidence only partially supports the stated duration."])
    return ComponentResult(0.6, reasons=["Some experience evidence is present, but the requirement is not quantified."])


def score_project_relevance(profile: MatchingProfile, job: JobPosting) -> tuple[ComponentResult, list[str]]:
    if not profile.project_texts:
        return ComponentResult(None), []
    searchable = _unique_terms(job.required_skills + job.preferred_skills + [job.domain] + [job.job_title])
    relevant_projects = []
    matched_terms: set[str] = set()
    evidence = profile.project_evidence or [(project, profile.project_skills) for project in profile.project_texts]
    for project, project_skills in evidence:
        project_terms = set(project_skills)
        overlap = project_terms & set(searchable)
        if overlap:
            relevant_projects.append(project)
            matched_terms.update(overlap)
    score = len(matched_terms) / len(searchable) if searchable else 0.0
    return ComponentResult(min(score, 1.0)), relevant_projects


def score_qualifications(profile: MatchingProfile, job: JobPosting) -> ComponentResult:
    if not profile.qualification_text:
        return ComponentResult(None, reasons=["No certification, achievement, or qualification evidence is available."])
    requirement_terms = _unique_terms(job.qualifications)
    evidence = normalize_term(profile.qualification_text)
    matched = [term for term in requirement_terms if normalize_term(term) in evidence]
    return ComponentResult(
        len(matched) / len(requirement_terms) if requirement_terms else 1.0,
        matched=matched,
        missing=[term for term in requirement_terms if term not in matched],
    )


def _match_score(components: dict[str, ComponentResult]) -> float:
    active = {name: result for name, result in components.items() if result.score is not None}
    total_weight = sum(MATCH_WEIGHTS[name] for name in active)
    weighted = sum(result.score * MATCH_WEIGHTS[name] for name, result in active.items() if result.score is not None)
    return round(weighted / total_weight * 100, 1) if total_weight else 0.0


def _result(job: JobPosting, retrieval: JobSearchResult, profile: MatchingProfile) -> JobMatchResult:
    required = score_required_skills(profile, job)
    preferred = score_preferred_skills(profile, job)
    experience = score_experience(profile, job)
    education = score_education(profile, job)
    project, relevant_projects = score_project_relevance(profile, job)
    qualifications = score_qualifications(profile, job)
    components = {
        "required_skills": required,
        "preferred_skills": preferred,
        "experience": experience,
        "education": education,
        "project_relevance": project,
        "qualifications": qualifications,
    }
    strengths = [f"{skill} matched" for skill in required.matched]
    strengths.extend(f"{skill} preferred skill matched" for skill in preferred.matched)
    if education.score == 1.0:
        strengths.append("Education requirement satisfied")
    if relevant_projects:
        strengths.append(f"Relevant project evidence: {relevant_projects[0]}")
    gaps = [f"{skill} missing" for skill in required.missing]
    gaps.extend(f"{skill} preferred skill not found" for skill in preferred.missing)
    reasoning = (
        f"The candidate matches {len(required.matched)} of {len(job.required_skills)} required skills"
        f" and {len(preferred.matched)} of {len(job.preferred_skills)} preferred skills. "
        + (f"Relevant project evidence includes {relevant_projects[0]}. " if relevant_projects else "No directly overlapping project evidence was found. ")
        + (f"The main gap is {required.missing[0]}." if required.missing else "No required skill gaps were found.")
    )
    return JobMatchResult(
        job_id=job.job_id,
        job_title=job.job_title,
        company=job.company,
        domain=job.domain,
        location=job.location,
        work_mode=job.work_mode,
        employment_type=job.employment_type,
        retrieval_score=retrieval.similarity_score,
        match_score=_match_score(components),
        required_skills_score=required.score,
        preferred_skills_score=preferred.score,
        experience_score=experience.score,
        education_score=education.score or 0.0,
        project_relevance_score=project.score or 0.0,
        qualification_score=qualifications.score or 0.0,
        matched_required_skills=required.matched,
        missing_required_skills=required.missing,
        matched_preferred_skills=preferred.matched,
        missing_preferred_skills=preferred.missing,
        relevant_projects=relevant_projects,
        strengths=strengths,
        gaps=gaps,
        reasoning=reasoning,
    )


def match_jobs_for_profile(profile: CandidateProfile, structured_data: dict, top_k: int = 10) -> list[JobMatchResult]:
    if not 1 <= top_k <= 20:
        raise ValueError("top_k must be between 1 and 20.")
    normalized = normalize_profile(profile, structured_data)
    query = " ".join(normalized.retrieval_terms[:40])
    if not query:
        raise ValueError("The structured profile does not contain enough information for job retrieval.")
    retrievals = search_jobs(query, top_k=top_k)
    jobs = {job.job_id: job for job in load_job_postings()}
    results = [_result(jobs[item.job_id], item, normalized) for item in retrievals]
    return sorted(results, key=lambda item: (-item.match_score, -item.retrieval_score, item.job_id))


def match_jobs_for_resume(db: Session, resume_id: int, top_k: int = 10) -> list[JobMatchResult]:
    resume = db.get(Resume, resume_id)
    if resume is None:
        raise LookupError("Resume not found.")
    profile = db.get(CandidateProfile, resume.candidate_profile_id)
    structured = db.scalar(select(StructuredResume).where(StructuredResume.resume_id == resume_id))
    if profile is None or structured is None:
        raise ValueError("A structured resume is required before matching jobs.")
    return match_jobs_for_profile(profile, structured.data, top_k)
