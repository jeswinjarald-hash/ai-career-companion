from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


def normalize_list(values: list[str] | None) -> list[str]:
    if values is None:
        return []

    normalized: list[str] = []
    for value in values:
        item = value.strip()
        if item and item not in normalized:
            normalized.append(item)
    return normalized


class CandidateProfileFields(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    education: str | None = Field(default=None, max_length=1000)
    degree: str | None = Field(default=None, max_length=255)
    specialization: str | None = Field(default=None, max_length=255)
    experience_level: str | None = Field(default=None, max_length=100)
    career_interests: list[str] = Field(default_factory=list, max_length=20)
    target_roles: list[str] = Field(default_factory=list, max_length=20)
    skills: list[str] = Field(default_factory=list, max_length=50)
    career_goals: str | None = Field(default=None, max_length=2000)

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("full_name must not be empty")
        return stripped

    @field_validator("education", "degree", "specialization", "experience_level", "career_goals")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None

    @field_validator("career_interests", "target_roles", "skills")
    @classmethod
    def normalize_lists(cls, value: list[str]) -> list[str]:
        return normalize_list(value)


class CandidateProfileCreate(CandidateProfileFields):
    pass


class CandidateProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    email: EmailStr | None = None
    education: str | None = Field(default=None, max_length=1000)
    degree: str | None = Field(default=None, max_length=255)
    specialization: str | None = Field(default=None, max_length=255)
    experience_level: str | None = Field(default=None, max_length=100)
    career_interests: list[str] | None = Field(default=None, max_length=20)
    target_roles: list[str] | None = Field(default=None, max_length=20)
    skills: list[str] | None = Field(default=None, max_length=50)
    career_goals: str | None = Field(default=None, max_length=2000)

    @field_validator("full_name")
    @classmethod
    def validate_update_full_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("full_name must not be empty")
        return stripped

    @field_validator("education", "degree", "specialization", "experience_level", "career_goals")
    @classmethod
    def strip_update_optional_text(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None

    @field_validator("career_interests", "target_roles", "skills")
    @classmethod
    def normalize_update_lists(cls, value: list[str] | None) -> list[str] | None:
        return normalize_list(value) if value is not None else None


class CandidateProfileResponse(CandidateProfileFields):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime