from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import User
from app.schemas.text_result import CandidateContextResponse
from app.services.auth import require_current_user
from app.services.candidate_context import build_candidate_context, get_candidate_context
from app.services.profile import get_owned_profile
from app.services.resume import get_resume

router = APIRouter(tags=["candidate-context"])


@router.post("/api/profiles/{profile_id}/candidate-context", response_model=CandidateContextResponse)
def create_candidate_context(
    profile_id: int,
    resume_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user),
) -> CandidateContextResponse:
    profile = get_owned_profile(db, profile_id, current_user.id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Candidate profile not found.")
    resume = get_resume(db, resume_id)
    if resume is None or resume.candidate_profile_id != profile_id:
        raise HTTPException(status_code=404, detail="Resume not found for candidate profile.")
    try:
        return build_candidate_context(db, profile, resume)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/api/profiles/{profile_id}/candidate-context", response_model=CandidateContextResponse)
def read_candidate_context(
    profile_id: int,
    resume_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user),
) -> CandidateContextResponse:
    if get_owned_profile(db, profile_id, current_user.id) is None:
        raise HTTPException(status_code=404, detail="Candidate profile not found.")
    context = get_candidate_context(db, profile_id, resume_id)
    if context is None:
        raise HTTPException(status_code=404, detail="Candidate context not found.")
    return context