from collections.abc import Generator
from io import BytesIO
from types import SimpleNamespace
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient
from docx import Document
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import Base, get_db
from app.main import app
from app.services import resume as resume_service
from app.services.resume_validation import MAX_RESUME_SIZE


@pytest.fixture
def resume_client(tmp_path, monkeypatch) -> Generator[tuple[TestClient, object], None, None]:
    engine = create_engine(f"sqlite:///{tmp_path / 'resume-api.db'}")
    session_factory = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    storage_dir = tmp_path / "resumes"
    monkeypatch.setattr(
        resume_service,
        "get_settings",
        lambda: SimpleNamespace(resume_storage_dir=str(storage_dir)),
    )

    def override_get_db() -> Generator[Session, None, None]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client, storage_dir
    app.dependency_overrides.clear()
    engine.dispose()


DEFAULT_PASSWORD = "Password123"


def register_session(
    client: TestClient, email: str = "resume@example.com", full_name: str = "Resume Candidate"
) -> dict:
    response = client.post(
        "/api/auth/register",
        json={
            "full_name": full_name,
            "email": email,
            "password": DEFAULT_PASSWORD,
            "confirm_password": DEFAULT_PASSWORD,
        },
    )
    assert response.status_code == 201
    return response.json()


def create_profile(client: TestClient) -> int:
    return register_session(client)["profile"]["id"]


def valid_pdf() -> bytes:
    stream = b"BT /F1 12 Tf 72 720 Td (Resume Test) Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
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


def valid_docx() -> bytes:
    document = Document()
    output = BytesIO()
    document.save(output)
    return output.getvalue()


def arbitrary_zip() -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("random.txt", b"not a docx")
    return buffer.getvalue()


def test_uploads_pdf_and_docx_and_persists_metadata(resume_client) -> None:
    client, storage_dir = resume_client
    profile_id = create_profile(client)

    for filename, content_type, contents in [
        ("resume.pdf", "application/pdf", valid_pdf()),
        ("resume.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", valid_docx()),
    ]:
        response = client.post(
            f"/api/profiles/{profile_id}/resumes",
            files={"file": (filename, contents, content_type)},
        )
        assert response.status_code == 201
        record = response.json()
        assert record["candidate_profile_id"] == profile_id
        assert record["original_filename"] == filename
        assert record["file_type"] == filename.rsplit(".", 1)[1]
        assert record["file_size"] == len(contents)
        assert record["status"] == "uploaded"
        assert "storage_path" not in record
        stored_files = list(storage_dir.iterdir())
        assert len(stored_files) == 1 if filename.endswith(".pdf") else 2
        assert any(path.suffix == f".{record['file_type']}" and path.read_bytes() == contents for path in stored_files)

        retrieval = client.get(f"/api/resumes/{record['id']}")
        assert retrieval.status_code == 200
        assert retrieval.json() == record

    listed = client.get(f"/api/profiles/{profile_id}/resumes")
    assert listed.status_code == 200
    assert len(listed.json()) == 2


def test_resume_upload_rejects_missing_profile_empty_and_unsupported_files(resume_client) -> None:
    client, _ = resume_client
    profile_id = create_profile(client)

    missing_profile = client.post(
        "/api/profiles/999/resumes", files={"file": ("resume.pdf", b"bytes", "application/pdf")}
    )
    assert missing_profile.status_code == 404
    empty = client.post(
        f"/api/profiles/{profile_id}/resumes",
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )
    assert empty.status_code == 400

    unsupported = client.post(
        f"/api/profiles/{profile_id}/resumes",
        files={"file": ("resume.txt", b"bytes", "text/plain")},
    )
    assert unsupported.status_code == 400

    assert client.get("/api/resumes/999").status_code == 404


def test_rejects_mismatched_corrupt_and_oversized_uploads_without_persistence(resume_client) -> None:
    client, storage_dir = resume_client
    profile_id = create_profile(client)
    cases = [
        ("resume.txt", b"plain text", "text/plain"),
        ("renamed.pdf", b"plain text", "application/pdf"),
        ("renamed.docx", valid_pdf(), "application/octet-stream"),
        ("random.docx", arbitrary_zip(), "application/octet-stream"),
        ("corrupt.pdf", b"%PDF-1.7\ntruncated", "application/pdf"),
        ("corrupt.docx", b"not a zip", "application/octet-stream"),
        ("empty.pdf", b"", "application/pdf"),
        ("large.pdf", b"x" * (MAX_RESUME_SIZE + 1), "application/pdf"),
    ]

    for filename, contents, content_type in cases:
        response = client.post(
            f"/api/profiles/{profile_id}/resumes",
            files={"file": (filename, contents, content_type)},
        )
        assert response.status_code == 400

    assert not storage_dir.exists() or list(storage_dir.iterdir()) == []
    assert client.get(f"/api/profiles/{profile_id}/resumes").json() == []


def test_valid_files_allow_generic_mime_type(resume_client) -> None:
    client, storage_dir = resume_client
    profile_id = create_profile(client)

    response = client.post(
        f"/api/profiles/{profile_id}/resumes",
        files={"file": ("resume.pdf", valid_pdf(), "application/octet-stream")},
    )

    assert response.status_code == 201
    assert len(list(storage_dir.iterdir())) == 1


def test_resume_routes_require_authentication(resume_client) -> None:
    client, _ = resume_client
    profile_id = create_profile(client)
    upload = client.post(
        f"/api/profiles/{profile_id}/resumes",
        files={"file": ("resume.pdf", valid_pdf(), "application/pdf")},
    )
    resume_id = upload.json()["id"]
    client.post("/api/auth/logout")

    assert client.post(
        f"/api/profiles/{profile_id}/resumes",
        files={"file": ("resume.pdf", valid_pdf(), "application/pdf")},
    ).status_code == 401
    assert client.get(f"/api/resumes/{resume_id}").status_code == 401
    assert client.get(f"/api/profiles/{profile_id}/resumes").status_code == 401


def test_user_cannot_access_or_upload_to_another_users_profile_or_resume(resume_client) -> None:
    client, _ = resume_client
    profile_id = create_profile(client)
    upload = client.post(
        f"/api/profiles/{profile_id}/resumes",
        files={"file": ("resume.pdf", valid_pdf(), "application/pdf")},
    )
    resume_id = upload.json()["id"]

    with TestClient(app) as intruder_client:
        register_session(intruder_client, email="intruder@example.com", full_name="Intruder")

        assert intruder_client.get(f"/api/resumes/{resume_id}").status_code == 404
        assert intruder_client.get(f"/api/profiles/{profile_id}/resumes").status_code == 404
        assert intruder_client.post(
            f"/api/profiles/{profile_id}/resumes",
            files={"file": ("resume.pdf", valid_pdf(), "application/pdf")},
        ).status_code == 404
        assert intruder_client.post(f"/api/resumes/{resume_id}/extract-text").status_code == 404
        assert intruder_client.get(f"/api/resumes/{resume_id}/job-matches").status_code == 404

    # the owner's own access is unaffected by the intruder's attempts
    assert client.get(f"/api/resumes/{resume_id}").status_code == 200
