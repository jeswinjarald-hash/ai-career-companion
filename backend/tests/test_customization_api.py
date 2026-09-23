"""Milestone 3.2 API-level tests: authentication, ownership (spec test case H),
versioning (never overwrites a prior version), user edits, regeneration, and export.
"""

from fastapi.testclient import TestClient

from app.main import app
from test_resume_api import register_session, resume_client  # noqa: F401
from test_structured_context import prepare

FASTAPI_INTERN_ID = "JOB-0035"  # required: Python, SQL, REST APIs, Git — preferred: FastAPI, Flask, PostgreSQL, Docker, Agile


def _prepare_structured(client: TestClient) -> tuple[int, int]:
    profile_id, resume_id = prepare(client)
    assert client.post(f"/api/resumes/{resume_id}/structure").status_code == 200
    return profile_id, resume_id


def test_customization_endpoints_require_authentication(resume_client) -> None:  # noqa: F811
    client, _ = resume_client
    profile_id, resume_id = _prepare_structured(client)
    generated = client.post(f"/api/resumes/{resume_id}/application-customizations", params={"job_id": FASTAPI_INTERN_ID}).json()
    customization_id = generated["id"]
    assert client.post("/api/auth/logout").status_code == 204

    assert client.post(f"/api/resumes/{resume_id}/application-customizations", params={"job_id": FASTAPI_INTERN_ID}).status_code == 401
    assert client.get(f"/api/resumes/{resume_id}/application-customizations").status_code == 401
    assert client.get(f"/api/resumes/{resume_id}/application-customizations/{customization_id}").status_code == 401
    assert client.patch(f"/api/resumes/{resume_id}/application-customizations/{customization_id}", json={"summary": "x"}).status_code == 401
    assert client.post(f"/api/resumes/{resume_id}/application-customizations/{customization_id}/regenerate").status_code == 401
    assert client.get(f"/api/resumes/{resume_id}/application-customizations/{customization_id}/export", params={"document": "resume", "format": "pdf"}).status_code == 401


def test_customization_requires_structured_resume(resume_client) -> None:  # noqa: F811
    client, _ = resume_client
    profile_id = register_session(client, email="fresh-m32@example.com")["profile"]["id"]
    upload = client.post(f"/api/profiles/{profile_id}/resumes", files={"file": ("resume.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")})
    if upload.status_code != 201:
        return
    resume_id = upload.json()["id"]
    response = client.post(f"/api/resumes/{resume_id}/application-customizations", params={"job_id": FASTAPI_INTERN_ID})
    assert response.status_code == 409


def test_customization_404s_for_unknown_resume_and_unknown_job(resume_client) -> None:  # noqa: F811
    client, _ = resume_client
    profile_id, resume_id = _prepare_structured(client)

    assert client.post("/api/resumes/999999/application-customizations", params={"job_id": FASTAPI_INTERN_ID}).status_code == 404
    assert client.post(f"/api/resumes/{resume_id}/application-customizations", params={"job_id": "JOB-DOES-NOT-EXIST"}).status_code == 404
    assert client.get(f"/api/resumes/{resume_id}/application-customizations/999999").status_code == 404


def test_user_cannot_access_or_edit_another_users_customization(resume_client) -> None:  # noqa: F811
    client, _ = resume_client
    profile_id, resume_id = _prepare_structured(client)
    generated = client.post(f"/api/resumes/{resume_id}/application-customizations", params={"job_id": FASTAPI_INTERN_ID}).json()
    customization_id = generated["id"]

    with TestClient(app) as intruder_client:
        register_session(intruder_client, email="intruder-m32@example.com", full_name="Intruder")
        assert intruder_client.get(f"/api/resumes/{resume_id}/application-customizations/{customization_id}").status_code == 404
        assert intruder_client.get(f"/api/resumes/{resume_id}/application-customizations").status_code == 404
        assert intruder_client.patch(f"/api/resumes/{resume_id}/application-customizations/{customization_id}", json={"summary": "hacked"}).status_code == 404
        assert intruder_client.post(f"/api/resumes/{resume_id}/application-customizations/{customization_id}/regenerate").status_code == 404
        assert intruder_client.get(f"/api/resumes/{resume_id}/application-customizations/{customization_id}/export", params={"document": "resume", "format": "pdf"}).status_code == 404

    # owner's own access is unaffected
    assert client.get(f"/api/resumes/{resume_id}/application-customizations/{customization_id}").status_code == 200


