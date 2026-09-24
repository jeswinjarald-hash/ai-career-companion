"""Milestone 3.4 service-level tests: intent routing into M2/M3.1/M3.2/M3.3, job/resume
context retention across turns, missing-context follow-ups, grounding (no fabricated
candidate claims, missing skills stay missing), factual job comparison, LLM
synthesis acceptance/rejection, conversation persistence, and ownership. No real
external LLM is ever called — every LLM-path test injects a fake provider.
"""

from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import Base
from app.models import CandidateProfile, Resume, StructuredResume
from app.services.assistant_service import create_conversation, get_conversation, list_conversations, send_message
from app.services.llm_provider import LLMUnavailableError, NullLLMProvider
from app.services.resume_customization_service import list_customizations
from app.services.interview_prep_service import list_interview_preparations
from app.services.skill_gap_service import get_persisted_skill_gap

FASTAPI_INTERN_ID = "JOB-0035"  # required: Python, SQL, REST APIs, Git — preferred: FastAPI, Flask, PostgreSQL, Docker, Agile
BACKEND_INTERN_ID = "JOB-0036"

STRUCTURED_DATA = {
    "header": "Alex Morgan",
    "skills": ["Python", "FastAPI", "SQL", "Git"],
    "education": [{"degree": "B.Tech", "raw_text": "B.Tech Computer Science, Example University, 2026"}],
    "experience": [{"raw_text": "Backend Intern at Acme Corp, Jan 2025 - Jun 2025. Worked on REST API development using FastAPI and Git."}],
    "internships": [],
    "projects": [
        {"title": "Career API", "description": "Built REST APIs using Python and FastAPI with PostgreSQL persistence.",
         "raw_text": "Career API - Built REST APIs using Python and FastAPI with PostgreSQL persistence.",
         "technologies": ["Python", "FastAPI", "PostgreSQL"]},
    ],
    "certifications": [{"raw_text": "Python for Everybody - Coursera"}], "achievements": [], "qualifications": [], "learning": [],
}

# A student genuinely missing a REQUIRED skill (REST APIs) — not just absent from the
# skills list, but absent from experience/project text too, so M3.1 has no fuzzy
# evidence to fall back on and this is a real critical gap, not a false negative.
STRUCTURED_DATA_WITH_CRITICAL_GAP = {
    "header": "Alex Morgan",
    "skills": ["Python", "SQL", "Git"],
    "education": [{"degree": "B.Tech", "raw_text": "B.Tech Computer Science, Example University, 2026"}],
    "experience": [{"raw_text": "Data Analyst Intern at Acme Corp, Jan 2025 - Jun 2025. Wrote SQL reports and used Git for version control."}],
    "internships": [], "projects": [], "certifications": [], "achievements": [], "qualifications": [], "learning": [],
}


@pytest.fixture
def db() -> Generator[Session, None, None]:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    with session_factory() as session:
        yield session
    engine.dispose()


def seed(db: Session, user_id: int = 1, data: dict = STRUCTURED_DATA) -> tuple[CandidateProfile, Resume, StructuredResume]:
    profile = CandidateProfile(user_id=user_id, full_name="Alex Morgan", email=f"assistant-{user_id}@example.com", skills=[], career_interests=[], target_roles=[])
    db.add(profile)
    db.flush()
    resume = Resume(candidate_profile_id=profile.id, original_filename="resume.pdf", stored_filename=f"resume-assistant-{user_id}.pdf", file_type="pdf", mime_type="application/pdf", file_size=10, storage_path="/tmp/resume.pdf", status="structured")
    db.add(resume)
    db.flush()
    structured = StructuredResume(resume_id=resume.id, data=data)
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

    def generate_json(self, system_prompt: str, payload: dict) -> dict:
        raise LLMUnavailableError("simulated timeout")


def _echo_baseline(payload: dict, _call_count: int) -> dict:
    return {"message": "Refined: " + payload["baseline_answer"]}


def test_job_discovery_routes_to_m2(db: Session) -> None:
    profile, resume, _structured = seed(db)
    conversation = create_conversation(db, profile.user_id)
    response = send_message(db, profile.user_id, conversation.id, "Which internships fit my resume?", llm_provider=NullLLMProvider())
    assert response.message.intent == "JOB_DISCOVERY"
    assert "match" in response.message.content.lower()
    assert response.message.suggested_actions


def test_skill_gap_routes_to_m3_1_and_persists(db: Session) -> None:
    profile, resume, structured = seed(db)
    conversation = create_conversation(db, profile.user_id)
    response = send_message(db, profile.user_id, conversation.id, f"What skills am I missing for {FASTAPI_INTERN_ID}?", llm_provider=NullLLMProvider())
    assert response.message.intent == "SKILL_GAP"
    persisted = get_persisted_skill_gap(db, profile.user_id, FASTAPI_INTERN_ID, structured.updated_at)
    assert persisted is not None  # M3.1's own service was actually called, not reimplemented


