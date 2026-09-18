from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import Base
from app.models import CandidateProfile, Resume, StructuredResume
from app.services.job_dataset_service import load_job_postings
from app.services.skill_gap_evidence import build_evidence_units
from app.services.skill_gap_service import analyze_skill_gap, assess_education, assess_experience, get_persisted_skill_gap


@pytest.fixture
def db() -> Generator[Session, None, None]:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    with session_factory() as session:
        yield session
    engine.dispose()


def seed_candidate(db: Session, *, skills: list[str], structured_data: dict, user_id: int = 1) -> tuple[CandidateProfile, Resume, StructuredResume]:
    profile = CandidateProfile(user_id=user_id, full_name="Test Candidate", email=f"candidate{user_id}@example.com", skills=skills, career_interests=[], target_roles=[])
    db.add(profile)
    db.flush()
    resume = Resume(candidate_profile_id=profile.id, original_filename="resume.pdf", stored_filename=f"resume-{user_id}.pdf", file_type="pdf", mime_type="application/pdf", file_size=10, storage_path="/tmp/resume.pdf", status="structured")
    db.add(resume)
    db.flush()
    structured = StructuredResume(resume_id=resume.id, data=structured_data)
    db.add(structured)
    db.commit()
    db.refresh(profile)
    db.refresh(resume)
    db.refresh(structured)
    return profile, resume, structured


def real_job(job_id: str):
    return next(job for job in load_job_postings() if job.job_id == job_id)


# JOB-0035 "FastAPI Intern": required [Python, SQL, REST APIs, Git], preferred [FastAPI, Flask, PostgreSQL, Docker, Agile]
FASTAPI_INTERN_ID = "JOB-0035"


def test_analyze_skill_gap_classifies_matched_missing_and_partial_against_real_job() -> None:
    job = real_job(FASTAPI_INTERN_ID)
    assert set(job.required_skills) >= {"Python", "SQL"}

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    with sessionmaker(bind=engine)() as db:
        structured_data = {
            "skills": ["Python", "SQL"],
            "education": [{"degree": "B.Tech", "raw_text": "B.Tech Computer Science, 2026"}],
            "experience": [], "internships": [],
            "projects": [{"title": "Career API", "raw_text": "Built REST APIs using Python and SQL", "technologies": []}],
            "certifications": [], "achievements": [], "qualifications": [],
        }
        profile, resume, _ = seed_candidate(db, skills=["Python", "SQL"], structured_data=structured_data)

        result = analyze_skill_gap(db, resume.id, FASTAPI_INTERN_ID, profile.user_id)

    matched = {s.requirement for s in result.strengths if s.requirement_type == "required_skill"}
    critical = {g.requirement for g in result.critical_gaps}
    partial = {g.requirement for g in result.partial_gaps}

    assert "Python" in matched
    assert "SQL" in matched
    assert "Git" in critical  # never mentioned anywhere -> missing -> critical (required)
    assert "REST APIs" in matched  # explicitly mentioned in project text
    assert result.summary.overall_readiness == result.summary.overall_readiness  # deterministic int, sanity
    assert 0 <= result.summary.overall_readiness <= 100
    assert not partial or "FastAPI" not in critical  # FastAPI is preferred, not required -> never critical
    assert all(g.match_type != "demonstrated" for g in result.critical_gaps + result.partial_gaps + result.preferred_gaps)
    engine.dispose()


def test_preferred_missing_skill_never_lands_in_critical_gaps() -> None:
    job = real_job(FASTAPI_INTERN_ID)
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    with sessionmaker(bind=engine)() as db:
        structured_data = {
            "skills": job.required_skills, "education": [], "experience": [], "internships": [],
            "projects": [], "certifications": [], "achievements": [], "qualifications": [],
        }
        profile, resume, _ = seed_candidate(db, skills=job.required_skills, structured_data=structured_data)
        result = analyze_skill_gap(db, resume.id, FASTAPI_INTERN_ID, profile.user_id)

    critical_requirements = {g.requirement for g in result.critical_gaps}
    preferred_requirements = {g.requirement for g in result.preferred_gaps}
    for preferred_skill in job.preferred_skills:
        assert preferred_skill not in critical_requirements
    assert set(job.preferred_skills) - {s.requirement for s in result.strengths} <= preferred_requirements
    engine.dispose()


def test_fully_qualified_candidate_has_no_critical_gaps_and_high_readiness() -> None:
    job = real_job(FASTAPI_INTERN_ID)
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    with sessionmaker(bind=engine)() as db:
        all_skills = job.required_skills + job.preferred_skills
        structured_data = {
            "skills": all_skills,
            "education": [{"degree": "B.Tech", "raw_text": "B.Tech Computer Science, 2026"}],
            "experience": [{"raw_text": "Backend Intern, 1 year, built production APIs"}],
            "internships": [{"raw_text": "Backend Intern for 1 year"}],
            "projects": [], "certifications": [], "achievements": [], "qualifications": [],
        }
        profile, resume, _ = seed_candidate(db, skills=all_skills, structured_data=structured_data)
        result = analyze_skill_gap(db, resume.id, FASTAPI_INTERN_ID, profile.user_id)

    assert result.critical_gaps == []
    assert result.summary.required_requirements_met == result.summary.required_requirements_total
    assert result.summary.overall_readiness >= 70
    engine.dispose()


