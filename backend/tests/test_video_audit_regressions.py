"""Regression tests for the final video-based quality audit.

Every resume here is synthetic. The defects reproduced:

1. Blank lines *inside* one project (DOCX resumes authored with an empty paragraph
   after each visual line, or a PDF page break mid-description) made every block's
   first line a "project", producing fragment projects such as "Built", "using
   Node, Express", "and MongoDB", "Developed" or "HTML," — with no parser warning.
2. Those fragment "projects" flowed into interview questions ('Walk me through the
   architecture of "HTML,"').
3. The grounding check reported "passed" while the resume structure was flagged as
   unreliable, and only checked job keywords and metric/leadership/years phrasing —
   not invented technologies, project names, degrees, employers or awards.
"""

import io
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from docx import Document
from fastapi.testclient import TestClient
from pypdf import PdfReader, PdfWriter

from app.models import ResumeSection
from app.schemas.customization import EvidenceRecord
from app.services.customization_llm import LLMRewriteResponse, validate_llm_response
from app.services.customization_validator import (
    build_evidence_corpus,
    build_validation_result,
    check_fabrication,
    check_unsupported_claims,
)
from app.services.docx_extraction import DocxExtractionError, extract_docx_text
from app.services.interview_evidence import ranked_projects
from app.services.interview_question_service import _technical_questions, clean_term, generate_questions
from app.services.job_dataset_service import load_job_postings
from app.services.pdf_extraction import PdfExtractionError, extract_pdf_text
from app.services.section_detection import detect_resume_sections
from app.services.structured_resume import (
    OUTDATED_PARSER_WARNING,
    PARSER_VERSION,
    _parser_warnings,
    build_structured_data,
    effective_parser_warnings,
    is_plausible_project_title,
)
from app.services.text_utils import normalize_resume_text
from pdf_line_fixture import pdf_from_lines
from test_resume_api import register_session, resume_client  # noqa: F401

JOBS = {job.job_id: job for job in load_job_postings()}
MERN_JOB_ID = "JOB-0051"  # MERN Stack Intern — required: JavaScript, HTML, CSS, Git
DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
FRAGMENTS = {"Built", "using", "and", "Developed", "HTML,", "CSS,", "JavaScript", "using Node, Express", "and MongoDB"}


def _structure(text: str) -> dict:
    detected = detect_resume_sections(normalize_resume_text(text))
    sections = [
        ResumeSection(resume_id=1, name=d.name, original_heading=d.original_heading, content=d.content, position=i)
        for i, d in enumerate(detected)
    ]
    data = build_structured_data(sections)
    data["parser_warnings"] = _parser_warnings(data)
    return data


def _docx_bytes(paragraphs: list[str]) -> bytes:
    document = Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    output = io.BytesIO()
    document.save(output)
    return output.getvalue()


def _extract_docx(tmp_path, paragraphs: list[str]) -> str:
    path = tmp_path / "synthetic.docx"
    path.write_bytes(_docx_bytes(paragraphs))
    extraction = extract_docx_text(MagicMock(), SimpleNamespace(id=1, file_type="docx", storage_path=str(path), status=""))
    return extraction.normalized_text


def _extract_pdf(tmp_path, pages: list[list[str]]) -> str:
    writer = PdfWriter()
    for lines in pages:
        for page in PdfReader(io.BytesIO(pdf_from_lines(lines))).pages:
            writer.add_page(page)
    path = tmp_path / "synthetic.pdf"
    with path.open("wb") as handle:
        writer.write(handle)
    extraction = extract_pdf_text(MagicMock(), SimpleNamespace(id=1, file_type="pdf", storage_path=str(path), status=""))
    return extraction.normalized_text


# --- 1. Resume parsing --------------------------------------------------------------


def test_docx_blank_paragraph_per_line_does_not_fragment_a_project(tmp_path) -> None:
    text = _extract_docx(tmp_path, [
        "Alex Sample", "PROJECTS", "Society Ledger App", "", "Built", "", "using Node, Express", "", "and MongoDB", "",
        "Developed", "", "a ledger for members, payments and loans.", "", "SKILLS", "HTML, CSS, JavaScript",
    ])
    data = _structure(text)
    assert [p["title"] for p in data["projects"]] == ["Society Ledger App"]
    description = data["projects"][0]["description"]
    assert "Built using Node, Express and MongoDB" in description
    assert "Developed a ledger for members, payments and loans." in description
    assert {"Express", "MongoDB"} <= set(data["projects"][0]["technologies"])
    assert data["parser_warnings"] == []


def test_pdf_page_break_inside_a_description_keeps_one_project(tmp_path) -> None:
    text = _extract_pdf(tmp_path, [
        ["Alex Sample", "PROJECTS", "Society Ledger App - Built using Node, Express and MongoDB", "Developed a full-stack ledger"],
        ["using HTML, CSS and MongoDB for members and loans.", "SKILLS", "HTML, CSS"],
    ])
    data = _structure(text)
    assert [p["title"] for p in data["projects"]] == ["Society Ledger App"]
    assert data["projects"][0]["description"] == "Developed a full-stack ledger using HTML, CSS and MongoDB for members and loans."


def test_split_technology_list_becomes_technologies_not_projects() -> None:
    data = _structure("Alex Sample\nPROJECTS\nSociety Ledger App\n\nHTML,\n\nCSS,\n\nJavaScript\n\nDeveloped a ledger for a housing society.")
    assert [p["title"] for p in data["projects"]] == ["Society Ledger App"]
    assert {"HTML", "CSS", "JavaScript"} <= set(data["projects"][0]["technologies"])
    assert not {p["title"] for p in data["projects"]} & FRAGMENTS


def test_project_titles_and_complete_descriptions_are_extracted() -> None:
    data = _structure(
        "ALEX SAMPLE\nalex.sample@example.com\n\nPROJECTS\n"
        "Society Ledger App — Built using Node, Express and MongoDB\n"
        "• Developed a full-stack ledger using HTML, CSS,\n"
        "JavaScript, Node.js, Express.js and MongoDB.\n"
        "• Designed REST APIs for members and loans.\n\n"
        "Storefront Demo — Built using HTML, CSS, JavaScript, React\n"
        "Developed an e-commerce web application with a product listing and cart.\n"
    )
    first, second = data["projects"]
    assert (first["title"], second["title"]) == ("Society Ledger App", "Storefront Demo")
    assert "JavaScript, Node.js, Express.js and MongoDB." in first["description"]
    assert "Designed REST APIs for members and loans." in first["description"]
    # The annotation's technologies survive (never overwritten by a later list) and
    # "Node" is canonicalized instead of duplicated next to "Node.js".
    assert first["technologies"][:3] == ["Node.js", "Express", "MongoDB"]
    assert "Node" not in first["technologies"]
    assert second["technologies"] == ["HTML", "CSS", "JavaScript", "React"]
    assert data["header"].startswith("ALEX SAMPLE")


def test_skills_section_is_not_mixed_with_project_descriptions() -> None:
    data = _structure(
        "Alex Sample\nSKILLS\nFrontend Development\nSQL Programming\nProblem Solving\n\n"
        "PROJECTS\nSociety Ledger App — Built using Node, Express and MongoDB\nDeveloped a ledger using React and Docker.\n"
    )
    assert data["skills"] == ["Frontend Development", "SQL", "Problem Solving"]
    assert not {"Node.js", "MongoDB", "React", "Docker", "Developed", "using"} & set(data["skills"])
    assert {"Node.js", "MongoDB", "React", "Docker"} <= set(data["projects"][0]["technologies"])


@pytest.mark.parametrize("heading", ["EXPERIENCE", "Work Experience", "EMPLOYMENT", "Internship Experience"])
def test_experience_sections_are_detected(heading: str) -> None:
    data = _structure(f"Alex Sample\n{heading}\nWeb Intern, Example Labs\n• Built dashboards in React.\nEDUCATION\nB.Tech Information Technology, 2028")
    entries = data["experience"] + data["internships"]
    assert len(entries) == 1 and "Web Intern, Example Labs" in entries[0]["raw_text"]
    assert data["education"][0]["degree"] == "B.Tech" and data["education"][0]["graduation_year"] == 2028


