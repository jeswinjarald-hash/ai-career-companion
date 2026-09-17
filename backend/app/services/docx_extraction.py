from pathlib import Path

from docx import Document
from docx.document import Document as DocumentObject
from docx.table import Table
from docx.text.paragraph import Paragraph
from sqlalchemy.orm import Session

from app.models import Resume, ResumeExtraction
from app.services.pdf_extraction import get_extraction, record_extraction_failure
from app.services.text_utils import normalize_resume_text


class DocxExtractionError(Exception):
    pass


def _iter_blocks(document: DocumentObject):
    parent = document.element.body
    for child in parent.iterchildren():
        if child.tag.endswith("}p"):
            yield Paragraph(child, parent)
        elif child.tag.endswith("}tbl"):
            yield Table(child, parent)


def _table_text(table: Table) -> str:
    rows = []
    for row in table.rows:
        cells = [cell.text.strip() for cell in row.cells]
        if any(cells):
            rows.append(" | ".join(cells))
    return "\n".join(rows)


def extract_docx_text(db: Session, resume: Resume) -> ResumeExtraction:
    if resume.file_type.lower() != "docx":
        raise DocxExtractionError("DOCX text extraction is only supported for DOCX resumes.")

    resume.status = "extracting_text"
    try:
        file_path = Path(resume.storage_path)
        if not file_path.is_file():
            raise DocxExtractionError("The stored DOCX file could not be found.")

        document = Document(file_path)
        blocks = []
        for block in _iter_blocks(document):
            if isinstance(block, Paragraph):
                if block.text.strip():
                    blocks.append(block.text)
            elif isinstance(block, Table):
                table_text = _table_text(block)
                if table_text:
                    blocks.append(table_text)

        raw_text = "\n".join(blocks)
        normalized_text = normalize_resume_text(raw_text)
        if not normalized_text:
            raise DocxExtractionError("No extractable text was found in this DOCX resume.")
    except DocxExtractionError as exc:
        record_extraction_failure(db, resume, str(exc))
        raise
    except Exception as exc:
        record_extraction_failure(db, resume, "The DOCX text could not be extracted.")
        raise DocxExtractionError("The DOCX text could not be extracted.") from exc

    extraction = get_extraction(db, resume.id)
    if extraction is None:
        extraction = ResumeExtraction(resume_id=resume.id)
        db.add(extraction)
    extraction.raw_text = raw_text
    extraction.normalized_text = normalized_text
    extraction.page_count = 0
    extraction.extraction_status = "text_extracted"
    extraction.error_message = None
    resume.status = "text_extracted"
    db.commit()
    db.refresh(extraction)
    return extraction