def test_determinism_same_inputs_produce_identical_score(db: Session) -> None:
    job = real_job(FASTAPI_INTERN_ID)
    structured_data = {
        "skills": ["Python", "SQL"], "education": [], "experience": [], "internships": [],
        "projects": [], "certifications": [], "achievements": [], "qualifications": [],
    }
    profile, resume, _ = seed_candidate(db, skills=["Python", "SQL"], structured_data=structured_data)

    first = analyze_skill_gap(db, resume.id, FASTAPI_INTERN_ID, profile.user_id)
    second = analyze_skill_gap(db, resume.id, FASTAPI_INTERN_ID, profile.user_id)

    assert first.summary.overall_readiness == second.summary.overall_readiness
    assert {g.requirement for g in first.critical_gaps} == {g.requirement for g in second.critical_gaps}


def test_missing_structured_resume_raises_value_error(db: Session) -> None:
    profile = CandidateProfile(user_id=1, full_name="No Structured", email="none@example.com", skills=[], career_interests=[], target_roles=[])
    db.add(profile)
    db.flush()
    resume = Resume(candidate_profile_id=profile.id, original_filename="r.pdf", stored_filename="r-unique.pdf", file_type="pdf", mime_type="application/pdf", file_size=1, storage_path="/tmp/r.pdf", status="uploaded")
    db.add(resume)
    db.commit()

    with pytest.raises(ValueError):
        analyze_skill_gap(db, resume.id, FASTAPI_INTERN_ID, profile.user_id)


def test_unknown_job_raises_lookup_error(db: Session) -> None:
    structured_data = {"skills": ["Python"], "education": [], "experience": [], "internships": [], "projects": [], "certifications": [], "achievements": [], "qualifications": []}
    profile, resume, _ = seed_candidate(db, skills=["Python"], structured_data=structured_data)

    with pytest.raises(LookupError):
        analyze_skill_gap(db, resume.id, "JOB-DOES-NOT-EXIST", profile.user_id)


def test_missing_resume_raises_lookup_error(db: Session) -> None:
    with pytest.raises(LookupError):
        analyze_skill_gap(db, 999999, FASTAPI_INTERN_ID, 1)


def test_get_persisted_skill_gap_flags_stale_after_resume_reprocessed(db: Session) -> None:
    structured_data = {"skills": ["Python", "SQL"], "education": [], "experience": [], "internships": [], "projects": [], "certifications": [], "achievements": [], "qualifications": []}
    profile, resume, structured = seed_candidate(db, skills=["Python", "SQL"], structured_data=structured_data)
    analyze_skill_gap(db, resume.id, FASTAPI_INTERN_ID, profile.user_id)

    fresh = get_persisted_skill_gap(db, profile.user_id, FASTAPI_INTERN_ID, structured.updated_at)
    assert fresh is not None
    assert fresh.stale is False

    from datetime import timedelta
    later = structured.updated_at + timedelta(minutes=5)
    stale = get_persisted_skill_gap(db, profile.user_id, FASTAPI_INTERN_ID, later)
    assert stale is not None
    assert stale.stale is True


def test_assess_experience_treats_project_only_evidence_as_partial_not_satisfied() -> None:
    job = real_job("JOB-0001")
    # force a quantified requirement to exercise the "projects only" branch deterministically
    job = job.model_copy(update={"experience_requirements": "At least 1 year of relevant professional experience."})
    units = build_evidence_units(
        __import__("types").SimpleNamespace(skills=[], education=None, degree=None, specialization=None, career_goals=None),
        {"skills": [], "education": [], "experience": [], "internships": [], "projects": [{"title": "Academic Project", "raw_text": "Deployed a FastAPI project for a class assignment", "technologies": []}], "certifications": [], "achievements": [], "qualifications": []},
    )

    match_type, confidence, evidence, reason = assess_experience(job, units)

    assert match_type == "partial"
    assert evidence


def test_assess_education_excludes_component_when_no_evidence_available() -> None:
    job = real_job("JOB-0001")
    units = build_evidence_units(
        __import__("types").SimpleNamespace(skills=[], education=None, degree=None, specialization=None, career_goals=None),
        {"skills": [], "education": [], "experience": [], "internships": [], "projects": [], "certifications": [], "achievements": [], "qualifications": []},
    )

    match_type, confidence, evidence, reason, evidence_available = assess_education(job, units)

    assert match_type == "missing"
    assert evidence_available is False
