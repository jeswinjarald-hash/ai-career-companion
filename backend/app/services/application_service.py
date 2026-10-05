"""Milestone 4.1 — Application tracking service.

All tracker logic lives here (routes only map exceptions to HTTP): creation from a
canonical opportunity (server-side snapshot) or a manual entry, partial updates,
filtering, the dashboard summary and the reminder list. Everything is plain
database querying plus deterministic date rules — no FAISS, embeddings or LLM.

Date conventions: "today" is the current UTC date and "now" the current UTC time,
matching the project's `utc_now()` timestamps. Deadline / applied / follow-up are
calendar dates; `interview_at` is a timezone-aware instant stored in UTC.
"""

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import Select, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Application, ApplicationCustomization, InterviewPreparation
from app.schemas.application import (
    ACTIVE_STATUSES,
    APPLICATION_STATUSES,
    AWAITING_RESPONSE_STATUSES,
    COMPLETED_STATUSES,
    PRE_APPLICATION_STATUSES,
    SNAPSHOT_FIELDS,
    ApplicationCreate,
    ApplicationReminder,
    ApplicationRemindersResponse,
    ApplicationSort,
    ApplicationSummary,
    ApplicationUpdate,
    as_utc,
)
from app.services.job_dataset_service import load_job_postings

UPCOMING_DEADLINE_WINDOW_DAYS = 7
DEFAULT_REMINDER_WINDOW_DAYS = 7
MAX_REMINDER_WINDOW_DAYS = 60
# An application that has sat in applied/under_review this long without any status
# change, and with no follow-up date set, is reported as pending a response.
PENDING_AFTER_DAYS = 14


class DuplicateApplicationError(ValueError):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def get_owned_application(db: Session, application_id: int, user_id: int) -> Application | None:
    application = db.get(Application, application_id)
    if application is None or application.user_id != user_id:
        return None
    return application


def _snapshot_from_dataset(job_id: str) -> dict[str, str]:
    job = next((job for job in load_job_postings() if job.job_id == job_id), None)
    if job is None:
        raise LookupError(f"Opportunity {job_id} was not found.")
    return {
        "company": job.company,
        "job_title": job.job_title,
        "employment_type": job.employment_type,
        "location": job.location,
        "work_mode": job.work_mode,
        "job_description": job.job_description,
    }


def _validate_artifacts(db: Session, user_id: int, job_id: str | None, customization_id: int | None, interview_preparation_id: int | None) -> None:
    """Generated documents may only be linked when they belong to the same user and
    were generated for the same canonical opportunity as the application. Manual
    applications have no canonical job, so no generated document can match them.
    Unowned records are reported as not found, never as "belongs to someone else".
    """
    checks = (
        (customization_id, ApplicationCustomization, "Application customization"),
        (interview_preparation_id, InterviewPreparation, "Interview preparation"),
    )
    for artifact_id, model, label in checks:
        if artifact_id is None:
            continue
        record = db.get(model, artifact_id)
        if record is None or record.user_id != user_id:
            raise LookupError(f"{label} not found.")
        if job_id is None:
            raise ValueError(f"{label} {artifact_id} was generated for {record.job_id} and cannot be linked to a manual application.")
        if record.job_id != job_id:
            raise ValueError(f"{label} {artifact_id} was generated for {record.job_id}, not for {job_id}.")


def _commit(db: Session, application: Application) -> Application:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise DuplicateApplicationError("This opportunity is already in your application tracker.") from exc
    db.refresh(application)
    return application


def _normalize_interview_at(value: datetime | None) -> datetime | None:
    return value.astimezone(timezone.utc) if value is not None else None


def create_application(db: Session, user_id: int, payload: ApplicationCreate) -> Application:
    if payload.job_id is not None:
        if db.scalar(select(Application.id).where(Application.user_id == user_id, Application.job_id == payload.job_id)) is not None:
            raise DuplicateApplicationError("This opportunity is already in your application tracker.")
        source = "dataset"
        opportunity = _snapshot_from_dataset(payload.job_id)
    else:
        source = "manual"
        opportunity = {name: getattr(payload, name) for name in SNAPSHOT_FIELDS}

    _validate_artifacts(db, user_id, payload.job_id, payload.customization_id, payload.interview_preparation_id)

    now = _utc_now()
    application = Application(
        user_id=user_id,
        source=source,
        job_id=payload.job_id,
        **opportunity,
        status=payload.status,
        status_updated_at=now,
        applied_date=payload.applied_date,
        deadline=payload.deadline,
        interview_at=_normalize_interview_at(payload.interview_at),
        interview_status=payload.interview_status,
        follow_up_date=payload.follow_up_date,
        notes=payload.notes,
        customization_id=payload.customization_id,
        interview_preparation_id=payload.interview_preparation_id,
        created_at=now,
        updated_at=now,
    )
    db.add(application)
    return _commit(db, application)


