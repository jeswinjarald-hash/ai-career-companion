"""Milestone 3.2 LLM rewrite layer tests.

No real external LLM is ever called — every test injects a fake `LLMProvider`
(`generate_customization(..., llm_provider=...)`) so behavior is deterministic and
network-free. Covers: valid grounded rewrite acceptance, rejection of hallucinated
skills/metrics/leadership claims (falling back to the deterministic pipeline),
unknown evidence_id rejection, malformed JSON, provider timeout, generation_mode
persistence, and that immutability/ownership/versioning still hold on the LLM path.
"""

from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import Base
from app.models import CandidateProfile, Resume, StructuredResume
from app.models.career_state import ApplicationCustomization as ApplicationCustomizationRecord
from app.services.llm_provider import LLMUnavailableError
from app.services.resume_customization_service import generate_customization

# required: Python, SQL, REST APIs, Git — preferred: FastAPI, Flask, PostgreSQL, Docker, Agile
FASTAPI_INTERN_ID = "JOB-0035"

STRUCTURED_DATA = {
    "header": "Alex Morgan",
    "skills": ["Python", "FastAPI", "SQL", "Git"],
    "education": [{"degree": "B.Tech", "raw_text": "B.Tech Computer Science, Example University, 2026"}],
    "experience": [{"raw_text": "Backend Intern at Acme Corp. Worked on REST API development using FastAPI and Git."}],
    "internships": [],
    "projects": [{
        "title": "Career API", "description": "Built REST APIs using Python and FastAPI with PostgreSQL persistence.",
        "raw_text": "Career API - Built REST APIs using Python and FastAPI with PostgreSQL persistence.",
        "technologies": ["Python", "FastAPI", "PostgreSQL"],
    }],
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


def seed(db: Session, user_id: int = 1) -> tuple[CandidateProfile, Resume, StructuredResume]:
    profile = CandidateProfile(user_id=user_id, full_name="Test Candidate", email=f"llm-test-{user_id}@example.com", skills=["Python", "FastAPI", "SQL", "Git"], career_interests=[], target_roles=[])
    db.add(profile)
    db.flush()
    resume = Resume(candidate_profile_id=profile.id, original_filename="resume.pdf", stored_filename=f"resume-llm-{user_id}.pdf", file_type="pdf", mime_type="application/pdf", file_size=10, storage_path="/tmp/resume.pdf", status="structured")
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
    model = "fake-model-1"

    def __init__(self, responder) -> None:
        self._responder = responder
        self.call_count = 0

    def generate_json(self, system_prompt: str, payload: dict) -> dict:
        self.call_count += 1
        return self._responder(payload, self.call_count)


class FakeTimeoutProvider:
    name = "fake-timeout"
    model = "fake-model-1"

    def __init__(self) -> None:
        self.call_count = 0

    def generate_json(self, system_prompt: str, payload: dict) -> dict:
        self.call_count += 1
        raise LLMUnavailableError("simulated timeout")


def _grounded_response(payload: dict, _call_count: int) -> dict:
    bullets = [
        {
            "source_path": item["source_path"],
            "rewritten_text": f"Rewritten: {item['original_text']}",
            "evidence_ids": [e["evidence_id"] for e in payload["allowed_evidence"] if e["source_path"] == item["source_path"]][:1],
            "job_keywords_used": ["FastAPI"],
        }
        for item in payload["bullets_to_rewrite"]
    ]
    return {
        "summary": "Rewritten summary: Python/FastAPI backend student with hands-on REST API experience.",
        "summary_evidence_ids": [payload["allowed_evidence"][0]["evidence_id"]],
        "bullets": bullets,
        "cover_letter_paragraphs": [
            {"text": f"I am interested in the {payload['job']['title']} role at {payload['job']['company']}.", "evidence_ids": []},
            {"text": "My Python and FastAPI experience is directly relevant to this role.", "evidence_ids": [payload["allowed_evidence"][0]["evidence_id"]]},
            {"text": "Thank you for your consideration.", "evidence_ids": []},
        ],
    }


def test_valid_grounded_rewrite_is_accepted_and_marks_generation_mode_llm(db: Session) -> None:
    profile, resume, _structured = seed(db)
    provider = FakeProvider(_grounded_response)

    result = generate_customization(db, resume.id, FASTAPI_INTERN_ID, profile.user_id, llm_provider=provider)

    assert result.generation.mode == "llm"
    assert result.generation.provider == "fake"
    assert result.generation.model == "fake-model-1"
    assert result.generation.fallback_reason is None
    assert result.tailored_resume.summary.startswith("Rewritten summary")
    assert result.tailored_resume.projects[0].tailored_text.startswith("Rewritten: ")
    assert result.tailored_resume.projects[0].evidence_ids  # LLM's cited evidence carried through
    assert result.validation.passed is True


def test_docker_hallucination_is_rejected_and_falls_back(db: Session) -> None:
    profile, resume, _structured = seed(db)

    def hallucinate(payload: dict, _call_count: int) -> dict:
        return {
            "summary": "Experienced Docker and Kubernetes containerization engineer.",
            "summary_evidence_ids": [],
            "bullets": [{"source_path": item["source_path"], "rewritten_text": "Deployed services using Docker.", "evidence_ids": [], "job_keywords_used": ["Docker"]} for item in payload["bullets_to_rewrite"]],
            "cover_letter_paragraphs": [{"text": "I have strong Docker experience.", "evidence_ids": []}],
        }

    result = generate_customization(db, resume.id, FASTAPI_INTERN_ID, profile.user_id, llm_provider=FakeProvider(hallucinate))

    assert result.generation.mode == "deterministic_fallback"
    assert "docker" not in result.tailored_resume.summary.lower()
    assert "docker" not in result.cover_letter_text.lower()


def test_fabricated_metric_is_rejected_and_falls_back(db: Session) -> None:
    profile, resume, _structured = seed(db)

    def fabricate_metric(payload: dict, _call_count: int) -> dict:
        return {
            "summary": "Improved API response time by 40% using FastAPI.",
            "summary_evidence_ids": [],
            "bullets": [{"source_path": item["source_path"], "rewritten_text": item["original_text"], "evidence_ids": [], "job_keywords_used": []} for item in payload["bullets_to_rewrite"]],
            "cover_letter_paragraphs": [{"text": "I improved performance by 40% in my last project.", "evidence_ids": []}],
        }

    result = generate_customization(db, resume.id, FASTAPI_INTERN_ID, profile.user_id, llm_provider=FakeProvider(fabricate_metric))

    assert result.generation.mode == "deterministic_fallback"
    assert "40%" not in result.tailored_resume.summary
    assert "40%" not in result.cover_letter_text


def test_fabricated_leadership_claim_is_rejected_and_falls_back(db: Session) -> None:
    profile, resume, _structured = seed(db)

    def fabricate_leadership(payload: dict, _call_count: int) -> dict:
        return {
            "summary": "B.Tech student with hands-on Python and FastAPI experience.",
            "summary_evidence_ids": [],
            "bullets": [{"source_path": item["source_path"], "rewritten_text": "Led a team of 5 engineers.", "evidence_ids": [], "job_keywords_used": []} for item in payload["bullets_to_rewrite"]],
            "cover_letter_paragraphs": [{"text": "I led a team of 5 to deliver this project.", "evidence_ids": []}],
        }

    result = generate_customization(db, resume.id, FASTAPI_INTERN_ID, profile.user_id, llm_provider=FakeProvider(fabricate_leadership))

    assert result.generation.mode == "deterministic_fallback"
    assert "team of 5" not in result.cover_letter_text.lower()
    for project in result.tailored_resume.projects:
        assert "led a team" not in project.tailored_text.lower()


def test_unknown_evidence_id_is_rejected_and_falls_back(db: Session) -> None:
    profile, resume, _structured = seed(db)

    def unknown_evidence(payload: dict, _call_count: int) -> dict:
        return {
            "summary": "B.Tech student with hands-on Python and FastAPI experience.",
            "summary_evidence_ids": ["EV-DOES-NOT-EXIST"],
            "bullets": [{"source_path": item["source_path"], "rewritten_text": item["original_text"], "evidence_ids": ["EV-ALSO-FAKE"], "job_keywords_used": []} for item in payload["bullets_to_rewrite"]],
            "cover_letter_paragraphs": [{"text": "Thank you for your consideration.", "evidence_ids": []}],
        }

    provider = FakeProvider(unknown_evidence)
    result = generate_customization(db, resume.id, FASTAPI_INTERN_ID, profile.user_id, llm_provider=provider)

    assert result.generation.mode == "deterministic_fallback"
    assert "unknown evidence_ids" in (result.generation.fallback_reason or "")
    assert provider.call_count == 2  # original attempt + one repair attempt, no more


def test_malformed_json_shape_triggers_repair_then_fallback(db: Session) -> None:
    profile, resume, _structured = seed(db)

    def malformed(payload: dict, call_count: int) -> dict:
        # Missing the required "bullets"/"cover_letter_paragraphs" keys entirely —
        # fails schema validation, not content validation.
        return {"not_the_expected_shape": True}

    provider = FakeProvider(malformed)
    result = generate_customization(db, resume.id, FASTAPI_INTERN_ID, profile.user_id, llm_provider=provider)

    assert result.generation.mode == "deterministic_fallback"
    assert result.generation.repair_attempted is True
    assert provider.call_count == 2
    # the deterministic baseline is still a fully valid, grounded result
    assert result.validation.passed is True


def test_provider_timeout_falls_back_without_a_repair_attempt(db: Session) -> None:
    profile, resume, _structured = seed(db)
    provider = FakeTimeoutProvider()

    result = generate_customization(db, resume.id, FASTAPI_INTERN_ID, profile.user_id, llm_provider=provider)

    assert result.generation.mode == "deterministic_fallback"
    assert result.generation.repair_attempted is False
    assert "provider_unavailable" in (result.generation.fallback_reason or "")
    assert provider.call_count == 1  # no wasted repair call against a dead connection


def test_repair_succeeds_on_second_attempt(db: Session) -> None:
    profile, resume, _structured = seed(db)

    def bad_then_good(payload: dict, call_count: int) -> dict:
        if call_count == 1:
            return {
                "summary": "Improved throughput by 40%.",
                "summary_evidence_ids": [], "bullets": [], "cover_letter_paragraphs": [{"text": "ok", "evidence_ids": []}],
            }
        return _grounded_response(payload, call_count)

    provider = FakeProvider(bad_then_good)
    result = generate_customization(db, resume.id, FASTAPI_INTERN_ID, profile.user_id, llm_provider=provider)

    assert provider.call_count == 2
    assert result.generation.repair_attempted is True
    assert result.generation.mode == "llm"
    assert result.generation.fallback_reason is None


def test_original_resume_unchanged_on_llm_path(db: Session) -> None:
    profile, resume, structured = seed(db)
    before_data = dict(structured.data)
    before_updated_at = structured.updated_at

    generate_customization(db, resume.id, FASTAPI_INTERN_ID, profile.user_id, llm_provider=FakeProvider(_grounded_response))

    db.refresh(structured)
    assert structured.data == before_data
    assert structured.updated_at == before_updated_at


def test_ownership_still_enforced_on_llm_path(db: Session) -> None:
    profile_a, resume_a, _s = seed(db, user_id=1)
    profile_b, _resume_b, _s2 = seed(db, user_id=2)

    with pytest.raises(LookupError):
        generate_customization(db, resume_a.id, FASTAPI_INTERN_ID, profile_b.user_id, llm_provider=FakeProvider(_grounded_response))


def test_versioning_still_works_on_llm_path(db: Session) -> None:
    profile, resume, _structured = seed(db)
    first = generate_customization(db, resume.id, FASTAPI_INTERN_ID, profile.user_id, llm_provider=FakeProvider(_grounded_response))
    second = generate_customization(db, resume.id, FASTAPI_INTERN_ID, profile.user_id, llm_provider=FakeProvider(_grounded_response))

    assert second.version == first.version + 1
    records = list(db.scalars(select(ApplicationCustomizationRecord).where(ApplicationCustomizationRecord.resume_id == resume.id)))
    assert {r.version for r in records} == {1, 2}


def test_no_provider_configured_uses_deterministic_pipeline_directly(db: Session) -> None:
    from app.services.llm_provider import NullLLMProvider

    profile, resume, _structured = seed(db)
    result = generate_customization(db, resume.id, FASTAPI_INTERN_ID, profile.user_id, llm_provider=NullLLMProvider())

    assert result.generation.mode == "deterministic_fallback"
    assert result.generation.attempted_llm is False
    assert result.generation.fallback_reason == "no_provider_configured"
