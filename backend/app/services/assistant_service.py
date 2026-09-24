"""Milestone 3.4 — Career Assistant orchestrator.

Ties together intent detection (`assistant_intent`), context resolution
(`assistant_context`), the per-intent handlers that call M2/M3.1/M3.2/M3.3's own
service functions (`assistant_handlers`), and optional grounded LLM wording
(`assistant_llm`), then persists the conversation turn. This module owns no
business logic of its own beyond routing and persistence.
"""

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Conversation, ConversationMessage
from app.schemas.assistant import (
    AssistantResponse, ConversationDetail, ConversationSummary, MessageOut, SuggestedAction,
)
from app.schemas.customization import GenerationMetadata
from app.services.assistant_context import ResolvedContext, resolve_context
from app.services.assistant_handlers import HANDLERS
from app.services.assistant_intent import detect_intent
from app.services.assistant_llm import synthesize_response
from app.services.llm_provider import LLMProvider, get_llm_provider

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _message_to_out(message: ConversationMessage) -> MessageOut:
    meta = message.metadata_json or {}
    generation = meta.get("generation")
    return MessageOut(
        id=message.id, role=message.role, content=message.content, intent=message.intent,
        job_id=meta.get("job_id"), resume_id=meta.get("resume_id"),
        suggested_actions=[SuggestedAction.model_validate(action) for action in meta.get("suggested_actions", [])],
        context_used=meta.get("context_used", []),
        generation=GenerationMetadata.model_validate(generation) if generation else None,
        created_at=message.created_at,
    )


def _to_detail(conversation: Conversation, messages: list[ConversationMessage]) -> ConversationDetail:
    return ConversationDetail(
        id=conversation.id, title=conversation.title,
        active_job_id=conversation.active_job_id, active_resume_id=conversation.active_resume_id,
        messages=[_message_to_out(m) for m in messages],
        created_at=conversation.created_at, updated_at=conversation.updated_at,
    )


def create_conversation(db: Session, user_id: int, title: str | None = None, job_id: str | None = None) -> ConversationDetail:
    conversation = Conversation(user_id=user_id, title=title, active_job_id=job_id)
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return _to_detail(conversation, [])


def list_conversations(db: Session, user_id: int) -> list[ConversationSummary]:
    statement = select(Conversation).where(Conversation.user_id == user_id).order_by(Conversation.updated_at.desc())
    conversations = list(db.scalars(statement))
    summaries = []
    for conversation in conversations:
        count = db.scalar(
            select(func.count()).select_from(ConversationMessage).where(ConversationMessage.conversation_id == conversation.id)
        ) or 0
        summaries.append(ConversationSummary(
            id=conversation.id, title=conversation.title,
            active_job_id=conversation.active_job_id, active_resume_id=conversation.active_resume_id,
            message_count=count, created_at=conversation.created_at, updated_at=conversation.updated_at,
        ))
    return summaries


def get_conversation(db: Session, user_id: int, conversation_id: int) -> ConversationDetail | None:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None or conversation.user_id != user_id:
        return None
    statement = select(ConversationMessage).where(ConversationMessage.conversation_id == conversation.id).order_by(ConversationMessage.id.asc())
    messages = list(db.scalars(statement))
    return _to_detail(conversation, messages)


def delete_conversation(db: Session, user_id: int, conversation_id: int) -> bool:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None or conversation.user_id != user_id:
        return False
    db.query(ConversationMessage).filter(ConversationMessage.conversation_id == conversation.id).delete()
    db.delete(conversation)
    db.commit()
    return True


def _recent_messages_for_llm(db: Session, conversation_id: int) -> list[dict]:
    statement = select(ConversationMessage).where(ConversationMessage.conversation_id == conversation_id).order_by(ConversationMessage.id.desc()).limit(6)
    rows = list(db.scalars(statement))
    rows.reverse()
    return [{"role": row.role, "content": row.content} for row in rows]


