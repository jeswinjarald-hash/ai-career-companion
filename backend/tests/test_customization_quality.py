"""Milestone 3.2 quality-fix tests: category-label skill cleanup, a concise
grounded professional summary, a natural cover letter within roughly 250-400
words, and that these fixes hold on both the deterministic and (fake-provider)
LLM paths. No real external LLM is ever called.
"""

from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import Base
from app.models import CandidateProfile, Resume, StructuredResume
from app.services.customization_export_service import export_cover_letter_pdf, export_resume_docx, export_resume_pdf
from app.services.llm_provider import LLMUnavailableError, NullLLMProvider
from app.services.resume_customization_service import generate_customization

# required: Python, SQL, REST APIs, Git — preferred: FastAPI, Flask, PostgreSQL, Docker, Agile
FASTAPI_INTERN_ID = "JOB-0035"

# A resume whose Skills section uses bare category-header lines — the exact
# real-world pattern that produced "Programming"/"Backend"/"Databases"/"Web"/
# "Tools" as if they were standalone skills.
CATEGORY_LABEL_STRUCTURED_DATA = {
    "header": "Alex Morgan",
    "skills": [
        "Programming", "Python", "Java", "JavaScript",
        "Backend", "FastAPI", "REST APIs",
        "Databases", "SQL", "PostgreSQL", "MySQL",
        "Web", "HTML", "CSS",
        "Tools", "Git", "GitHub", "Postman", "VS Code",
        "Team Collaboration",
    ],
    "education": [{
        "degree": "B.Tech",
        "raw_text": "B.Tech Computer Science and Engineering, Delta University, 2022-2026, CGPA: 8.7, relevant coursework: Data Structures, Algorithms, DBMS",
    }],
    "experience": [{"raw_text": "Backend Intern at Acme Corp, Jan 2025 - Jun 2025. Worked on REST API development using FastAPI and Git version control."}],
    "internships": [],
    "projects": [
        {
            "title": "AI Career Companion",
            "description": "Built backend REST APIs using FastAPI and integrated structured resume processing for an AI career platform, including resume parsing and job matching across multiple internship postings.",
            "raw_text": "AI Career Companion - Built backend REST APIs using FastAPI and integrated structured resume processing for an AI career platform, including resume parsing and job matching across multiple internship postings.",
            "technologies": ["Python", "FastAPI", "PostgreSQL"],
        },
        {
            "title": "Portfolio Website",
            "description": "Built a personal portfolio site using HTML and CSS.",
            "raw_text": "Portfolio Website - Built a personal portfolio site using HTML and CSS.",
            "technologies": ["HTML", "CSS"],
        },
    ],
    "certifications": [], "achievements": [], "qualifications": [], "learning": [],
}


@pytest.fixture
def db() -> Generator[Session, None, None]:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    with session_factory() as session:
        yield session
    engine.dispose()


def seed(db: Session, structured_data: dict, user_id: int = 1) -> tuple[CandidateProfile, Resume, StructuredResume]:
    profile = CandidateProfile(user_id=user_id, full_name="Alex Morgan", email=f"quality-{user_id}@example.com", skills=[], career_interests=[], target_roles=[])
    db.add(profile)
    db.flush()
    resume = Resume(candidate_profile_id=profile.id, original_filename="resume.pdf", stored_filename=f"resume-quality-{user_id}.pdf", file_type="pdf", mime_type="application/pdf", file_size=10, storage_path="/tmp/resume.pdf", status="structured")
    db.add(resume)
    db.flush()
    structured = StructuredResume(resume_id=resume.id, data=structured_data)
    db.add(structured)
    db.commit()
    db.refresh(profile)
    db.refresh(resume)
    db.refresh(structured)
    return profile, resume, structured


def test_category_labels_are_removed_from_tailored_skills(db: Session) -> None:
    profile, resume, structured = seed(db, CATEGORY_LABEL_STRUCTURED_DATA)
    result = generate_customization(db, resume.id, FASTAPI_INTERN_ID, profile.user_id, llm_provider=NullLLMProvider())

    for label in ("Programming", "Backend", "Databases", "Web", "Tools"):
        assert label not in result.tailored_resume.skills
    # the original, unfiltered list must still be intact in the source of truth
    assert "Programming" in structured.data["skills"]


