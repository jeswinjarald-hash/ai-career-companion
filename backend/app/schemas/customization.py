from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ConfidenceType = Literal["direct", "supporting", "learning_only"]
SourceType = Literal[
    "skill", "project", "experience", "internship", "education",
    "certification", "achievement", "qualification", "profile",
]
KeywordStatus = Literal["supported", "partial", "unsupported"]
KeywordRequirementType = Literal["required_skill", "preferred_skill"]
CustomizationStatus = Literal["ready", "validation_warning"]
GenerationMode = Literal["llm", "deterministic_fallback"]


class EvidenceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    source_type: SourceType
    source_name: str
    source_path: str
    raw_text: str
    canonical_terms: list[str]
    confidence_type: ConfidenceType


class KeywordClassification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    keyword: str
    requirement_type: KeywordRequirementType
    status: KeywordStatus
    reason: str
    matched_evidence_ids: list[str]


class TailoredBullet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    original_text: str
    tailored_text: str
    source_path: str
    job_keywords_used: list[str]
    evidence_ids: list[str] = Field(default_factory=list)
    introduced_claims: list[str] = Field(default_factory=list)


class TailoredProject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    original_text: str
    tailored_text: str
    technologies: list[str]
    source_path: str
    relevance_rank: int
    job_keywords_used: list[str]
    evidence_ids: list[str] = Field(default_factory=list)
    introduced_claims: list[str] = Field(default_factory=list)


class TailoredEducationEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw_text: str
    source_path: str


class TailoredResume(BaseModel):
    model_config = ConfigDict(extra="forbid")

    header: str
    summary: str
    summary_sources: list[str]
    skills: list[str]
    education: list[TailoredEducationEntry]
    projects: list[TailoredProject]
    experience: list[TailoredBullet]
    internships: list[TailoredBullet]
    certifications: list[str]
    achievements: list[str]


class CoverLetterSentence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    sources: list[str]
    evidence_ids: list[str] = Field(default_factory=list)


class ValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool
    warnings: list[str]
    removed_claims: list[str]


class GenerationMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: GenerationMode
    attempted_llm: bool
    provider: str | None = None
    model: str | None = None
    repair_attempted: bool = False
    fallback_reason: str | None = None


class UserEdits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str | None = None
    cover_letter_text: str | None = None
    bullet_edits: dict[str, str] = Field(default_factory=dict)
    edited_fields: list[str] = Field(default_factory=list)


class ApplicationCustomization(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    resume_id: int
    job_id: str
    job_title: str
    company: str
    version: int
    status: CustomizationStatus
    stale: bool
    parser_warning_notice: str | None
    evidence: list[EvidenceRecord]
    keyword_classification: list[KeywordClassification]
    tailored_resume: TailoredResume
    cover_letter: list[CoverLetterSentence]
    cover_letter_text: str
    validation: ValidationResult
    generation: GenerationMetadata
    user_edits: UserEdits
    created_at: datetime
    updated_at: datetime


class ApplicationCustomizationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    resume_id: int
    job_id: str
    job_title: str
    company: str
    version: int
    status: CustomizationStatus
    stale: bool
    generation_mode: GenerationMode
    created_at: datetime
    updated_at: datetime


class ApplicationCustomizationEditPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str | None = None
    cover_letter_text: str | None = None
    bullet_edits: dict[str, str] | None = None
