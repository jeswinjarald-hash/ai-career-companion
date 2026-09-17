from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.job_matching import match_jobs_for_profile
from app.services.job_vector_store import INDEX_PATH, METADATA_PATH


pytestmark = pytest.mark.skipif(
    not (Path(INDEX_PATH).is_file() and Path(METADATA_PATH).is_file()),
    reason="Build the M2.2 vector index before real matching integration tests.",
)


def candidate(skills: list[str], interests: list[str], roles: list[str], education: str = "B.Tech Computer Science") -> SimpleNamespace:
    return SimpleNamespace(
        skills=skills,
        education=education,
        degree="B.Tech" if education else "",
        specialization="Computer Science" if education else "",
        experience_level="Internship",
        career_interests=interests,
        target_roles=roles,
        career_goals="Build practical projects",
    )


@pytest.mark.parametrize(
    ("profile", "projects", "expected_domain"),
    [
        (candidate(["Python", "Pandas", "NumPy", "Scikit-learn", "SQL", "Machine Learning"], ["machine learning"], ["Machine Learning Intern"]), [{"raw_text": "Classification with Pandas and Scikit-learn", "technologies": ["Pandas", "Scikit-learn", "Machine Learning"]}], "Machine Learning"),
        (candidate(["HTML", "CSS", "JavaScript", "React", "TypeScript", "Git"], ["frontend"], ["Frontend Developer"]), [{"raw_text": "React JavaScript web application", "technologies": ["React", "JavaScript"]}], "Frontend Development"),
        (candidate(["Python", "FastAPI", "SQL", "PostgreSQL", "Git", "REST APIs"], ["backend"], ["Python Backend Developer"]), [{"raw_text": "FastAPI REST API with PostgreSQL", "technologies": ["FastAPI", "REST APIs", "PostgreSQL"]}], "Python Backend"),
        (candidate(["Linux", "Computer Networks", "Cybersecurity Fundamentals", "SIEM", "Python"], ["cybersecurity"], ["SOC Analyst"]), [{"raw_text": "Linux SIEM security monitoring", "technologies": ["Linux", "SIEM"]}], "Cybersecurity"),
    ],
)
def test_strong_profiles_retrieve_and_match_their_domain(profile, projects, expected_domain) -> None:
    results = match_jobs_for_profile(profile, {"skills": [], "education": [], "experience": [], "projects": projects}, top_k=5)

    assert len(results) == 5
    assert expected_domain in {result.domain for result in results}
    assert all(result.retrieval_score >= 0 for result in results)
    assert all(0 <= result.match_score <= 100 for result in results)
    assert all(result.reasoning for result in results)


def test_weak_profile_has_lower_scores_and_identifies_gaps() -> None:
    profile = candidate(["basic programming", "HTML", "communication"], [], [], education="")
    results = match_jobs_for_profile(profile, {"skills": [], "education": [], "experience": [], "projects": []}, top_k=5)

    assert max(result.match_score for result in results) < 60
    assert any(result.missing_required_skills for result in results)
    assert any("missing" in gap for result in results for gap in result.gaps)
