import logging
from pathlib import Path

from pypdf import PageObject, PdfReader
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Resume, ResumeExtraction
from app.services.text_utils import normalize_resume_text


logger = logging.getLogger(__name__)


class PdfExtractionError(Exception):
    pass


_FRAGMENTED_MIN_LINES = 20
_FRAGMENTED_SINGLE_TOKEN_SHARE = 0.6


def is_word_fragmented(text: str) -> bool:
    """True when extracted text has (almost) one word per line — a known pypdf
    plain-mode failure on Google Docs (Skia) PDFs, whose flipped text matrix makes
    pypdf emit a line break between every word even though the words share one
    baseline. Real resume lines are overwhelmingly multi-word."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < _FRAGMENTED_MIN_LINES:
        return False
    single_token = sum(1 for line in lines if len(line.split()) == 1)
    return single_token / len(lines) >= _FRAGMENTED_SINGLE_TOKEN_SHARE


def _positioned_page_text(page: PageObject) -> str:
    """Rebuilds a page's lines from each text run's real device-space position.

    pypdf's content-stream order is kept (it reads one column at a time, so a
    two-column resume's sidebar is not interleaved with the main column — unlike
    pypdf's "layout" mode), but its own line breaks are ignored: runs on the same
    baseline join into one line, a normal line advance starts a new line, and a
    larger vertical gap (paragraph spacing, or a jump to another column) becomes a
    blank line.
    """
    runs: list[tuple[float, float, float, str]] = []

    def visit(text: str, cm: list[float], tm: list[float], _font_dict: object, font_size: float) -> None:
        if not text or text == "\n":
            return
        a, b, c, d, e, f = cm
        x = tm[4] * a + tm[5] * c + e
        y = tm[4] * b + tm[5] * d + f
        size = abs(font_size * (tm[3] * d - tm[2] * b)) or abs(font_size) or 10.0
        runs.append((x, y, size, text))

    page.extract_text(visitor_text=visit)

    parts: list[str] = []
    last: tuple[float, float, float, str] | None = None
    for x, y, size, text in runs:
        if last is None:
            if text.strip():
                parts.append(text)
                last = (x, y, size, text)
            continue
        last_x, last_y, last_size, last_text = last
        tolerance = 0.4 * max(size, last_size)
        if abs(y - last_y) <= tolerance and x >= last_x:
            if text.strip():
                # No explicit space run between two runs on one line: insert one only
                # when the horizontal gap is clearly wider than the previous run.
                estimated_end = last_x + 0.45 * last_size * len(last_text)
                if parts and not parts[-1].endswith(" ") and x > estimated_end + 0.3 * last_size:
                    parts.append(" ")
                parts.append(text)
                last = (x, y, size, text)
            elif parts and not parts[-1].endswith(" "):
                parts.append(" ")
            continue
        if not text.strip():
            continue
        gap = last_y - y
        parts.append("\n\n" if gap > 1.6 * max(size, last_size) or gap < -tolerance else "\n")
        parts.append(text)
        last = (x, y, size, text)
    return "".join(parts)


def _page_text(page: PageObject) -> tuple[str, bool]:
    text = page.extract_text() or ""
    if not is_word_fragmented(text):
        return text, False
    rebuilt = _positioned_page_text(page)
    if rebuilt.strip() and not is_word_fragmented(rebuilt):
        return rebuilt, True
    return text, False


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
        rebuilt_pages = 0
        for page in reader.pages:
            text, rebuilt = _page_text(page)
            page_text.append(text)
            rebuilt_pages += rebuilt
        if rebuilt_pages:
            # Diagnostic only — never resume text.
            logger.info("pdf_extraction_rebuilt_lines resume_id=%s pages=%s", resume.id, rebuilt_pages)

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
