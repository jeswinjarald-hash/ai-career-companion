from typing import Literal

from pydantic import BaseModel, ConfigDict


class JobChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    job_id: str
    job_title: str
    company: str
    domain: str
    chunk_type: Literal["overview", "requirements", "responsibilities"]
    text: str
    location: str
    work_mode: str
    employment_type: str


class JobSearchResult(BaseModel):
    job_id: str
    job_title: str
    company: str
    domain: str
    location: str
    work_mode: str
    employment_type: str
    required_skills: list[str]
    preferred_skills: list[str]
    similarity_score: float
    matched_chunk_types: list[str]
    matched_text_preview: str | None = None
