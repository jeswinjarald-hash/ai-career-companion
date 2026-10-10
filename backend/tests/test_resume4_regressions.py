"""Regression tests for the Resume_4.pdf failure seen in the latest recording.

Root cause (confirmed on the real file, reproduced here with a sanitized fixture):
the resume is a Google Docs (Skia) export. pypdf's default plain-mode extraction
emits a line break between *every word* of such PDFs, so the persisted raw text
was one word per paragraph and every capitalised word ("Society", "Finance",
"Management", ...) became its own "project". All names and wording below are
synthetic; only the layout pattern of the real file is kept.
"""

import io
import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from app.core.database import get_db
from app.main import app
from app.models import StructuredResume
from app.models import ResumeSection
from app.services.pdf_extraction import extract_pdf_text, is_word_fragmented
from app.services.section_detection import detect_resume_sections
from app.services.structured_resume import (
    OUTDATED_PARSER_WARNING,
    PARSER_VERSION,
    _parser_warnings,
    build_structured_data,
    effective_parser_warnings,
    excluded_projects_sentence,
    is_reliable_project,
)
from app.services.text_utils import normalize_resume_text
from pdf_line_fixture import pdf_from_lines
from skia_pdf_fixture import MAIN_COLUMN, SIDEBAR, skia_style_pdf
from test_resume_api import register_session, resume_client  # noqa: F401

PROJECT_TITLES = ["Community Ledger Portal", "Online Store Manager"]
FRAGMENT_WORDS = {"Community", "Ledger", "Portal", "Online", "Store", "Manager", "Built", "using", "and", "Developed", "HTML,", "MongoDB"}
MERN_JOB_ID = "JOB-0051"


def _skia_pdf() -> bytes:
    return skia_style_pdf(MAIN_COLUMN, SIDEBAR)


def _extract(tmp_path, content: bytes) -> str:
    path = tmp_path / "sanitized.pdf"
    path.write_bytes(content)
    return extract_pdf_text(MagicMock(), SimpleNamespace(id=1, file_type="pdf", storage_path=str(path), status="")).normalized_text


def _structure(text: str) -> dict:
    detected = detect_resume_sections(text)
    sections = [ResumeSection(resume_id=1, name=d.name, original_heading=d.original_heading, content=d.content, position=i) for i, d in enumerate(detected)]
    data = build_structured_data(sections)
    data["parser_warnings"] = _parser_warnings(data)
    return data


# --- Stage 1: PDF extraction ------------------------------------------------------


def test_pypdf_plain_mode_still_fragments_skia_pdfs_documenting_the_root_cause() -> None:
    plain = PdfReader(io.BytesIO(_skia_pdf())).pages[0].extract_text()
    if not is_word_fragmented(plain):
        pytest.skip("pypdf no longer fragments Skia-style PDFs; the rebuild fallback is then unused")
    # Before the fix this one-word-per-line text was persisted verbatim.
    before = _structure(normalize_resume_text(plain))
    assert any(project["title"] in FRAGMENT_WORDS for project in before["projects"])


def test_extraction_rebuilds_lines_from_glyph_positions(tmp_path) -> None:
    text = _extract(tmp_path, _skia_pdf())
    assert not is_word_fragmented(text)
    assert "Community Ledger Portal — Built using Node,Express and\nMongoDB" in text
    assert "Developed a full-stack Community Ledger Portal independently\nusing HTML, CSS" in text
    # Column order is preserved: the sidebar is not interleaved into the main column.
    assert text.index("checkout.") < text.index("SKILLS") < text.index("LANGUAGES")


def test_normally_extracted_pdfs_are_not_rebuilt(tmp_path) -> None:
    lines = ["Alex Sample", "PROJECTS", "Ledger App - Built using Node, Express and MongoDB", "Developed a ledger for members."] * 6
    plain = PdfReader(io.BytesIO(pdf_from_lines(lines))).pages[0].extract_text()
    assert _extract(tmp_path, pdf_from_lines(lines)) == normalize_resume_text(plain)


# --- Stage 2/3: sections and structured projects -----------------------------------


def test_sanitized_resume_structures_exactly_like_the_reviewed_ground_truth(tmp_path) -> None:
    data = _structure(_extract(tmp_path, _skia_pdf()))
    assert [s["name"] for s in data["sections"]] == ["header", "education", "projects", "skills", "certifications", "languages"]
    assert [p["title"] for p in data["projects"]] == PROJECT_TITLES
    ledger, store = data["projects"]
    assert ledger["technologies"][:3] == ["Node.js", "Express", "MongoDB"]
    assert ledger["description"].startswith("Developed a full-stack Community Ledger Portal independently using HTML, CSS")
    assert ledger["description"].endswith("manage members, payments, expenses and loans.")
    assert store["technologies"][:4] == ["HTML", "CSS", "JavaScript", "React"]
    assert data["education"][0]["graduation_year"] == 2028
    assert data["skills"] == ["Frontend Development", "SQL", "OOP"]
    assert [c["raw_text"] for c in data["certifications"]] == ["ONLINE CERTIFIED IN JAVA PROGRAMME", "Completed Course on Data Visualization using Python"]
    assert [entry["raw_text"] for entry in data["languages"]] == ["ENGLISH", "FRENCH"]
    assert data["experience"] == [] and data["internships"] == []
    assert data["parser_warnings"] == []


@pytest.mark.parametrize("content_line", ["JUNE 2024 - JUNE 2028", "(OOP)", "ONLINE CERTIFIED IN", "PROGRAMME"])
def test_capitalised_content_is_not_mistaken_for_a_section_heading(content_line: str) -> None:
    text = f"Alex Sample\nEDUCATION\nB.Tech Information Technology\n{content_line}\nPROJECTS\nLedger App - Built using React\nA ledger."
    assert [s.name for s in detect_resume_sections(text)] == ["header", "education", "projects"]


def test_language_and_certificate_lines_in_capitals_stay_in_their_sections() -> None:
    text = "Alex Sample\nADDITIONAL\n\nONLINE CERTIFIED IN JAVA\nPROGRAMME\n\nLANGUAGES\n\nENGLISH\n\nFRENCH"
    sections = detect_resume_sections(text)
    assert [s.name for s in sections] == ["header", "certifications", "languages"]


def test_a_genuine_unrecognised_capitalised_heading_is_still_detected() -> None:
    sections = detect_resume_sections("Alex Sample\nPROJECTS\nLedger App\n\nVOLUNTEERING\nTaught weekend coding classes.")
    assert [s.name for s in sections] == ["header", "projects", "custom"]


def test_ligatures_are_expanded() -> None:
    assert normalize_resume_text("ﬁnancial and efﬁcient ﬂows") == "financial and efficient flows"


@pytest.mark.parametrize("project,reliable", [
    ({"title": "Community Ledger Portal", "description": "A ledger.", "technologies": []}, True),
    ({"title": "Career Companion API", "description": "", "technologies": []}, True),  # title-only listing
    ({"title": "Community", "description": "", "technologies": []}, False),
    ({"title": "Portal", "description": "", "technologies": []}, False),
    ({"title": "Built using Developed a full-stack portal", "description": "", "technologies": []}, False),
    ({"title": "HTML,", "description": "", "technologies": []}, False),
    ({"title": "", "description": "A ledger app.", "technologies": []}, True),
    ("not a dict", False),
])
def test_project_reliability(project, reliable: bool) -> None:
    assert is_reliable_project(project) is reliable


# --- Stage 4/5: persistence, API and downstream evidence ---------------------------


def _upload_pdf(client: TestClient, email: str, content: bytes) -> tuple[int, int]:
    profile_id = register_session(client, email=email, full_name="Sample Person")["profile"]["id"]
    upload = client.post(f"/api/profiles/{profile_id}/resumes", files={"file": ("sanitized.pdf", content, "application/pdf")})
    assert upload.status_code == 201, upload.text
    resume_id = upload.json()["id"]
    for step in ("extract-text", "detect-sections", "structure"):
        assert client.post(f"/api/resumes/{resume_id}/{step}").status_code == 200
    return profile_id, resume_id


def test_fresh_upload_is_persisted_and_served_with_the_current_parser(resume_client) -> None:  # noqa: F811
    client, _ = resume_client
    _profile_id, resume_id = _upload_pdf(client, "fresh@example.com", _skia_pdf())
    data = client.get(f"/api/resumes/{resume_id}/structured").json()["data"]
    assert data["parser_version"] == PARSER_VERSION and data["parser_warnings"] == []
    assert [p["title"] for p in data["projects"]] == PROJECT_TITLES

    # Recommendation reasoning and customization project cards cite only real projects.
    matches = client.get(f"/api/resumes/{resume_id}/job-matches", params={"top_k": 10}).json()
    reasoning = " ".join(m["reasoning"] + " ".join(m.get("relevant_projects", []) or []) for m in matches)
    assert not any(f"'{word}'" in reasoning or f'"{word}"' in reasoning for word in FRAGMENT_WORDS)
    customization = client.post(f"/api/resumes/{resume_id}/application-customizations", params={"job_id": MERN_JOB_ID}).json()
    assert [p["title"] for p in customization["tailored_resume"]["projects"]] == PROJECT_TITLES or \
        sorted(p["title"] for p in customization["tailored_resume"]["projects"]) == sorted(PROJECT_TITLES)
    assert customization["parser_warning_notice"] is None and customization["validation"]["passed"] is True


