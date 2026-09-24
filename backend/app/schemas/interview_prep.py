from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.customization import EvidenceRecord, GenerationMetadata, ValidationResult

QuestionCategory = Literal["technical", "resume", "project", "role", "hr", "skill_gap"]
Difficulty = Literal["easy", "medium", "hard"]
RevisionPriority = Literal["high", "medium", "low"]
InterviewPrepStatus = Literal["ready", "validation_warning"]


class InterviewQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str
    category: QuestionCategory
    difficulty: Difficulty
    why_asked: str
    what_interviewer_is_testing: str
    preparation_guidance: str
    topics_to_review: list[str] = Field(default_factory=list)
    source_requirements: list[str] = Field(default_factory=list)
    source_evidence_ids: list[str] = Field(default_factory=list)


class RevisionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    priority: RevisionPriority
    topic: str
    reason: str
    suggested_revision: str
    estimated_focus: str


class MockAnswerEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strengths: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)
    missing_points: list[str] = Field(default_factory=list)
    suggested_structure: str
    grounded_feedback: str
    generation: GenerationMetadata


class InterviewPreparation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    resume_id: int
    job_id: str
    job_title: str
    company: str
    version: int
    status: InterviewPrepStatus
    stale: bool
    parser_warning_notice: str | None
    preparation_summary: str
    questions: list[InterviewQuestion]
    revision_plan: list[RevisionItem]
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    validation: ValidationResult
    generation: GenerationMetadata
    created_at: datetime
    updated_at: datetime


class InterviewPreparationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    resume_id: int
    job_id: str
    job_title: str
    company: str
    version: int
    status: InterviewPrepStatus
    stale: bool
    generation_mode: Literal["llm", "deterministic_fallback"]
    created_at: datetime
    updated_at: datetime


class MockAnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_index: int = Field(ge=0)
    answer: str = Field(min_length=1)