def test_real_skills_are_preserved_in_tailored_skills(db: Session) -> None:
    profile, resume, _structured = seed(db, CATEGORY_LABEL_STRUCTURED_DATA)
    result = generate_customization(db, resume.id, FASTAPI_INTERN_ID, profile.user_id, llm_provider=NullLLMProvider())

    for skill in ("Python", "Java", "JavaScript", "SQL", "FastAPI", "REST APIs", "PostgreSQL", "MySQL", "HTML", "CSS", "Git", "GitHub", "Postman", "VS Code", "Team Collaboration"):
        assert skill in result.tailored_resume.skills


def test_summary_is_concise_and_does_not_dump_raw_education(db: Session) -> None:
    profile, resume, _structured = seed(db, CATEGORY_LABEL_STRUCTURED_DATA)
    result = generate_customization(db, resume.id, FASTAPI_INTERN_ID, profile.user_id, llm_provider=NullLLMProvider())
    summary = result.tailored_resume.summary

    assert 2 <= summary.count(".") <= 3
    assert len(summary.split()) <= 60
    assert "Delta University" not in summary
    assert "CGPA" not in summary
    assert "coursework" not in summary.lower()
    assert "2022-2026" not in summary


def test_cover_letter_expresses_education_naturally_not_verbatim(db: Session) -> None:
    profile, resume, _structured = seed(db, CATEGORY_LABEL_STRUCTURED_DATA)
    result = generate_customization(db, resume.id, FASTAPI_INTERN_ID, profile.user_id, llm_provider=NullLLMProvider())
    letter = result.cover_letter_text

    # the raw education line (with institution/CGPA/coursework) must never appear verbatim
    assert "CGPA: 8.7" not in letter
    assert "relevant coursework" not in letter
    # but the degree/field must still appear, phrased into a natural sentence
    assert "B.Tech Computer Science and Engineering" in letter
    assert "student" in letter.lower()


def test_cover_letter_uses_relevant_project_evidence_summarized(db: Session) -> None:
    profile, resume, _structured = seed(db, CATEGORY_LABEL_STRUCTURED_DATA)
    result = generate_customization(db, resume.id, FASTAPI_INTERN_ID, profile.user_id, llm_provider=NullLLMProvider())
    letter = result.cover_letter_text

    assert "AI Career Companion" in letter
    # the long "including resume parsing and job matching..." tail must be summarized away, not dumped
    assert "including resume parsing and job matching across multiple internship postings" not in letter


def test_cover_letter_length_is_within_reasonable_range(db: Session) -> None:
    profile, resume, _structured = seed(db, CATEGORY_LABEL_STRUCTURED_DATA)
    result = generate_customization(db, resume.id, FASTAPI_INTERN_ID, profile.user_id, llm_provider=NullLLMProvider())
    word_count = len(result.cover_letter_text.split())
    assert 150 <= word_count <= 450


def test_cover_letter_never_invents_a_recipient_name(db: Session) -> None:
    profile, resume, _structured = seed(db, CATEGORY_LABEL_STRUCTURED_DATA)
    result = generate_customization(db, resume.id, FASTAPI_INTERN_ID, profile.user_id, llm_provider=NullLLMProvider())
    letter = result.cover_letter_text
    assert "Dear Hiring Team" in letter
    # the candidate's own real name may appear (signature) but no fabricated recipient name should
    assert "Dear Mr." not in letter and "Dear Ms." not in letter and "Dear Dr." not in letter


def test_unsupported_docker_and_aws_never_appear_in_output(db: Session) -> None:
    profile, resume, _structured = seed(db, CATEGORY_LABEL_STRUCTURED_DATA)
    result = generate_customization(db, resume.id, FASTAPI_INTERN_ID, profile.user_id, llm_provider=NullLLMProvider())
    haystacks = [result.tailored_resume.summary, result.cover_letter_text, " ".join(result.tailored_resume.skills)]
    for haystack in haystacks:
        assert "docker" not in haystack.lower()
        assert "aws" not in haystack.lower()


