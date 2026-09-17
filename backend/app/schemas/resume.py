from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ResumeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    candidate_profile_id: int
    original_filename: str
    file_type: str
    mime_type: str | None
    file_size: int
    status: str
    created_at: datetime
    updated_at: datetime