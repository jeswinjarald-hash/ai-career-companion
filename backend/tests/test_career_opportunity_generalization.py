"""Career Opportunity Generalization — tests that the project now works across the
full opportunity-type spectrum (internship, entry-level job, graduate role, trainee,
apprenticeship), not just internships, without regressing any existing milestone.

Uses real dataset records throughout (no mock data): `JOB-0001` (a legacy pure
internship), `JOB-0035` (a legacy "Entry Level" record whose title still literally
says "Intern" — a known, documented pre-existing data quirk, kept unchanged per the
backward-compatibility requirement), and `JOB-0254`/`JOB-0299` (newly added, cleanly
titled Graduate Role / Trainee records) as concrete opportunity-type fixtures.
"""

from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import Base
from app.models import CandidateProfile, Resume, StructuredResume
from app.services.assistant_intent import detect_intent
from app.services.assistant_service import create_conversation, send_message
from app.services.interview_prep_service import generate_interview_preparation
from app.services.job_dataset_service import load_job_postings
from app.services.job_matching import normalize_profile, score_experience, score_required_skills
from app.services.job_search_service import search_jobs
from app.services.job_vector_store import load_vector_store
from app.services.llm_provider import NullLLMProvider
from app.services.resume_customization_service import generate_customization
from app.services.skill_gap_service import analyze_skill_gap

LEGACY_INTERNSHIP_ID = "JOB-0001"
LEGACY_ENTRY_LEVEL_ID = "JOB-0035"  # required: Python, SQL, REST APIs, Git
GRADUATE_ROLE_ID = "JOB-0254"  # required: Python, SQL, REST APIs, Git (same skill set as JOB-0035)
TRAINEE_ID = "JOB-0299"

