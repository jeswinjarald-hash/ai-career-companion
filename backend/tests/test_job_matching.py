from types import SimpleNamespace

import pytest

from app.schemas.job_chunk import JobSearchResult
from app.schemas.job_posting import JobPosting
from app.services import job_matching
from app.services.job_matching import (
    MatchingProfile,
    normalize_profile,
    score_education,
    score_experience,
    score_preferred_skills,
    score_project_relevance,
    score_required_skills,
)


def make_job(**overrides) -> JobPosting:
    values = {
        "job_id": "JOB-TEST",
        "job_title": "Python Backend Intern",
        "company": "Example Co",
        "location": "Remote",
        "work_mode": "Remote",
        "employment_type": "Internship",
        "domain": "Python Backend",
        "job_description": "Build backend services.",
        "responsibilities": ["Build APIs"],
        "required_skills": ["Python", "SQL", "FastAPI", "Git"],
        "preferred_skills": ["Docker", "REST APIs"],
        "qualifications": ["Strong problem-solving ability"],
        "experience_requirements": "No prior professional experience required; academic projects are acceptable.",
        "education_requirements": "Pursuing B.E./B.Tech in Computer Science, Information Technology, or a related field.",
        "source_type": "synthetic_curated",
        "posted_date": "2026-01-01",
        "raw_text": "Backend posting",
    }
    values.update(overrides)
    return JobPosting(**values)


def profile(skills: list[str], education: str = "B.Tech Computer Science") -> MatchingProfile:
    return MatchingProfile(
        skills=[job_matching.normalize_term(skill) for skill in skills],
        education_text=education,
        experience_text="Backend Intern project experience",
        project_texts=["Built a FastAPI REST API with PostgreSQL"],
        project_skills=["fastapi", "rest apis", "postgresql"],
        qualification_text="",
        retrieval_terms=skills,
    )


def test_required_skills_are_exact_alias_aware_and_deterministic() -> None:
    result = score_required_skills(profile(["Python", "SQL", "fast api", "Git", "Python"]), make_job())

    assert result.matched == ["Python", "SQL", "FastAPI", "Git"]
    assert result.missing == []
    assert result.score == 1.0


def test_partial_and_missing_required_skills_are_reported() -> None:
    result = score_required_skills(profile(["Python", "SQL"]), make_job())

    assert result.matched == ["Python", "SQL"]
    assert result.missing == ["FastAPI", "Git"]
    assert result.score == 0.5


def test_preferred_empty_category_is_not_a_penalty() -> None:
    result = score_preferred_skills(profile(["Python"]), make_job(preferred_skills=[]))

    assert result.score == 1.0
    assert result.missing == []


def test_education_and_experience_rules_are_conservative() -> None:
    candidate = profile(["Python"])
    assert score_education(candidate, make_job()).score == 1.0
    assert score_education(profile(["Python"], education="History"), make_job()).score == 0.0
    missing_education = MatchingProfile(**{**candidate.__dict__, "education_text": ""})
    assert score_education(missing_education, make_job()).score is None
    assert score_experience(candidate, make_job()).score == 1.0


def test_project_relevance_uses_project_evidence() -> None:
    result, projects = score_project_relevance(profile(["Python"]), make_job())

    assert result.score > 0
    assert projects == ["Built a FastAPI REST API with PostgreSQL"]


def test_normalization_deduplicates_and_builds_retrieval_terms() -> None:
    candidate = SimpleNamespace(
        skills=["Python", "python", "React.js"],
        education="B.Tech Information Technology",
        degree="B.Tech",
        specialization="",
        experience_level="Internship",
        career_interests=["backend"],
        target_roles=["Python Backend"],
        career_goals="Build APIs",
    )
    normalized = normalize_profile(candidate, {"skills": ["FastAPI"], "projects": [], "education": [], "experience": []})

    assert normalized.skills == ["python", "react", "fastapi"]
    assert "python backend" in normalized.retrieval_terms


def test_matching_service_ranks_by_match_score_not_retrieval_order(monkeypatch) -> None:
    jobs = [make_job(job_id="JOB-A"), make_job(job_id="JOB-B", required_skills=["Java", "Spring Boot", "Git", "SQL"])]
    retrievals = [
        JobSearchResult(job_id="JOB-B", job_title="Java", company="Example", domain="Java Backend", location="Remote", work_mode="Remote", employment_type="Internship", required_skills=jobs[1].required_skills, preferred_skills=[], similarity_score=0.99, matched_chunk_types=["requirements"]),
        JobSearchResult(job_id="JOB-A", job_title="Python", company="Example", domain="Python Backend", location="Remote", work_mode="Remote", employment_type="Internship", required_skills=jobs[0].required_skills, preferred_skills=jobs[0].preferred_skills, similarity_score=0.70, matched_chunk_types=["requirements"]),
    ]
    monkeypatch.setattr(job_matching, "search_jobs", lambda query, top_k: retrievals)
    monkeypatch.setattr(job_matching, "load_job_postings", lambda: jobs)
    candidate = SimpleNamespace(skills=["Python", "SQL", "FastAPI", "Git"], education="B.Tech Computer Science", degree="B.Tech", specialization="", experience_level="Internship", career_interests=[], target_roles=[], career_goals="")

    results = job_matching.match_jobs_for_profile(candidate, {"skills": [], "projects": [], "education": [], "experience": []}, top_k=2)

    assert [result.job_id for result in results] == ["JOB-A", "JOB-B"]
    assert results[0].retrieval_score == 0.70
    assert results[0].match_score > results[1].match_score


@pytest.mark.parametrize("top_k", [0, 21])
def test_matching_rejects_invalid_top_k(monkeypatch, top_k: int) -> None:
    with pytest.raises(ValueError, match="top_k"):
        job_matching.match_jobs_for_profile(SimpleNamespace(), {}, top_k)
