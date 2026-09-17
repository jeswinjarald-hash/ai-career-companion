from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import CandidateProfile, Resume
from app.services.resume_validation import (
    MAX_RESUME_SIZE,
    ResumeValidationError,
    validate_resume_upload,
)


class ResumeUploadError(Exception):
    pass


def _storage_directory() -> Path:
    storage_dir = Path(get_settings().resume_storage_dir)
    storage_dir.mkdir(parents=True, exist_ok=True)
    return storage_dir


def create_resume(db: Session, profile: CandidateProfile, upload: UploadFile) -> Resume:
    original_filename = Path(upload.filename or "").name
    if not original_filename:
        raise ResumeUploadError("A resume filename is required.")

    content = upload.file.read(MAX_RESUME_SIZE + 1)
    try:
        file_type = validate_resume_upload(original_filename, upload.content_type, content)
    except ResumeValidationError as exc:
        raise ResumeUploadError(str(exc)) from exc

    extension = f".{file_type}"
    stored_filename = f"resume_{uuid4().hex}{extension}"
    storage_path: Path | None = None

    try:
        storage_path = _storage_directory() / stored_filename
        file_size = len(content)
        with storage_path.open("wb") as destination:
            destination.write(content)

        resume = Resume(
            candidate_profile_id=profile.id,
            original_filename=original_filename,
            stored_filename=stored_filename,
            file_type=file_type,
            mime_type=upload.content_type,
            file_size=file_size,
            storage_path=str(storage_path),
            status="uploaded",
        )
        db.add(resume)
        db.commit()
        db.refresh(resume)
        return resume
    except Exception:
        if storage_path is not None and storage_path.exists():
            storage_path.unlink()
        db.rollback()
        raise


def get_resume(db: Session, resume_id: int) -> Resume | None:
    return db.get(Resume, resume_id)


def get_owned_resume(db: Session, resume_id: int, user_id: int) -> Resume | None:
    resume = db.get(Resume, resume_id)
    if resume is None:
        return None
    profile = db.get(CandidateProfile, resume.candidate_profile_id)
    if profile is None or profile.user_id != user_id:
        return None
    return resume


def list_profile_resumes(db: Session, profile_id: int) -> list[Resume]:
    statement = select(Resume).where(Resume.candidate_profile_id == profile_id).order_by(Resume.created_at.desc())
    return list(db.scalars(statement))