"""Milestone 3.2 service-level tests: evidence provenance, grounded keyword
classification (spec test cases A/B/C), project relevance ordering (case F),
original-resume immutability (case I), staleness detection (case J), negative
testing (spec section 38), and deterministic consistency (spec section 39).
"""

from datetime import timedelta
from io import BytesIO

from docx import Document
from fastapi.testclient import TestClient

from app.services.resume_customization_service import generate_customization, get_customization
from test_resume_api import create_profile, resume_client  # noqa: F401
from test_skill_gap_service import db, seed_candidate  # noqa: F401
from test_structured_context import prepare

# required: Python, SQL, REST APIs, Git — preferred: FastAPI, Flask, PostgreSQL, Docker, Agile
FASTAPI_INTERN_ID = "JOB-0035"


def _docx(sections: list[tuple[str, str]]) -> bytes:
    document = Document()
    for heading, body in sections:
        document.add_paragraph(heading)
        document.add_paragraph(body)
    output = BytesIO()
    document.save(output)
    return output.getvalue()


def _docx_lines(lines: list[str]) -> bytes:
    document = Document()
    for line in lines:
        document.add_paragraph(line)
    output = BytesIO()
    document.save(output)
    return output.getvalue()


def _upload_and_structure(client: TestClient, profile_id: int, sections: list[tuple[str, str]] | bytes) -> tuple[int, dict]:
    content = sections if isinstance(sections, bytes) else _docx(sections)
    upload = client.post(
        f"/api/profiles/{profile_id}/resumes",
        files={"file": ("resume.docx", content, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    assert upload.status_code == 201
    resume_id = upload.json()["id"]
    assert client.post(f"/api/resumes/{resume_id}/extract-text").status_code == 200
    assert client.post(f"/api/resumes/{resume_id}/detect-sections").status_code == 200
    structure = client.post(f"/api/resumes/{resume_id}/structure")
    assert structure.status_code == 200
    return resume_id, structure.json()["data"]


def _prepare_structured(client: TestClient) -> tuple[int, int]:
    profile_id, resume_id = prepare(client)
    assert client.post(f"/api/resumes/{resume_id}/structure").status_code == 200
    return profile_id, resume_id


def test_evidence_records_carry_source_path_provenance_for_every_source_type(resume_client) -> None:  # noqa: F811
    client, _ = resume_client
    profile_id, resume_id = _prepare_structured(client)
    generate = client.post(f"/api/resumes/{resume_id}/application-customizations", params={"job_id": FASTAPI_INTERN_ID})
    assert generate.status_code == 200
    evidence = generate.json()["evidence"]
    assert len(evidence) > 0
    for record in evidence:
        assert record["evidence_id"]
        assert record["source_path"]
        assert record["raw_text"].strip() != ""
        assert record["confidence_type"] in ("direct", "supporting", "learning_only")
    source_types = {record["source_type"] for record in evidence}
    assert "skill" in source_types
    assert "education" in source_types


def test_supported_keyword_is_classified_supported(resume_client) -> None:  # noqa: F811
    client, _ = resume_client
    profile_id, resume_id = _prepare_structured(client)
    result = client.post(f"/api/resumes/{resume_id}/application-customizations", params={"job_id": FASTAPI_INTERN_ID}).json()
    classifications = {c["keyword"]: c["status"] for c in result["keyword_classification"]}
    assert classifications["Python"] == "supported"  # required, explicitly in fixture resume skills
    assert classifications["FastAPI"] == "supported"  # preferred, explicitly in fixture resume skills


def test_unsupported_keyword_is_never_added_to_tailored_skills(resume_client) -> None:  # noqa: F811
    client, _ = resume_client
    profile_id, resume_id = _prepare_structured(client)
    structured = client.get(f"/api/resumes/{resume_id}/structured").json()["data"]
    result = client.post(f"/api/resumes/{resume_id}/application-customizations", params={"job_id": FASTAPI_INTERN_ID}).json()

    classifications = {c["keyword"]: c["status"] for c in result["keyword_classification"]}
    assert classifications["Git"] == "unsupported"  # required skill never mentioned in the fixture resume

    tailored_skills = set(result["tailored_resume"]["skills"])
    original_skills = set(structured["skills"])
    assert tailored_skills == original_skills  # reordered only, never a superset
    assert "Git" not in tailored_skills
    assert "SQL" not in tailored_skills


def test_learning_only_skill_is_classified_partial_and_never_added_as_a_skill(resume_client) -> None:  # noqa: F811
    client, _ = resume_client
    profile_id = create_profile(client)
    resume_id, structured_data = _upload_and_structure(client, profile_id, [
        ("TECHNICAL SKILLS", "Python, FastAPI"),
        ("EDUCATION", "B.Tech Computer Science, Example University, 2024"),
        ("CURRENTLY LEARNING", "Docker, Kubernetes"),
    ])
    assert "Docker" not in structured_data["skills"]

    result = client.post(f"/api/resumes/{resume_id}/application-customizations", params={"job_id": FASTAPI_INTERN_ID}).json()
    classifications = {c["keyword"]: c["status"] for c in result["keyword_classification"]}
    # Docker is a preferred skill for this job; only learning exposure exists, never
    # hands-on evidence, so it must be "partial" — never "supported".
    assert classifications["Docker"] == "partial"
    assert "Docker" not in result["tailored_resume"]["skills"]
    assert "Docker" not in result["tailored_resume"]["summary"]


def test_project_relevance_ordering_ranks_the_backend_project_first_for_a_backend_job(resume_client) -> None:  # noqa: F811
    client, _ = resume_client
    profile_id = create_profile(client)
    resume_id, _data = _upload_and_structure(client, profile_id, _docx_lines([
        "TECHNICAL SKILLS", "Python, FastAPI, React, CSS",
        "EDUCATION", "B.Tech Computer Science, Example University, 2024",
        "PROJECTS",
        "Frontend Dashboard",
        "Built a responsive dashboard UI using React and CSS.",
        "",
        "Backend Task API",
        "Built a REST API backend using Python and FastAPI with SQL persistence.",
    ]))
    result = client.post(f"/api/resumes/{resume_id}/application-customizations", params={"job_id": FASTAPI_INTERN_ID}).json()
    projects = {p["title"]: p["relevance_rank"] for p in result["tailored_resume"]["projects"]}
    assert projects["Backend Task API"] < projects["Frontend Dashboard"]


def test_original_structured_resume_is_never_mutated_by_customization(resume_client) -> None:  # noqa: F811
    client, _ = resume_client
    profile_id, resume_id = _prepare_structured(client)
    before = client.get(f"/api/resumes/{resume_id}/structured").json()

    client.post(f"/api/resumes/{resume_id}/application-customizations", params={"job_id": FASTAPI_INTERN_ID})

    after = client.get(f"/api/resumes/{resume_id}/structured").json()
    assert before["data"] == after["data"]
    assert before["updated_at"] == after["updated_at"]


def test_customization_is_marked_stale_once_the_source_resume_is_newer(db) -> None:  # noqa: F811
    structured_data = {
        "skills": ["Python", "SQL"], "education": [{"degree": "B.Tech", "raw_text": "B.Tech Computer Science, 2026"}],
        "experience": [], "internships": [],
        "projects": [{"title": "Career API", "raw_text": "Career API", "description": "Built REST APIs using Python and SQL.", "technologies": ["Python", "SQL"]}],
        "certifications": [], "achievements": [], "qualifications": [],
    }
    profile, resume, structured = seed_candidate(db, skills=["Python", "SQL"], structured_data=structured_data)
    generated = generate_customization(db, resume.id, FASTAPI_INTERN_ID, profile.user_id)
    assert generated.stale is False

    fresh = get_customization(db, resume.id, generated.id, current_resume_updated_at=structured.updated_at)
    assert fresh is not None and fresh.stale is False

    later = structured.updated_at + timedelta(minutes=5)
    stale = get_customization(db, resume.id, generated.id, current_resume_updated_at=later)
    assert stale is not None
    assert stale.stale is True


def test_no_fabricated_skill_appears_for_a_job_requiring_entirely_absent_technologies(resume_client) -> None:  # noqa: F811
    client, _ = resume_client
    profile_id, resume_id = _prepare_structured(client)
    # JOB-0035's requirements never include AWS/Kubernetes; the fixture resume never
    # mentions them either — neither should ever appear as a claimed skill anywhere.
    result = client.post(f"/api/resumes/{resume_id}/application-customizations", params={"job_id": FASTAPI_INTERN_ID}).json()
    haystacks = [
        " ".join(result["tailored_resume"]["skills"]),
        result["tailored_resume"]["summary"],
        result["cover_letter_text"],
    ]
    for haystack in haystacks:
        assert "aws" not in haystack.lower()
        assert "kubernetes" not in haystack.lower()


def test_regenerating_produces_deterministic_keyword_classification(resume_client) -> None:  # noqa: F811
    client, _ = resume_client
    profile_id, resume_id = _prepare_structured(client)
    first = client.post(f"/api/resumes/{resume_id}/application-customizations", params={"job_id": FASTAPI_INTERN_ID}).json()
    second = client.post(f"/api/resumes/{resume_id}/application-customizations/{first['id']}/regenerate").json()

    assert second["version"] == first["version"] + 1
    first_classification = {c["keyword"]: c["status"] for c in first["keyword_classification"]}
    second_classification = {c["keyword"]: c["status"] for c in second["keyword_classification"]}
    assert first_classification == second_classification
    assert set(first["tailored_resume"]["skills"]) == set(second["tailored_resume"]["skills"])
