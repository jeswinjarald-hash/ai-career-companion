from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import Base, get_db
from app.main import app
from test_resume_api import register_session


@pytest.fixture
def client(tmp_path) -> Generator[TestClient, None, None]:
    engine = create_engine(f"sqlite:///{tmp_path / 'profile-api.db'}")
    session_factory = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db() -> Generator[Session, None, None]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    engine.dispose()


PROFILE_UPDATE_PAYLOAD = {
    "full_name": "Test Candidate",
    "education": "B.Tech",
    "degree": "B.Tech",
    "specialization": "Information Technology",
    "experience_level": "Student",
    "career_interests": [" Backend Development ", "Backend Development", "Cloud Computing"],
    "target_roles": [" Backend Engineer "],
    "skills": [" Python ", "Python", "SQL"],
    "career_goals": "Build strong backend engineering skills.",
}


def test_registration_creates_linked_profile_and_update_persists(client: TestClient) -> None:
    session = register_session(client, email="candidate@example.com", full_name="Test Candidate")
    profile = session["profile"]
    assert profile is not None
    assert profile["email"] == "candidate@example.com"
    assert profile["full_name"] == "Test Candidate"
    profile_id = profile["id"]
    created_updated_at = profile["updated_at"]

    get_response = client.get(f"/api/profiles/{profile_id}")
    assert get_response.status_code == 200
    assert get_response.json()["email"] == "candidate@example.com"

    update_response = client.patch(f"/api/profiles/{profile_id}", json=PROFILE_UPDATE_PAYLOAD)
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["experience_level"] == "Student"
    assert updated["career_interests"] == ["Backend Development", "Cloud Computing"]
    assert updated["skills"] == ["Python", "SQL"]
    assert updated["updated_at"] > created_updated_at

    persisted_response = client.get(f"/api/profiles/{profile_id}")
    assert persisted_response.json()["experience_level"] == "Student"


def test_profile_routes_require_authentication(client: TestClient) -> None:
    session = register_session(client, email="owner@example.com")
    profile_id = session["profile"]["id"]
    assert client.post("/api/auth/logout").status_code == 204

    assert client.get(f"/api/profiles/{profile_id}").status_code == 401
    assert client.patch(f"/api/profiles/{profile_id}", json={"full_name": "Nobody"}).status_code == 401
    assert client.post("/api/profiles", json={"full_name": "X", "email": "x@example.com"}).status_code == 401


def test_user_cannot_access_or_update_another_users_profile(client: TestClient) -> None:
    owner_session = register_session(client, email="owner@example.com")
    owner_profile_id = owner_session["profile"]["id"]

    with TestClient(app) as intruder_client:
        intruder_session = register_session(intruder_client, email="intruder@example.com", full_name="Intruder")
        assert intruder_session["profile"]["id"] != owner_profile_id

        assert intruder_client.get(f"/api/profiles/{owner_profile_id}").status_code == 404
        assert intruder_client.patch(
            f"/api/profiles/{owner_profile_id}", json={"full_name": "Hijacked"}
        ).status_code == 404

    # the owner's own profile is untouched by the intruder's attempts
    owner_profile = client.get(f"/api/profiles/{owner_profile_id}").json()
    assert owner_profile["full_name"] == owner_session["user"]["full_name"]


def test_create_profile_requires_auth_and_validates_payload(client: TestClient) -> None:
    register_session(client, email="creator@example.com")

    create_response = client.post(
        "/api/profiles", json={"full_name": "Second Profile", "email": "second@example.com"}
    )
    assert create_response.status_code == 201

    duplicate_response = client.post(
        "/api/profiles", json={"full_name": "Second Profile", "email": "second@example.com"}
    )
    assert duplicate_response.status_code == 409
    assert duplicate_response.json() == {"detail": "A profile with this email already exists."}

    invalid_payloads = [
        {"email": "missing-name@example.com"},
        {"full_name": "   ", "email": "blank-name@example.com"},
        {"full_name": "Invalid Email", "email": "not-an-email"},
    ]
    for payload in invalid_payloads:
        response = client.post("/api/profiles", json=payload)
        assert response.status_code == 422


def test_profile_not_found_and_openapi_contract(client: TestClient) -> None:
    register_session(client, email="lookup@example.com")

    missing_response = client.get("/api/profiles/999999")
    assert missing_response.status_code == 404
    assert missing_response.json() == {"detail": "Candidate profile not found."}

    missing_update_response = client.patch("/api/profiles/999999", json={"full_name": "Nobody"})
    assert missing_update_response.status_code == 404

    openapi = client.get("/openapi.json").json()
    assert "/api/profiles" in openapi["paths"]
    assert "/api/profiles/{profile_id}" in openapi["paths"]