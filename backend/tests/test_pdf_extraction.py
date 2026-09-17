from io import BytesIO

from fastapi.testclient import TestClient
from pypdf import PdfWriter

from test_resume_api import create_profile, resume_client, valid_docx, valid_pdf
from app.services.text_utils import normalize_resume_text


def pdf_with_pages(texts: list[str]) -> bytes:
    page_ids = list(range(3, 3 + len(texts)))
    content_ids = list(range(3 + len(texts), 3 + len(texts) * 2))
    font_id = content_ids[-1] + 1
    objects = [
        f"<< /Type /Catalog /Pages 2 0 R >>".encode(),
        f"<< /Type /Pages /Kids [{ ' '.join(f'{page_id} 0 R' for page_id in page_ids) }] /Count {len(texts)} >>".encode(),
    ]
    for page_id, content_id in zip(page_ids, content_ids):
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>".encode()
        )
    for text in texts:
        stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
        objects.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    content = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(content))
        content.extend(f"{index} 0 obj\n".encode())
        content.extend(obj)
        content.extend(b"\nendobj\n")
    xref_offset = len(content)
    content.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    content.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        content.extend(f"{offset:010d} 00000 n \n".encode())
    content.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode()
    )
    return bytes(content)


def blank_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_normalization_preserves_meaningful_lines() -> None:
    normalized = normalize_resume_text("Name   Candidate\r\n\r\n\r\nSkills\t Python\x00")

    assert normalized == "Name Candidate\n\nSkills Python"


def upload(client: TestClient, profile_id: int, filename: str, contents: bytes, content_type: str):
    response = client.post(
        f"/api/profiles/{profile_id}/resumes",
        files={"file": (filename, contents, content_type)},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_extracts_and_persists_single_page_pdf(resume_client) -> None:
    client, _ = resume_client
    resume = upload(client, create_profile(client), "resume.pdf", valid_pdf(), "application/pdf")

    response = client.post(f"/api/resumes/{resume['id']}/extract-text")
    assert response.status_code == 200
    extraction = response.json()
    assert extraction["resume_id"] == resume["id"]
    assert extraction["status"] == "text_extracted"
    assert extraction["page_count"] == 1
    assert "Resume Test" in extraction["normalized_text"]
    assert extraction["character_count"] == len(extraction["normalized_text"])

    assert client.get(f"/api/resumes/{resume['id']}").json()["status"] == "text_extracted"
    assert client.get(f"/api/resumes/{resume['id']}/extraction").json() == extraction


def test_extracts_all_pages_and_is_idempotent(resume_client) -> None:
    client, _ = resume_client
    resume = upload(
        client,
        create_profile(client),
        "multi-page.pdf",
        pdf_with_pages(["First Page", "Second Page"]),
        "application/pdf",
    )

    first = client.post(f"/api/resumes/{resume['id']}/extract-text")
    second = client.post(f"/api/resumes/{resume['id']}/extract-text")
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert second.json()["page_count"] == 2
    assert "First Page" in second.json()["normalized_text"]
    assert "Second Page" in second.json()["normalized_text"]


def test_image_only_pdf_fails_cleanly_and_persists_failure(resume_client) -> None:
    client, _ = resume_client
    resume = upload(client, create_profile(client), "scanned.pdf", blank_pdf(), "application/pdf")

    response = client.post(f"/api/resumes/{resume['id']}/extract-text")
    assert response.status_code == 400
    assert "Scanned-image" in response.json()["detail"]

    extraction = client.get(f"/api/resumes/{resume['id']}/extraction")
    assert extraction.status_code == 200
    assert extraction.json()["status"] == "extraction_failed"
    assert client.get(f"/api/resumes/{resume['id']}").json()["status"] == "extraction_failed"


def test_docx_and_missing_resume_are_rejected(resume_client) -> None:
    client, _ = resume_client
    resume = upload(
        client,
        create_profile(client),
        "resume.docx",
        valid_docx(),
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    response = client.post(f"/api/resumes/{resume['id']}/extract-text")
    assert response.status_code == 400
    assert "No extractable text" in response.json()["detail"]
    assert client.get(f"/api/resumes/{resume['id']}/extraction").json()["status"] == "extraction_failed"
    assert client.post("/api/resumes/999/extract-text").status_code == 404
    assert client.get("/api/resumes/999/extraction").status_code == 404
