from app.models import ResumeSection
from app.services.structured_resume import _education, _projects, _skills, build_structured_data
from app.services.text_utils import normalize_resume_text


def section(name: str, content: str, position: int = 0) -> ResumeSection:
    return ResumeSection(name=name, original_heading=None, content=content, position=position)


# ---------------------------------------------------------------------------
# Projects: unbulleted, wrapped PDF-style text (no bullet glyph survived at all,
# only the original indentation, and a mid-sentence line wrap with no marker).
# ---------------------------------------------------------------------------

UNBULLETED_PROJECTS = """AI Career Companion - Resume and Job Matching Platform
 Built a FastAPI backend that processes resumes, structures skills, education, experience and projects, and exposes REST
endpoints.
 Implemented PostgreSQL-backed data handling, API validation, error handling and automated backend tests.
 Used Python, FastAPI, SQL, PostgreSQL, REST APIs, Git and Postman.
Student Placement Prediction - Machine Learning Project
 Cleaned and analyzed student data with Pandas and NumPy, trained classification models using Scikit-learn, and compared
accuracy, precision and recall.
 Created visualizations with Matplotlib and documented model evaluation results and limitations."""


def test_unbulleted_wrapped_projects_stay_two_projects_with_correct_descriptions() -> None:
    projects = _projects([section("projects", UNBULLETED_PROJECTS)])

    assert len(projects) == 2
    first, second = projects
    assert first["title"] == "AI Career Companion - Resume and Job Matching Platform"
    assert second["title"] == "Student Placement Prediction - Machine Learning Project"

    # The mid-sentence PDF line wrap ("...exposes REST" / "endpoints.") is rejoined
    # into the first project's description, not miscounted as a new project.
    assert "exposes REST endpoints." in first["description"]
    assert "Implemented PostgreSQL-backed" in first["description"]
    assert "accuracy, precision and recall." in second["description"]
    assert "Created visualizations with Matplotlib" in second["description"]

    # Descriptions must not bleed across projects.
    assert "Cleaned and analyzed" not in first["description"]
    assert "Built a FastAPI backend" not in second["description"]


# ---------------------------------------------------------------------------
# Projects: dash-bulleted PDF-style text, including a tech-stack line right
# under the title and a bullet whose continuation line is itself indented.
# ---------------------------------------------------------------------------

DASH_BULLETED_PROJECTS = """AI Career Companion - Backend Foundation
Python, FastAPI, SQLAlchemy, SQLite, React, TypeScript
 - Built REST APIs for candidate profile creation, retrieval, and updates with validation and persistent storage.
 - Implemented secure PDF and DOCX resume upload with file-size checks, format validation, and database
 metadata.
- Added PDF text extraction using pypdf and stored normalized resume text for later structured analysis.

Task Management REST API
Python, FastAPI, PostgreSQL, Docker
 - Developed CRUD APIs for users and tasks with request validation, error handling, and database persistence.
 - Containerized the application with Docker and tested endpoints using Postman."""


def test_dash_bulleted_projects_stay_two_projects_with_technologies_and_descriptions() -> None:
    projects = _projects([section("projects", DASH_BULLETED_PROJECTS)])

    assert len(projects) == 2
    first, second = projects
    assert first["title"] == "AI Career Companion - Backend Foundation"
    assert second["title"] == "Task Management REST API"

    # The un-bulleted technology line directly under a title is not miscounted
    # as a new project; it is captured as that project's technologies.
    assert set(first["technologies"]) == {"Python", "FastAPI", "SQLAlchemy", "SQLite", "React", "TypeScript"}
    assert set(second["technologies"]) == {"Python", "FastAPI", "PostgreSQL", "Docker"}

    assert "and database metadata." in first["description"]
    assert "Added PDF text extraction" in first["description"]
    assert "Developed CRUD APIs" in second["description"]
    assert "Built REST APIs" not in second["description"]


# ---------------------------------------------------------------------------
# Education: degree + institution/graduation/CGPA metadata split across lines,
# including a "start - end" year range, must group into one entry.
# ---------------------------------------------------------------------------

def test_degree_and_graduation_metadata_on_separate_lines_form_one_education_entry() -> None:
    content = (
        "B.Tech in Information Technology - ABC Institute of Technology, Bengaluru\n"
        "Expected Graduation: 2027 | CGPA: 8.4/10"
    )

    entries = _education([section("education", content)])

    assert len(entries) == 1
    assert entries[0]["degree"] == "B.Tech"
    assert entries[0]["graduation_year"] == 2027
    assert "CGPA: 8.4/10" in entries[0]["raw_text"]


def test_year_range_uses_graduation_year_not_enrollment_year() -> None:
    content = (
        "B.Tech in Information Technology\n"
        "Demo Institute of Technology, Chennai | 2023 - 2027 | CGPA: 8.4 / 10\n"
        "Relevant coursework: Data Structures, Operating Systems, Computer Networks."
    )

    entries = _education([section("education", content)])

    assert len(entries) == 1
    assert entries[0]["degree"] == "B.Tech"
    # The later year in a "start - end" range is the graduation year, not the
    # first digits matched (which would wrongly be the enrollment year).
    assert entries[0]["graduation_year"] == 2027


def test_two_distinct_degree_lines_produce_two_education_entries() -> None:
    content = "B.Tech in Information Technology | 2027\n12th - State Board | 2023"

    entries = _education([section("education", content)])

    assert len(entries) == 2
    assert entries[0]["degree"] == "B.Tech"
    assert entries[1]["degree"] == "12th"


# ---------------------------------------------------------------------------
# Skills: vocabulary should detect previously-missed but legitimate skills.
# ---------------------------------------------------------------------------

def test_expanded_skill_vocabulary_detects_previously_missed_skills() -> None:
    text = (
        "Data & ML: Pandas, NumPy, Scikit-learn, Machine Learning, Statistics, Matplotlib\n"
        "Tools: Git, GitHub, Linux, Docker, Postman, VS Code\n"
        "Core CS: Data Structures, Algorithms, OOP, DBMS, Software Development Lifecycle"
    )

    detected = set(_skills(text))

    for expected in ["Statistics", "Matplotlib", "Postman", "VS Code", "Software Development Lifecycle"]:
        assert expected in detected


def test_skill_detection_is_generic_not_tied_to_one_resume() -> None:
    # A differently-worded line using the same vocabulary should also match —
    # proves the detection is alias-based, not a literal match on fixed text.
    detected = set(_skills("Comfortable with statistics, matplotlib plotting, and the full SDLC."))
    assert {"Statistics", "Matplotlib", "Software Development Lifecycle"} <= detected


# ---------------------------------------------------------------------------
# Bullet/glyph artifact normalization.
# ---------------------------------------------------------------------------

def test_bullet_glyph_variants_normalize_to_canonical_bullet() -> None:
    raw = "PROJECTS\n• First point\n▪ Second point\n□ Third point\n Fourth point"

    normalized = normalize_resume_text(raw)

    assert "• First point" in normalized
    assert "• Second point" in normalized
    assert "• Third point" in normalized
    assert "• Fourth point" in normalized
    # No corrupted Private Use Area glyphs should survive into the output.
    assert "" not in normalized
    assert "▪" not in normalized
    assert "□" not in normalized


def test_stray_private_use_and_replacement_characters_are_stripped() -> None:
    raw = "Skills: Python, SQL�, Git"

    normalized = normalize_resume_text(raw)

    assert "" not in normalized
    assert "�" not in normalized
    assert "Python" in normalized and "SQL" in normalized and "Git" in normalized


def test_normalized_bullets_still_group_correctly_into_one_project() -> None:
    raw = "PROJECTS\nSolo Project\n Did the first thing.\n Did the second thing."
    normalized = normalize_resume_text(raw)
    project_content = normalized.split("PROJECTS\n", 1)[1]

    projects = _projects([section("projects", project_content)])

    assert len(projects) == 1
    assert "Did the first thing." in projects[0]["description"]
    assert "Did the second thing." in projects[0]["description"]


def test_build_structured_data_contains_no_stray_control_or_private_use_characters() -> None:
    sections = [
        section("skills", "Python, Statistics, Matplotlib", position=0),
        section("projects", "Solo Project\n Cleaned up  artifacts.", position=1),
    ]
    data = build_structured_data(sections)

    serialized = str(data)
    assert "" not in serialized
    assert "�" not in serialized
