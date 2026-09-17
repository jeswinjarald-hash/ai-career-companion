from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import User
from app.schemas.profile import CandidateProfileCreate, CandidateProfileResponse, CandidateProfileUpdate
from app.services.auth import require_current_user
from app.services.profile import DuplicateProfileError, create_profile, get_owned_profile, update_profile


router = APIRouter(prefix="/api/profiles", tags=["profiles"])


@router.post("", response_model=CandidateProfileResponse, status_code=status.HTTP_201_CREATED)
def create_candidate_profile(
    profile_data: CandidateProfileCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user),
) -> CandidateProfileResponse:
    try:
        return create_profile(db, profile_data, user_id=current_user.id)
    except DuplicateProfileError:
        raise HTTPException(status_code=409, detail="A profile with this email already exists.")


@router.get("/{profile_id}", response_model=CandidateProfileResponse)
def read_candidate_profile(
    profile_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user),
) -> CandidateProfileResponse:
    profile = get_owned_profile(db, profile_id, current_user.id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Candidate profile not found.")
    return profile


@router.patch("/{profile_id}", response_model=CandidateProfileResponse)
def update_candidate_profile(
    profile_id: int,
    profile_data: CandidateProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user),
) -> CandidateProfileResponse:
    profile = get_owned_profile(db, profile_id, current_user.id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Candidate profile not found.")
    try:
        return update_profile(db, profile, profile_data)
    except DuplicateProfileError:
        raise HTTPException(status_code=409, detail="A profile with this email already exists.")