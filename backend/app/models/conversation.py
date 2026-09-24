from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Conversation(Base):
    """Milestone 3.4 — a persisted career-assistant chat conversation. Tracks the
    "active" job/resume the conversation is currently talking about, so a follow-up
    message ("what skills am I missing?") doesn't require the user to repeat a job id
    that was already established earlier in the same conversation.
    """

    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    active_job_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    active_resume_id: Mapped[int | None] = mapped_column(ForeignKey("resumes.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class ConversationMessage(Base):
    """One turn in a conversation. `metadata_json` holds only what the frontend needs
    to render the turn (suggested actions, the job/resume ids actually used, which
    context sources were consulted, generation metadata) — never raw provider
    secrets, hidden chain-of-thought, or full internal prompts.
    """

    __tablename__ = "conversation_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str | None] = mapped_column(String(32), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