def test_resume_without_experience_heading_reports_no_experience_and_keeps_name() -> None:
    data = _structure("ALEX SAMPLE\nEDUCATION\nB.Tech Information Technology\n2024 - 2028\nSKILLS\nGit")
    assert data["experience"] == [] and data["internships"] == []
    assert [s["name"] for s in data["sections"]] == ["header", "education", "skills"]
    assert data["header"] == "ALEX SAMPLE"


def test_lone_bullet_glyph_lines_are_reattached() -> None:
    # pypdf decodes some fonts' bullet glyph as DEL (0x7F), on its own line.
    normalized = normalize_resume_text("PROJECTS\nLedger App\n\x7f\nBuilt dashboards in React.\n\nWrote tests.")
    assert "\x7f" not in normalized
    assert normalized.splitlines()[2:] == ["• Built dashboards in React.", "• Wrote tests."]


def test_empty_and_malformed_pdfs_fail_with_a_clear_error(tmp_path) -> None:
    blank = tmp_path / "blank.pdf"
    blank.write_bytes(pdf_from_lines([" "]))
    with pytest.raises(PdfExtractionError, match="No extractable text"):
        extract_pdf_text(MagicMock(), SimpleNamespace(id=1, file_type="pdf", storage_path=str(blank), status=""))
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"%PDF-1.4\nthis is not a real pdf body")
    with pytest.raises(PdfExtractionError, match="could not be extracted"):
        extract_pdf_text(MagicMock(), SimpleNamespace(id=1, file_type="pdf", storage_path=str(broken), status=""))


def test_whitespace_only_docx_fails_with_a_clear_error(tmp_path) -> None:
    with pytest.raises(DocxExtractionError, match="No extractable text"):
        _extract_docx(tmp_path, ["", "   ", ""])


def test_poorly_formatted_resume_with_missing_sections_does_not_crash() -> None:
    data = _structure("just some text with no headings at all")
    assert data["projects"] == [] and data["education"] == [] and data["experience"] == []
    assert data["header"] == "just some text with no headings at all"


def test_fragment_titles_raise_a_parser_warning_and_evidence_is_preserved() -> None:
    # The first block of a section has no previous project to join, so a fragment
    # there still becomes a project — and must be reported, not silently accepted.
    data = _structure("Alex Sample\nPROJECTS\nusing Node and Express\n\nLedger App\nDeveloped a ledger.")
    assert any(w.startswith("fragmented_project_titles") for w in data["parser_warnings"])
    assert data["sections"][1]["content"].startswith("using Node and Express")  # raw source evidence kept


@pytest.mark.parametrize("title,plausible", [
    ("Society Ledger App", True), ("E-commerce Management", True), ("React Portfolio Website", True),
    ("Built", False), ("using", False), ("and", False), ("HTML,", False), ("JavaScript", False),
    ("Node, Express and MongoDB", False), ("", False),
])
def test_project_title_plausibility(title: str, plausible: bool) -> None:
    assert is_plausible_project_title(title) is plausible


def test_results_from_an_older_parser_are_flagged_without_rewriting_them() -> None:
    stored = {"parser_warnings": [], "projects": [{"title": "using"}]}
    assert effective_parser_warnings(stored) == [OUTDATED_PARSER_WARNING]
    assert stored["parser_warnings"] == []
    assert effective_parser_warnings({"parser_warnings": [], "parser_version": PARSER_VERSION}) == []


# --- 2/3. Downstream consistency and interview quality ----------------------------


def _mern_resume() -> bytes:
    return _docx_bytes([
        "Alex Sample", "alex.sample@example.com",
        "EDUCATION", "Example Institute of Technology", "B.Tech Information Technology", "2024 - 2028",
        "PROJECTS", "Society Ledger App — Built using Node, Express and MongoDB", "",
        "Developed a full-stack ledger for a housing society using HTML, CSS,", "",
        "JavaScript, Node.js and MongoDB with REST APIs.", "",
        "Storefront Demo — Built using HTML, CSS, JavaScript, React",
        "Developed an e-commerce web application with a product listing and cart.",
        "SKILLS", "Frontend Development", "SQL Programming", "Problem Solving", "Git",
    ])


