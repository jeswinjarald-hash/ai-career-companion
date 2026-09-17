from app.services.section_detection import detect_resume_sections
from test_docx_extraction import docx_bytes, upload_docx
from test_pdf_extraction import pdf_with_pages
from test_resume_api import create_profile, resume_client


def test_detector_maps_aliases_and_preserves_order() -> None:
    text = """Candidate Name
candidate@example.com
Chennai

PROFESSIONAL SUMMARY
Backend developer.

Key Skills
Python

Academic Qualifications
B.Tech

Work History
Built APIs.

Academic Projects
Project A

Awards & Achievements
Won award.

Certifications & Courses
Cloud course.
"""

    sections = detect_resume_sections(text)
    assert [section.name for section in sections] == [
        "header", "summary", "skills", "education", "experience", "projects", "achievements", "certifications"
    ]
    assert sections[0].content.startswith("Candidate Name")
    assert sections[1].original_heading == "PROFESSIONAL SUMMARY"
    assert sections[3].content == "B.Tech"


def test_detector_avoids_prose_and_preserves_repeated_and_unknown_sections() -> None:
    text = """My experience includes Python and Java.
Projects helped me improve my technical skills.

PROJECTS
Project A

ACADEMIC PROJECTS
Project B

LEADERSHIP
Led a student team.
"""

    sections = detect_resume_sections(text)
    assert [section.name for section in sections] == ["header", "projects", "projects", "custom"]
    assert sections[0].content.startswith("My experience")
    assert sections[1].content == "Project A"
    assert sections[2].content == "Project B"
    assert sections[3].original_heading == "LEADERSHIP"
    assert sections[3].content == "Led a student team."


def test_detector_without_headings_preserves_all_text() -> None:
    sections = detect_resume_sections("Candidate Name\nPython developer with API experience.")

    assert len(sections) == 1
    assert sections[0].name == "header"
    assert "Python developer" in sections[0].content


def test_pdf_sections_are_detected_and_reprocessing_is_idempotent(resume_client) -> None:
    client, _ = resume_client
    profile_id = create_profile(client)
    upload = client.post(
        f"/api/profiles/{profile_id}/resumes",
        files={"file": ("sections.pdf", pdf_with_pages(["TECHNICAL SKILLS\\nPython\\n\\nEDUCATION\\nB.Tech"]), "application/pdf")},
    )
    assert upload.status_code == 201
    resume_id = upload.json()["id"]
    assert client.post(f"/api/resumes/{resume_id}/extract-text").status_code == 200

    first = client.post(f"/api/resumes/{resume_id}/detect-sections")
    second = client.post(f"/api/resumes/{resume_id}/detect-sections")
    assert first.status_code == 200
    assert second.status_code == 200
    assert [item["name"] for item in second.json()["sections"]] == ["skills", "education"]
    assert len(second.json()["sections"]) == 2
    assert [item["content"] for item in first.json()["sections"]] == [
        item["content"] for item in second.json()["sections"]
    ]
    assert client.get(f"/api/resumes/{resume_id}/sections").json() == second.json()


def test_docx_sections_use_same_detector(resume_client) -> None:
    client, _ = resume_client
    profile_id = create_profile(client)
    upload = upload_docx(client, profile_id, docx_bytes(with_table=False, with_text=True))
    resume_id = upload["id"]
    assert client.post(f"/api/resumes/{resume_id}/extract-text").status_code == 200

    response = client.post(f"/api/resumes/{resume_id}/detect-sections")
    assert response.status_code == 200
    sections = response.json()["sections"]
    assert sections[0]["name"] == "header"
    assert "Candidate Name" in sections[0]["content"]


def test_detection_requires_extraction_and_missing_resume_is_404(resume_client) -> None:
    client, _ = resume_client
    profile_id = create_profile(client)
    upload = upload_docx(client, profile_id, docx_bytes(with_table=False, with_text=True))
    resume_id = upload["id"]

    assert client.post(f"/api/resumes/{resume_id}/detect-sections").status_code == 409
    assert client.get(f"/api/resumes/{resume_id}/sections").status_code == 404
    assert client.post("/api/resumes/999/detect-sections").status_code == 404
    assert client.get("/api/resumes/999/sections").status_code == 404
