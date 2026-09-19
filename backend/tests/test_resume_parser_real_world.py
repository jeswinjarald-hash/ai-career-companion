"""Regression tests for the "structured resume extraction is broken for real-world
resume formats" bug, based on the structure of a real reviewed resume (two projects
with an inline "Name — Built using X, Y and Z" tech annotation and no bullets, an
institution-then-degree education block, an explicit-but-unrecognized-vocabulary
Skills section, an "Additional" certifications section, and a Languages section, with
NO experience/internship heading at all).

These fixtures mirror that *structure* generically — nothing here is specific to any
one person's name or resume — so the coverage holds for any resume shaped this way,
not just the one that was manually reviewed.
"""

from app.models import ResumeSection
from app.services.section_detection import detect_resume_sections
from app.services.structured_resume import _education, _projects, build_structured_data

REAL_WORLD_RESUME_TEXT = """RANJITKUMAR S
Software Developer Aspirant
ranjitkumar.28it@licet.ac.in

EDUCATION
Loyola ICAM College of Engineering And Technology, Chennai
B.Tech Information Technology
June 2024 - June 2028

PROJECTS
Society Finance Management — Built using Node,Express and MongoDB
Developed a full-stack Society Finance Management System independently
using HTML, CSS, JavaScript, Node.js, Express.js, and MongoDB. The project
was designed to manage members, payments, expenses, and loans through a
responsive frontend and REST APIs backed by a MongoDB database with CRUD
operations.

E-commerce Management — Built using Html,Css,Javascript,React
Developed a dynamic e-commerce web application featuring product listing,
shopping cart, checkout, and an order success page. Implemented
component-based frontend development with interactive state management.

SKILLS
Frontend Development
Basic Backend Development
SQL Programming
Object-Oriented Programming (OOP)
Problem Solving

ADDITIONAL
NPTEL Certified in Java Programme
Completed Hands-on Course on Artificial Intelligence and Its Real-Time Application using Python
NPTEL Certified in English

LANGUAGES
English
Tamil
"""


def _structured_data() -> dict:
    detected = detect_resume_sections(REAL_WORLD_RESUME_TEXT)
    sections = [
        ResumeSection(resume_id=1, name=d.name, original_heading=d.original_heading, content=d.content, position=i)
        for i, d in enumerate(detected)
    ]
    return build_structured_data(sections)


def _projects_section(content: str) -> list[dict]:
    section = ResumeSection(resume_id=1, name="projects", original_heading="PROJECTS", content=content, position=0)
    return _projects([section])


PROJECTS_TEXT = REAL_WORLD_RESUME_TEXT.split("PROJECTS\n", 1)[1].split("\nSKILLS", 1)[0]


# A. Two projects with an inline tech stack.
def test_a_two_projects_with_inline_tech_stack() -> None:
    assert len(_projects_section(PROJECTS_TEXT)) == 2


# B. Exact project names.
def test_b_project_names_are_exact() -> None:
    projects = _projects_section(PROJECTS_TEXT)
    assert [p["title"] for p in projects] == ["Society Finance Management", "E-commerce Management"]


# C. No word-by-word (or sentence-fragment-by-fragment) projects.
def test_c_no_word_by_word_or_fragment_projects() -> None:
    projects = _projects_section(PROJECTS_TEXT)
    titles = {p["title"] for p in projects}
    forbidden = {
        "Society", "Finance", "Management", "Built", "using", "Developed", "a", "full-stack",
        "and", "The", "project", "was", "designed", "to", "Node,Express", "MongoDB",
    }
    assert titles.isdisjoint(forbidden)
    assert len(projects) == 2  # nothing extra snuck in beyond the two real projects


# D. Project technologies.
def test_d_project_technologies_are_identified() -> None:
    projects = _projects_section(PROJECTS_TEXT)
    first, second = projects
    for expected in ("Node.js", "Express", "MongoDB", "HTML", "CSS", "JavaScript"):
        assert expected in first["technologies"], f"{expected} missing from project 1: {first['technologies']}"
    for expected in ("HTML", "CSS", "JavaScript", "React"):
        assert expected in second["technologies"], f"{expected} missing from project 2: {second['technologies']}"


# E. No experience section -> no experience entries.
def test_e_no_experience_heading_means_empty_experience() -> None:
    data = _structured_data()
    assert data["experience"] == []
    assert data["internships"] == []
    # the degenerate fragment described in the bug report must never survive as an entry
    assert not any(entry.get("raw_text", "").strip() == "in" for entry in data["experience"])


# F. Education: one complete entry.
def test_f_education_is_one_complete_entry() -> None:
    entries = _education([ResumeSection(
        resume_id=1, name="education", original_heading="EDUCATION", position=0,
        content="Loyola ICAM College of Engineering And Technology, Chennai\nB.Tech Information Technology\nJune 2024 - June 2028",
    )])
    assert len(entries) == 1
    assert "Loyola ICAM College of Engineering And Technology" in entries[0]["raw_text"]
    assert "B.Tech Information Technology" in entries[0]["raw_text"]
    assert entries[0]["degree"] == "B.Tech"
    assert entries[0]["graduation_year"] == 2028


# G. Explicit skills/concepts are preserved, not silently dropped for lacking a
# recognized-vocabulary match.
def test_g_explicit_skill_concepts_are_preserved() -> None:
    data = _structured_data()
    for expected in ("Frontend Development", "Basic Backend Development", "SQL", "OOP", "Problem Solving"):
        assert expected in data["skills"], f"{expected} missing from skills: {data['skills']}"


# H. Languages stay a separate field, never leaking into projects/experience/skills.
def test_h_languages_are_isolated_from_other_sections() -> None:
    data = _structured_data()
    language_values = {entry["raw_text"] for entry in data["languages"]}
    assert language_values == {"English", "Tamil"}
    assert "English" not in data["skills"]
    assert "Tamil" not in data["skills"]
    project_titles = {p["title"] for p in data["projects"]}
    assert "English" not in project_titles and "Tamil" not in project_titles
    assert data["experience"] == []


# I. "Additional" (NPTEL/course) content is classified as certifications, not projects
# or unclassified noise.
def test_i_additional_courses_become_certifications_not_projects() -> None:
    data = _structured_data()
    certification_texts = {entry["raw_text"] for entry in data["certifications"]}
    assert "NPTEL Certified in Java Programme" in certification_texts
    assert "NPTEL Certified in English" in certification_texts
    assert any("Artificial Intelligence" in text for text in certification_texts)
    project_titles = {p["title"] for p in data["projects"]}
    assert not any("NPTEL" in title for title in project_titles)
    assert len(data["projects"]) == 2  # additional/certification content never inflates the project count


# J. Multi-line wrapped project descriptions stay attached to the same project, not
# fragmented or turned into new projects.
def test_j_wrapped_description_lines_stay_attached_to_one_project() -> None:
    projects = _projects_section(PROJECTS_TEXT)
    first = projects[0]
    assert "manage members, payments, expenses, and loans" in first["description"]
    assert "CRUD operations" in first["description"]
    assert "Developed a full-stack" in first["description"]


def test_full_pipeline_matches_the_reviewed_ground_truth() -> None:
    """The single end-to-end assertion tying every piece together."""
    data = _structured_data()
    assert len(data["education"]) == 1
    assert len(data["projects"]) == 2
    assert len(data["experience"]) == 0
    assert len(data["internships"]) == 0
    assert {p["title"] for p in data["projects"]} == {"Society Finance Management", "E-commerce Management"}
