from datetime import date, datetime, timezone
from typing import Literal, get_args

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

# Single source of truth for the M4.1 lifecycle. Routes, filters, summary and
# reminders all classify through these constants rather than their own literals.
ApplicationStatus = Literal[
    "saved", "planning", "applied", "under_review", "shortlisted",
    "interview_scheduled", "interview_completed", "offer", "rejected", "withdrawn",
]
ApplicationSource = Literal["dataset", "manual"]
InterviewStatus = Literal["scheduled", "completed", "cancelled"]
ApplicationSort = Literal["updated_desc", "created_desc", "deadline_asc", "applied_desc", "company_asc"]
ReminderType = Literal["deadline", "interview", "follow_up", "pending"]

APPLICATION_STATUSES: tuple[str, ...] = get_args(ApplicationStatus)
COMPLETED_STATUSES = frozenset({"offer", "rejected", "withdrawn"})
ACTIVE_STATUSES = frozenset(APPLICATION_STATUSES) - COMPLETED_STATUSES
# Not yet submitted — the only statuses for which an application deadline still matters.
PRE_APPLICATION_STATUSES = frozenset({"saved", "planning"})
# Submitted and waiting on the employer — used by the "pending" reminder rule.
AWAITING_RESPONSE_STATUSES = frozenset({"applied", "under_review"})

SNAPSHOT_FIELDS = ("company", "job_title", "employment_type", "location", "work_mode", "job_description")


def is_active_status(status: str) -> bool:
    return status in ACTIVE_STATUSES


def as_utc(value: datetime) -> datetime:
    # SQLite returns naive datetimes even for DateTime(timezone=True) columns; every
    # stored value is written in UTC, so naive here always means UTC.
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _strip_or_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class _TrackerFields(BaseModel):
    """User-owned tracker fields, shared by create and update."""

    applied_date: date | None = None
    deadline: date | None = None
    # AwareDatetime: a naive interview time is rejected (422) rather than silently
    # assumed to be in some timezone.
    interview_at: AwareDatetime | None = None
    interview_status: InterviewStatus | None = None
    follow_up_date: date | None = None
    notes: str | None = Field(default=None, max_length=10000)
    customization_id: int | None = Field(default=None, ge=1)
    interview_preparation_id: int | None = Field(default=None, ge=1)

    @field_validator("notes")
    @classmethod
    def strip_notes(cls, value: str | None) -> str | None:
        return _strip_or_none(value)


class _ManualOpportunityFields(BaseModel):
    company: str | None = Field(default=None, max_length=255)
    job_title: str | None = Field(default=None, max_length=255)
    employment_type: str | None = Field(default=None, max_length=64)
    location: str | None = Field(default=None, max_length=255)
    work_mode: str | None = Field(default=None, max_length=32)
    job_description: str | None = Field(default=None, max_length=20000)

    @field_validator(*SNAPSHOT_FIELDS)
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        return _strip_or_none(value)


class ApplicationCreate(_TrackerFields, _ManualOpportunityFields):
    """Either `job_id` (canonical opportunity — the server snapshots its fields) or
    a manual entry with at least `company` and `job_title`.
    """

    model_config = ConfigDict(extra="forbid")

    job_id: str | None = Field(default=None, min_length=1, max_length=64)
    status: ApplicationStatus = "saved"

    @model_validator(mode="after")
    def check_source_fields(self) -> "ApplicationCreate":
        supplied_snapshot = [name for name in SNAPSHOT_FIELDS if getattr(self, name) is not None]
        if self.job_id is not None:
            if supplied_snapshot:
                raise ValueError(
                    "Opportunity details are taken from the opportunity dataset when job_id is given; "
                    f"do not supply: {', '.join(supplied_snapshot)}."
                )
        elif self.company is None or self.job_title is None:
            raise ValueError("Manual applications require company and job_title.")
        return self


class ApplicationUpdate(_TrackerFields, _ManualOpportunityFields):
    """Partial update; only fields present in the request are applied (an explicit
    null clears an optional field). Opportunity fields are editable only on manual
    applications — the service rejects them for dataset applications.
    """

    model_config = ConfigDict(extra="forbid")

    status: ApplicationStatus | None = None

    @model_validator(mode="after")
    def reject_null_required(self) -> "ApplicationUpdate":
        for name in ("status", "company", "job_title"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be cleared.")
        return self


class ApplicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: ApplicationSource
    job_id: str | None
    company: str
    job_title: str
    employment_type: str | None
    location: str | None
    work_mode: str | None
    job_description: str | None
    status: ApplicationStatus
    status_updated_at: datetime
    applied_date: date | None
    deadline: date | None
    interview_at: datetime | None
    interview_status: InterviewStatus | None
    follow_up_date: date | None
    notes: str | None
    customization_id: int | None
    interview_preparation_id: int | None
    created_at: datetime
    updated_at: datetime

    @field_validator("status_updated_at", "interview_at", "created_at", "updated_at")
    @classmethod
    def attach_utc(cls, value: datetime | None) -> datetime | None:
        return as_utc(value) if value is not None else None

    @computed_field
    @property
    def is_active(self) -> bool:
        return is_active_status(self.status)


class ApplicationSummary(BaseModel):
    total_applications: int
    active_applications: int
    completed_applications: int
    upcoming_deadlines: int
    interviews_scheduled: int
    offers_received: int
    rejected_applications: int
    upcoming_deadline_window_days: int
    status_counts: dict[str, int]


class ApplicationReminder(BaseModel):
    type: ReminderType
    application_id: int
    company: str
    job_title: str
    status: ApplicationStatus
    due_date: date
    due_at: datetime | None = None
    days_until: int
    overdue: bool
    message: str


class ApplicationRemindersResponse(BaseModel):
    window_days: int
    today: date
    reminders: list[ApplicationReminder]