def update_application(db: Session, application: Application, payload: ApplicationUpdate) -> Application:
    changes = payload.model_dump(exclude_unset=True)

    snapshot_changes = [name for name in SNAPSHOT_FIELDS if name in changes]
    if snapshot_changes and application.source == "dataset":
        raise ValueError(
            "Opportunity details of a dataset application come from the opportunity dataset and cannot be edited: "
            f"{', '.join(snapshot_changes)}."
        )

    if "customization_id" in changes or "interview_preparation_id" in changes:
        _validate_artifacts(
            db, application.user_id, application.job_id,
            changes.get("customization_id"), changes.get("interview_preparation_id"),
        )

    if "interview_at" in changes:
        changes["interview_at"] = _normalize_interview_at(changes["interview_at"])

    new_status = changes.get("status")
    if new_status is not None and new_status != application.status:
        application.status_updated_at = _utc_now()

    for field, value in changes.items():
        setattr(application, field, value)
    return _commit(db, application)


def delete_application(db: Session, application: Application) -> None:
    # Only the tracker row is removed; linked generated documents are left untouched.
    db.delete(application)
    db.commit()


_SORTS = {
    "updated_desc": (Application.updated_at.desc(), Application.id.desc()),
    "created_desc": (Application.created_at.desc(), Application.id.desc()),
    "deadline_asc": (Application.deadline.is_(None), Application.deadline.asc(), Application.id.asc()),
    "applied_desc": (Application.applied_date.is_(None), Application.applied_date.desc(), Application.id.desc()),
    "company_asc": (Application.company.asc(), Application.job_title.asc(), Application.id.asc()),
}


def list_applications(
    db: Session,
    user_id: int,
    *,
    statuses: list[str] | None = None,
    q: str | None = None,
    active: bool | None = None,
    deadline_from: date | None = None,
    deadline_to: date | None = None,
    applied_from: date | None = None,
    applied_to: date | None = None,
    sort: ApplicationSort = "updated_desc",
) -> list[Application]:
    for start, end, name in ((deadline_from, deadline_to, "deadline"), (applied_from, applied_to, "applied")):
        if start is not None and end is not None and start > end:
            raise ValueError(f"{name}_from must not be after {name}_to.")

    statement: Select = select(Application).where(Application.user_id == user_id)
    if statuses:
        statement = statement.where(Application.status.in_(statuses))
    if q is not None and q.strip():
        term = q.strip()
        statement = statement.where(or_(
            Application.company.icontains(term, autoescape=True),
            Application.job_title.icontains(term, autoescape=True),
        ))
    if active is not None:
        statement = statement.where(Application.status.in_(ACTIVE_STATUSES if active else COMPLETED_STATUSES))
    # A date-range filter only matches rows that actually have that date set.
    if deadline_from is not None:
        statement = statement.where(Application.deadline >= deadline_from)
    if deadline_to is not None:
        statement = statement.where(Application.deadline <= deadline_to)
    if applied_from is not None:
        statement = statement.where(Application.applied_date >= applied_from)
    if applied_to is not None:
        statement = statement.where(Application.applied_date <= applied_to)
    return list(db.scalars(statement.order_by(*_SORTS[sort])))


def _user_applications(db: Session, user_id: int) -> list[Application]:
    # Summary and reminders are computed in Python over the user's own rows: SQLite
    # drops tzinfo from stored datetimes, so comparing `interview_at` in SQL would be
    # dialect-dependent. Per-user tracker volumes are small.
    return list(db.scalars(select(Application).where(Application.user_id == user_id)))


def _has_upcoming_deadline(application: Application, today: date, window_days: int) -> bool:
    return (
        application.status in PRE_APPLICATION_STATUSES
        and application.deadline is not None
        and today <= application.deadline <= today + timedelta(days=window_days)
    )


