from io import BytesIO
from pathlib import Path
from typing import BinaryIO
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from pypdf import PdfReader


SUPPORTED_EXTENSIONS = {".pdf", ".docx"}
MAX_RESUME_SIZE = 10 * 1024 * 1024
_GENERIC_MIME_TYPES = {"", "application/octet-stream", "binary/octet-stream"}
_EXPECTED_MIME_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class ResumeValidationError(Exception):
    pass


def validate_resume_upload(filename: str, mime_type: str | None, content: bytes) -> str:
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise ResumeValidationError("Unsupported resume format. Upload a PDF or DOCX file.")
    if not content:
        raise ResumeValidationError("The resume file must not be empty.")
    if len(content) > MAX_RESUME_SIZE:
        raise ResumeValidationError("The resume file exceeds the maximum allowed size of 10 MiB.")

    normalized_mime_type = (mime_type or "").lower().split(";", 1)[0].strip()
    expected_mime_type = _EXPECTED_MIME_TYPES[extension]
    if normalized_mime_type not in _GENERIC_MIME_TYPES and normalized_mime_type != expected_mime_type:
        raise ResumeValidationError("The uploaded MIME type does not match the file extension.")

    if extension == ".pdf":
        validate_pdf(content)
    else:
        validate_docx(content)
    return extension.removeprefix(".")


def validate_pdf(content: bytes) -> None:
    if not content.startswith(b"%PDF-"):
        raise ResumeValidationError("The file extension does not match the uploaded file content.")
    try:
        reader = PdfReader(BytesIO(content), strict=True)
        len(reader.pages)
    except Exception as exc:
        raise ResumeValidationError("The uploaded file is not a valid PDF.") from exc


def validate_docx(content: bytes) -> None:
    try:
        with ZipFile(BytesIO(content)) as archive:
            names = set(archive.namelist())
            required_entries = {"[Content_Types].xml", "word/document.xml"}
            if not required_entries.issubset(names):
                raise ResumeValidationError("The uploaded DOCX file is corrupted or invalid.")
            for entry in required_entries:
                ElementTree.parse(archive.open(entry))
    except ResumeValidationError:
        raise
    except (BadZipFile, KeyError, ElementTree.ParseError, OSError, ValueError) as exc:
        raise ResumeValidationError("The uploaded DOCX file is corrupted or invalid.") from exc
