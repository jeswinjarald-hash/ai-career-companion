from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MatchType = Literal["demonstrated", "partial", "learning_only", "missing"]
RequirementType = Literal["required_skill", "preferred_skill", "qualification", "education", "experience"]
Priority = Literal["high", "medium", "low"]
EvidenceSource = Literal[
    "profile_skills", "resume_skills", "project", "experience", "internship",
    "certification", "achievement", "qualification", "education", "learning", "profile",
]


class EvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: EvidenceSource
    source_name: str
    evidence: str


class StrengthItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement: str
    requirement_type: RequirementType
    evidence: list[EvidenceItem]
    reason: str


class GapItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement: str
    requirement_type: RequirementType
    match_type: MatchType
    priority: Priority
    confidence: float = Field(ge=0, le=1)
    importance: str
    student_evidence: list[EvidenceItem]
    reason: str
    recommendation: str
    suggested_evidence_to_build: str


class ScoreComponent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    component: Literal["required_skills", "preferred_skills", "experience", "education", "qualifications"]
    label: str
    weight: float
    included: bool
    score: float | None
    matched: int
    total: int


class SkillGapSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overall_readiness: int = Field(ge=0, le=100)
    required_requirements_met: int
    required_requirements_total: int
    preferred_requirements_met: int
    preferred_requirements_total: int
    critical_gap_count: int
    partial_gap_count: int
    preferred_gap_count: int
    experience_gap_count: int
    qualification_gap_count: int
    score_breakdown: list[ScoreComponent]


class SkillGapAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    job_title: str
    company: str
    domain: str
    location: str
    resume_id: int
    profile_id: int
    generated_at: datetime
    resume_updated_at: datetime
    stale: bool
    summary: SkillGapSummary
    strengths: list[StrengthItem]
    critical_gaps: list[GapItem]
    partial_gaps: list[GapItem]
    preferred_gaps: list[GapItem]
    experience_gaps: list[GapItem]
    qualification_gaps: list[GapItem]
    recommendations: list[GapItem]