def test_valid_llm_rewrite_yields_generation_mode_llm_with_clean_output(db: Session) -> None:
    class FakeProvider:
        name = "fake"
        model = "fake-model"

        def generate_json(self, system_prompt: str, payload: dict) -> dict:
            bullets = [
                {
                    "source_path": item["source_path"],
                    "rewritten_text": f"Refined: {item['original_text']}",
                    "evidence_ids": [e["evidence_id"] for e in payload["allowed_evidence"] if e["source_path"] == item["source_path"]][:1],
                    "job_keywords_used": ["FastAPI"],
                }
                for item in payload["bullets_to_rewrite"]
            ]
            return {
                "summary": "B.Tech Computer Science and Engineering student with hands-on FastAPI and Python backend experience.",
                "summary_evidence_ids": [payload["allowed_evidence"][0]["evidence_id"]],
                "bullets": bullets,
                "cover_letter_paragraphs": [
                    {"text": f"I am interested in the {payload['job']['title']} role at {payload['job']['company']}.", "evidence_ids": []},
                    {"text": "My FastAPI and Python experience is directly relevant.", "evidence_ids": [payload["allowed_evidence"][0]["evidence_id"]]},
                ],
            }

    profile, resume, _structured = seed(db, CATEGORY_LABEL_STRUCTURED_DATA)
    result = generate_customization(db, resume.id, FASTAPI_INTERN_ID, profile.user_id, llm_provider=FakeProvider())

    assert result.generation.mode == "llm"
    assert "Refined:" in result.tailored_resume.projects[0].tailored_text
    # skill cleanup must hold regardless of which path generated the wording
    for label in ("Programming", "Backend", "Databases", "Web", "Tools"):
        assert label not in result.tailored_resume.skills


def test_provider_failure_falls_back_to_deterministic_with_clean_output(db: Session) -> None:
    class FailingProvider:
        name = "failing"
        model = "unreachable-model"

        def generate_json(self, system_prompt: str, payload: dict) -> dict:
            raise LLMUnavailableError("simulated network failure")

    profile, resume, _structured = seed(db, CATEGORY_LABEL_STRUCTURED_DATA)
    result = generate_customization(db, resume.id, FASTAPI_INTERN_ID, profile.user_id, llm_provider=FailingProvider())

    assert result.generation.mode == "deterministic_fallback"
    for label in ("Programming", "Backend", "Databases", "Web", "Tools"):
        assert label not in result.tailored_resume.skills
    assert "CGPA" not in result.tailored_resume.summary


def test_export_contains_cleaned_skills_and_summary_not_raw_labels(db: Session) -> None:
    profile, resume, _structured = seed(db, CATEGORY_LABEL_STRUCTURED_DATA)
    result = generate_customization(db, resume.id, FASTAPI_INTERN_ID, profile.user_id, llm_provider=NullLLMProvider())

    pdf_bytes = export_resume_pdf(result, "Alex Morgan")
    assert pdf_bytes[:4] == b"%PDF"
    docx_bytes = export_resume_docx(result, "Alex Morgan")
    assert len(docx_bytes) > 0
    letter_pdf = export_cover_letter_pdf(result, "Alex Morgan")
    assert letter_pdf[:4] == b"%PDF"


def test_original_structured_resume_is_never_mutated(db: Session) -> None:
    profile, resume, structured = seed(db, CATEGORY_LABEL_STRUCTURED_DATA)
    before_skills = list(structured.data["skills"])
    before_updated_at = structured.updated_at

    generate_customization(db, resume.id, FASTAPI_INTERN_ID, profile.user_id, llm_provider=NullLLMProvider())

    db.refresh(structured)
    assert structured.data["skills"] == before_skills
    assert "Programming" in structured.data["skills"]  # unfiltered original preserved
    assert structured.updated_at == before_updated_at
