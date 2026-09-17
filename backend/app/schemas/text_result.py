from datetime import datetime

from pydantic import BaseModel, ConfigDict


class StructuredResumeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    resume_id: int
    data: dict
    created_at: datetime
    updated_at: datetime


class CandidateContextResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    candidate_profile_id: int
    resume_id: int
    context_json: dict
    created_at: datetime
    updated_at: datetime