def test_resume_customization_routes_to_m3_2_and_persists(db: Session) -> None:
    profile, resume, _structured = seed(db)
    conversation = create_conversation(db, profile.user_id)
    response = send_message(db, profile.user_id, conversation.id, f"Customize my resume for {FASTAPI_INTERN_ID}.", llm_provider=NullLLMProvider())
    assert response.message.intent == "RESUME_CUSTOMIZATION"
    versions = list_customizations(db, resume.id, FASTAPI_INTERN_ID)
    assert len(versions) == 1  # a real M3.2 ApplicationCustomization was generated


def test_interview_prep_routes_to_m3_3_and_persists(db: Session) -> None:
    profile, resume, _structured = seed(db)
    conversation = create_conversation(db, profile.user_id)
    response = send_message(db, profile.user_id, conversation.id, f"Prepare me for the interview for {FASTAPI_INTERN_ID}.", llm_provider=NullLLMProvider())
    assert response.message.intent == "INTERVIEW_PREP"
    preps = list_interview_preparations(db, resume.id, FASTAPI_INTERN_ID)
    assert len(preps) == 1  # a real M3.3 InterviewPreparation was generated


def test_job_context_carries_across_turns_without_repeating_id(db: Session) -> None:
    profile, resume, _structured = seed(db)
    conversation = create_conversation(db, profile.user_id)
    first = send_message(db, profile.user_id, conversation.id, f"Tell me about {FASTAPI_INTERN_ID}", llm_provider=NullLLMProvider())
    assert first.active_job_id == FASTAPI_INTERN_ID

    second = send_message(db, profile.user_id, conversation.id, "Why does this role fit me?", llm_provider=NullLLMProvider())
    assert second.message.intent == "JOB_MATCH_EXPLANATION"
    assert second.message.job_id == FASTAPI_INTERN_ID  # never asked to repeat the id

    third = send_message(db, profile.user_id, conversation.id, "What skills am I missing?", llm_provider=NullLLMProvider())
    assert third.message.job_id == FASTAPI_INTERN_ID

    fourth = send_message(db, profile.user_id, conversation.id, "Now prepare me for the interview.", llm_provider=NullLLMProvider())
    assert fourth.message.intent == "INTERVIEW_PREP"
    assert fourth.message.job_id == FASTAPI_INTERN_ID


def test_missing_job_context_asks_a_followup_instead_of_guessing(db: Session) -> None:
    profile, resume, _structured = seed(db)
    conversation = create_conversation(db, profile.user_id)
    response = send_message(db, profile.user_id, conversation.id, "What skills am I missing?", llm_provider=NullLLMProvider())
    assert response.message.intent == "SKILL_GAP"
    assert response.message.job_id is None
    assert "opportunity" in response.message.content.lower()
    assert response.message.generation is None  # no service/LLM call was attempted


def test_missing_resume_context_asks_a_followup(db: Session) -> None:
    profile = CandidateProfile(user_id=1, full_name="No Resume", email="noresume@example.com", skills=[], career_interests=[], target_roles=[])
    db.add(profile)
    db.commit()
    conversation = create_conversation(db, profile.user_id)
    response = send_message(db, profile.user_id, conversation.id, "Which internships fit my resume?", llm_provider=NullLLMProvider())
    assert "resume" in response.message.content.lower()
    assert any(a.action == "upload_resume" for a in response.message.suggested_actions)


def test_missing_skills_remain_missing_never_claimed_as_demonstrated(db: Session) -> None:
    profile, resume, _structured = seed(db, data=STRUCTURED_DATA_WITH_CRITICAL_GAP)
    conversation = create_conversation(db, profile.user_id)
    response = send_message(db, profile.user_id, conversation.id, f"What skills am I missing for {FASTAPI_INTERN_ID}?", llm_provider=NullLLMProvider())
    content = response.message.content.lower()
    assert "rest apis" in content
    assert "missing" in content or "critical gap" in content
    assert "you already demonstrate: rest apis" not in content


def test_hallucinated_llm_claim_falls_back(db: Session) -> None:
    profile, resume, _structured = seed(db, data=STRUCTURED_DATA_WITH_CRITICAL_GAP)
    conversation = create_conversation(db, profile.user_id)

    def hallucinate(payload: dict, _call_count: int) -> dict:
        return {"message": "You have 5 years of professional experience with REST APIs."}

    response = send_message(db, profile.user_id, conversation.id, f"What skills am I missing for {FASTAPI_INTERN_ID}?", llm_provider=FakeProvider(hallucinate))
    assert response.message.generation.mode == "deterministic_fallback"
    assert "5 years" not in response.message.content


def test_job_comparison_is_factual_and_never_declares_a_winner(db: Session) -> None:
    profile, resume, _structured = seed(db)
    conversation = create_conversation(db, profile.user_id)
    response = send_message(db, profile.user_id, conversation.id, f"Compare {FASTAPI_INTERN_ID} and {BACKEND_INTERN_ID}", llm_provider=NullLLMProvider())
    assert response.message.intent == "JOB_COMPARISON"
    content = response.message.content.lower()
    assert "is better" not in content
    assert "required skills" in content
    assert len(response.message.suggested_actions) == 2


