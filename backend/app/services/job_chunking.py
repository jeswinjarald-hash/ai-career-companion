from collections.abc import Iterable

from app.schemas.job_chunk import JobChunk
from app.schemas.job_posting import JobPosting

CHUNK_TYPES = ("overview", "requirements", "responsibilities")


def _join_items(items: Iterable[str]) -> str:
    return "; ".join(items)


def chunk_job_posting(job: JobPosting) -> list[JobChunk]:
    context = {
        "job_id": job.job_id,
        "job_title": job.job_title,
        "company": job.company,
        "domain": job.domain,
        "location": job.location,
        "work_mode": job.work_mode,
        "employment_type": job.employment_type,
    }
    return [
        JobChunk(
            **context,
            chunk_id=f"{job.job_id}::overview",
            chunk_type="overview",
            text=(
                f"Job title: {job.job_title}. Company: {job.company}. Domain: {job.domain}. "
                f"Location: {job.location}. Work mode: {job.work_mode}. "
                f"Employment type: {job.employment_type}. Description: {job.job_description}"
            ),
        ),
        JobChunk(
            **context,
            chunk_id=f"{job.job_id}::requirements",
            chunk_type="requirements",
            text=(
                f"Requirements for {job.job_title} at {job.company} in {job.domain}. "
                f"Required skills: {_join_items(job.required_skills)}. "
                f"Preferred skills: {_join_items(job.preferred_skills)}. "
                f"Qualifications: {_join_items(job.qualifications)}. "
                f"Experience: {job.experience_requirements}. "
                f"Education: {job.education_requirements}."
            ),
        ),
        JobChunk(
            **context,
            chunk_id=f"{job.job_id}::responsibilities",
            chunk_type="responsibilities",
            text=(
                f"Responsibilities for {job.job_title} at {job.company} in {job.domain}: "
                f"{_join_items(job.responsibilities)}."
            ),
        ),
    ]


def chunk_job_postings(jobs: list[JobPosting]) -> list[JobChunk]:
    chunks = [chunk for job in jobs for chunk in chunk_job_posting(job)]
    chunk_ids = [chunk.chunk_id for chunk in chunks]
    if len(chunk_ids) != len(set(chunk_ids)):
        raise ValueError("Duplicate chunk IDs were generated.")
    job_ids = {job.job_id for job in jobs}
    missing_parent_ids = sorted({chunk.job_id for chunk in chunks} - job_ids)
    if missing_parent_ids:
        raise ValueError(f"Chunks reference unknown jobs: {', '.join(missing_parent_ids)}")
    if any(not chunk.text.strip() for chunk in chunks):
        raise ValueError("Empty job chunk text was generated.")
    return chunks
