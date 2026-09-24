"""Milestone 3.3 service-level tests: grounded question generation across all six
categories, revision-plan prioritization from M3.1's own gaps, no fabricated skill
claims, LLM refinement acceptance/rejection, staleness, and immutability. No real
external LLM is ever called — every LLM-path test injects a fake provider.
"""

from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import Base
from app.models import CandidateProfile, Resume, StructuredResume
from app.services.interview_prep_service import generate_interview_preparation, get_interview_preparation
from app.services.llm_provider import LLMUnavailableError, NullLLMProvider

# required: Python, SQL, REST APIs, Git — preferred: FastAPI, Flask, PostgreSQL, Docker, Agile
FASTAPI_INTERN_ID = "JOB-0035"

STRUCTURED_DATA = {
    "header": "Alex Morgan",
    "skills": ["Python", "FastAPI", "SQL", "Git"],
    "education": [{"degree": "B.Tech", "raw_text": "B.Tech Computer Science, Example University, 2026"}],
    "experience": [{"raw_text": "Backend Intern at Acme Corp, Jan 2025 - Jun 2025. Worked on REST API development using FastAPI and Git."}],
    "internships": [],
    "projects": [
        {
            "title": "Career API", "description": "Built REST APIs using Python and FastAPI with PostgreSQL persistence.",
            "raw_text": "Career API - Built REST APIs using Python and FastAPI with PostgreSQL persistence.",
            "technologies": ["Python", "FastAPI", "PostgreSQL"],
        },
        {
            "title": "Portfolio Website", "description": "Built a personal portfolio site using HTML and CSS.",
            "raw_text": "Portfolio Website - Built a personal portfolio site using HTML and CSS.",
            "technologies": ["HTML", "CSS"],
        },
    ],
    "certifications": [{"raw_text": "Python for Everybody - Coursera"}], "achievements": [], "qualifications": [], "learning": [],
}


@pytest.fixture
def db() -> Generator[Session, None, None]:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    with session_factory() as session:
        yield session
    engine.dispose()


def seed(db: Session, user_id: int = 1) -> tuple[CandidateProfile, Resume, StructuredResume]:
    profile = CandidateProfile(user_id=user_id, full_name="Alex Morgan", email=f"interview-{user_id}@example.com", skills=[], career_interests=[], target_roles=[])
    db.add(profile)
    db.flush()
    resume = Resume(candidate_profile_id=profile.id, original_filename="resume.pdf", stored_filename=f"resume-interview-{user_id}.pdf", file_type="pdf", mime_type="application/pdf", file_size=10, storage_path="/tmp/resume.pdf", status="structured")
    db.add(resume)
    db.flush()
    structured = StructuredResume(resume_id=resume.id, data=STRUCTURED_DATA)
    db.add(structured)
    db.commit()
    db.refresh(profile)
    db.refresh(resume)
    db.refresh(structured)
    return profile, resume, structured


class FakeProvider:
    name = "fake"
    model = "fake-model"

    def __init__(self, responder) -> None:
        self._responder = responder
        self.call_count = 0

    def generate_json(self, system_prompt: str, payload: dict) -> dict:
        self.call_count += 1
        return self._responder(payload, self.call_count)


class FakeTimeoutProvider:
    name = "fake-timeout"
    model = "fake-model"

    def __init__(self) -> None:
        self.call_count = 0

    def generate_json(self, system_prompt: str, payload: dict) -> dict:
        self.call_count += 1
        raise LLMUnavailableError("simulated timeout")


def _grounded_response(payload: dict, _call_count: int) -> dict:
    return {
        "preparation_summary": "Refined: " + payload["preparation_summary"],
        "questions": [
            {"index": q["index"], "question": "Refined: " + q["question"], "why_asked": q["why_asked"], "what_interviewer_is_testing": q["what_interviewer_is_testing"], "preparation_guidance": q["preparation_guidance"], "evidence_ids": q["existing_evidence_ids"]}
            for q in payload["questions"]
        ],
        "revision_plan": [{"topic": r["topic"], "reason": r["reason"], "suggested_revision": r["suggested_revision"], "estimated_focus": r["estimated_focus"]} for r in payload["revision_plan"]],
    }


def test_technical_questions_are_grounded_in_real_job_requirements(db: Session) -> None:
    profile, resume, _structured = seed(db)
    result = generate_interview_preparation(db, resume.id, FASTAPI_INTERN_ID, profile.user_id, llm_provider=NullLLMProvider())

    technical = [q for q in result.questions if q.category == "technical"]
    assert technical
    job_terms = {"python", "sql", "rest apis", "git", "fastapi", "flask", "postgresql", "docker", "agile"}
    for q in technical:
        assert q.source_requirements, q.question
        assert all(req.lower() in job_terms for req in q.source_requirements)


def test_resume_questions_reference_real_resume_evidence(db: Session) -> None:
    profile, resume, _structured = seed(db)
    result = generate_interview_preparation(db, resume.id, FASTAPI_INTERN_ID, profile.user_id, llm_provider=NullLLMProvider())

    resume_qs = [q for q in result.questions if q.category == "resume"]
    assert resume_qs
    for q in resume_qs:
        assert q.source_evidence_ids, q.question


def test_project_questions_reference_real_project_names(db: Session) -> None:
    profile, resume, _structured = seed(db)
    result = generate_interview_preparation(db, resume.id, FASTAPI_INTERN_ID, profile.user_id, llm_provider=NullLLMProvider())

    project_qs = [q for q in result.questions if q.category == "project"]
    assert project_qs
    assert any("Career API" in q.question for q in project_qs)
    # never invents a project that doesn't exist
    for q in project_qs:
        assert "Career API" in q.question or "Portfolio Website" in q.question


