from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import CandidateProfile
from app.schemas.profile import CandidateProfileCreate, CandidateProfileUpdate


class DuplicateProfileError(Exception):
    pass


def create_profile(
    db: Session, profile_data: CandidateProfileCreate, user_id: int | None = None
) -> CandidateProfile:
    profile = CandidateProfile(**profile_data.model_dump(), user_id=user_id)
    db.add(profile)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise DuplicateProfileError from exc
    db.refresh(profile)
    return profile


def get_profile(db: Session, profile_id: int) -> CandidateProfile | None:
    return db.get(CandidateProfile, profile_id)


def get_owned_profile(db: Session, profile_id: int, user_id: int) -> CandidateProfile | None:
    profile = db.get(CandidateProfile, profile_id)
    if profile is None or profile.user_id != user_id:
        return None
    return profile


def update_profile(
    db: Session, profile: CandidateProfile, profile_data: CandidateProfileUpdate
) -> CandidateProfile:
    for field, value in profile_data.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise DuplicateProfileError from exc
    db.refresh(profile)
    return profile