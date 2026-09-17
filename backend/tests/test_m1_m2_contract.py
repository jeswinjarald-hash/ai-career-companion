from pathlib import Path
from types import SimpleNamespace

from app.api import resume as resume_api
from app.schemas.job_chunk import JobSearchResult
from app.schemas.job_posting import JobPosting
from app.services import job_matching
from app.services.job_matching import match_jobs_for_profile
from test_resume_api import register_session, resume_client, valid_docx
from test_structured_context import prepare
from test_structured_context import resume_docx


def profile() -> SimpleNamespace:
    return SimpleNamespace(
        skills=[],
        education="B.Tech Information Technology",
        degree="B.Tech",
        specialization="Information Technology",
        experience_level="0-1 years",
        career_interests=["backend"],
        target_roles=["Backend Developer"],
        career_goals=None,
    )


def job(required_skills: list[str], preferred_skills: list[str] | None = None) -> JobPosting:
    return JobPosting(
        job_id="JOB-TEST",
        job_title="Python Backend Intern",
        company="Example Co",
        location="Remote",
        work_mode="Remote",
        employment_type="Internship",
        domain="Python Backend",
        job_description="Build backend services.",
        responsibilities=["Build APIs"],
        required_skills=required_skills,
        preferred_skills=preferred_skills or [],
        qualifications=[],
        experience_requirements="0-1 years",
        education_requirements="Computer Science or related field",
        source_type="synthetic_curated",
        posted_date="2026-01-01",
        raw_text="Python Backend Intern",
    )


def retrieval(job_record: JobPosting) -> JobSearchResult:
    return JobSearchResult(
        job_id=job_record.job_id,
        job_title=job_record.job_title,
        company=job_record.company,
        domain=job_record.domain,
        location=job_record.location,
        work_mode=job_record.work_mode,
        employment_type=job_record.employment_type,
        required_skills=job_record.required_skills,
        preferred_skills=job_record.preferred_skills,
        similarity_score=0.9,
        matched_chunk_types=[],
    )


def use_job(monkeypatch, job_record: JobPosting) -> None:
    monkeypatch.setattr(job_matching, "search_jobs", lambda query, top_k: [retrieval(job_record)])
    monkeypatch.setattr(job_matching, "load_job_postings", lambda: [job_record])


def test_structured_skills_are_consumed_by_matching(monkeypatch) -> None:
    record = job(["Python", "FastAPI"])
    use_job(monkeypatch, record)

    result = match_jobs_for_profile(profile(), {"skills": ["Python", "FastAPI"]}, top_k=1)[0]

    assert result.matched_required_skills == ["Python", "FastAPI"]
    assert result.missing_required_skills == []


def test_project_technologies_are_consumed_as_skills_and_evidence(monkeypatch) -> None:
    record = job(["FastAPI"])
    use_job(monkeypatch, record)

    result = match_jobs_for_profile(
        profile(),
        {"skills": [], "projects": [{"title": "Career API", "description": "", "technologies": ["FastAPI"], "raw_text": "Career API"}]},
        top_k=1,
    )[0]

    assert result.matched_required_skills == ["FastAPI"]
    assert result.relevant_projects == ["Career API"]
    assert result.project_relevance_score > 0


def test_education_propagates_to_education_score(monkeypatch) -> None:
    record = job([])
    use_job(monkeypatch, record)

    result = match_jobs_for_profile(profile(), {"skills": [], "education": []}, top_k=1)[0]

    assert result.education_score == 1.0


def test_missing_required_skill_is_reported(monkeypatch) -> None:
    record = job(["Python", "Docker"])
    use_job(monkeypatch, record)

    result = match_jobs_for_profile(profile(), {"skills": ["Python"]}, top_k=1)[0]

    assert result.matched_required_skills == ["Python"]
    assert result.missing_required_skills == ["Docker"]
    assert "Docker missing" in result.gaps


