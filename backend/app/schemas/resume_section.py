from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ResumeSectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    resume_id: int
    name: str
    original_heading: str | None
    content: str
    position: int
    created_at: datetime
    updated_at: datetime


class ResumeSectionsResponse(BaseModel):
    resume_id: int
    sections: list[ResumeSectionResponse]
