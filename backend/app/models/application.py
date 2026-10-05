from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Application(Base):
    """Milestone 4.1 — one tracked application (canonical-dataset or manual).

    For `source="dataset"` rows the opportunity fields (company, job_title, ...) are a
    snapshot copied from the dataset at creation time, so the tracker keeps its
    historical meaning even if the regenerable dataset file later changes. Generated
    documents are referenced by id, never copied. Deadline/interview/follow-up dates
    are only ever user-supplied — the dataset has no deadline field.
    """

    __tablename__ = "applications"
    # NULLs are distinct in a SQL unique constraint, so this blocks duplicate tracking
    # of the same canonical job per user while allowing any number of manual rows.
    __table_args__ = (UniqueConstraint("user_id", "job_id", name="uq_applications_user_job"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    job_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    company: Mapped[str] = mapped_column(String(255), nullable=False)
    job_title: Mapped[str] = mapped_column(String(255), nullable=False)
    employment_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    work_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    job_description: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="saved")
    status_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    applied_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    interview_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    interview_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    follow_up_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    customization_id: Mapped[int | None] = mapped_column(ForeignKey("application_customizations.id"), nullable=True)
    interview_preparation_id: Mapped[int | None] = mapped_column(ForeignKey("interview_preparations.id"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