def test_regenerate_creates_a_new_version_and_keeps_the_prior_one(resume_client) -> None:  # noqa: F811
    client, _ = resume_client
    profile_id, resume_id = _prepare_structured(client)
    v1 = client.post(f"/api/resumes/{resume_id}/application-customizations", params={"job_id": FASTAPI_INTERN_ID}).json()
    assert v1["version"] == 1

    v2 = client.post(f"/api/resumes/{resume_id}/application-customizations/{v1['id']}/regenerate").json()
    assert v2["version"] == 2
    assert v2["id"] != v1["id"]

    # the prior version is still readable, unmodified — never overwritten
    still_v1 = client.get(f"/api/resumes/{resume_id}/application-customizations/{v1['id']}")
    assert still_v1.status_code == 200
    assert still_v1.json()["version"] == 1

    listing = client.get(f"/api/resumes/{resume_id}/application-customizations", params={"job_id": FASTAPI_INTERN_ID}).json()
    assert {item["version"] for item in listing} == {1, 2}


def test_generating_again_for_the_same_job_creates_a_new_version_not_an_overwrite(resume_client) -> None:  # noqa: F811
    client, _ = resume_client
    profile_id, resume_id = _prepare_structured(client)
    first = client.post(f"/api/resumes/{resume_id}/application-customizations", params={"job_id": FASTAPI_INTERN_ID}).json()
    second = client.post(f"/api/resumes/{resume_id}/application-customizations", params={"job_id": FASTAPI_INTERN_ID}).json()
    assert second["id"] != first["id"]
    assert second["version"] == first["version"] + 1


def test_user_edit_is_persisted_and_marked_as_user_edited_not_generated(resume_client) -> None:  # noqa: F811
    client, _ = resume_client
    profile_id, resume_id = _prepare_structured(client)
    generated = client.post(f"/api/resumes/{resume_id}/application-customizations", params={"job_id": FASTAPI_INTERN_ID}).json()
    customization_id = generated["id"]
    original_summary = generated["tailored_resume"]["summary"]

    edit = client.patch(
        f"/api/resumes/{resume_id}/application-customizations/{customization_id}",
        json={"summary": "I am an excellent candidate with unverifiable claims."},
    )
    assert edit.status_code == 200
    body = edit.json()
    assert body["tailored_resume"]["summary"] == "I am an excellent candidate with unverifiable claims."
    assert body["tailored_resume"]["summary"] != original_summary
    assert "summary" in body["user_edits"]["edited_fields"]

    # persisted — re-fetching shows the same edited content, not the original generated text
    refetched = client.get(f"/api/resumes/{resume_id}/application-customizations/{customization_id}")
    assert refetched.json()["tailored_resume"]["summary"] == "I am an excellent candidate with unverifiable claims."


def test_export_returns_pdf_and_docx_for_resume_and_cover_letter(resume_client) -> None:  # noqa: F811
    client, _ = resume_client
    profile_id, resume_id = _prepare_structured(client)
    generated = client.post(f"/api/resumes/{resume_id}/application-customizations", params={"job_id": FASTAPI_INTERN_ID}).json()
    customization_id = generated["id"]

    for document in ("resume", "cover_letter"):
        for fmt in ("pdf", "docx"):
            response = client.get(
                f"/api/resumes/{resume_id}/application-customizations/{customization_id}/export",
                params={"document": document, "format": fmt},
            )
            assert response.status_code == 200, response.text
            assert len(response.content) > 0
            assert response.headers["content-disposition"].startswith("attachment;")
            if fmt == "pdf":
                assert response.content[:4] == b"%PDF"


def test_export_rejects_invalid_document_or_format(resume_client) -> None:  # noqa: F811
    client, _ = resume_client
    profile_id, resume_id = _prepare_structured(client)
    generated = client.post(f"/api/resumes/{resume_id}/application-customizations", params={"job_id": FASTAPI_INTERN_ID}).json()
    customization_id = generated["id"]

    assert client.get(f"/api/resumes/{resume_id}/application-customizations/{customization_id}/export", params={"document": "resume", "format": "txt"}).status_code == 422
    assert client.get(f"/api/resumes/{resume_id}/application-customizations/{customization_id}/export", params={"document": "invalid", "format": "pdf"}).status_code == 422
