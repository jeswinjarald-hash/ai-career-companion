from app.services.job_chunking import chunk_job_postings
from app.services.job_dataset_service import load_job_postings


def test_dataset_generates_three_deterministic_chunks_per_job() -> None:
    jobs = load_job_postings()
    chunks = chunk_job_postings(jobs)

    assert len(chunks) == 540
    assert len({chunk.chunk_id for chunk in chunks}) == 540
    assert {chunk.chunk_type for chunk in chunks} == {"overview", "requirements", "responsibilities"}
    assert {chunk.job_id for chunk in chunks} == {job.job_id for job in jobs}
    assert all(chunk.text.strip() for chunk in chunks)
    assert [chunk.chunk_id for chunk in chunks[:3]] == [
        "JOB-0001::overview",
        "JOB-0001::requirements",
        "JOB-0001::responsibilities",
    ]
