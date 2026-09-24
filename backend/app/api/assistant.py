import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import User
from app.schemas.assistant import (
    AssistantResponse, ConversationDetail, ConversationSummary, CreateConversationRequest, SendMessageRequest,
)
from app.services.assistant_service import create_conversation, delete_conversation, get_conversation, list_conversations, send_message
from app.services.auth import require_current_user

router = APIRouter(prefix="/api/career-assistant", tags=["career-assistant"])
logger = logging.getLogger(__name__)


@router.post("/conversations", response_model=ConversationDetail)
def start_conversation(
    payload: CreateConversationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user),
) -> ConversationDetail:
    return create_conversation(db, current_user.id, title=payload.title, job_id=payload.job_id)


@router.get("/conversations", response_model=list[ConversationSummary])
def read_conversations(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user),
) -> list[ConversationSummary]:
    return list_conversations(db, current_user.id)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def read_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user),
) -> ConversationDetail:
    result = get_conversation(db, current_user.id, conversation_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return result


@router.post("/conversations/{conversation_id}/messages", response_model=AssistantResponse)
def post_message(
    conversation_id: int,
    payload: SendMessageRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user),
) -> AssistantResponse:
    try:
        return send_message(db, current_user.id, conversation_id, payload.content, job_id_hint=payload.job_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception:
        logger.exception("career_assistant_message_failed conversation_id=%s", conversation_id)
        raise


@router.delete("/conversations/{conversation_id}", status_code=204)
def remove_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user),
) -> None:
    if not delete_conversation(db, current_user.id, conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found.")