def test_missing_skills_are_never_claimed_as_existing(db: Session) -> None:
    profile, resume, _structured = seed(db)
    result = generate_interview_preparation(db, resume.id, FASTAPI_INTERN_ID, profile.user_id, llm_provider=NullLLMProvider())

    for q in result.questions:
        if q.category == "technical" and "Docker" in q.source_requirements:
            assert "how you used" not in q.question.lower()
            assert "your docker" not in q.question.lower()
        if q.category == "skill_gap":
            # a skill_gap question must explicitly name the gap, never assert the student has it
            assert "does not show" in q.question or "partial" in q.question.lower()


def test_skill_gap_questions_are_labeled_as_gaps_with_correct_requirements(db: Session) -> None:
    profile, resume, _structured = seed(db)
    result = generate_interview_preparation(db, resume.id, FASTAPI_INTERN_ID, profile.user_id, llm_provider=NullLLMProvider())

    skill_gap_qs = [q for q in result.questions if q.category == "skill_gap"]
    assert skill_gap_qs
    topics = {req for q in skill_gap_qs for req in q.source_requirements}
    assert "Docker" in topics or "Agile" in topics or "Flask" in topics


def test_unrelated_technologies_are_excluded(db: Session) -> None:
    profile, resume, _structured = seed(db)
    result = generate_interview_preparation(db, resume.id, FASTAPI_INTERN_ID, profile.user_id, llm_provider=NullLLMProvider())

    all_text = " ".join(q.question for q in result.questions).lower()
    for unrelated in ("kubernetes", "react", "pytorch", "tensorflow", "mongodb", "azure"):
        assert unrelated not in all_text


def test_revision_priorities_follow_m3_1_gaps(db: Session) -> None:
    profile, resume, _structured = seed(db)
    result = generate_interview_preparation(db, resume.id, FASTAPI_INTERN_ID, profile.user_id, llm_provider=NullLLMProvider())

    priorities = [item.priority for item in result.revision_plan]
    priority_rank = {"high": 0, "medium": 1, "low": 2}
    assert priorities == sorted(priorities, key=lambda p: priority_rank[p])
    topics = {item.topic for item in result.revision_plan}
    assert "Docker" in topics or "Agile" in topics or "Flask" in topics


def test_malformed_llm_output_falls_back(db: Session) -> None:
    profile, resume, _structured = seed(db)

    def malformed(payload: dict, call_count: int) -> dict:
        return {"not_the_expected_shape": True}

    provider = FakeProvider(malformed)
    result = generate_interview_preparation(db, resume.id, FASTAPI_INTERN_ID, profile.user_id, llm_provider=provider)

    assert result.generation.mode == "deterministic_fallback"
    assert result.generation.repair_attempted is True
    assert provider.call_count == 2


def test_provider_timeout_falls_back_without_repair(db: Session) -> None:
    profile, resume, _structured = seed(db)
    provider = FakeTimeoutProvider()
    result = generate_interview_preparation(db, resume.id, FASTAPI_INTERN_ID, profile.user_id, llm_provider=provider)

    assert result.generation.mode == "deterministic_fallback"
    assert result.generation.repair_attempted is False
    assert provider.call_count == 1


def test_valid_llm_response_yields_generation_mode_llm(db: Session) -> None:
    profile, resume, _structured = seed(db)
    provider = FakeProvider(_grounded_response)
    result = generate_interview_preparation(db, resume.id, FASTAPI_INTERN_ID, profile.user_id, llm_provider=provider)

    assert result.generation.mode == "llm"
    assert result.preparation_summary.startswith("Refined:")
    assert all(q.question.startswith("Refined:") for q in result.questions)


def test_hallucinated_llm_skill_falls_back(db: Session) -> None:
    profile, resume, _structured = seed(db)

    def hallucinate(payload: dict, _call_count: int) -> dict:
        return {
            "preparation_summary": "You have 5 years of professional experience with AWS.",
            "questions": [{"index": q["index"], "question": q["question"], "why_asked": q["why_asked"], "what_interviewer_is_testing": q["what_interviewer_is_testing"], "preparation_guidance": q["preparation_guidance"], "evidence_ids": []} for q in payload["questions"]],
            "revision_plan": [{"topic": r["topic"], "reason": r["reason"], "suggested_revision": r["suggested_revision"], "estimated_focus": r["estimated_focus"]} for r in payload["revision_plan"]],
        }

    result = generate_interview_preparation(db, resume.id, FASTAPI_INTERN_ID, profile.user_id, llm_provider=FakeProvider(hallucinate))
    assert result.generation.mode == "deterministic_fallback"
    assert "5 years" not in result.preparation_summary
    assert "AWS" not in result.preparation_summary


def test_original_resume_and_profile_unchanged(db: Session) -> None:
    profile, resume, structured = seed(db)
    before_skills = list(structured.data["skills"])
    before_updated_at = structured.updated_at

    generate_interview_preparation(db, resume.id, FASTAPI_INTERN_ID, profile.user_id, llm_provider=NullLLMProvider())

    db.refresh(structured)
    assert structured.data["skills"] == before_skills
    assert structured.updated_at == before_updated_at


def test_stale_detection(db: Session) -> None:
    from datetime import timedelta
    profile, resume, structured = seed(db)
    generated = generate_interview_preparation(db, resume.id, FASTAPI_INTERN_ID, profile.user_id, llm_provider=NullLLMProvider())
    assert generated.stale is False

    later = structured.updated_at + timedelta(minutes=5)
    stale_result = get_interview_preparation(db, resume.id, generated.id, current_resume_updated_at=later)
    assert stale_result is not None
    assert stale_result.stale is True