def test_same_resume_is_consistent_across_every_downstream_feature(resume_client) -> None:  # noqa: F811
    from app.services.job_matching import normalize_term

    client, _ = resume_client
    profile_id = register_session(client, email="trace@example.com", full_name="Alex Sample")["profile"]["id"]
    resume_id = client.post(f"/api/profiles/{profile_id}/resumes", files={"file": ("resume.docx", _mern_resume(), DOCX_TYPE)}).json()["id"]
    for step in ("extract-text", "detect-sections", "structure"):
        assert client.post(f"/api/resumes/{resume_id}/{step}").status_code == 200
    data = client.get(f"/api/resumes/{resume_id}/structured").json()["data"]

    titles = [p["title"] for p in data["projects"]]
    assert titles == ["Society Ledger App", "Storefront Demo"]
    assert data["parser_warnings"] == [] and data["parser_version"] == PARSER_VERSION
    assert data["skills"] == ["Frontend Development", "SQL", "Problem Solving", "Git"]
    evidenced = {normalize_term(t) for t in data["skills"]} | {normalize_term(t) for p in data["projects"] for t in p["technologies"]}
    assert {normalize_term(t) for t in ("Node.js", "MongoDB", "HTML", "CSS", "JavaScript", "React")} <= evidenced  # from projects, not the Skills section

    # Skill gap: every demonstrated strength is a skill/technology the resume evidences.
    gap = client.post(f"/api/resumes/{resume_id}/skill-gap", params={"job_id": MERN_JOB_ID}).json()
    strengths = {normalize_term(s["requirement"]) for s in gap["strengths"] if s["requirement_type"] in ("required_skill", "preferred_skill")}
    assert strengths and strengths <= evidenced

    # Customization: grounded, with no parser warning to hide, and only real skills/projects.
    customization = client.post(f"/api/resumes/{resume_id}/application-customizations", params={"job_id": MERN_JOB_ID}).json()
    assert customization["validation"]["passed"] is True and customization["parser_warning_notice"] is None
    assert set(customization["tailored_resume"]["skills"]) <= set(data["skills"])
    assert {p["title"] for p in customization["tailored_resume"]["projects"]} == set(titles)

    # Interview prep: project questions only about real projects, no malformed terms, no repeats.
    prep = client.post(f"/api/resumes/{resume_id}/interview-preparations", params={"job_id": MERN_JOB_ID}).json()
    questions = prep["questions"]
    project_questions = [q for q in questions if q["category"] == "project"]
    assert project_questions and all(any(f'"{t}"' in q["question"] for t in titles) for q in project_questions)
    assert not any(',"' in q["question"] or '",' in q["question"].replace('", ', '"') for q in questions)
    assert len({q["question"] for q in questions}) == len(questions)
    assert all(q["difficulty"] in ("easy", "medium", "hard") for q in questions)

    # Editing in an unsupported claim is re-validated, not left showing "passed".
    edited = client.patch(
        f"/api/resumes/{resume_id}/application-customizations/{customization['id']}",
        json={"summary": "Built production systems with Kubernetes and won a national hackathon."},
    ).json()
    assert edited["validation"]["passed"] is False and edited["status"] == "validation_warning"
    assert any(w.startswith("Edited text:") for w in edited["validation"]["warnings"])
    corrected = client.patch(
        f"/api/resumes/{resume_id}/application-customizations/{customization['id']}",
        json={"summary": "Information Technology student who built a full-stack ledger with Node.js and MongoDB."},
    ).json()
    assert corrected["validation"]["passed"] is True and not any(w.startswith("Edited text:") for w in corrected["validation"]["warnings"])


def _job(**updates):
    return JOBS[MERN_JOB_ID].model_copy(update=updates)


def _context(job, supported: set[str], evidence: list[EvidenceRecord] | None = None):
    return SimpleNamespace(job=job, supported_terms=supported, evidence_records=evidence or [])


def test_terms_are_punctuation_normalized() -> None:
    assert [clean_term(t) for t in ["HTML,", "CSS,", "'React'", "Node.js.", "C++", "CI/CD", " REST  APIs "]] == [
        "HTML", "CSS", "React", "Node.js", "C++", "CI/CD", "REST APIs",
    ]


def test_technical_questions_never_quote_malformed_or_duplicate_skills() -> None:
    job = _job(required_skills=["HTML,", "CSS,", "HTML", "JavaScript"], preferred_skills=["CSS", "React"])
    questions = _technical_questions(_context(job, supported=set()))
    text = " ".join(q.question + q.why_asked for q in questions)
    assert '"HTML,"' not in text and '"CSS,"' not in text
    assert sorted(s for q in questions for s in q.source_requirements) == ["CSS", "HTML", "JavaScript", "React"]
    assert all(q.category == "technical" for q in questions)


def test_near_duplicate_template_questions_are_merged() -> None:
    job = _job(required_skills=["SQL", "MongoDB"], preferred_skills=["PostgreSQL"])
    questions = _technical_questions(_context(job, supported=set()))
    schema_questions = [q for q in questions if "relational schema" in q.question]
    assert len(schema_questions) == 1
    assert schema_questions[0].source_requirements == ["SQL", "MongoDB", "PostgreSQL"]
    assert schema_questions[0].difficulty == "medium"  # required skills involved


def test_demonstrated_required_skill_gets_evidence_and_scenario_questions() -> None:
    evidence = [EvidenceRecord(
        evidence_id="EV-001", source_type="project", source_name="Society Ledger App",
        source_path="structured_resume.projects[0].raw_text", raw_text="Society Ledger App - Developed a ledger using JavaScript and HTML.",
        canonical_terms=["javascript", "html"], confidence_type="direct",
    )]
    job = _job(required_skills=["JavaScript", "HTML"], preferred_skills=[])
    questions = _technical_questions(_context(job, supported={"javascript", "html"}, evidence=evidence))
    evidence_questions = [q for q in questions if q.source_evidence_ids == ["EV-001"]]
    assert len(evidence_questions) == 1 and "JavaScript and HTML" in evidence_questions[0].question
    assert {q.difficulty for q in questions} == {"medium", "hard"}


def test_generic_scenario_questions_are_not_repeated_per_skill() -> None:
    job = _job(required_skills=["JavaScript", "HTML", "CSS"], preferred_skills=[])
    questions = _technical_questions(_context(job, supported={"javascript", "html", "css"}))
    scenarios = [q for q in questions if q.difficulty == "hard"]
    assert len(scenarios) == 1 and "JavaScript, HTML and CSS" in scenarios[0].question


def test_technology_listed_only_in_a_project_tech_stack_counts_as_project_evidence() -> None:
    evidence = [EvidenceRecord(
        evidence_id="EV-002", source_type="project", source_name="Storefront Demo",
        source_path="structured_resume.projects[1].raw_text", raw_text="Storefront Demo - Developed an e-commerce web application.",
        canonical_terms=["html", "css", "javascript", "react"], confidence_type="direct",
    )]
    job = _job(required_skills=[], preferred_skills=["React"])
    questions = _technical_questions(_context(job, supported={"react"}, evidence=evidence))
    assert questions[0].source_evidence_ids == ["EV-002"] and '"Storefront Demo"' in questions[0].question


def test_fragment_and_single_technology_projects_are_never_interview_topics() -> None:
    data = {"projects": [
        {"title": "HTML,", "description": "", "technologies": []},
        {"title": "using", "description": "", "technologies": []},
        {"title": "JavaScript", "description": "", "technologies": ["JavaScript"]},
        {"title": "Society Ledger App", "description": "A ledger.", "technologies": ["Node.js"]},
    ]}
    assert [p["title"] for p, _i, _s in ranked_projects(data, set(), set())] == ["Society Ledger App"]


def test_generated_question_list_has_no_repeats() -> None:
    question = SimpleNamespace(question="Tell me about yourself.")
    context = SimpleNamespace()
    import app.services.interview_question_service as service

    originals = {name: getattr(service, name) for name in ("_technical_questions", "_resume_questions", "_project_questions", "_role_questions", "_hr_questions", "_skill_gap_questions")}
    try:
        for name in originals:
            setattr(service, name, lambda _ctx: [question, SimpleNamespace(question="tell me about yourself")])
        assert len(generate_questions(context)) == 1
    finally:
        for name, original in originals.items():
            setattr(service, name, original)


