from fastapi import APIRouter, HTTPException, Query

from app.schemas.job_chunk import JobSearchResult
from app.schemas.job_posting import JobPosting
from app.services.job_dataset_service import load_job_postings
from app.services.job_search_service import JobSearchError, search_jobs

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("/search", response_model=list[JobSearchResult])
def search_internship_jobs(
    q: str = Query(..., min_length=1),
    top_k: int = Query(5, ge=1, le=20),
) -> list[JobSearchResult]:
    try:
        return search_jobs(q, top_k)
    except JobSearchError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{job_id}", response_model=JobPosting)
def read_internship_job(job_id: str) -> JobPosting:
    job = next((job for job in load_job_postings() if job.job_id == job_id), None)
    if job is None:
        raise HTTPException(status_code=404, detail="Job posting not found.")
    return job
