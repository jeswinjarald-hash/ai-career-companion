from pydantic import BaseModel, ConfigDict, Field


class JobMatchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    job_title: str
    company: str
    domain: str
    location: str
    work_mode: str
    employment_type: str
    retrieval_score: float
    match_score: float = Field(ge=0, le=100)
    required_skills_score: float = Field(ge=0, le=1)
    preferred_skills_score: float = Field(ge=0, le=1)
    experience_score: float = Field(ge=0, le=1)
    education_score: float = Field(ge=0, le=1)
    project_relevance_score: float = Field(ge=0, le=1)
    qualification_score: float = Field(ge=0, le=1)
    matched_required_skills: list[str]
    missing_required_skills: list[str]
    matched_preferred_skills: list[str]
    missing_preferred_skills: list[str]
    relevant_projects: list[str]
    strengths: list[str]
    gaps: list[str]
    reasoning: str