def test_changing_structured_resume_changes_matching_result(monkeypatch) -> None:
    record = job(["Python"])
    use_job(monkeypatch, record)

    with_python = match_jobs_for_profile(profile(), {"skills": ["Python"]}, top_k=1)[0]
    without_python = match_jobs_for_profile(profile(), {"skills": []}, top_k=1)[0]

    assert with_python.match_score > without_python.match_score
    assert with_python.matched_required_skills != without_python.matched_required_skills


def test_matching_requires_structured_resume(resume_client) -> None:
    client, _ = resume_client
    session = register_session(client, email="unstructured@example.com", full_name="Unstructured Candidate")
    profile_id = session["profile"]["id"]
    upload = client.post(
        f"/api/profiles/{profile_id}/resumes",
        files={
            "file": (
                "resume.docx",
                valid_docx(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )

    assert upload.status_code == 201
    assert client.get(f"/api/resumes/{upload.json()['id']}/job-matches").status_code == 409


def test_matching_uses_requested_resume_id_without_stale_resume(resume_client, monkeypatch) -> None:
    client, _ = resume_client
    profile_id, first_resume_id = prepare(client)
    second_upload = client.post(
        f"/api/profiles/{profile_id}/resumes",
        files={
            "file": (
                "second.docx",
                resume_docx(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert second_upload.status_code == 201
    second_resume_id = second_upload.json()["id"]
    captured_ids: list[int] = []

    def fake_match(db, resume_id, top_k):
        captured_ids.append(resume_id)
        return []

    monkeypatch.setattr(resume_api, "match_jobs_for_resume", fake_match)

    assert client.get(f"/api/resumes/{first_resume_id}/job-matches").status_code == 200
    assert client.get(f"/api/resumes/{second_resume_id}/job-matches").status_code == 200
    assert captured_ids == [first_resume_id, second_resume_id]


def test_real_resume_flow_reaches_ranked_matches(resume_client) -> None:
    client, _ = resume_client
    session = register_session(client, email="arun.audit@example.com", full_name="Arun Kumar")
    profile_id = session["profile"]["id"]
    assert client.patch(
        f"/api/profiles/{profile_id}",
        json={
            "education": "B.Tech Information Technology",
            "degree": "B.Tech",
            "specialization": "Information Technology",
            "experience_level": "0-1 years",
            "career_interests": ["Backend Engineering"],
            "target_roles": ["Backend Developer"],
        },
    ).status_code == 200
    resume_path = next((Path(__file__).parents[1] / "data" / "resumes").glob("*.pdf"))
    upload = client.post(
        f"/api/profiles/{profile_id}/resumes",
        files={"file": (resume_path.name, resume_path.read_bytes(), "application/pdf")},
    )
    resume_id = upload.json()["id"]

    extraction = client.post(f"/api/resumes/{resume_id}/extract-text")
    sections = client.post(f"/api/resumes/{resume_id}/detect-sections")
    structured = client.post(f"/api/resumes/{resume_id}/structure")
    matches = client.get(f"/api/resumes/{resume_id}/job-matches?top_k=5")

    assert upload.status_code == 201
    assert extraction.status_code == 200
    assert extraction.json()["character_count"] > 500
    assert sections.status_code == 200
    assert {item["name"] for item in sections.json()["sections"]} >= {"skills", "education", "projects", "experience"}
    assert structured.status_code == 200
    data = structured.json()["data"]
    assert {"skills", "education", "experience", "internships", "projects", "certifications", "achievements", "qualifications"} <= data.keys()
    assert {"Python", "FastAPI", "SQL", "Git"} <= set(data["skills"])
    assert data["projects"]
    assert matches.status_code == 200
    assert len(matches.json()) == 5
    assert all(item["reasoning"] and item["strengths"] is not None and item["gaps"] is not None for item in matches.json())
    print(
        {
            "profile_id": profile_id,
            "resume_id": resume_id,
            "skills": data["skills"],
            "projects": data["projects"],
            "top_matches": [
                {
                    "title": item["job_title"],
                    "domain": item["domain"],
                    "score": item["match_score"],
                    "matched": item["matched_required_skills"],
                    "missing": item["missing_required_skills"],
                    "projects": item["relevant_projects"],
                }
                for item in matches.json()
            ],
        }
    )
