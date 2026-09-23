"""Regression tests for the CORS preflight 400 that blocked `/api/auth/me`.

Root cause: `CORSMiddleware` was configured with a fixed, finite list of guessed
dev ports ("5173".."5176"). Vite auto-increments to the next free port whenever a
prior dev server is still holding one, so the frontend's real origin could drift
past that hardcoded list. When it did, the browser's preflight `OPTIONS` request
carried an `Origin` header the middleware didn't recognize, and Starlette replied
`400 Bad Request` ("Disallowed CORS origin") before `/api/auth/me` was ever reached.

The fix (`app/main.py`) allows any `http(s)://localhost:<port>` or
`http(s)://127.0.0.1:<port>` origin via `allow_origin_regex`, gated to
`app_env == "development"`, instead of enumerating ports. `allow_origins=["*"]` is
never used because this app authenticates with a credentialed session cookie, and
the CORS spec (enforced by browsers) forbids combining a wildcard origin with
credentials — these tests also confirm an unrelated origin is still rejected, so
the fix didn't accidentally widen this into a true wildcard.
"""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import Base, get_db
from app.main import app, cors_origin_regex_for_env
from app.models import AuthSession

PASSWORD = "Password123"

PREFLIGHT_HEADERS = {
    "Access-Control-Request-Method": "GET",
    "Access-Control-Request-Headers": "content-type",
}


@pytest.fixture
def client(tmp_path) -> Generator[TestClient, None, None]:
    engine = create_engine(f"sqlite:///{tmp_path / 'cors-api.db'}")
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


def test_cors_origin_regex_active_only_in_development() -> None:
    assert cors_origin_regex_for_env("development") is not None
    assert cors_origin_regex_for_env("production") is None
    assert cors_origin_regex_for_env("test") is None


@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        # Regression case: a Vite instance that drifted past the old hardcoded
        # "5173".."5176" allowlist because earlier dev servers held those ports.
        "http://localhost:5177",
        "http://localhost:9999",
        "http://127.0.0.1:5177",
    ],
)
def test_options_preflight_allowed_for_any_local_dev_port(client: TestClient, origin: str) -> None:
    response = client.options(
        "/api/auth/me",
        headers={"Origin": origin, **PREFLIGHT_HEADERS},
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert response.headers["access-control-allow-credentials"] == "true"


def test_options_preflight_rejected_for_unknown_origin(client: TestClient) -> None:
    response = client.options(
        "/api/auth/me",
        headers={"Origin": "http://evil.com", **PREFLIGHT_HEADERS},
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_actual_response_carries_credentialed_cors_headers_for_allowed_origin(client: TestClient) -> None:
    response = client.get("/api/auth/me", headers={"Origin": "http://localhost:5173"})

    assert response.status_code == 401
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert response.headers["access-control-allow-credentials"] == "true"


def test_unauthenticated_auth_me_returns_401(client: TestClient) -> None:
    assert client.get("/api/auth/me").status_code == 401


def test_authenticated_auth_me_returns_200(client: TestClient) -> None:
    register = client.post(
        "/api/auth/register",
        json={
            "full_name": "Cors Test",
            "email": "cors.test@example.com",
            "password": PASSWORD,
            "confirm_password": PASSWORD,
        },
    )
    assert register.status_code == 201

    response = client.get("/api/auth/me", headers={"Origin": "http://localhost:5173"})
    assert response.status_code == 200
    assert response.json()["user"]["email"] == "cors.test@example.com"


def test_fresh_login_succeeds_after_invalid_session(client: TestClient, tmp_path) -> None:
    client.post(
        "/api/auth/register",
        json={
            "full_name": "Invalid Session",
            "email": "invalid.session@example.com",
            "password": PASSWORD,
            "confirm_password": PASSWORD,
        },
    )
    assert client.get("/api/auth/me").status_code == 200

    engine = create_engine(f"sqlite:///{tmp_path / 'cors-api.db'}")
    with sessionmaker(bind=engine)() as session:
        session.execute(delete(AuthSession))
        session.commit()
    engine.dispose()

    # The stale cookie no longer maps to a live session: /auth/me must cleanly
    # report "no session" rather than erroring, so the UI can fall back to Sign In.
    assert client.get("/api/auth/me").status_code == 401

    login = client.post(
        "/api/auth/login",
        json={"email": "invalid.session@example.com", "password": PASSWORD},
    )
    assert login.status_code == 200
    assert client.get("/api/auth/me").status_code == 200


def test_repeated_auth_me_calls_are_idempotent_and_do_not_error(client: TestClient) -> None:
    # Stand-in for React StrictMode's dev-mode double-invoke of the session-restore
    # effect: repeated calls must stay well-behaved (same result, no server-side
    # state change), not compound into escalating failures.
    for _ in range(3):
        assert client.get("/api/auth/me").status_code == 401