STRUCTURED_DATA = {
    "header": "Alex Morgan", "skills": ["Python", "FastAPI", "SQL", "Git"],
    "education": [{"degree": "B.Tech", "raw_text": "B.Tech Computer Science, Example University, 2026"}],
    "experience": [{"raw_text": "Backend Intern at Acme Corp, Jan 2025 - Jun 2025. Worked on REST API development using FastAPI and Git."}],
    "internships": [],
    "projects": [{"title": "Career API", "description": "Built REST APIs using Python and FastAPI with PostgreSQL persistence.",
                  "raw_text": "Career API - Built REST APIs using Python and FastAPI with PostgreSQL persistence.", "technologies": ["Python", "FastAPI", "PostgreSQL"]}],
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
    profile = CandidateProfile(user_id=user_id, full_name="Alex Morgan", email=f"generalize-{user_id}@example.com", skills=[], career_interests=[], target_roles=[])
    db.add(profile)
    db.flush()
    resume = Resume(candidate_profile_id=profile.id, original_filename="resume.pdf", stored_filename=f"resume-generalize-{user_id}.pdf", file_type="pdf", mime_type="application/pdf", file_size=10, storage_path="/tmp/resume.pdf", status="structured")
    db.add(resume)
    db.flush()
    structured = StructuredResume(resume_id=resume.id, data=STRUCTURED_DATA)
    db.add(structured)
    db.commit()
    db.refresh(profile)
    db.refresh(resume)
    db.refresh(structured)
    return profile, resume, structured


# 1. Canonical dataset contains multiple opportunity types
def test_canonical_dataset_has_multiple_opportunity_types() -> None:
    jobs = load_job_postings()
    types = {job.employment_type for job in jobs}
    assert types == {"Internship", "Entry Level", "Graduate Role", "Trainee", "Apprenticeship"}
    assert len(jobs) == 320


# 2/3/4/5. Retrieval works across types, and the opportunity type persists through search
def test_search_retrieves_all_opportunity_types_with_type_preserved() -> None:
    internship_hit = search_jobs("cybersecurity internship", top_k=5)
    assert any(r.employment_type == "Internship" for r in internship_hit)

    entry_level_hit = search_jobs("junior Java developer", top_k=5)
    assert any(r.employment_type == "Entry Level" for r in entry_level_hit)

    graduate_hit = search_jobs("graduate data analyst", top_k=5)
    assert any(r.employment_type == "Graduate Role" for r in graduate_hit)

    trainee_hit = search_jobs("DevOps trainee", top_k=5)
    assert any(r.employment_type == "Trainee" for r in trainee_hit)

    # every result carries a real, dataset-sourced employment_type, never blank/invented
    for result in internship_hit + entry_level_hit + graduate_hit + trainee_hit:
        assert result.employment_type in {"Internship", "Entry Level", "Graduate Role", "Trainee", "Apprenticeship"}


# 6. Job matching works for non-internship roles. Tested against the scoring
# components directly (not `match_jobs_for_resume`'s retrieval-ranked top-20, which
# is a best-effort semantic result set that a specific job isn't guaranteed to enter
# among 320 real postings) — this verifies M2's matching computation itself is
# correct and type-agnostic, the same scoring path every job type goes through.
def test_job_matching_works_for_a_graduate_role(db: Session) -> None:
    profile, resume, _structured = seed(db)
    job = next(j for j in load_job_postings() if j.job_id == GRADUATE_ROLE_ID)
    matching_profile = normalize_profile(profile, STRUCTURED_DATA)

    required_result = score_required_skills(matching_profile, job)
    assert required_result.score is not None and required_result.score > 0
    assert "Python" in required_result.matched

    experience_result = score_experience(matching_profile, job)
    assert experience_result.score is not None
    # the graduate program's own forgiving experience requirement must not be
    # scored as if it were a multi-year professional-experience requirement
    assert experience_result.score >= 0.5


# 7. M3.1 skill gap works with an entry-level/graduate job
def test_m3_1_skill_gap_works_for_graduate_role(db: Session) -> None:
    profile, resume, _structured = seed(db)
    analysis = analyze_skill_gap(db, resume.id, GRADUATE_ROLE_ID, profile.user_id)
    assert analysis.job_id == GRADUATE_ROLE_ID
    assert analysis.summary.overall_readiness > 0
    # a fair, non-punitive experience assessment for a graduate program (facts, not internship-only leniency)
    assert not any("penal" in g.reason.lower() for g in analysis.experience_gaps)


# 8/12. M3.2 customization works for a graduate role and never claims it's an internship
def test_m3_2_customization_works_for_graduate_role_without_internship_wording(db: Session) -> None:
    profile, resume, _structured = seed(db)
    customization = generate_customization(db, resume.id, GRADUATE_ROLE_ID, profile.user_id, llm_provider=NullLLMProvider())
    assert "Graduate Python Backend Engineer" in customization.cover_letter_text
    assert "internship" not in customization.cover_letter_text.lower()
    assert "intern" not in customization.tailored_resume.summary.lower()


# 9/12. M3.3 interview prep works for a graduate role and never claims it's an internship
def test_m3_3_interview_prep_works_for_graduate_role_without_internship_wording(db: Session) -> None:
    profile, resume, _structured = seed(db)
    prep = generate_interview_preparation(db, resume.id, GRADUATE_ROLE_ID, profile.user_id, llm_provider=NullLLMProvider())
    assert prep.job_title == "Graduate Python Backend Engineer"
    assert "internship" not in prep.preparation_summary.lower()
    for question in prep.questions:
        assert "internship" not in question.question.lower()


# 10. M3.4 intent detection understands job/internship/graduate/trainee language equally
@pytest.mark.parametrize("message,expected_intent", [
    ("Find internships for me", "JOB_DISCOVERY"),
    ("Find entry-level jobs", "JOB_DISCOVERY"),
    ("Which graduate roles fit me?", "JOB_DISCOVERY"),
    ("What skills am I missing for this trainee role?", "SKILL_GAP"),
])
def test_assistant_intent_understands_all_opportunity_type_language(message: str, expected_intent: str) -> None:
    result = detect_intent(message, active_job_id=None)
    assert result["intent"] == expected_intent


# 11. M3.4 job comparison can compare different opportunity types, factually
def test_assistant_compares_internship_and_entry_level_job_factually(db: Session) -> None:
    profile, resume, _structured = seed(db)
    conversation = create_conversation(db, profile.user_id)
    response = send_message(db, profile.user_id, conversation.id, f"Compare {LEGACY_INTERNSHIP_ID} and {LEGACY_ENTRY_LEVEL_ID}", llm_provider=NullLLMProvider())
    assert response.message.intent == "JOB_COMPARISON"
    content = response.message.content.lower()
    assert "type:" in content
    assert "internship" in content and "entry level" in content
    assert "is better" not in content


# 13. Existing internship IDs still resolve (backward compatibility)
def test_existing_internship_ids_still_resolve() -> None:
    jobs = {job.job_id: job for job in load_job_postings()}
    assert LEGACY_INTERNSHIP_ID in jobs
    assert jobs[LEGACY_INTERNSHIP_ID].job_title == "Software Developer Intern"
    assert jobs[LEGACY_INTERNSHIP_ID].employment_type == "Internship"
    assert LEGACY_ENTRY_LEVEL_ID in jobs
    assert jobs[LEGACY_ENTRY_LEVEL_ID].employment_type == "Entry Level"


# 14. FAISS vector count matches dataset chunk count (3 chunks per job)
def test_faiss_index_count_matches_dataset() -> None:
    jobs = load_job_postings()
    index, chunks = load_vector_store()
    assert index.ntotal == len(chunks)
    assert len(chunks) == len(jobs) * 3
    assert {chunk.job_id for chunk in chunks} == {job.job_id for job in jobs}


# 15. Ownership/persistence unchanged for a non-internship opportunity
def test_ownership_and_persistence_unchanged_for_graduate_role(db: Session) -> None:
    owner, resume, _structured = seed(db, user_id=1)
    intruder = CandidateProfile(user_id=2, full_name="Intruder", email="intruder-generalize@example.com", skills=[], career_interests=[], target_roles=[])
    db.add(intruder)
    db.commit()

    analyze_skill_gap(db, resume.id, GRADUATE_ROLE_ID, owner.user_id)
    with pytest.raises(LookupError):
        analyze_skill_gap(db, resume.id, GRADUATE_ROLE_ID, 2)
