from pathlib import Path

import pytest

from app.services.job_search_service import search_jobs
from app.services.job_vector_store import INDEX_PATH, METADATA_PATH


pytestmark = pytest.mark.skipif(
    not (Path(INDEX_PATH).is_file() and Path(METADATA_PATH).is_file()),
    reason="Build the persisted vector index before running real retrieval integration tests.",
)


@pytest.mark.parametrize(
    ("query", "expected_domains"),
    [
        ("Python machine learning internship with pandas and model training", {"Machine Learning", "Data Science", "Generative AI / NLP"}),
        ("React JavaScript frontend web development internship", {"Frontend Development", "Full Stack Development"}),
        ("cybersecurity SOC Linux networking security internship", {"Cybersecurity"}),
        ("AWS Docker cloud infrastructure internship", {"Cloud Computing", "DevOps"}),
        ("SQL Excel Power BI data analyst internship", {"Data Analytics", "Database / SQL"}),
    ],
)
def test_real_retrieval_returns_relevant_domains(query: str, expected_domains: set[str]) -> None:
    results = search_jobs(query, top_k=5)

    assert len(results) == 5
    assert len({result.job_id for result in results}) == 5
    assert all(results[index].similarity_score >= results[index + 1].similarity_score for index in range(4))
    assert {result.domain for result in results} & expected_domains
