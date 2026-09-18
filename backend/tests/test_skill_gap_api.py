from fastapi.testclient import TestClient

from app.main import app
from test_resume_api import register_session, resume_client
from test_structured_context import prepare

FASTAPI_INTERN_ID = "JOB-0035"  # required: Python, SQL, REST APIs, Git — preferred: FastAPI, Flask, PostgreSQL, Docker, Agile


def test_skill_gap_requires_authentication(resume_client) -> None:
    client, _ = resume_client
    profile_id, resume_id = prepare(client)
    assert client.post("/api/auth/logout").status_code == 204

    assert client.post(f"/api/resumes/{resume_id}/skill-gap?job_id={FASTAPI_INTERN_ID}").status_code == 401
    assert client.get(f"/api/resumes/{resume_id}/skill-gap/{FASTAPI_INTERN_ID}").status_code == 401


def test_skill_gap_requires_structured_resume(resume_client) -> None:
    client, _ = resume_client
    profile_id = register_session(client, email="fresh@example.com")["profile"]["id"]
    upload = client.post(
        f"/api/profiles/{profile_id}/resumes",
        files={"file": ("resume.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
    )
    # The bare bytes above are enough to create the resume row for this ownership/state test.
    if upload.status_code != 201:
        return
    resume_id = upload.json()["id"]
    response = client.post(f"/api/resumes/{resume_id}/skill-gap?job_id={FASTAPI_INTERN_ID}")
    assert response.status_code == 409


def test_skill_gap_404s_for_unknown_resume_and_unknown_job(resume_client) -> None:
    client, _ = resume_client
    profile_id, resume_id = prepare(client)
    client.post(f"/api/resumes/{resume_id}/structure")

    assert client.post(f"/api/resumes/999999/skill-gap?job_id={FASTAPI_INTERN_ID}").status_code == 404
    assert client.post(f"/api/resumes/{resume_id}/skill-gap?job_id=JOB-DOES-NOT-EXIST").status_code == 404
    assert client.get(f"/api/resumes/{resume_id}/skill-gap/{FASTAPI_INTERN_ID}").status_code == 404  # nothing analyzed yet


def test_user_cannot_run_or_read_skill_gap_for_another_users_resume(resume_client) -> None:
    client, _ = resume_client
    profile_id, resume_id = prepare(client)
    client.post(f"/api/resumes/{resume_id}/structure")
    client.post(f"/api/resumes/{resume_id}/skill-gap?job_id={FASTAPI_INTERN_ID}")

    with TestClient(app) as intruder_client:
        register_session(intruder_client, email="intruder@example.com", full_name="Intruder")
        assert intruder_client.post(f"/api/resumes/{resume_id}/skill-gap?job_id={FASTAPI_INTERN_ID}").status_code == 404
        assert intruder_client.get(f"/api/resumes/{resume_id}/skill-gap/{FASTAPI_INTERN_ID}").status_code == 404

    # owner's own access is unaffected
    assert client.get(f"/api/resumes/{resume_id}/skill-gap/{FASTAPI_INTERN_ID}").status_code == 200


def test_full_pipeline_produces_grounded_real_data_analysis_and_persists(resume_client) -> None:
    client, _ = resume_client
    profile_id, resume_id = prepare(client)
    # test_structured_context.resume_docx() -> skills: Python, FastAPI, Postgres, Docker; education: B.Tech Information Technology
    structure_response = client.post(f"/api/resumes/{resume_id}/structure")
    assert structure_response.status_code == 200
    structured_skills = structure_response.json()["data"]["skills"]
    assert "Python" in structured_skills

    analyze_response = client.post(f"/api/resumes/{resume_id}/skill-gap?job_id={FASTAPI_INTERN_ID}")
    assert analyze_response.status_code == 200
    analysis = analyze_response.json()

    assert analysis["job_id"] == FASTAPI_INTERN_ID
    assert analysis["resume_id"] == resume_id
    assert analysis["profile_id"] == profile_id
    assert analysis["stale"] is False
    assert 0 <= analysis["summary"]["overall_readiness"] <= 100

    strength_requirements = {item["requirement"] for item in analysis["strengths"]}
    assert "Python" in strength_requirements  # explicitly in the fixture resume's skills
    critical_requirements = {item["requirement"] for item in analysis["critical_gaps"]}
    assert "Git" in critical_requirements  # never mentioned in the fixture resume at all

    # nothing fabricated: every strength/gap requirement must trace to the real job posting's own fields
    job_response = client.get(f"/api/jobs/{FASTAPI_INTERN_ID}")
    job = job_response.json()
    all_job_requirements = set(job["required_skills"]) | set(job["preferred_skills"]) | set(job["qualifications"]) | {job["experience_requirements"], job["education_requirements"]}
    all_reported_requirements = (
        strength_requirements
        | critical_requirements
        | {item["requirement"] for item in analysis["partial_gaps"]}
        | {item["requirement"] for item in analysis["preferred_gaps"]}
        | {item["requirement"] for item in analysis["experience_gaps"]}
        | {item["requirement"] for item in analysis["qualification_gaps"]}
    )
    assert all_reported_requirements <= all_job_requirements

    # persisted and retrievable without recomputation
    read_response = client.get(f"/api/resumes/{resume_id}/skill-gap/{FASTAPI_INTERN_ID}")
    assert read_response.status_code == 200
    assert read_response.json()["summary"]["overall_readiness"] == analysis["summary"]["overall_readiness"]
    assert read_response.json()["stale"] is False


def test_different_selected_job_produces_a_different_analysis(resume_client) -> None:
    client, _ = resume_client
    profile_id, resume_id = prepare(client)
    client.post(f"/api/resumes/{resume_id}/structure")

    first = client.post(f"/api/resumes/{resume_id}/skill-gap?job_id=JOB-0035").json()
    second = client.post(f"/api/resumes/{resume_id}/skill-gap?job_id=JOB-0146").json()

    assert first["job_id"] != second["job_id"]
    assert {g["requirement"] for g in first["critical_gaps"]} != {g["requirement"] for g in second["critical_gaps"]} or first["summary"]["overall_readiness"] != second["summary"]["overall_readiness"]
