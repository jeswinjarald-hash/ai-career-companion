from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ResumeExtractionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    resume_id: int
    status: str
    page_count: int
    character_count: int
    raw_text: str | None
    normalized_text: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
