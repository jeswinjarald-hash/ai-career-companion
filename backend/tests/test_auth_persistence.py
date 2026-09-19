"""Regression tests for the "correct login fails after a restart" bug.

Root cause: the SQLite database path (and the resume storage directory) were plain
relative strings, resolved by SQLite/`pathlib` against the *process's current working
directory* at the moment the app connects. Two launches of the exact same app from two
different working directories therefore silently created/opened two different physical
files — a user who registered under one working directory would not exist in the other,
producing a 401 "Email or password is incorrect" on a perfectly correct password.

These tests cover two independent things:
  1. `resolve_backend_path` / `_database_url` resolve to the same absolute location
     regardless of the process's current working directory (the actual root cause).
  2. Data written through one engine/session survives being closed and reopened
     through a brand new engine/session pointed at the same file (the actual
     "restart" behavior an end user experiences), which is the scenario the bug
     manifested in.
"""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import resolve_backend_path
from app.core.database import Base, _database_url, get_db
from app.main import app

PASSWORD = "Password123"


def test_resolve_backend_path_is_independent_of_current_working_directory(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    from_cwd_a = resolve_backend_path("./data/ai_career_companion.db")

    other_dir = tmp_path / "somewhere_else"
    other_dir.mkdir()
    monkeypatch.chdir(other_dir)
    from_cwd_b = resolve_backend_path("./data/ai_career_companion.db")

    assert from_cwd_a == from_cwd_b


def test_resolve_backend_path_leaves_absolute_paths_untouched(tmp_path) -> None:
    absolute = tmp_path / "custom" / "app.db"
    assert resolve_backend_path(str(absolute)) == absolute


def test_database_url_resolves_identically_regardless_of_launch_directory(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    url_a = _database_url()

    other_dir = tmp_path / "elsewhere"
    other_dir.mkdir()
    monkeypatch.chdir(other_dir)
    url_b = _database_url()

    assert url_a == url_b
    assert url_a.startswith("sqlite:///")
    assert resolve_backend_path(url_a.removeprefix("sqlite:///")).is_absolute()


def _client_for(engine, session_factory) -> TestClient:
    def override_get_db() -> Generator[Session, None, None]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "restart-sim.db"


def test_login_succeeds_after_full_app_restart_simulation(db_path) -> None:
    # "Process 1": register a user, then shut everything down completely.
    engine_1 = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(bind=engine_1)
    session_factory_1 = sessionmaker(bind=engine_1)
    with _client_for(engine_1, session_factory_1) as client_1:
        response = client_1.post(
            "/api/auth/register",
            json={"full_name": "Restart Test", "email": "restart@example.com", "password": PASSWORD, "confirm_password": PASSWORD},
        )
        assert response.status_code == 201
    app.dependency_overrides.clear()
    engine_1.dispose()

    # "Process 2": a completely fresh engine/session/client bound to the same file —
    # nothing carried over in memory from "process 1" except what's on disk.
    engine_2 = create_engine(f"sqlite:///{db_path}")
    session_factory_2 = sessionmaker(bind=engine_2)
    with _client_for(engine_2, session_factory_2) as client_2:
        login = client_2.post("/api/auth/login", json={"email": "restart@example.com", "password": PASSWORD})
        assert login.status_code == 200
        assert login.json()["user"]["email"] == "restart@example.com"
    app.dependency_overrides.clear()
    engine_2.dispose()


def test_wrong_password_then_correct_password_after_restart(db_path) -> None:
    engine_1 = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(bind=engine_1)
    session_factory_1 = sessionmaker(bind=engine_1)
    with _client_for(engine_1, session_factory_1) as client_1:
        client_1.post(
            "/api/auth/register",
            json={"full_name": "Retry Test", "email": "retry@example.com", "password": PASSWORD, "confirm_password": PASSWORD},
        )
    app.dependency_overrides.clear()
    engine_1.dispose()

    engine_2 = create_engine(f"sqlite:///{db_path}")
    session_factory_2 = sessionmaker(bind=engine_2)
    with _client_for(engine_2, session_factory_2) as client_2:
        wrong = client_2.post("/api/auth/login", json={"email": "retry@example.com", "password": "WrongPass123"})
        assert wrong.status_code == 401

        correct = client_2.post("/api/auth/login", json={"email": "retry@example.com", "password": PASSWORD})
        assert correct.status_code == 200
    app.dependency_overrides.clear()
    engine_2.dispose()


def test_email_whitespace_and_casing_are_normalized_consistently_across_restart(db_path) -> None:
    engine_1 = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(bind=engine_1)
    session_factory_1 = sessionmaker(bind=engine_1)
    with _client_for(engine_1, session_factory_1) as client_1:
        response = client_1.post(
            "/api/auth/register",
            json={"full_name": "Case Test", "email": "  Case.Test@Example.com  ", "password": PASSWORD, "confirm_password": PASSWORD},
        )
        assert response.status_code == 201
        assert response.json()["user"]["email"] == "case.test@example.com"
    app.dependency_overrides.clear()
    engine_1.dispose()

    engine_2 = create_engine(f"sqlite:///{db_path}")
    session_factory_2 = sessionmaker(bind=engine_2)
    with _client_for(engine_2, session_factory_2) as client_2:
        login = client_2.post("/api/auth/login", json={"email": "CASE.TEST@EXAMPLE.COM", "password": PASSWORD})
        assert login.status_code == 200
    app.dependency_overrides.clear()
    engine_2.dispose()


def test_existing_user_and_resume_data_survive_reinitialization(db_path) -> None:
    from app.models import CandidateProfile, Resume

    engine_1 = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(bind=engine_1)
    session_factory_1 = sessionmaker(bind=engine_1)
    with _client_for(engine_1, session_factory_1) as client_1:
        register = client_1.post(
            "/api/auth/register",
            json={"full_name": "Data Survives", "email": "survives@example.com", "password": PASSWORD, "confirm_password": PASSWORD},
        )
        profile_id = register.json()["profile"]["id"]
        with session_factory_1() as session:
            session.add(Resume(
                candidate_profile_id=profile_id, original_filename="resume.pdf", stored_filename="resume-survives.pdf",
                file_type="pdf", mime_type="application/pdf", file_size=10, storage_path="/tmp/resume.pdf", status="uploaded",
            ))
            session.commit()
    app.dependency_overrides.clear()
    engine_1.dispose()

    # Re-initializing against the same file (what `init_db()` does on every real
    # startup) must not drop or clear the tables that already exist.
    engine_2 = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(bind=engine_2)
    with sessionmaker(bind=engine_2)() as session:
        from sqlalchemy import select
        profile = session.scalar(select(CandidateProfile).where(CandidateProfile.email == "survives@example.com"))
        assert profile is not None
        resumes = list(session.scalars(select(Resume).where(Resume.candidate_profile_id == profile.id)))
        assert len(resumes) == 1
        assert resumes[0].original_filename == "resume.pdf"
    engine_2.dispose()


def test_invalid_old_session_cookie_does_not_block_a_fresh_correct_login(db_path) -> None:
    from sqlalchemy import delete

    from app.models import AuthSession

    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    with _client_for(engine, session_factory) as client:
        client.post(
            "/api/auth/register",
            json={"full_name": "Stale Cookie", "email": "stale@example.com", "password": PASSWORD, "confirm_password": PASSWORD},
        )
        assert client.get("/api/auth/me").status_code == 200

        # Simulate a stale session left over from a previous run: the browser still
        # holds the cookie it was given, but the server-side session record behind it
        # is gone (e.g. it expired and was purged, or the dev database was reset).
        with session_factory() as session:
            session.execute(delete(AuthSession))
            session.commit()
        assert client.get("/api/auth/me").status_code == 401

        login = client.post("/api/auth/login", json={"email": "stale@example.com", "password": PASSWORD})
        assert login.status_code == 200
        assert client.get("/api/auth/me").status_code == 200
    app.dependency_overrides.clear()
    engine.dispose()
