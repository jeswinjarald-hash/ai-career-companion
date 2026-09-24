import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.models import StructuredResume, User
from app.models.career_state import InterviewPreparation as InterviewPreparationRecord
from app.schemas.interview_prep import InterviewPreparation, InterviewPreparationSummary, MockAnswerEvaluation, MockAnswerRequest
from app.services.auth import require_current_user
from app.services.interview_mock_service import evaluate_mock_answer
from app.services.interview_prep_service import generate_interview_preparation, get_interview_preparation, list_interview_preparations
from app.services.llm_provider import get_llm_provider
from app.services.resume import get_owned_resume

router = APIRouter(tags=["interview-preparation"])
logger = logging.getLogger(__name__)


@router.post("/api/resumes/{resume_id}/interview-preparations", response_model=InterviewPreparation)
def create_interview_preparation(
    resume_id: int,
    job_id: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user),
) -> InterviewPreparation:
    if get_owned_resume(db, resume_id, current_user.id) is None:
        raise HTTPException(status_code=404, detail="Resume not found.")
    try:
        return generate_interview_preparation(db, resume_id, job_id, current_user.id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception:
        logger.exception("interview_prep_generation_failed resume_id=%s job_id=%s", resume_id, job_id)
        raise


@router.get("/api/resumes/{resume_id}/interview-preparations", response_model=list[InterviewPreparationSummary])
def read_interview_preparations(
    resume_id: int,
    job_id: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user),
) -> list[InterviewPreparationSummary]:
    if get_owned_resume(db, resume_id, current_user.id) is None:
        raise HTTPException(status_code=404, detail="Resume not found.")
    return list_interview_preparations(db, resume_id, job_id)


@router.get("/api/resumes/{resume_id}/interview-preparations/{prep_id}", response_model=InterviewPreparation)
def read_interview_preparation(
    resume_id: int,
    prep_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user),
) -> InterviewPreparation:
    if get_owned_resume(db, resume_id, current_user.id) is None:
        raise HTTPException(status_code=404, detail="Resume not found.")
    structured = db.scalar(select(StructuredResume).where(StructuredResume.resume_id == resume_id))
    result = get_interview_preparation(db, resume_id, prep_id, structured.updated_at if structured else None)
    if result is None:
        raise HTTPException(status_code=404, detail="Interview preparation not found.")
    return result


@router.post("/api/resumes/{resume_id}/interview-preparations/{prep_id}/regenerate", response_model=InterviewPreparation)
def regenerate_interview_preparation(
    resume_id: int,
    prep_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user),
) -> InterviewPreparation:
    if get_owned_resume(db, resume_id, current_user.id) is None:
        raise HTTPException(status_code=404, detail="Resume not found.")
    existing = db.get(InterviewPreparationRecord, prep_id)
    if existing is None or existing.resume_id != resume_id:
        raise HTTPException(status_code=404, detail="Interview preparation not found.")
    try:
        return generate_interview_preparation(db, resume_id, existing.job_id, current_user.id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/api/resumes/{resume_id}/interview-preparations/{prep_id}/mock-answer", response_model=MockAnswerEvaluation)
def submit_mock_answer(
    resume_id: int,
    prep_id: int,
    payload: MockAnswerRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user),
) -> MockAnswerEvaluation:
    if get_owned_resume(db, resume_id, current_user.id) is None:
        raise HTTPException(status_code=404, detail="Resume not found.")
    structured = db.scalar(select(StructuredResume).where(StructuredResume.resume_id == resume_id))
    prep = get_interview_preparation(db, resume_id, prep_id, structured.updated_at if structured else None)
    if prep is None:
        raise HTTPException(status_code=404, detail="Interview preparation not found.")
    if payload.question_index >= len(prep.questions):
        raise HTTPException(status_code=404, detail="Question not found in this interview preparation.")

    question = prep.questions[payload.question_index]
    provider = get_llm_provider(get_settings())
    return evaluate_mock_answer(provider, question, payload.answer)
