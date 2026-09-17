from typing import Literal

from pydantic import BaseModel, ConfigDict


class JobPosting(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    job_title: str
    company: str
    location: str
    work_mode: Literal["On-site", "Hybrid", "Remote"]
    employment_type: Literal["Internship", "Entry Level"]
    domain: str
    job_description: str
    responsibilities: list[str]
    required_skills: list[str]
    preferred_skills: list[str]
    qualifications: list[str]
    experience_requirements: str
    education_requirements: str
    source_type: Literal["synthetic_curated"]
    posted_date: str
    raw_text: str