def _missing_context_followup(intent_result: dict, ctx: ResolvedContext) -> tuple[str | None, list[SuggestedAction]]:
    if intent_result["requires_resume_context"]:
        if ctx.resume is None:
            return "I don't see a resume on your account yet. Upload one so I can give you grounded advice.", [SuggestedAction(label="Upload resume", action="upload_resume")]
        if not ctx.resume_is_processed:
            return "Your resume is uploaded but not processed yet. Process it first so I can use your extracted skills and experience.", [SuggestedAction(label="Process resume", action="process_resume")]

    if intent_result["requires_second_job_context"] and ctx.job is None and ctx.second_job is None:
        # Neither opportunity of a comparison was identified — ask for both together
        # rather than asking for the first one only and leaving the second unexplained.
        return 'To compare two opportunities, please mention both ids (e.g. "compare JOB-0035 and JOB-0041").', []

    if intent_result["requires_job_context"]:
        if ctx.job_not_found:
            return f"I couldn't find an opportunity with id {ctx.job_not_found}. Could you double-check the id, or open its details page first?", []
        if ctx.job is None:
            return "Which opportunity would you like me to use? You can mention its id (e.g. JOB-0035) or open its details page first.", []

    if intent_result["requires_second_job_context"]:
        if ctx.second_job_not_found:
            return f"I couldn't find an opportunity with id {ctx.second_job_not_found}. Could you double-check both ids?", []
        if ctx.second_job is None:
            return 'To compare two opportunities, please mention both ids (e.g. "compare JOB-0035 and JOB-0041").', []

    return None, []


def send_message(
    db: Session, user_id: int, conversation_id: int, content: str,
    job_id_hint: str | None = None, llm_provider: LLMProvider | None = None,
) -> AssistantResponse:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None or conversation.user_id != user_id:
        raise LookupError("Conversation not found.")

    remembered_job_id = job_id_hint or conversation.active_job_id
    intent_result = detect_intent(content, remembered_job_id)
    ctx = resolve_context(db, user_id, intent_result["job_id"], intent_result.get("second_job_id"))

    user_message = ConversationMessage(
        conversation_id=conversation.id, role="user", content=content, intent=intent_result["intent"],
        metadata_json={"job_id": intent_result["job_id"], "resume_id": ctx.resume.id if ctx.resume else None},
    )
    db.add(user_message)
    db.flush()

    resume_changed_notice = None
    if conversation.active_resume_id is not None and ctx.resume is not None and conversation.active_resume_id != ctx.resume.id:
        resume_changed_notice = "I'm now using your most recently uploaded resume, which is newer than the one used earlier in this conversation."

    followup_text, followup_actions = _missing_context_followup(intent_result, ctx)
    if followup_text is not None:
        assistant_message = ConversationMessage(
            conversation_id=conversation.id, role="assistant", content=followup_text, intent=intent_result["intent"],
            metadata_json={
                "job_id": intent_result["job_id"], "resume_id": ctx.resume.id if ctx.resume else None,
                "suggested_actions": [action.model_dump() for action in followup_actions],
                "context_used": [], "generation": None,
            },
        )
        db.add(assistant_message)
        conversation.updated_at = _utc_now()
        db.commit()
        db.refresh(assistant_message)
        db.refresh(conversation)
        return AssistantResponse(message=_message_to_out(assistant_message), active_job_id=conversation.active_job_id, active_resume_id=conversation.active_resume_id)

    handler = HANDLERS[intent_result["intent"]]
    result = handler(db, user_id, ctx, content)

    provider = llm_provider if llm_provider is not None else get_llm_provider(get_settings())
    recent = _recent_messages_for_llm(db, conversation.id)
    synthesized, generation_meta = synthesize_response(
        provider, intent_result["intent"], result.facts, result.message, content,
        recent, result.unsupported_terms, result.grounding_mode,
    )
    if synthesized is not None:
        final_text = synthesized
        generation = GenerationMetadata(mode="llm", **generation_meta)
    else:
        final_text = result.message
        generation = GenerationMetadata(mode="deterministic_fallback", **generation_meta)

    notices = [note for note in (result.stale_notice, resume_changed_notice) if note]
    if notices:
        final_text = final_text + "\n\n" + " ".join(notices)

    assistant_message = ConversationMessage(
        conversation_id=conversation.id, role="assistant", content=final_text, intent=intent_result["intent"],
        metadata_json={
            "job_id": result.job_id, "resume_id": result.resume_id,
            "suggested_actions": [action.model_dump() for action in result.suggested_actions],
            "context_used": result.context_used, "generation": json.loads(generation.model_dump_json()),
        },
    )
    db.add(assistant_message)

    # Never clear a previously established active job/resume just because this
    # particular intent didn't need one (e.g. GENERAL_CAREER_CHAT).
    if result.job_id:
        conversation.active_job_id = result.job_id
    if result.resume_id:
        conversation.active_resume_id = result.resume_id
    if conversation.title is None:
        conversation.title = content[:80]
    conversation.updated_at = _utc_now()

    db.commit()
    db.refresh(assistant_message)
    db.refresh(conversation)
    return AssistantResponse(message=_message_to_out(assistant_message), active_job_id=conversation.active_job_id, active_resume_id=conversation.active_resume_id)
