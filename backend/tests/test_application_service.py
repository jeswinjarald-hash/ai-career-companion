"""Milestone 4.1 service tests for the deterministic summary and reminder rules,
evaluated against a fixed `now` so date boundaries are exact.
"""

from collections.abc import Generator
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import Base
from app.models import Application, User
from app.schemas.application import ACTIVE_STATUSES, APPLICATION_STATUSES, COMPLETED_STATUSES, is_active_status
from app.services.application_service import PENDING_AFTER_DAYS, build_reminders, build_summary

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)
TODAY = NOW.date()


@pytest.fixture
def db(tmp_path) -> Generator[Session, None, None]:
    engine = create_engine(f"sqlite:///{tmp_path / 'application-service.db'}")
    Base.metadata.create_all(bind=engine)
    with sessionmaker(bind=engine)() as session:
        yield session
    engine.dispose()


@pytest.fixture
def user_id(db: Session) -> int:
    user = User(full_name="Student", email="student@example.com", password_hash="x")
    db.add(user)
    db.commit()
    return user.id


def add(db: Session, user_id: int, company: str, status: str = "saved", status_since: datetime = NOW, **fields) -> Application:
    application = Application(user_id=user_id, source="manual", company=company, job_title="Role", status=status, status_updated_at=status_since, **fields)
    db.add(application)
    db.commit()
    return application


def reminder_keys(db: Session, user_id: int, days: int = 7) -> list[tuple[str, str]]:
    return [(item.type, item.company) for item in build_reminders(db, user_id, days, now=NOW).reminders]


def test_status_classification_is_complete_and_disjoint() -> None:
    assert COMPLETED_STATUSES == {"offer", "rejected", "withdrawn"}
    assert ACTIVE_STATUSES | COMPLETED_STATUSES == set(APPLICATION_STATUSES)
    assert not ACTIVE_STATUSES & COMPLETED_STATUSES
    assert is_active_status("interview_completed") and not is_active_status("withdrawn")


def test_upcoming_deadline_window_boundaries(db: Session, user_id: int) -> None:
    add(db, user_id, "Today", deadline=TODAY)
    add(db, user_id, "Edge", deadline=TODAY + timedelta(days=7))
    add(db, user_id, "Beyond", deadline=TODAY + timedelta(days=8))
    add(db, user_id, "Expired", deadline=TODAY - timedelta(days=1))
    add(db, user_id, "AlreadyApplied", status="applied", deadline=TODAY + timedelta(days=2))
    add(db, user_id, "Withdrawn", status="withdrawn", deadline=TODAY + timedelta(days=2))
    add(db, user_id, "NoDeadline")

    assert build_summary(db, user_id, now=NOW).upcoming_deadlines == 2
    assert reminder_keys(db, user_id) == [("deadline", "Today"), ("deadline", "Edge")]
    assert ("deadline", "Beyond") in reminder_keys(db, user_id, days=8)


def test_scheduled_interviews_require_a_future_time_and_an_open_interview(db: Session, user_id: int) -> None:
    add(db, user_id, "Upcoming", status="interview_scheduled", interview_at=NOW + timedelta(days=2), interview_status="scheduled")
    add(db, user_id, "NoStatusYet", status="shortlisted", interview_at=NOW + timedelta(hours=3))
    add(db, user_id, "Far", status="interview_scheduled", interview_at=NOW + timedelta(days=20), interview_status="scheduled")
    add(db, user_id, "Past", status="interview_completed", interview_at=NOW - timedelta(hours=1), interview_status="scheduled")
    add(db, user_id, "Cancelled", status="interview_scheduled", interview_at=NOW + timedelta(days=1), interview_status="cancelled")
    add(db, user_id, "Rejected", status="rejected", interview_at=NOW + timedelta(days=1), interview_status="scheduled")
    add(db, user_id, "StatusOnly", status="interview_scheduled")

    assert build_summary(db, user_id, now=NOW).interviews_scheduled == 3
    reminders = build_reminders(db, user_id, 7, now=NOW).reminders
    assert [(item.type, item.company) for item in reminders] == [("interview", "NoStatusYet"), ("interview", "Upcoming")]
    assert reminders[0].due_at == NOW + timedelta(hours=3)
    assert reminders[1].days_until == 2


def test_follow_up_reminders_include_due_and_overdue_but_not_far_future(db: Session, user_id: int) -> None:
    add(db, user_id, "Overdue", status="applied", follow_up_date=TODAY - timedelta(days=3))
    add(db, user_id, "DueToday", status="applied", follow_up_date=TODAY)
    add(db, user_id, "Later", status="applied", follow_up_date=TODAY + timedelta(days=30))
    add(db, user_id, "ClosedOut", status="offer", follow_up_date=TODAY)

    reminders = build_reminders(db, user_id, 7, now=NOW).reminders
    assert [(item.type, item.company, item.overdue) for item in reminders] == [
        ("follow_up", "Overdue", True), ("follow_up", "DueToday", False),
    ]


def test_pending_rule_flags_stale_submitted_applications_without_follow_up(db: Session, user_id: int) -> None:
    stale = NOW - timedelta(days=PENDING_AFTER_DAYS)
    add(db, user_id, "Stale", status="applied", status_since=stale)
    add(db, user_id, "StaleReview", status="under_review", status_since=stale - timedelta(days=5))
    add(db, user_id, "Fresh", status="applied", status_since=NOW - timedelta(days=PENDING_AFTER_DAYS - 1))
    add(db, user_id, "HasFollowUp", status="applied", status_since=stale, follow_up_date=TODAY + timedelta(days=30))
    add(db, user_id, "StaleSaved", status="saved", status_since=stale)
    add(db, user_id, "StaleRejected", status="rejected", status_since=stale)

    assert sorted(reminder_keys(db, user_id)) == [("pending", "Stale"), ("pending", "StaleReview")]


def test_unrelated_applications_produce_no_reminders_and_naive_storage_is_utc(db: Session, user_id: int) -> None:
    add(db, user_id, "Plain")
    add(db, user_id, "Offer", status="offer", deadline=TODAY + timedelta(days=1))
    # SQLite hands back naive datetimes; they must still be compared as UTC instants.
    add(db, user_id, "NaiveStored", status="shortlisted", interview_at=(NOW + timedelta(hours=1)).replace(tzinfo=None))
    assert reminder_keys(db, user_id) == [("interview", "NaiveStored")]


def test_summary_is_scoped_to_the_user(db: Session, user_id: int) -> None:
    other = User(full_name="Other", email="other@example.com", password_hash="x")
    db.add(other)
    db.commit()
    add(db, other.id, "TheirOffer", status="offer")
    add(db, user_id, "Mine", status="rejected")

    summary = build_summary(db, user_id, now=NOW)
    assert (summary.total_applications, summary.offers_received, summary.rejected_applications, summary.active_applications) == (1, 0, 1, 0)


def test_reminder_window_bounds_are_enforced(db: Session, user_id: int) -> None:
    with pytest.raises(ValueError):
        build_reminders(db, user_id, 0, now=NOW)
    with pytest.raises(ValueError):
        build_reminders(db, user_id, 61, now=NOW)
    assert build_reminders(db, user_id, 60, now=NOW).today == date(2026, 10, 3)
