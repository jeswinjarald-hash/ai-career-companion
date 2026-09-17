from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import User
from app.schemas.resume_extraction import ResumeExtractionResponse
from app.schemas.resume import ResumeResponse
from app.schemas.resume_section import ResumeSectionResponse, ResumeSectionsResponse
from app.schemas.text_result import StructuredResumeResponse
from app.schemas.job_match import JobMatchResult
from app.services.auth import require_current_user
from app.services.docx_extraction import DocxExtractionError, extract_docx_text
from app.services.profile import get_owned_profile
from app.services.pdf_extraction import PdfExtractionError, extract_pdf_text, get_extraction
from app.services.resume import ResumeUploadError, create_resume, get_owned_resume, list_profile_resumes
from app.services.section_detection import get_resume_sections, persist_resume_sections
from app.services.structured_resume import get_structured_resume, structure_resume
from app.services.job_matching import match_jobs_for_resume


router = APIRouter(tags=["resumes"])


@router.post(
    "/api/profiles/{profile_id}/resumes",
    response_model=ResumeResponse,
    status_code=status.HTTP_201_CREATED,
)
def upload_resume(
    profile_id: int,
    file: UploadFile,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user),
) -> ResumeResponse:
    profile = get_owned_profile(db, profile_id, current_user.id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Candidate profile not found.")
    try:
        return create_resume(db, profile, file)
    except ResumeUploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/resumes/{resume_id}", response_model=ResumeResponse)
def read_resume(
    resume_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user),
) -> ResumeResponse:
    resume = get_owned_resume(db, resume_id, current_user.id)
    if resume is None:
        raise HTTPException(status_code=404, detail="Resume not found.")
    return resume


@router.get("/api/profiles/{profile_id}/resumes", response_model=list[ResumeResponse])
def read_profile_resumes(
    profile_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user),
) -> list[ResumeResponse]:
    if get_owned_profile(db, profile_id, current_user.id) is None:
        raise HTTPException(status_code=404, detail="Candidate profile not found.")
    return list_profile_resumes(db, profile_id)


def _extraction_response(extraction) -> ResumeExtractionResponse:
    return ResumeExtractionResponse(
        id=extraction.id,
        resume_id=extraction.resume_id,
        status=extraction.extraction_status,
        page_count=extraction.page_count,
        character_count=len(extraction.normalized_text or ""),
        raw_text=extraction.raw_text,
        normalized_text=extraction.normalized_text,
        error_message=extraction.error_message,
        created_at=extraction.created_at,
        updated_at=extraction.updated_at,
    )


@router.post("/api/resumes/{resume_id}/extract-text", response_model=ResumeExtractionResponse)
def extract_resume_text(
    resume_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user),
) -> ResumeExtractionResponse:
    resume = get_owned_resume(db, resume_id, current_user.id)
    if resume is None:
        raise HTTPException(status_code=404, detail="Resume not found.")
    try:
        if resume.file_type.lower() == "pdf":
            extraction = extract_pdf_text(db, resume)
        elif resume.file_type.lower() == "docx":
            extraction = extract_docx_text(db, resume)
        else:
            raise HTTPException(status_code=400, detail="Text extraction is not supported for this file type.")
        return _extraction_response(extraction)
    except (PdfExtractionError, DocxExtractionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/resumes/{resume_id}/extraction", response_model=ResumeExtractionResponse)
def read_resume_extraction(
    resume_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user),
) -> ResumeExtractionResponse:
    if get_owned_resume(db, resume_id, current_user.id) is None:
        raise HTTPException(status_code=404, detail="Resume not found.")
    extraction = get_extraction(db, resume_id)
    if extraction is None:
        raise HTTPException(status_code=404, detail="Resume extraction not found.")
    return _extraction_response(extraction)


@router.post("/api/resumes/{resume_id}/detect-sections", response_model=ResumeSectionsResponse)
def detect_sections(
    resume_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user),
) -> ResumeSectionsResponse:
    resume = get_owned_resume(db, resume_id, current_user.id)
    if resume is None:
        raise HTTPException(status_code=404, detail="Resume not found.")
    extraction = get_extraction(db, resume_id)
    if extraction is None or not extraction.normalized_text:
        raise HTTPException(status_code=409, detail="Resume text extraction is required before section detection.")
    sections = persist_resume_sections(db, resume, extraction.normalized_text)
    return ResumeSectionsResponse(resume_id=resume_id, sections=sections)


@router.get("/api/resumes/{resume_id}/sections", response_model=ResumeSectionsResponse)
def read_resume_sections(
    resume_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user),
) -> ResumeSectionsResponse:
    if get_owned_resume(db, resume_id, current_user.id) is None:
        raise HTTPException(status_code=404, detail="Resume not found.")
    sections = get_resume_sections(db, resume_id)
    if not sections:
        raise HTTPException(status_code=404, detail="Resume sections not found.")
    return ResumeSectionsResponse(resume_id=resume_id, sections=sections)


@router.post("/api/resumes/{resume_id}/structure", response_model=StructuredResumeResponse)
def structure_resume_endpoint(
    resume_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user),
) -> StructuredResumeResponse:
    resume = get_owned_resume(db, resume_id, current_user.id)
    if resume is None:
        raise HTTPException(status_code=404, detail="Resume not found.")
    try:
        return structure_resume(db, resume)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/api/resumes/{resume_id}/structured", response_model=StructuredResumeResponse)
def read_structured_resume(
    resume_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user),
) -> StructuredResumeResponse:
    if get_owned_resume(db, resume_id, current_user.id) is None:
        raise HTTPException(status_code=404, detail="Resume not found.")
    result = get_structured_resume(db, resume_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Structured resume not found.")
    return result


@router.get("/api/resumes/{resume_id}/job-matches", response_model=list[JobMatchResult])
def read_job_matches(
    resume_id: int,
    top_k: int = Query(10, ge=1, le=20),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user),
) -> list[JobMatchResult]:
    if get_owned_resume(db, resume_id, current_user.id) is None:
        raise HTTPException(status_code=404, detail="Resume not found.")
    try:
        return match_jobs_for_resume(db, resume_id, top_k)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc