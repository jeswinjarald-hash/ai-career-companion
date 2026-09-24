import json
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.schemas.job_posting import JobPosting

DATASET_DIRECTORY = Path(__file__).resolve().parents[2] / "data" / "internships"
DATASET_PATH = DATASET_DIRECTORY / "career_opportunities_320.json"
EXPECTED_RECORD_COUNT = 320
REQUIRED_RAW_TEXT_LABELS = (
    "Job Title:",
    "Company:",
    "Location:",
    "Work Mode:",
    "Employment Type:",
    "Domain:",
    "Description:",
    "Responsibilities:",
    "Required Skills:",
    "Preferred Skills:",
    "Qualifications:",
    "Experience:",
    "Education:",
)


class JobDatasetError(ValueError):
    pass


def _validate_raw_text(record: JobPosting, index: int) -> None:
    raw_text = record.raw_text.strip()
    if not raw_text:
        raise JobDatasetError(f"Record {index} ({record.job_id}) has empty raw_text.")

    missing_labels = [label for label in REQUIRED_RAW_TEXT_LABELS if label not in raw_text]
    if missing_labels:
        labels = ", ".join(missing_labels)
        raise JobDatasetError(f"Record {index} ({record.job_id}) is missing raw_text labels: {labels}.")

    source_fields = (
        record.job_title,
        record.company,
        record.location,
        record.work_mode,
        record.employment_type,
        record.domain,
        record.job_description,
        record.experience_requirements,
        record.education_requirements,
    )
    missing_values = [value for value in source_fields if value not in raw_text]
    list_values = [
        *record.responsibilities,
        *record.required_skills,
        *record.preferred_skills,
        *record.qualifications,
    ]
    missing_values.extend(value for value in list_values if value not in raw_text)
    if missing_values:
        raise JobDatasetError(f"Record {index} ({record.job_id}) has incomplete raw_text content.")


def _validate_required_values(record: JobPosting, index: int) -> None:
    scalar_fields = (
        "job_id",
        "job_title",
        "company",
        "location",
        "work_mode",
        "employment_type",
        "domain",
        "job_description",
        "experience_requirements",
        "education_requirements",
        "source_type",
        "posted_date",
        "raw_text",
    )
    empty_fields = [field for field in scalar_fields if not getattr(record, field).strip()]
    list_fields = ("responsibilities", "required_skills", "preferred_skills", "qualifications")
    empty_fields.extend(
        field
        for field in list_fields
        if not getattr(record, field) or any(not value.strip() for value in getattr(record, field))
    )
    if empty_fields:
        raise JobDatasetError(
            f"Record {index} ({record.job_id}) has empty required fields: {', '.join(empty_fields)}."
        )
    try:
        date.fromisoformat(record.posted_date)
    except ValueError as exc:
        raise JobDatasetError(f"Record {index} ({record.job_id}) has an invalid posted_date.") from exc


def _validate_records(payload: Any) -> list[JobPosting]:
    if not isinstance(payload, list):
        raise JobDatasetError("The job dataset must contain a JSON array.")
    if len(payload) != EXPECTED_RECORD_COUNT:
        raise JobDatasetError(
            f"Expected {EXPECTED_RECORD_COUNT} job postings, found {len(payload)}."
        )

    postings: list[JobPosting] = []
    for index, item in enumerate(payload):
        try:
            posting = JobPosting.model_validate(item)
        except ValidationError as exc:
            raise JobDatasetError(f"Invalid job posting at index {index}: {exc}") from exc
        _validate_required_values(posting, index)
        _validate_raw_text(posting, index)
        postings.append(posting)

    job_ids = [posting.job_id for posting in postings]
    duplicate_ids = sorted({job_id for job_id in job_ids if job_ids.count(job_id) > 1})
    if duplicate_ids:
        raise JobDatasetError(f"Duplicate job_id values: {', '.join(duplicate_ids)}.")

    raw_texts = [posting.raw_text for posting in postings]
    if len(set(raw_texts)) != len(raw_texts):
        raise JobDatasetError("Duplicate raw_text content exists in the job dataset.")
    return postings


def load_job_postings(dataset_path: Path | None = None) -> list[JobPosting]:
    path = dataset_path or DATASET_PATH
    if not path.is_file():
        raise JobDatasetError(f"Job dataset not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise JobDatasetError(f"Unable to read job dataset {path}: {exc}") from exc
    return _validate_records(payload)
