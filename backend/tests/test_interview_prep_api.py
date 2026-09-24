"""Milestone 3.3 API-level tests: authentication, ownership isolation, versioning
(regenerate never overwrites a prior version), and the optional mock-answer endpoint.

`get_llm_provider` is monkeypatched to always return `NullLLMProvider` here: the real
`backend/.env` may have a live Gemini key configured for manual/browser validation,
but `get_settings()` is process-wide `lru_cache`d, so without this override these
API-level tests would make real, billed calls to Gemini. Both call sites
(`app.services.interview_prep_service` and `app.api.interview_prep` each bind their
own local `get_llm_provider` name via `from ... import`) must be patched, since
patching the origin module alone would not affect already-bound imported names.
"""

import pytest
from fastapi.testclient import TestClient

import app.api.interview_prep as interview_prep_api
import app.services.interview_prep_service as interview_prep_service
from app.main import app
from app.services.llm_provider import NullLLMProvider
from test_resume_api import register_session, resume_client  # noqa: F401
from test_structured_context import prepare

FASTAPI_INTERN_ID = "JOB-0035"  # required: Python, SQL, REST APIs, Git — preferred: FastAPI, Flask, PostgreSQL, Docker, Agile


@pytest.fixture(autouse=True)
def no_live_llm_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(interview_prep_service, "get_llm_provider", lambda _settings: NullLLMProvider())
    monkeypatch.setattr(interview_prep_api, "get_llm_provider", lambda _settings: NullLLMProvider())


def _prepare_structured(client: TestClient) -> tuple[int, int]:
    profile_id, resume_id = prepare(client)
    assert client.post(f"/api/resumes/{resume_id}/structure").status_code == 200
    return profile_id, resume_id


def test_interview_prep_requires_authentication(resume_client) -> None:  # noqa: F811
    client, _ = resume_client
    profile_id, resume_id = _prepare_structured(client)
    generated = client.post(f"/api/resumes/{resume_id}/interview-preparations", params={"job_id": FASTAPI_INTERN_ID}).json()
    prep_id = generated["id"]
    assert client.post("/api/auth/logout").status_code == 204

    assert client.post(f"/api/resumes/{resume_id}/interview-preparations", params={"job_id": FASTAPI_INTERN_ID}).status_code == 401
    assert client.get(f"/api/resumes/{resume_id}/interview-preparations").status_code == 401
    assert client.get(f"/api/resumes/{resume_id}/interview-preparations/{prep_id}").status_code == 401
    assert client.post(f"/api/resumes/{resume_id}/interview-preparations/{prep_id}/regenerate").status_code == 401
    assert client.post(f"/api/resumes/{resume_id}/interview-preparations/{prep_id}/mock-answer", json={"question_index": 0, "answer": "test"}).status_code == 401


def test_interview_prep_requires_structured_resume(resume_client) -> None:  # noqa: F811
    client, _ = resume_client
    profile_id = register_session(client, email="fresh-interview@example.com")["profile"]["id"]
    upload = client.post(f"/api/profiles/{profile_id}/resumes", files={"file": ("resume.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")})
    if upload.status_code != 201:
        return
    resume_id = upload.json()["id"]
    response = client.post(f"/api/resumes/{resume_id}/interview-preparations", params={"job_id": FASTAPI_INTERN_ID})
    assert response.status_code == 409


def test_interview_prep_404s_for_unknown_resume_and_unknown_job(resume_client) -> None:  # noqa: F811
    client, _ = resume_client
    profile_id, resume_id = _prepare_structured(client)

    assert client.post("/api/resumes/999999/interview-preparations", params={"job_id": FASTAPI_INTERN_ID}).status_code == 404
    assert client.post(f"/api/resumes/{resume_id}/interview-preparations", params={"job_id": "JOB-DOES-NOT-EXIST"}).status_code == 404
    assert client.get(f"/api/resumes/{resume_id}/interview-preparations/999999").status_code == 404


