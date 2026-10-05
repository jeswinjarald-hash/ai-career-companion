"""Milestone 4.1 API tests: application tracking CRUD, dataset snapshotting, duplicate
protection, ownership, status lifecycle, dates, filtering, summary, reminders, and
links to generated customization / interview-preparation records.

Generated-document rows are inserted directly (no generation pipeline, no LLM), since
only their ownership and job_id matter to the tracker.
"""

from collections.abc import Generator
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import Base, get_db
from app.main import app
from app.models import ApplicationCustomization, InterviewPreparation, Resume
from app.services.job_dataset_service import load_job_postings
from test_resume_api import DEFAULT_PASSWORD

JOB_A = "JOB-0035"
JOB_B = "JOB-0001"


@pytest.fixture
def tracker(tmp_path) -> Generator[tuple[TestClient, sessionmaker], None, None]:
    engine = create_engine(f"sqlite:///{tmp_path / 'applications-api.db'}")
    session_factory = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db() -> Generator[Session, None, None]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client, session_factory
    app.dependency_overrides.clear()
    engine.dispose()


def login_as(client: TestClient, email: str) -> dict:
    """Registers (first time) or logs in, leaving `client` authenticated as `email`."""
    register = client.post("/api/auth/register", json={"full_name": email.split("@")[0], "email": email, "password": DEFAULT_PASSWORD, "confirm_password": DEFAULT_PASSWORD})
    if register.status_code == 201:
        return register.json()
    response = client.post("/api/auth/login", json={"email": email, "password": DEFAULT_PASSWORD})
    assert response.status_code == 200
    return response.json()


def manual(client: TestClient, **fields) -> dict:
    response = client.post("/api/applications", json={"company": "Acme Labs", "job_title": "Data Intern", **fields})
    assert response.status_code == 201, response.text
    return response.json()


def insert_artifacts(session_factory: sessionmaker, auth: dict, job_id: str) -> tuple[int, int]:
    now = datetime.now(timezone.utc)
    with session_factory() as db:
        resume = Resume(
            candidate_profile_id=auth["profile"]["id"], original_filename="cv.pdf",
            stored_filename=f"resume_{auth['user']['id']}_{job_id}_{now.timestamp()}.pdf", file_type="pdf",
            mime_type="application/pdf", file_size=10, storage_path="unused", status="uploaded",
        )
        db.add(resume)
        db.flush()
        common = {"user_id": auth["user"]["id"], "resume_id": resume.id, "job_id": job_id, "version": 1, "source_resume_updated_at": now, "data": {}}
        customization = ApplicationCustomization(**common)
        preparation = InterviewPreparation(**common)
        db.add_all([customization, preparation])
        db.commit()
        return customization.id, preparation.id


# --- Creation -----------------------------------------------------------------

