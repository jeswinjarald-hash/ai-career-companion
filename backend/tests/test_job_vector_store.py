import numpy as np

from app.schemas.job_chunk import JobChunk
from app.services import job_vector_store


def test_faiss_index_persists_and_reloads_with_metadata(tmp_path, monkeypatch) -> None:
    chunks = [
        JobChunk(
            chunk_id="JOB-0001::overview",
            job_id="JOB-0001",
            job_title="Python Intern",
            company="Example Co",
            domain="Python Backend",
            chunk_type="overview",
            text="Python backend internship",
            location="Remote",
            work_mode="Remote",
            employment_type="Internship",
        ),
        JobChunk(
            chunk_id="JOB-0001::requirements",
            job_id="JOB-0001",
            job_title="Python Intern",
            company="Example Co",
            domain="Python Backend",
            chunk_type="requirements",
            text="Python SQL requirements",
            location="Remote",
            work_mode="Remote",
            employment_type="Internship",
        ),
    ]
    monkeypatch.setattr(job_vector_store, "VECTOR_STORE_DIRECTORY", tmp_path)
    monkeypatch.setattr(job_vector_store, "INDEX_PATH", tmp_path / "jobs.faiss")
    monkeypatch.setattr(job_vector_store, "METADATA_PATH", tmp_path / "jobs.json")
    monkeypatch.setattr(job_vector_store, "embedding_dimension", lambda: 3)
    monkeypatch.setattr(job_vector_store, "get_model_name", lambda: "test-model")
    embeddings = np.array([[1, 0, 0], [0, 1, 0]], dtype=np.float32)

    index = job_vector_store.build_index(embeddings)
    job_vector_store.save_vector_store(index, chunks)
    reloaded_index, reloaded_chunks = job_vector_store.load_vector_store()

    assert reloaded_index.ntotal == 2
    assert [chunk.chunk_id for chunk in reloaded_chunks] == [chunk.chunk_id for chunk in chunks]
    assert reloaded_index.d == 3
