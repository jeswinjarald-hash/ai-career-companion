from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.job_dataset_service import load_job_postings
from app.services.job_vector_store import INDEX_PATH, METADATA_PATH


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


def test_job_search_validates_query_and_top_k(client: TestClient) -> None:
    assert client.get("/api/jobs/search", params={"q": ""}).status_code == 422
    assert client.get("/api/jobs/search", params={"q": "python", "top_k": 0}).status_code == 422
    assert client.get("/api/jobs/search", params={"q": "python", "top_k": 21}).status_code == 422


@pytest.mark.skipif(
    not (Path(INDEX_PATH).is_file() and Path(METADATA_PATH).is_file()),
    reason="Build the persisted vector index before running real retrieval integration tests.",
)
def test_job_search_returns_real_ranked_results(client: TestClient) -> None:
    response = client.get("/api/jobs/search", params={"q": "Python machine learning internship", "top_k": 3})

    assert response.status_code == 200
    results = response.json()
    assert len(results) == 3
    for result in results:
        assert {
            "job_id", "job_title", "company", "domain", "location", "work_mode",
            "employment_type", "required_skills", "preferred_skills", "similarity_score",
            "matched_chunk_types",
        } <= result.keys()
    scores = [result["similarity_score"] for result in results]
    assert scores == sorted(scores, reverse=True)


def test_job_details_returns_real_dataset_record(client: TestClient) -> None:
    known_job = load_job_postings()[0]

    response = client.get(f"/api/jobs/{known_job.job_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["job_id"] == known_job.job_id
    assert body["job_title"] == known_job.job_title
    assert body["required_skills"] == known_job.required_skills
    assert body["job_description"] == known_job.job_description


def test_job_details_unknown_id_is_404(client: TestClient) -> None:
    response = client.get("/api/jobs/JOB-DOES-NOT-EXIST")

    assert response.status_code == 404