def test_user_cannot_access_another_users_interview_prep(resume_client) -> None:  # noqa: F811
    client, _ = resume_client
    profile_id, resume_id = _prepare_structured(client)
    generated = client.post(f"/api/resumes/{resume_id}/interview-preparations", params={"job_id": FASTAPI_INTERN_ID}).json()
    prep_id = generated["id"]

    with TestClient(app) as intruder_client:
        register_session(intruder_client, email="intruder-interview@example.com", full_name="Intruder")
        assert intruder_client.get(f"/api/resumes/{resume_id}/interview-preparations/{prep_id}").status_code == 404
        assert intruder_client.get(f"/api/resumes/{resume_id}/interview-preparations").status_code == 404
        assert intruder_client.post(f"/api/resumes/{resume_id}/interview-preparations/{prep_id}/regenerate").status_code == 404
        assert intruder_client.post(f"/api/resumes/{resume_id}/interview-preparations/{prep_id}/mock-answer", json={"question_index": 0, "answer": "test"}).status_code == 404

    # owner's own access is unaffected
    assert client.get(f"/api/resumes/{resume_id}/interview-preparations/{prep_id}").status_code == 200


def test_regenerate_creates_a_new_version_and_keeps_the_prior_one(resume_client) -> None:  # noqa: F811
    client, _ = resume_client
    profile_id, resume_id = _prepare_structured(client)
    v1 = client.post(f"/api/resumes/{resume_id}/interview-preparations", params={"job_id": FASTAPI_INTERN_ID}).json()
    assert v1["version"] == 1

    v2 = client.post(f"/api/resumes/{resume_id}/interview-preparations/{v1['id']}/regenerate").json()
    assert v2["version"] == 2
    assert v2["id"] != v1["id"]

    still_v1 = client.get(f"/api/resumes/{resume_id}/interview-preparations/{v1['id']}")
    assert still_v1.status_code == 200
    assert still_v1.json()["version"] == 1

    listing = client.get(f"/api/resumes/{resume_id}/interview-preparations", params={"job_id": FASTAPI_INTERN_ID}).json()
    assert {item["version"] for item in listing} == {1, 2}


def test_generating_again_for_the_same_job_creates_a_new_version(resume_client) -> None:  # noqa: F811
    client, _ = resume_client
    profile_id, resume_id = _prepare_structured(client)
    first = client.post(f"/api/resumes/{resume_id}/interview-preparations", params={"job_id": FASTAPI_INTERN_ID}).json()
    second = client.post(f"/api/resumes/{resume_id}/interview-preparations", params={"job_id": FASTAPI_INTERN_ID}).json()
    assert second["id"] != first["id"]
    assert second["version"] == first["version"] + 1


def test_full_preparation_structure_and_categories(resume_client) -> None:  # noqa: F811
    client, _ = resume_client
    profile_id, resume_id = _prepare_structured(client)
    result = client.post(f"/api/resumes/{resume_id}/interview-preparations", params={"job_id": FASTAPI_INTERN_ID}).json()

    assert result["job_id"] == FASTAPI_INTERN_ID
    assert result["preparation_summary"]
    categories = {q["category"] for q in result["questions"]}
    assert categories == {"technical", "resume", "project", "role", "hr", "skill_gap"}
    for q in result["questions"]:
        assert q["difficulty"] in ("easy", "medium", "hard")
        assert q["why_asked"]
        assert q["what_interviewer_is_testing"]
        assert q["preparation_guidance"]
    assert result["revision_plan"]
    assert result["generation"]["mode"] in ("llm", "deterministic_fallback")


def test_mock_answer_endpoint_returns_grounded_evaluation(resume_client) -> None:  # noqa: F811
    client, _ = resume_client
    profile_id, resume_id = _prepare_structured(client)
    prep = client.post(f"/api/resumes/{resume_id}/interview-preparations", params={"job_id": FASTAPI_INTERN_ID}).json()
    prep_id = prep["id"]

    response = client.post(
        f"/api/resumes/{resume_id}/interview-preparations/{prep_id}/mock-answer",
        json={"question_index": 0, "answer": "I built this using FastAPI and Python, focusing on clean REST endpoint design."},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["suggested_structure"]
    assert body["grounded_feedback"]
    assert body["generation"]["mode"] in ("llm", "deterministic_fallback")
    assert "score" not in body  # no numeric/fake score field


def test_mock_answer_rejects_out_of_range_question_index(resume_client) -> None:  # noqa: F811
    client, _ = resume_client
    profile_id, resume_id = _prepare_structured(client)
    prep = client.post(f"/api/resumes/{resume_id}/interview-preparations", params={"job_id": FASTAPI_INTERN_ID}).json()
    prep_id = prep["id"]

    response = client.post(
        f"/api/resumes/{resume_id}/interview-preparations/{prep_id}/mock-answer",
        json={"question_index": 99999, "answer": "test"},
    )
    assert response.status_code == 404
