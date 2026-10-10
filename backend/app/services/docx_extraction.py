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


_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_MC_FALLBACK = "{http://schemas.openxmlformats.org/markup-compatibility/2006}Fallback"


def _paragraph_text(p_element) -> str:
    return "".join(node.text or "" for node in p_element.iter(f"{{{_W_NS}}}t"))


def _textbox_lines(paragraph: Paragraph) -> list[str]:
    """Text held in floating text boxes anchored to this paragraph.

    python-docx's ``Paragraph.text`` never includes it, so two-column templates
    (sidebar in a text box) lost their whole sidebar. Word stores each text box
    twice — the modern drawing and a VML fallback copy — so fallback copies are
    skipped to avoid duplicating the content.
    """
    lines: list[str] = []
    for content in paragraph._p.iter(f"{{{_W_NS}}}txbxContent"):
        if any(ancestor.tag == _MC_FALLBACK for ancestor in content.iterancestors()):
            continue
        for p_element in content.iter(f"{{{_W_NS}}}p"):
            lines.append(_paragraph_text(p_element))
    return lines


def _header_lines(document: DocumentObject) -> list[str]:
    """Page-header paragraphs (many templates put the name and contact details
    there), each distinct header once, ahead of the body."""
    lines: list[str] = []
    seen: set[str] = set()
    for section in document.sections:
        header = section.header
        if header.is_linked_to_previous and lines:
            continue
        for paragraph in header.paragraphs:
            text = paragraph.text.strip()
            if text and text not in seen:
                seen.add(text)
                lines.append(text)
    return lines


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
        blocks = _header_lines(document)
        if blocks:
            blocks.append("")
        for block in _iter_blocks(document):
            if isinstance(block, Paragraph):
                # A blank paragraph is kept as an empty line rather than dropped: it is
                # the author's own visual separator between entries (e.g. between two
                # projects), and downstream section-aware parsers rely on that blank
                # line as a structural boundary signal. `normalize_resume_text` already
                # collapses any resulting run of 3+ blank lines down to one, so this
                # cannot reintroduce excessive whitespace.
                if block.text.strip() or blocks:
                    blocks.append(block.text)
                textbox_lines = _textbox_lines(block)
                if textbox_lines:
                    # A floating text box (a two-column template's sidebar) is its
                    # own block of content, separated from the surrounding flow.
                    blocks.extend(["", *textbox_lines, ""])
            elif isinstance(block, Table):
                table_text = _table_text(block)
                if table_text:
                    blocks.append(table_text)
        while blocks and not blocks[-1].strip():
            blocks.pop()

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