def _plant_stale_fragmented_record(client: TestClient, resume_id: int, with_other_evidence: bool = True) -> None:
    """Replaces the stored structure with the sanitized shape of the stored v2
    record observed for resume 18: single-word title fragments, one prose fragment
    title, plus the two real projects lost inside them."""
    stale = {
        "parser_version": 2, "parser_warnings": ["many_single_word_project_titles: [...]"], "header": "SAMPLE PERSON",
        "skills": ["Frontend Development", "SQL"] if with_other_evidence else [],
        "education": [{"degree": "B.Tech", "graduation_year": 2028, "raw_text": "Example Institute B.Tech Information Technology 2024 - 2028"}] if with_other_evidence else [],
        "experience": [], "internships": [],
        "certifications": [{"raw_text": "ONLINE CERTIFIED IN JAVA PROGRAMME"}] if with_other_evidence else [],
        "achievements": [], "qualifications": [], "interests": [], "learning": [], "languages": [],
        "summary": None, "sections": [],
        "projects": [
            {"title": "Community", "description": "", "technologies": [], "raw_text": "Community"},
            {"title": "Ledger", "description": "", "technologies": [], "raw_text": "Ledger"},
            {"title": "Portal", "description": "", "technologies": [], "raw_text": "Portal"},
            {"title": "Built using Developed a full-stack Community Ledger Portal", "description": "", "technologies": ["Node.js", "MongoDB"],
             "raw_text": "Built using Developed a full-stack Community Ledger Portal"},
            {"title": "Online", "description": "", "technologies": [], "raw_text": "Online"},
        ],
    }
    session = next(app.dependency_overrides[get_db]())
    record = session.query(StructuredResume).filter(StructuredResume.resume_id == resume_id).one()
    record.data = stale
    session.commit()
    session.close()


def test_stale_fragmented_record_is_flagged_and_never_used_as_project_evidence(resume_client) -> None:  # noqa: F811
    client, _ = resume_client
    _profile_id, resume_id = _upload_pdf(client, "stale@example.com", _skia_pdf())
    _plant_stale_fragmented_record(client, resume_id)

    served = client.get(f"/api/resumes/{resume_id}/structured").json()["data"]
    assert OUTDATED_PARSER_WARNING in served["parser_warnings"]  # warning propagated through the API
    assert len(served["projects"]) == 5  # source records are preserved, not deleted

    matches = client.get(f"/api/resumes/{resume_id}/job-matches", params={"top_k": 10}).json()
    for match in matches:
        assert not (set(match.get("relevant_projects", []) or []) & {"Community", "Ledger", "Portal", "Online"})
        assert "Built using Developed" not in match["reasoning"]

    customization = client.post(f"/api/resumes/{resume_id}/application-customizations", params={"job_id": MERN_JOB_ID}).json()
    assert customization["tailored_resume"]["projects"] == []  # no project comparison cards from fragments
    assert all(e["source_type"] != "project" for e in customization["evidence"])
    assert customization["validation"]["passed"] is False and customization["status"] == "validation_warning"
    assert "5 extracted project entries looked like parsing fragments" in customization["parser_warning_notice"]

    prep = client.post(f"/api/resumes/{resume_id}/interview-preparations", params={"job_id": MERN_JOB_ID}).json()
    assert not [q for q in prep["questions"] if q["category"] == "project"]
    assert prep["validation"]["passed"] is False


def test_generation_refuses_when_only_fragment_projects_remain(resume_client) -> None:  # noqa: F811
    client, _ = resume_client
    _profile_id, resume_id = _upload_pdf(client, "fragments-only@example.com", _skia_pdf())
    _plant_stale_fragmented_record(client, resume_id, with_other_evidence=False)
    response = client.post(f"/api/resumes/{resume_id}/application-customizations", params={"job_id": MERN_JOB_ID})
    # Fragments are not evidence, so nothing is generated from them — an explicit
    # refusal instead of materials built on parsing debris.
    assert response.status_code == 409
    assert "Not enough grounded evidence" in response.json()["detail"]


