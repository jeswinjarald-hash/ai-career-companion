from app.schemas.job_match import JobMatchResult
from app.api import resume as resume_api
from app.services import job_matching

from test_resume_api import resume_client
from test_structured_context import prepare


def test_job_matches_endpoint_uses_structured_resume_and_validates_state(resume_client, monkeypatch) -> None:
    client, _ = resume_client
    profile_id, resume_id = prepare(client)
    assert client.get("/api/resumes/999/job-matches").status_code == 404
    fake_result = JobMatchResult(
        job_id="JOB-0001",
        job_title="Python Backend Intern",
        company="Example Co",
        domain="Python Backend",
        location="Remote",
        work_mode="Remote",
        employment_type="Internship",
        retrieval_score=0.7,
        match_score=80.0,
        required_skills_score=0.75,
        preferred_skills_score=0.5,
        experience_score=1.0,
        education_score=1.0,
        project_relevance_score=0.5,
        qualification_score=0.0,
        matched_required_skills=["Python"],
        missing_required_skills=["FastAPI"],
        matched_preferred_skills=[],
        missing_preferred_skills=["Docker"],
        relevant_projects=[],
        strengths=["Python matched"],
        gaps=["FastAPI missing"],
        reasoning="The candidate matches 1 of 2 required skills.",
    )
    monkeypatch.setattr(resume_api, "match_jobs_for_resume", lambda db, resume_id, top_k: [fake_result])

    response = client.get(f"/api/resumes/{resume_id}/job-matches?top_k=1")

    assert response.status_code == 200
    assert response.json()[0]["retrieval_score"] == 0.7
    assert response.json()[0]["match_score"] == 80.0
    assert client.get(f"/api/resumes/{resume_id}/job-matches?top_k=0").status_code == 422