# --- 5. Grounding / evidence validation ----------------------------------------------


EVIDENCE = [
    EvidenceRecord(evidence_id="EV-001", source_type="skill", source_name="Resume Skills Section", source_path="structured_resume.skills",
                   raw_text="Frontend Development, SQL, Git", canonical_terms=["sql", "git"], confidence_type="direct"),
    EvidenceRecord(evidence_id="EV-002", source_type="education", source_name="Resume Education Section", source_path="structured_resume.education[0].raw_text",
                   raw_text="Example Institute of Technology B.Tech Information Technology 2024 - 2028", canonical_terms=[], confidence_type="direct"),
    EvidenceRecord(evidence_id="EV-003", source_type="project", source_name="Society Ledger App", source_path="structured_resume.projects[0].raw_text",
                   raw_text="Society Ledger App - Developed a ledger using Node.js, Express and MongoDB.", canonical_terms=["node.js", "express", "mongodb"], confidence_type="direct"),
]
CORPUS = build_evidence_corpus(EVIDENCE, JOBS[MERN_JOB_ID])
OPPORTUNITY = (JOBS[MERN_JOB_ID].job_title, JOBS[MERN_JOB_ID].company)


@pytest.mark.parametrize("claim,reason", [
    ('I built "Chat Assistant Pro" for a client.', "project/title"),
    ("I deployed services with Kubernetes and Docker.", "technology"),
    ("I am completing an M.Tech in Data Science.", "qualification"),
    ("I worked at Globex Corporation on billing systems.", "employer"),
    ("My professional experience has prepared me for this role.", "experience"),
    ("I won first place at a national hackathon.", "achievement"),
])
def test_unsupported_claims_are_detected(claim: str, reason: str) -> None:
    hit = check_unsupported_claims(claim, CORPUS, OPPORTUNITY)
    assert hit is not None and reason in hit


@pytest.mark.parametrize("claim", [
    'I built "Society Ledger App" using Node.js, Express and MongoDB.',
    "As a B.Tech Information Technology student, I use SQL and Git.",
    "I am writing to express my interest in the MERN Stack Intern role at NovaByte Labs.",
    "I would be ready to learn quickly and go further with feedback.",
    f'This role involves "{JOBS[MERN_JOB_ID].responsibilities[0]}", which matches my project work.',
])
def test_supported_claims_pass(claim: str) -> None:
    assert check_unsupported_claims(claim, CORPUS, OPPORTUNITY) is None


def test_llm_rewrite_with_an_invented_technology_is_rejected() -> None:
    response = LLMRewriteResponse.model_validate({
        "summary": "Developer experienced with Kubernetes.", "summary_evidence_ids": ["EV-001"],
        "bullets": [{"source_path": "structured_resume.projects[0].raw_text", "rewritten_text": 'Led "Payments Gateway" at Initech.', "evidence_ids": ["EV-003"]}],
        "cover_letter_paragraphs": [{"text": "I hold a Ph.D in Computer Science.", "evidence_ids": []}],
    })
    violations = validate_llm_response(response, {"EV-001", "EV-003"}, {"structured_resume.projects[0].raw_text"}, set(), OPPORTUNITY, CORPUS)
    assert any("summary" in v and "Kubernetes" in v for v in violations)
    assert any("bullet" in v and "Payments Gateway" in v for v in violations)
    assert any("cover_letter_paragraphs[0]" in v and "Ph.D" in v for v in violations)


def test_corpus_checks_are_opt_in_for_existing_callers() -> None:
    assert check_fabrication("I deployed services with Kubernetes.", set()) is None
    assert check_fabrication("I deployed services with Kubernetes.", set(), (), CORPUS) is not None


def test_grounding_is_never_reported_passed_when_the_structure_is_unreliable() -> None:
    notice = "Resume structure contains parsing warnings. Review extracted profile before customization."
    assert build_validation_result([], [], [], [], parser_warning_notice=notice).passed is False
    assert build_validation_result([], [], [], [], parser_warning_notice=None).passed is True