def test_job_comparison_requires_two_jobs(db: Session) -> None:
    profile, resume, _structured = seed(db)
    conversation = create_conversation(db, profile.user_id)
    response = send_message(db, profile.user_id, conversation.id, "Compare two roles for me", llm_provider=NullLLMProvider())
    assert response.message.intent == "JOB_COMPARISON"
    assert "compare" in response.message.content.lower()
    assert response.message.job_id is None


def test_provider_timeout_falls_back_without_repair(db: Session) -> None:
    profile, resume, _structured = seed(db)
    conversation = create_conversation(db, profile.user_id)
    response = send_message(db, profile.user_id, conversation.id, f"What skills am I missing for {FASTAPI_INTERN_ID}?", llm_provider=FakeTimeoutProvider())
    assert response.message.generation.mode == "deterministic_fallback"
    assert response.message.generation.repair_attempted is False
    assert response.message.content  # a real, grounded answer is still returned


def test_valid_llm_response_yields_ai_enhanced_mode(db: Session) -> None:
    profile, resume, _structured = seed(db)
    conversation = create_conversation(db, profile.user_id)
    provider = FakeProvider(_echo_baseline)
    response = send_message(db, profile.user_id, conversation.id, f"What skills am I missing for {FASTAPI_INTERN_ID}?", llm_provider=provider)
    assert response.message.generation.mode == "llm"
    assert response.message.content.startswith("Refined:")


def test_conversation_and_message_persistence(db: Session) -> None:
    profile, resume, _structured = seed(db)
    conversation = create_conversation(db, profile.user_id)
    send_message(db, profile.user_id, conversation.id, f"Tell me about {FASTAPI_INTERN_ID}", llm_provider=NullLLMProvider())
    send_message(db, profile.user_id, conversation.id, "Why does this role fit me?", llm_provider=NullLLMProvider())

    detail = get_conversation(db, profile.user_id, conversation.id)
    assert detail is not None
    assert len(detail.messages) == 4  # 2 user + 2 assistant, in order
    assert [m.role for m in detail.messages] == ["user", "assistant", "user", "assistant"]
    assert detail.messages[1].content  # assistant reply persisted with real content


def test_ownership_is_enforced(db: Session) -> None:
    owner, _resume, _structured = seed(db, user_id=1)
    conversation = create_conversation(db, owner.user_id)

    intruder = CandidateProfile(user_id=2, full_name="Intruder", email="intruder@example.com", skills=[], career_interests=[], target_roles=[])
    db.add(intruder)
    db.commit()

    assert get_conversation(db, 2, conversation.id) is None
    with pytest.raises(LookupError):
        send_message(db, 2, conversation.id, "hello", llm_provider=NullLLMProvider())


def test_stale_resume_context_is_auto_refreshed(db: Session) -> None:
    profile, resume, _structured = seed(db)
    conversation = create_conversation(db, profile.user_id)
    first = send_message(db, profile.user_id, conversation.id, f"Tell me about {FASTAPI_INTERN_ID}", llm_provider=NullLLMProvider())
    assert first.active_resume_id == resume.id

    newer_resume = Resume(candidate_profile_id=profile.id, original_filename="resume-v2.pdf", stored_filename="resume-assistant-newer.pdf", file_type="pdf", mime_type="application/pdf", file_size=10, storage_path="/tmp/resume-v2.pdf", status="structured")
    db.add(newer_resume)
    db.flush()
    db.add(StructuredResume(resume_id=newer_resume.id, data=STRUCTURED_DATA))
    db.commit()

    second = send_message(db, profile.user_id, conversation.id, "What skills am I missing?", llm_provider=NullLLMProvider())
    assert second.active_resume_id == newer_resume.id  # silently switched to the latest resume, not left stale
    assert "most recently uploaded resume" in second.message.content.lower()


def test_action_buttons_have_correct_metadata(db: Session) -> None:
    profile, resume, _structured = seed(db)
    conversation = create_conversation(db, profile.user_id)
    response = send_message(db, profile.user_id, conversation.id, f"Prepare me for the interview for {FASTAPI_INTERN_ID}.", llm_provider=NullLLMProvider())
    actions = response.message.suggested_actions
    assert len(actions) == 1
    assert actions[0].action == "prepare_interview"
    assert actions[0].job_id == FASTAPI_INTERN_ID
    assert actions[0].label


def test_list_conversations_returns_message_counts(db: Session) -> None:
    profile, resume, _structured = seed(db)
    conversation = create_conversation(db, profile.user_id)
    send_message(db, profile.user_id, conversation.id, "hello", llm_provider=NullLLMProvider())
    summaries = list_conversations(db, profile.user_id)
    assert len(summaries) == 1
    assert summaries[0].message_count == 2