def test_manual_application_is_created_with_defaults(tracker) -> None:
    client, _ = tracker
    login_as(client, "student@example.com")
    created = manual(client, location="Remote", notes="  Referred by a friend  ")

    assert created["source"] == "manual"
    assert created["job_id"] is None
    assert created["status"] == "saved"
    assert created["is_active"] is True
    assert created["notes"] == "Referred by a friend"
    for field in ("applied_date", "deadline", "interview_at", "follow_up_date", "customization_id", "interview_preparation_id"):
        assert created[field] is None

    fetched = client.get(f"/api/applications/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == created


def test_manual_application_requires_company_and_title(tracker) -> None:
    client, _ = tracker
    login_as(client, "student@example.com")
    assert client.post("/api/applications", json={"company": "Acme"}).status_code == 422
    assert client.post("/api/applications", json={"job_title": "Intern"}).status_code == 422
    assert client.post("/api/applications", json={"company": "   ", "job_title": "Intern"}).status_code == 422
    assert client.post("/api/applications", json={}).status_code == 422


def test_dataset_application_snapshots_the_canonical_opportunity(tracker) -> None:
    client, _ = tracker
    login_as(client, "student@example.com")
    job = next(job for job in load_job_postings() if job.job_id == JOB_A)

    response = client.post("/api/applications", json={"job_id": JOB_A, "deadline": "2026-12-01", "notes": "Strong fit"})
    assert response.status_code == 201
    created = response.json()
    assert created["source"] == "dataset"
    assert created["job_id"] == JOB_A
    assert created["company"] == job.company
    assert created["job_title"] == job.job_title
    assert created["employment_type"] == job.employment_type
    assert created["location"] == job.location
    assert created["work_mode"] == job.work_mode
    assert created["job_description"] == job.job_description
    assert created["deadline"] == "2026-12-01"


def test_dataset_application_rejects_client_supplied_opportunity_details(tracker) -> None:
    client, _ = tracker
    login_as(client, "student@example.com")
    response = client.post("/api/applications", json={"job_id": JOB_A, "company": "Spoofed Corp"})
    assert response.status_code == 422


def test_dataset_application_never_derives_a_deadline(tracker) -> None:
    client, _ = tracker
    login_as(client, "student@example.com")
    created = client.post("/api/applications", json={"job_id": JOB_A}).json()
    assert created["deadline"] is None


def test_unknown_job_id_is_rejected(tracker) -> None:
    client, _ = tracker
    login_as(client, "student@example.com")
    assert client.post("/api/applications", json={"job_id": "JOB-9999"}).status_code == 404


def test_duplicate_dataset_application_is_rejected_but_manual_lookalikes_are_allowed(tracker) -> None:
    client, _ = tracker
    login_as(client, "student@example.com")
    assert client.post("/api/applications", json={"job_id": JOB_A}).status_code == 201
    assert client.post("/api/applications", json={"job_id": JOB_A, "status": "applied"}).status_code == 409

    manual(client)
    manual(client)
    assert len(client.get("/api/applications").json()) == 3


def test_different_users_may_track_the_same_job(tracker) -> None:
    client, _ = tracker
    login_as(client, "first@example.com")
    assert client.post("/api/applications", json={"job_id": JOB_A}).status_code == 201
    login_as(client, "second@example.com")
    assert client.post("/api/applications", json={"job_id": JOB_A}).status_code == 201


def test_unknown_fields_and_statuses_are_rejected_on_create(tracker) -> None:
    client, _ = tracker
    login_as(client, "student@example.com")
    assert client.post("/api/applications", json={"company": "A", "job_title": "B", "status": "hired"}).status_code == 422
    assert client.post("/api/applications", json={"company": "A", "job_title": "B", "source": "dataset"}).status_code == 422
    assert client.post("/api/applications", json={"company": "A", "job_title": "B", "interview_status": "maybe"}).status_code == 422


# --- Authentication / ownership -------------------------------------------------

def test_application_endpoints_require_authentication(tracker) -> None:
    client, _ = tracker
    login_as(client, "student@example.com")
    application_id = manual(client)["id"]
    assert client.post("/api/auth/logout").status_code == 204

    assert client.post("/api/applications", json={"company": "A", "job_title": "B"}).status_code == 401
    assert client.get("/api/applications").status_code == 401
    assert client.get("/api/applications/summary").status_code == 401
    assert client.get("/api/applications/reminders").status_code == 401
    assert client.get(f"/api/applications/{application_id}").status_code == 401
    assert client.patch(f"/api/applications/{application_id}", json={"status": "applied"}).status_code == 401
    assert client.delete(f"/api/applications/{application_id}").status_code == 401


def test_user_cannot_read_update_or_delete_another_users_application(tracker) -> None:
    client, _ = tracker
    login_as(client, "owner@example.com")
    application_id = manual(client, notes="private")["id"]

    login_as(client, "intruder@example.com")
    assert client.get(f"/api/applications/{application_id}").status_code == 404
    assert client.patch(f"/api/applications/{application_id}", json={"status": "withdrawn"}).status_code == 404
    assert client.delete(f"/api/applications/{application_id}").status_code == 404
    assert client.get("/api/applications").json() == []
    assert client.get("/api/applications/summary").json()["total_applications"] == 0

    login_as(client, "owner@example.com")
    owned = client.get(f"/api/applications/{application_id}").json()
    assert owned["status"] == "saved"
    assert owned["notes"] == "private"


def test_delete_removes_only_the_owned_application(tracker) -> None:
    client, _ = tracker
    login_as(client, "student@example.com")
    keep = manual(client)["id"]
    remove = manual(client, company="Other Co")["id"]
    assert client.delete(f"/api/applications/{remove}").status_code == 204
    assert client.get(f"/api/applications/{remove}").status_code == 404
    assert [item["id"] for item in client.get("/api/applications").json()] == [keep]


# --- Status lifecycle ---------------------------------------------------------

def test_status_updates_track_status_updated_at_and_allow_moving_backward(tracker) -> None:
    client, _ = tracker
    login_as(client, "student@example.com")
    created = manual(client)
    first_stamp = created["status_updated_at"]

    applied = client.patch(f"/api/applications/{created['id']}", json={"status": "applied"}).json()
    assert applied["status"] == "applied"
    assert applied["status_updated_at"] > first_stamp

    notes_only = client.patch(f"/api/applications/{created['id']}", json={"notes": "Sent via portal"}).json()
    assert notes_only["status_updated_at"] == applied["status_updated_at"]

    same_status = client.patch(f"/api/applications/{created['id']}", json={"status": "applied"}).json()
    assert same_status["status_updated_at"] == applied["status_updated_at"]

    offer = client.patch(f"/api/applications/{created['id']}", json={"status": "offer"}).json()
    assert offer["is_active"] is False
    corrected = client.patch(f"/api/applications/{created['id']}", json={"status": "planning"}).json()
    assert corrected["status"] == "planning"
    assert corrected["is_active"] is True


def test_invalid_or_cleared_status_is_rejected(tracker) -> None:
    client, _ = tracker
    login_as(client, "student@example.com")
    application_id = manual(client)["id"]
    assert client.patch(f"/api/applications/{application_id}", json={"status": "hired"}).status_code == 422
    assert client.patch(f"/api/applications/{application_id}", json={"status": None}).status_code == 422
    assert client.get(f"/api/applications/{application_id}").json()["status"] == "saved"


def test_dataset_snapshot_cannot_be_edited_but_manual_details_can(tracker) -> None:
    client, _ = tracker
    login_as(client, "student@example.com")
    dataset_id = client.post("/api/applications", json={"job_id": JOB_A}).json()["id"]
    assert client.patch(f"/api/applications/{dataset_id}", json={"company": "Other"}).status_code == 409

    manual_id = manual(client)["id"]
    updated = client.patch(f"/api/applications/{manual_id}", json={"company": "Acme Research", "location": "Pune"}).json()
    assert updated["company"] == "Acme Research"
    assert updated["location"] == "Pune"
    assert client.patch(f"/api/applications/{manual_id}", json={"job_title": None}).status_code == 422


# --- Dates --------------------------------------------------------------------

def test_dates_are_stored_cleared_and_validated(tracker) -> None:
    client, _ = tracker
    login_as(client, "student@example.com")
    created = manual(
        client, applied_date="2026-09-01", deadline="2026-09-30", follow_up_date="2026-09-15",
        interview_at="2026-10-10T15:30:00+05:30", interview_status="scheduled",
    )
    assert created["applied_date"] == "2026-09-01"
    assert created["deadline"] == "2026-09-30"
    assert created["follow_up_date"] == "2026-09-15"
    # Stored and returned as the same instant, normalised to UTC.
    assert datetime.fromisoformat(created["interview_at"]) == datetime(2026, 10, 10, 10, 0, tzinfo=timezone.utc)
    assert datetime.fromisoformat(created["interview_at"]).utcoffset() == timedelta(0)

    cleared = client.patch(f"/api/applications/{created['id']}", json={"deadline": None, "interview_at": None, "interview_status": None}).json()
    assert cleared["deadline"] is None
    assert cleared["interview_at"] is None
    assert cleared["applied_date"] == "2026-09-01"

    # A naive interview time is ambiguous and is rejected rather than reinterpreted.
    assert client.patch(f"/api/applications/{created['id']}", json={"interview_at": "2026-10-10T15:30:00"}).status_code == 422
    assert client.patch(f"/api/applications/{created['id']}", json={"deadline": "2026-02-30"}).status_code == 422


# --- Filtering ----------------------------------------------------------------

@pytest.fixture
def seeded(tracker) -> TestClient:
    client, _ = tracker
    login_as(client, "student@example.com")
    manual(client, company="Acme Labs", job_title="Data Analyst Intern", status="applied", applied_date="2026-08-10", deadline="2026-08-01")
    manual(client, company="Globex", job_title="Backend Developer", status="saved", deadline="2026-11-20")
    manual(client, company="Initech", job_title="Data Engineer Trainee", status="rejected", applied_date="2026-07-05", deadline="2026-07-01")
    manual(client, company="Acme Cloud", job_title="DevOps Apprentice", status="offer", applied_date="2026-09-01")
    manual(client, company="100%_Wild", job_title="QA Intern", status="interview_scheduled")
    return client


def titles(response) -> set[str]:
    assert response.status_code == 200, response.text
    return {item["job_title"] for item in response.json()}


def test_search_by_company_and_role_is_case_insensitive(seeded) -> None:
    assert titles(seeded.get("/api/applications", params={"q": "acme"})) == {"Data Analyst Intern", "DevOps Apprentice"}
    assert titles(seeded.get("/api/applications", params={"q": "DATA"})) == {"Data Analyst Intern", "Data Engineer Trainee"}
    # LIKE wildcards in the search term are matched literally.
    assert titles(seeded.get("/api/applications", params={"q": "%_"})) == {"QA Intern"}


def test_filter_by_status_and_active(seeded) -> None:
    assert titles(seeded.get("/api/applications", params={"status": "saved"})) == {"Backend Developer"}
    assert titles(seeded.get("/api/applications", params=[("status", "offer"), ("status", "rejected")])) == {"DevOps Apprentice", "Data Engineer Trainee"}
    assert titles(seeded.get("/api/applications", params={"active": "false"})) == {"DevOps Apprentice", "Data Engineer Trainee"}
    assert titles(seeded.get("/api/applications", params={"active": "true"})) == {"Data Analyst Intern", "Backend Developer", "QA Intern"}
    assert seeded.get("/api/applications", params={"status": "hired"}).status_code == 422


def test_filter_by_deadline_and_application_date_ranges(seeded) -> None:
    assert titles(seeded.get("/api/applications", params={"deadline_from": "2026-07-15", "deadline_to": "2026-12-31"})) == {"Data Analyst Intern", "Backend Developer"}
    assert titles(seeded.get("/api/applications", params={"applied_from": "2026-08-01"})) == {"Data Analyst Intern", "DevOps Apprentice"}
    assert titles(seeded.get("/api/applications", params={"applied_to": "2026-07-31"})) == {"Data Engineer Trainee"}
    assert seeded.get("/api/applications", params={"deadline_from": "2026-12-01", "deadline_to": "2026-01-01"}).status_code == 422
    assert seeded.get("/api/applications", params={"applied_from": "2026-12-01", "applied_to": "2026-01-01"}).status_code == 422
    assert seeded.get("/api/applications", params={"deadline_from": "not-a-date"}).status_code == 422


def test_combined_filters_and_sorting(seeded) -> None:
    combined = seeded.get("/api/applications", params={"q": "data", "active": "true", "applied_from": "2026-08-01"})
    assert titles(combined) == {"Data Analyst Intern"}

    by_deadline = [item["job_title"] for item in seeded.get("/api/applications", params={"sort": "deadline_asc"}).json()]
    assert by_deadline[:3] == ["Data Engineer Trainee", "Data Analyst Intern", "Backend Developer"]
    by_company = [item["company"] for item in seeded.get("/api/applications", params={"sort": "company_asc"}).json()]
    assert by_company == sorted(by_company)
    assert seeded.get("/api/applications", params={"sort": "random"}).status_code == 422


# --- Summary and reminders (API level, relative to the real current date) -----

def test_summary_counts_real_persisted_rows(tracker) -> None:
    client, _ = tracker
    login_as(client, "student@example.com")
    assert client.get("/api/applications/summary").json()["total_applications"] == 0

    today = datetime.now(timezone.utc).date()
    future_interview = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    manual(client, deadline=(today + timedelta(days=2)).isoformat())
    manual(client, deadline=(today - timedelta(days=1)).isoformat())
    manual(client, status="interview_scheduled", interview_at=future_interview, interview_status="scheduled")
    manual(client, status="offer")
    manual(client, status="rejected")

    summary = client.get("/api/applications/summary").json()
    assert summary["total_applications"] == 5
    assert summary["active_applications"] == 3
    assert summary["completed_applications"] == 2
    assert summary["upcoming_deadlines"] == 1
    assert summary["interviews_scheduled"] == 1
    assert summary["offers_received"] == 1
    assert summary["rejected_applications"] == 1
    assert summary["upcoming_deadline_window_days"] == 7
    assert sum(summary["status_counts"].values()) == 5


def test_reminders_endpoint_validates_days_and_returns_data_driven_items(tracker) -> None:
    client, _ = tracker
    login_as(client, "student@example.com")
    assert client.get("/api/applications/reminders", params={"days": 0}).status_code == 422
    assert client.get("/api/applications/reminders", params={"days": 61}).status_code == 422
    assert client.get("/api/applications/reminders").json()["reminders"] == []

    today = datetime.now(timezone.utc).date()
    upcoming = manual(client, company="Soon Co", deadline=(today + timedelta(days=3)).isoformat())
    manual(client, company="Late Co", deadline=(today - timedelta(days=2)).isoformat())
    manual(client, company="Quiet Co")

    body = client.get("/api/applications/reminders", params={"days": 7}).json()
    assert body["window_days"] == 7
    assert [(item["type"], item["application_id"]) for item in body["reminders"]] == [("deadline", upcoming["id"])]
    assert body["reminders"][0]["days_until"] == 3


# --- Generated document links ---------------------------------------------------

def test_valid_customization_and_interview_preparation_links(tracker) -> None:
    client, session_factory = tracker
    auth = login_as(client, "student@example.com")
    customization_id, preparation_id = insert_artifacts(session_factory, auth, JOB_A)

    created = client.post("/api/applications", json={"job_id": JOB_A, "customization_id": customization_id}).json()
    assert created["customization_id"] == customization_id

    linked = client.patch(f"/api/applications/{created['id']}", json={"interview_preparation_id": preparation_id}).json()
    assert linked["interview_preparation_id"] == preparation_id
    assert linked["customization_id"] == customization_id

    unlinked = client.patch(f"/api/applications/{created['id']}", json={"customization_id": None}).json()
    assert unlinked["customization_id"] is None


def test_cross_user_artifact_links_are_rejected(tracker) -> None:
    client, session_factory = tracker
    other = login_as(client, "other@example.com")
    customization_id, preparation_id = insert_artifacts(session_factory, other, JOB_A)

    login_as(client, "student@example.com")
    assert client.post("/api/applications", json={"job_id": JOB_A, "customization_id": customization_id}).status_code == 404
    application_id = client.post("/api/applications", json={"job_id": JOB_A}).json()["id"]
    assert client.patch(f"/api/applications/{application_id}", json={"interview_preparation_id": preparation_id}).status_code == 404
    assert client.patch(f"/api/applications/{application_id}", json={"customization_id": 999999}).status_code == 404
    assert client.get(f"/api/applications/{application_id}").json()["interview_preparation_id"] is None


def test_incompatible_job_artifact_links_are_rejected(tracker) -> None:
    client, session_factory = tracker
    auth = login_as(client, "student@example.com")
    customization_id, preparation_id = insert_artifacts(session_factory, auth, JOB_B)

    assert client.post("/api/applications", json={"job_id": JOB_A, "customization_id": customization_id}).status_code == 409
    application_id = client.post("/api/applications", json={"job_id": JOB_A}).json()["id"]
    assert client.patch(f"/api/applications/{application_id}", json={"interview_preparation_id": preparation_id}).status_code == 409

    manual_id = manual(client)["id"]
    assert client.patch(f"/api/applications/{manual_id}", json={"customization_id": customization_id}).status_code == 409
