import json

import pytest

from app.schemas.job_posting import JobPosting
from app.services.job_dataset_service import JobDatasetError, load_job_postings


REQUIRED_FIELDS = {
    "job_id",
    "job_title",
    "company",
    "location",
    "work_mode",
    "employment_type",
    "domain",
    "job_description",
    "responsibilities",
    "required_skills",
    "preferred_skills",
    "qualifications",
    "experience_requirements",
    "education_requirements",
    "source_type",
    "posted_date",
    "raw_text",
}


def test_loads_canonical_dataset() -> None:
    postings = load_job_postings()

    assert len(postings) == 180
    assert all(isinstance(posting, JobPosting) for posting in postings)
    assert len({posting.job_id for posting in postings}) == 180


def test_postings_have_required_fields_array_fields_and_raw_text() -> None:
    postings = load_job_postings()

    for posting in postings:
        assert REQUIRED_FIELDS == set(JobPosting.model_fields)
        assert isinstance(posting.responsibilities, list)
        assert isinstance(posting.required_skills, list)
        assert isinstance(posting.preferred_skills, list)
        assert isinstance(posting.qualifications, list)
        assert posting.raw_text.strip()


def test_malformed_dataset_fails_validation(tmp_path) -> None:
    dataset_path = tmp_path / "malformed.json"
    payload = json.loads((load_job_postings.__globals__["DATASET_PATH"]).read_text(encoding="utf-8"))
    payload[0]["job_id"] = payload[1]["job_id"]
    dataset_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(JobDatasetError, match="Duplicate job_id"):
        load_job_postings(dataset_path)
