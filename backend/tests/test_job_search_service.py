import numpy as np
import pytest

from app.schemas.job_chunk import JobChunk
from app.schemas.job_posting import JobPosting
from app.services import job_search_service
from app.services.job_search_service import JobSearchError


def _job(job_id: str, domain: str) -> JobPosting:
    return JobPosting(
        job_id=job_id,
        job_title=f"{domain} Intern",
        company="Example Co",
        location="Remote",
        work_mode="Remote",
        employment_type="Internship",
        domain=domain,
        job_description=f"{domain} internship",
        responsibilities=["Build useful software"],
        required_skills=["Python"],
        preferred_skills=["SQL"],
        qualifications=["Problem solving"],
        experience_requirements="No experience required",
        education_requirements="Related degree",
        source_type="synthetic_curated",
        posted_date="2026-01-01",
        raw_text=f"{domain} internship posting",
    )


def test_search_aggregates_chunks_into_unique_jobs(monkeypatch) -> None:
    chunks = [
        JobChunk(chunk_id="JOB-1::overview", job_id="JOB-1", job_title="ML", company="A", domain="Machine Learning", chunk_type="overview", text="ML", location="Remote", work_mode="Remote", employment_type="Internship"),
        JobChunk(chunk_id="JOB-1::requirements", job_id="JOB-1", job_title="ML", company="A", domain="Machine Learning", chunk_type="requirements", text="ML skills", location="Remote", work_mode="Remote", employment_type="Internship"),
        JobChunk(chunk_id="JOB-2::overview", job_id="JOB-2", job_title="Web", company="B", domain="Frontend Development", chunk_type="overview", text="Web", location="Remote", work_mode="Remote", employment_type="Internship"),
    ]
    class FakeIndex:
        ntotal = 3
        def search(self, query, count):
            return np.array([[0.9, 0.8, 0.7]], dtype=np.float32), np.array([[0, 1, 2]])
    monkeypatch.setattr(job_search_service, "load_vector_store", lambda: (FakeIndex(), chunks))
    monkeypatch.setattr(job_search_service, "embed_query", lambda query: np.array([1, 0], dtype=np.float32))
    monkeypatch.setattr(job_search_service, "_load_jobs", lambda: [_job("JOB-1", "Machine Learning"), _job("JOB-2", "Frontend Development")])

    results = job_search_service.search_jobs("machine learning", top_k=2)

    assert [result.job_id for result in results] == ["JOB-1", "JOB-2"]
    assert results[0].similarity_score > results[1].similarity_score
    assert results[0].matched_chunk_types == ["overview", "requirements"]


@pytest.mark.parametrize("query,top_k", [("", 5), ("python", 0), ("python", 21)])
def test_search_rejects_invalid_input(query: str, top_k: int) -> None:
    with pytest.raises(JobSearchError):
        job_search_service.search_jobs(query, top_k)
