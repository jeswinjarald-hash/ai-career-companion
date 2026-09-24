"""Milestone 3.4 — context resolution for the Career Assistant.

Resolves the real database/dataset objects an intent needs (job posting, resume,
structured resume) from ids that came from the message, the conversation's
remembered active job, or an explicit frontend hint — every id is re-validated
against real data here, never trusted blindly (an unknown job id becomes a
`LookupError`, an unowned resume id is never returned).
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CandidateProfile, Resume, StructuredResume
from app.schemas.job_posting import JobPosting
from app.services.job_dataset_service import load_job_postings
from app.services.resume import list_profile_resumes


def get_job(job_id: str) -> JobPosting | None:
    return next((job for job in load_job_postings() if job.job_id == job_id), None)


def get_profile_for_user(db: Session, user_id: int) -> CandidateProfile | None:
    return db.scalar(select(CandidateProfile).where(CandidateProfile.user_id == user_id))


def latest_resume_for_user(db: Session, user_id: int) -> Resume | None:
    """The same "most recently created resume for this user" convention the
    frontend already uses for its own `activeResumeId` — the Career Assistant never
    introduces a second, different notion of "the current resume".
    """
    profile = get_profile_for_user(db, user_id)
    if profile is None:
        return None
    resumes = list_profile_resumes(db, profile.id)
    return resumes[0] if resumes else None


def get_structured(db: Session, resume_id: int) -> StructuredResume | None:
    return db.scalar(select(StructuredResume).where(StructuredResume.resume_id == resume_id))


@dataclass
class ResolvedContext:
    profile: CandidateProfile | None
    resume: Resume | None
    structured: StructuredResume | None
    resume_is_processed: bool
    job: JobPosting | None
    second_job: JobPosting | None
    job_not_found: str | None
    second_job_not_found: str | None


def resolve_context(db: Session, user_id: int, job_id: str | None, second_job_id: str | None) -> ResolvedContext:
    profile = get_profile_for_user(db, user_id)
    resume = latest_resume_for_user(db, user_id)
    structured = get_structured(db, resume.id) if resume is not None else None

    job = get_job(job_id) if job_id else None
    job_not_found = job_id if (job_id and job is None) else None

    second_job = get_job(second_job_id) if second_job_id else None
    second_job_not_found = second_job_id if (second_job_id and second_job is None) else None

    return ResolvedContext(
        profile=profile, resume=resume, structured=structured,
        resume_is_processed=structured is not None,
        job=job, second_job=second_job,
        job_not_found=job_not_found, second_job_not_found=second_job_not_found,
    )
