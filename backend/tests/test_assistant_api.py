"""Milestone 3.4 API-level tests: authentication, ownership isolation, conversation
CRUD, message send end-to-end, and prior-message loading. `get_llm_provider` is
monkeypatched to `NullLLMProvider` here for the same reason `test_interview_prep_api.py`
does it: `get_settings()` is process-wide `lru_cache`d and this repository's real
`backend/.env` may carry a live Gemini key for manual validation, so without this
override these tests would make real, billed calls.
"""

import pytest
from fastapi.testclient import TestClient

import app.services.assistant_service as assistant_service
from app.main import app
from app.services.llm_provider import NullLLMProvider
from test_resume_api import register_session, resume_client  # noqa: F401
from test_structured_context import prepare

FASTAPI_INTERN_ID = "JOB-0035"


@pytest.fixture(autouse=True)
def no_live_llm_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(assistant_service, "get_llm_provider", lambda _settings: NullLLMProvider())


def _prepare_structured(client: TestClient) -> tuple[int, int]:
    profile_id, resume_id = prepare(client)
    assert client.post(f"/api/resumes/{resume_id}/structure").status_code == 200
    return profile_id, resume_id


def test_endpoints_require_authentication(resume_client) -> None:  # noqa: F811
    client, _ = resume_client
    _prepare_structured(client)
    created = client.post("/api/career-assistant/conversations", json={}).json()
    conversation_id = created["id"]
    assert client.post("/api/auth/logout").status_code == 204

    assert client.post("/api/career-assistant/conversations", json={}).status_code == 401
    assert client.get("/api/career-assistant/conversations").status_code == 401
    assert client.get(f"/api/career-assistant/conversations/{conversation_id}").status_code == 401
    assert client.post(f"/api/career-assistant/conversations/{conversation_id}/messages", json={"content": "hi"}).status_code == 401
    assert client.delete(f"/api/career-assistant/conversations/{conversation_id}").status_code == 401


def test_create_and_list_and_get_conversation(resume_client) -> None:  # noqa: F811
    client, _ = resume_client
    _prepare_structured(client)
    created = client.post("/api/career-assistant/conversations", json={"title": "My chat"}).json()
    assert created["title"] == "My chat"
    assert created["messages"] == []

    listing = client.get("/api/career-assistant/conversations").json()
    assert len(listing) == 1
    assert listing[0]["id"] == created["id"]

    fetched = client.get(f"/api/career-assistant/conversations/{created['id']}").json()
    assert fetched["id"] == created["id"]


def test_get_unknown_conversation_404s(resume_client) -> None:  # noqa: F811
    client, _ = resume_client
    _prepare_structured(client)
    assert client.get("/api/career-assistant/conversations/999999").status_code == 404


def test_user_cannot_access_another_users_conversation(resume_client) -> None:  # noqa: F811
    client, _ = resume_client
    _prepare_structured(client)
    created = client.post("/api/career-assistant/conversations", json={}).json()
    conversation_id = created["id"]

    with TestClient(app) as intruder_client:
        register_session(intruder_client, email="intruder-assistant@example.com", full_name="Intruder")
        assert intruder_client.get(f"/api/career-assistant/conversations/{conversation_id}").status_code == 404
        assert intruder_client.post(f"/api/career-assistant/conversations/{conversation_id}/messages", json={"content": "hi"}).status_code == 404
        assert intruder_client.delete(f"/api/career-assistant/conversations/{conversation_id}").status_code == 404

    assert client.get(f"/api/career-assistant/conversations/{conversation_id}").status_code == 200


def test_send_message_end_to_end(resume_client) -> None:  # noqa: F811
    client, _ = resume_client
    _prepare_structured(client)
    conversation_id = client.post("/api/career-assistant/conversations", json={}).json()["id"]

    response = client.post(f"/api/career-assistant/conversations/{conversation_id}/messages", json={"content": f"What skills am I missing for {FASTAPI_INTERN_ID}?"})
    assert response.status_code == 200
    body = response.json()
    assert body["message"]["role"] == "assistant"
    assert body["message"]["intent"] == "SKILL_GAP"
    assert body["message"]["content"]
    assert body["active_job_id"] == FASTAPI_INTERN_ID
    assert body["message"]["generation"]["mode"] in ("llm", "deterministic_fallback")


def test_prior_messages_load_correctly_in_order(resume_client) -> None:  # noqa: F811
    client, _ = resume_client
    _prepare_structured(client)
    conversation_id = client.post("/api/career-assistant/conversations", json={}).json()["id"]

    client.post(f"/api/career-assistant/conversations/{conversation_id}/messages", json={"content": f"Tell me about {FASTAPI_INTERN_ID}"})
    client.post(f"/api/career-assistant/conversations/{conversation_id}/messages", json={"content": "Why does this role fit me?"})

    detail = client.get(f"/api/career-assistant/conversations/{conversation_id}").json()
    assert len(detail["messages"]) == 4
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant", "user", "assistant"]
    assert detail["messages"][2]["content"] == "Why does this role fit me?"


def test_delete_conversation(resume_client) -> None:  # noqa: F811
    client, _ = resume_client
    _prepare_structured(client)
    conversation_id = client.post("/api/career-assistant/conversations", json={}).json()["id"]

    assert client.delete(f"/api/career-assistant/conversations/{conversation_id}").status_code == 204
    assert client.get(f"/api/career-assistant/conversations/{conversation_id}").status_code == 404
    assert client.delete(f"/api/career-assistant/conversations/{conversation_id}").status_code == 404


def test_missing_content_is_rejected(resume_client) -> None:  # noqa: F811
    client, _ = resume_client
    _prepare_structured(client)
    conversation_id = client.post("/api/career-assistant/conversations", json={}).json()["id"]
    response = client.post(f"/api/career-assistant/conversations/{conversation_id}/messages", json={"content": ""})
    assert response.status_code == 422