def _has_scheduled_interview(application: Application, now: datetime) -> bool:
    return (
        application.status in ACTIVE_STATUSES
        and application.interview_at is not None
        and application.interview_status in (None, "scheduled")
        and as_utc(application.interview_at) >= now
    )


def build_summary(db: Session, user_id: int, now: datetime | None = None) -> ApplicationSummary:
    now = now or _utc_now()
    today = now.date()
    applications = _user_applications(db, user_id)
    status_counts = {status: 0 for status in APPLICATION_STATUSES}
    for application in applications:
        status_counts[application.status] = status_counts.get(application.status, 0) + 1
    active = sum(1 for application in applications if application.status in ACTIVE_STATUSES)
    return ApplicationSummary(
        total_applications=len(applications),
        active_applications=active,
        completed_applications=len(applications) - active,
        upcoming_deadlines=sum(1 for a in applications if _has_upcoming_deadline(a, today, UPCOMING_DEADLINE_WINDOW_DAYS)),
        interviews_scheduled=sum(1 for a in applications if _has_scheduled_interview(a, now)),
        offers_received=status_counts["offer"],
        rejected_applications=status_counts["rejected"],
        upcoming_deadline_window_days=UPCOMING_DEADLINE_WINDOW_DAYS,
        status_counts=status_counts,
    )


def _reminder(application: Application, type_: str, due_date: date, today: date, message: str, due_at: datetime | None = None) -> ApplicationReminder:
    days_until = (due_date - today).days
    return ApplicationReminder(
        type=type_, application_id=application.id, company=application.company, job_title=application.job_title,
        status=application.status, due_date=due_date, due_at=due_at, days_until=days_until,
        overdue=days_until < 0, message=message,
    )


def build_reminders(db: Session, user_id: int, window_days: int = DEFAULT_REMINDER_WINDOW_DAYS, now: datetime | None = None) -> ApplicationRemindersResponse:
    """Deterministic reminder rules (completed applications never produce reminders):

    - deadline: status saved/planning and today <= deadline <= today + window.
      Past deadlines are not reported as upcoming.
    - interview: interview_status unset or "scheduled" and now <= interview_at <= now + window.
    - follow_up: follow_up_date <= today + window (overdue follow-ups are included, flagged `overdue`).
    - pending: status applied/under_review, unchanged for >= PENDING_AFTER_DAYS, and no
      follow_up_date set (once the student sets one, the follow_up rule takes over).
    """
    if not 1 <= window_days <= MAX_REMINDER_WINDOW_DAYS:
        raise ValueError(f"days must be between 1 and {MAX_REMINDER_WINDOW_DAYS}.")
    now = now or _utc_now()
    today = now.date()
    horizon = today + timedelta(days=window_days)

    reminders: list[ApplicationReminder] = []
    for application in _user_applications(db, user_id):
        if application.status not in ACTIVE_STATUSES:
            continue
        label = f"{application.job_title} at {application.company}"

        if _has_upcoming_deadline(application, today, window_days):
            reminders.append(_reminder(application, "deadline", application.deadline, today, f"Application deadline for {label} is on {application.deadline.isoformat()}."))

        if _has_scheduled_interview(application, now):
            interview_at = as_utc(application.interview_at)
            if interview_at <= now + timedelta(days=window_days):
                reminders.append(_reminder(application, "interview", interview_at.date(), today, f"Interview for {label} is scheduled at {interview_at.isoformat()}.", due_at=interview_at))

        if application.follow_up_date is not None and application.follow_up_date <= horizon:
            when = "was due" if application.follow_up_date < today else "is due"
            reminders.append(_reminder(application, "follow_up", application.follow_up_date, today, f"Follow-up for {label} {when} on {application.follow_up_date.isoformat()}."))

        status_since = as_utc(application.status_updated_at)
        if (
            application.status in AWAITING_RESPONSE_STATUSES
            and application.follow_up_date is None
            and now - status_since >= timedelta(days=PENDING_AFTER_DAYS)
        ):
            waiting_days = (now - status_since).days
            reminders.append(_reminder(application, "pending", today, today, f"{label} has been '{application.status}' for {waiting_days} days with no update — consider following up."))

    reminders.sort(key=lambda item: (item.due_date, item.due_at or datetime.min.replace(tzinfo=timezone.utc), item.application_id, item.type))
    return ApplicationRemindersResponse(window_days=window_days, today=today, reminders=reminders)
