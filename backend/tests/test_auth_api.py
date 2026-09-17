from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import Base, get_db
from app.main import app

PASSWORD = "Password123"


@pytest.fixture
def client(tmp_path) -> Generator[TestClient, None, None]:
    engine = create_engine(f"sqlite:///{tmp_path / 'auth-api.db'}")
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


def test_register_creates_user_and_one_linked_profile(client: TestClient) -> None:
    response = client.post(
        "/api/auth/register",
        json={
            "full_name": "Ada Lovelace",
            "email": "ada@example.com",
            "password": PASSWORD,
            "confirm_password": PASSWORD,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["user"]["full_name"] == "Ada Lovelace"
    assert body["user"]["email"] == "ada@example.com"
    assert "password" not in body["user"]
    assert body["profile"] is not None
    assert body["profile"]["full_name"] == "Ada Lovelace"
    assert body["profile"]["email"] == "ada@example.com"
    assert "ai_career_session" in response.cookies

    # exactly one profile is linked to this user
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["profile"]["id"] == body["profile"]["id"]


def test_register_rejects_mismatched_passwords_and_duplicate_email(client: TestClient) -> None:
    mismatched = client.post(
        "/api/auth/register",
        json={
            "full_name": "Ada Lovelace",
            "email": "ada@example.com",
            "password": PASSWORD,
            "confirm_password": "Different123",
        },
    )
    assert mismatched.status_code == 422

    first = client.post(
        "/api/auth/register",
        json={"full_name": "Ada Lovelace", "email": "ada@example.com", "password": PASSWORD, "confirm_password": PASSWORD},
    )
    assert first.status_code == 201

    duplicate = client.post(
        "/api/auth/register",
        json={"full_name": "Ada Two", "email": "ada@example.com", "password": PASSWORD, "confirm_password": PASSWORD},
    )
    assert duplicate.status_code == 409


def test_login_succeeds_and_invalid_login_fails(client: TestClient) -> None:
    client.post(
        "/api/auth/register",
        json={"full_name": "Grace Hopper", "email": "grace@example.com", "password": PASSWORD, "confirm_password": PASSWORD},
    )
    client.post("/api/auth/logout")

    wrong_password = client.post("/api/auth/login", json={"email": "grace@example.com", "password": "WrongPass123"})
    assert wrong_password.status_code == 401

    unknown_email = client.post("/api/auth/login", json={"email": "nobody@example.com", "password": PASSWORD})
    assert unknown_email.status_code == 401

    correct = client.post("/api/auth/login", json={"email": "grace@example.com", "password": PASSWORD})
    assert correct.status_code == 200
    assert correct.json()["user"]["email"] == "grace@example.com"


def test_me_requires_session_and_survives_repeated_requests(client: TestClient) -> None:
    assert client.get("/api/auth/me").status_code == 401

    client.post(
        "/api/auth/register",
        json={"full_name": "Linus Torvalds", "email": "linus@example.com", "password": PASSWORD, "confirm_password": PASSWORD},
    )

    # simulates a page refresh: a fresh request on the same client (same cookie jar) stays authenticated
    first = client.get("/api/auth/me")
    second = client.get("/api/auth/me")
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["user"]["email"] == "linus@example.com"


def test_logout_invalidates_session(client: TestClient) -> None:
    client.post(
        "/api/auth/register",
        json={"full_name": "Margaret Hamilton", "email": "margaret@example.com", "password": PASSWORD, "confirm_password": PASSWORD},
    )
    assert client.get("/api/auth/me").status_code == 200

    logout_response = client.post("/api/auth/logout")
    assert logout_response.status_code == 204

    assert client.get("/api/auth/me").status_code == 401
