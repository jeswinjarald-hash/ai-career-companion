from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.customization import GenerationMetadata

Intent = Literal[
    "JOB_DISCOVERY", "JOB_MATCH_EXPLANATION", "SKILL_GAP", "RESUME_CUSTOMIZATION",
    "COVER_LETTER", "INTERVIEW_PREP", "LEARNING_GUIDANCE", "JOB_COMPARISON",
    "PROFILE_SUMMARY", "NEXT_BEST_ACTION", "GENERAL_CAREER_CHAT",
]
MessageRole = Literal["user", "assistant"]
ActionType = Literal[
    "upload_resume", "process_resume", "view_resume", "view_recommendations", "view_job",
    "analyze_skill_gap", "customize_application", "prepare_interview",
    "compare_jobs", "view_learning_plan",
]


class SuggestedAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    action: ActionType
    job_id: str | None = None


class IntentResult(BaseModel):
    """Internal (not returned directly by the API) — the output of deterministic
    intent detection, before any grounded data has been fetched.
    """

    model_config = ConfigDict(extra="forbid")

    intent: Intent
    confidence: float = Field(ge=0, le=1)
    job_id: str | None = None
    second_job_id: str | None = None
    resume_hint: int | None = None
    requires_job_context: bool = False
    requires_resume_context: bool = False
    requires_second_job_context: bool = False


class MessageOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    role: MessageRole
    content: str
    intent: Intent | None
    job_id: str | None
    resume_id: int | None
    suggested_actions: list[SuggestedAction]
    context_used: list[str]
    generation: GenerationMetadata | None
    created_at: datetime


class ConversationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    title: str | None
    active_job_id: str | None
    active_resume_id: int | None
    message_count: int
    created_at: datetime
    updated_at: datetime


class ConversationDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    title: str | None
    active_job_id: str | None
    active_resume_id: int | None
    messages: list[MessageOut]
    created_at: datetime
    updated_at: datetime


class CreateConversationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    job_id: str | None = None


class SendMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=4000)
    job_id: str | None = None


class AssistantResponse(BaseModel):
    """The API's response to a sent message — the freshly created assistant
    `MessageOut` plus the conversation's resulting active context, so the frontend
    never has to re-fetch the whole conversation just to know what job/resume the
    assistant is now tracking.
    """

    model_config = ConfigDict(extra="forbid")

    message: MessageOut
    active_job_id: str | None
    active_resume_id: int | None
