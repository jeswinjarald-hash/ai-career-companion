from pathlib import Path

from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Resume, ResumeExtraction
from app.services.text_utils import normalize_resume_text


class PdfExtractionError(Exception):
    pass


def get_extraction(db: Session, resume_id: int) -> ResumeExtraction | None:
    return db.scalar(select(ResumeExtraction).where(ResumeExtraction.resume_id == resume_id))


def record_extraction_failure(db: Session, resume: Resume, message: str) -> None:
    extraction = get_extraction(db, resume.id)
    if extraction is None:
        extraction = ResumeExtraction(resume_id=resume.id, extraction_status="extraction_failed")
        db.add(extraction)
    extraction.raw_text = None
    extraction.normalized_text = None
    extraction.page_count = 0
    extraction.extraction_status = "extraction_failed"
    extraction.error_message = message
    resume.status = "extraction_failed"
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise


def extract_pdf_text(db: Session, resume: Resume) -> ResumeExtraction:
    if resume.file_type.lower() != "pdf":
        raise PdfExtractionError("PDF text extraction is only supported for PDF resumes.")

    resume.status = "extracting_text"
    try:
        file_path = Path(resume.storage_path)
        if not file_path.is_file():
            raise PdfExtractionError("The stored PDF file could not be found.")

        reader = PdfReader(file_path, strict=True)
        page_count = len(reader.pages)
        page_text = []
        for page in reader.pages:
            page_text.append(page.extract_text() or "")

        raw_text = "\n\n".join(page_text)
        normalized_text = normalize_resume_text(raw_text)
        if not normalized_text:
            raise PdfExtractionError(
                "No extractable text was found in this PDF. Scanned-image resumes are not currently supported."
            )
    except PdfExtractionError as exc:
        record_extraction_failure(db, resume, str(exc))
        raise
    except Exception as exc:
        record_extraction_failure(db, resume, "The PDF text could not be extracted.")
        raise PdfExtractionError("The PDF text could not be extracted.") from exc

    extraction = get_extraction(db, resume.id)
    if extraction is None:
        extraction = ResumeExtraction(resume_id=resume.id)
        db.add(extraction)
    extraction.raw_text = raw_text
    extraction.normalized_text = normalized_text
    extraction.page_count = page_count
    extraction.extraction_status = "text_extracted"
    extraction.error_message = None
    resume.status = "text_extracted"
    db.commit()
    db.refresh(extraction)
    return extraction
