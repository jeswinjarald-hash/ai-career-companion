import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import CandidateProfile, StructuredResume, User
from app.models.career_state import ApplicationCustomization as ApplicationCustomizationRecord
from app.schemas.customization import ApplicationCustomization, ApplicationCustomizationEditPayload, ApplicationCustomizationSummary
from app.services.auth import require_current_user
from app.services.customization_export_service import export_cover_letter_docx, export_cover_letter_pdf, export_resume_docx, export_resume_pdf
from app.services.resume import get_owned_resume
from app.services.resume_customization_service import apply_user_edits, generate_customization, get_customization, list_customizations

router = APIRouter(tags=["application-customization"])
logger = logging.getLogger(__name__)


@router.post("/api/resumes/{resume_id}/application-customizations", response_model=ApplicationCustomization)
def create_application_customization(
    resume_id: int,
    job_id: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user),
) -> ApplicationCustomization:
    if get_owned_resume(db, resume_id, current_user.id) is None:
        raise HTTPException(status_code=404, detail="Resume not found.")
    try:
        return generate_customization(db, resume_id, job_id, current_user.id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception:
        logger.exception("customization_generation_failed resume_id=%s job_id=%s", resume_id, job_id)
        raise


@router.get("/api/resumes/{resume_id}/application-customizations", response_model=list[ApplicationCustomizationSummary])
def read_application_customizations(
    resume_id: int,
    job_id: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user),
) -> list[ApplicationCustomizationSummary]:
    if get_owned_resume(db, resume_id, current_user.id) is None:
        raise HTTPException(status_code=404, detail="Resume not found.")
    return list_customizations(db, resume_id, job_id)


@router.get("/api/resumes/{resume_id}/application-customizations/{customization_id}", response_model=ApplicationCustomization)
def read_application_customization(
    resume_id: int,
    customization_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user),
) -> ApplicationCustomization:
    if get_owned_resume(db, resume_id, current_user.id) is None:
        raise HTTPException(status_code=404, detail="Resume not found.")
    structured = db.scalar(select(StructuredResume).where(StructuredResume.resume_id == resume_id))
    result = get_customization(db, resume_id, customization_id, structured.updated_at if structured else None)
    if result is None:
        raise HTTPException(status_code=404, detail="Application customization not found.")
    return result


@router.patch("/api/resumes/{resume_id}/application-customizations/{customization_id}", response_model=ApplicationCustomization)
def update_application_customization(
    resume_id: int,
    customization_id: int,
    payload: ApplicationCustomizationEditPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user),
) -> ApplicationCustomization:
    if get_owned_resume(db, resume_id, current_user.id) is None:
        raise HTTPException(status_code=404, detail="Resume not found.")
    result = apply_user_edits(db, resume_id, customization_id, payload)
    if result is None:
        raise HTTPException(status_code=404, detail="Application customization not found.")
    return result


@router.post("/api/resumes/{resume_id}/application-customizations/{customization_id}/regenerate", response_model=ApplicationCustomization)
def regenerate_application_customization(
    resume_id: int,
    customization_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user),
) -> ApplicationCustomization:
    if get_owned_resume(db, resume_id, current_user.id) is None:
        raise HTTPException(status_code=404, detail="Resume not found.")
    existing = db.get(ApplicationCustomizationRecord, customization_id)
    if existing is None or existing.resume_id != resume_id:
        raise HTTPException(status_code=404, detail="Application customization not found.")
    try:
        return generate_customization(db, resume_id, existing.job_id, current_user.id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


_EXPORTERS = {
    ("resume", "pdf"): export_resume_pdf,
    ("resume", "docx"): export_resume_docx,
    ("cover_letter", "pdf"): export_cover_letter_pdf,
    ("cover_letter", "docx"): export_cover_letter_docx,
}
_MEDIA_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


@router.get("/api/resumes/{resume_id}/application-customizations/{customization_id}/export")
def export_application_customization(
    resume_id: int,
    customization_id: int,
    document: str = Query(..., pattern="^(resume|cover_letter)$"),
    format: str = Query(..., pattern="^(pdf|docx)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user),
) -> Response:
    resume = get_owned_resume(db, resume_id, current_user.id)
    if resume is None:
        raise HTTPException(status_code=404, detail="Resume not found.")
    structured = db.scalar(select(StructuredResume).where(StructuredResume.resume_id == resume_id))
    result = get_customization(db, resume_id, customization_id, structured.updated_at if structured else None)
    if result is None:
        raise HTTPException(status_code=404, detail="Application customization not found.")

    profile = db.get(CandidateProfile, resume.candidate_profile_id)
    candidate_name = profile.full_name if profile is not None else current_user.full_name

    try:
        content = _EXPORTERS[(document, format)](result, candidate_name)
    except Exception:
        logger.exception("customization_export_failed resume_id=%s customization_id=%s document=%s format=%s", resume_id, customization_id, document, format)
        raise HTTPException(status_code=500, detail="We could not generate this export. Please try again.")

    filename = f"{document.replace('_', '-')}-{result.job_id}-v{result.version}.{format}"
    return Response(
        content=content, media_type=_MEDIA_TYPES[format],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