def test_excluded_project_sentence_counts_only_unreliable_records() -> None:
    data = {"projects": [{"title": "Community", "description": "", "technologies": []}, {"title": "Ledger App", "description": "A ledger.", "technologies": []}]}
    assert excluded_projects_sentence(data).startswith(" 1 extracted project entry looked like parsing fragments and was not used")
    assert excluded_projects_sentence({"projects": []}) == ""
    assert effective_parser_warnings({"parser_version": PARSER_VERSION, "parser_warnings": []}) == []


# --- Skill Gap "couldn't connect" error path ---------------------------------------


def test_unexpected_server_error_keeps_cors_headers_and_is_logged(caplog) -> None:
    @app.get("/__test_unexpected_error")
    def _boom() -> None:
        raise RuntimeError("synthetic failure")

    try:
        client = TestClient(app, raise_server_exceptions=False)
        with caplog.at_level(logging.ERROR, logger="app.main"):
            response = client.get("/__test_unexpected_error", headers={"Origin": "http://localhost:5173"})
        # Without CORS headers the browser blocks the 500 and the frontend can only
        # report a network failure ("We couldn't connect to the skill gap service").
        assert response.status_code == 500 and response.json() == {"detail": "Internal server error"}
        assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
        assert any("unhandled_request_error" in record.getMessage() for record in caplog.records)
    finally:
        app.router.routes = [route for route in app.router.routes if getattr(route, "path", "") != "/__test_unexpected_error"]


# --- DOCX template layouts and unusual characters ----------------------------------


def test_docx_header_and_text_box_sidebar_are_extracted_once(tmp_path) -> None:
    from docx_layout_fixture import docx_with_header_and_sidebar

    from app.services.docx_extraction import extract_docx_text

    path = tmp_path / "template.docx"
    path.write_bytes(docx_with_header_and_sidebar(
        ["ALEX MORGAN", "alex.morgan@example.com"],
        ["EDUCATION", "B.Tech Computer Science, 2027", "PROJECTS", "Ledger App - Built using React", "Developed a ledger for members."],
        ["SKILLS", "Python", "SQL", "LANGUAGES", "English"],
    ))
    text = extract_docx_text(MagicMock(), SimpleNamespace(id=1, file_type="docx", storage_path=str(path), status="")).normalized_text
    assert text.startswith("ALEX MORGAN\nalex.morgan@example.com")
    assert text.count("Python") == 1  # the VML fallback copy of the text box is not duplicated
    data = _structure(text)
    assert data["skills"] == ["Python", "SQL"]
    assert [entry["raw_text"] for entry in data["languages"]] == ["English"]
    assert [p["title"] for p in data["projects"]] == ["Ledger App"]
    assert data["header"].startswith("ALEX MORGAN")


def test_invisible_and_non_breaking_characters_are_normalized() -> None:
    raw = "Node\u200b.js\u00a0and\u202fJava\u00adScript\ufeff with\u2009React"
    assert normalize_resume_text(raw) == "Node.js and JavaScript with React"
    data = _structure(normalize_resume_text("Alex Sample\nSKILLS\nNode​.js, Java­Script, React"))
    assert {"Node.js", "JavaScript", "React"} <= set(data["skills"])


def test_results_structured_by_parser_v3_are_reported_as_outdated() -> None:
    assert PARSER_VERSION >= 4
    assert effective_parser_warnings({"parser_version": 3, "parser_warnings": []}) == [OUTDATED_PARSER_WARNING]


def test_assistant_profile_summary_reasons_from_project_technologies() -> None:
    from app.services.assistant_handlers import handle_profile_summary
    from app.services.job_dataset_service import load_job_postings

    job = next(j for j in load_job_postings() if j.job_id == MERN_JOB_ID)
    structured = SimpleNamespace(data={"skills": ["SQL"], "projects": [
        {"title": "Community", "description": "", "technologies": []},  # a fragment: never mentioned
        {"title": "Online Store Manager", "description": "A store.", "technologies": ["HTML", "React"]},
        {"title": "Community Ledger Portal", "description": "A ledger.", "technologies": ["Node.js", "MongoDB", "JavaScript", "HTML"]},
    ]})
    ctx = SimpleNamespace(structured=structured, profile=None, job=job, resume=SimpleNamespace(id=7))
    result = handle_profile_summary(MagicMock(), 1, ctx, "Which of my projects is most relevant?")
    facts = result.facts
    assert [p["title"] for p in facts["projects"]] == ["Online Store Manager", "Community Ledger Portal"]
    assert facts["projects"][1]["technologies"] == ["Node.js", "MongoDB", "JavaScript", "HTML"]
    assert facts["most_relevant_project_for_selected_role"]["title"] == "Community Ledger Portal"
    text = result.message
    assert '"Community Ledger Portal" is your most relevant project' in text and "Community," not in text
