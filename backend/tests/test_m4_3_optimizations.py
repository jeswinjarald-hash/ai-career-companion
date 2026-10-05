"""Milestone 4.3 regression tests for accepted optimizations.

Each test uses phrasings and fixtures that differ from the M4 evaluation cases
(data/evaluation/m4/cases/) so an optimization cannot pass merely by fitting the
benchmark strings.
"""

from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import Base
from app.models import CandidateProfile, Resume, StructuredResume
from app.services.assistant_intent import extract_discovery_request
from app.services.assistant_service import create_conversation, send_message
from app.services.job_dataset_service import load_job_postings
from app.services.llm_provider import NullLLMProvider

JOBS = {job.job_id: job for job in load_job_postings()}

BACKEND_STUDENT = {
    "header": "Ravi Backend", "skills": ["Python", "SQL", "Git", "FastAPI"],
    "education": [{"degree": "B.Tech", "raw_text": "B.Tech Computer Engineering, Sample College, 2026"}],
    "experience": [], "internships": [],
    "projects": [{"title": "Notes API", "description": "REST API in FastAPI with SQL storage.", "raw_text": "Notes API - REST API in FastAPI with SQL storage.", "technologies": ["Python", "FastAPI", "SQL"]}],
    "certifications": [], "achievements": [], "qualifications": [], "learning": [],
}


@pytest.fixture
def db() -> Generator[Session, None, None]:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    with sessionmaker(bind=engine)() as session:
        yield session
    engine.dispose()


def seed(db: Session, data: dict, *, profile_skills: list[str] | None = None, education: str | None = None, user_id: int = 1) -> tuple[CandidateProfile, Resume]:
    profile = CandidateProfile(user_id=user_id, full_name="M43 Student", email=f"m43-{user_id}@example.com", skills=profile_skills or [],
                               education=education, career_interests=[], target_roles=[])
    db.add(profile)
    db.flush()
    resume = Resume(candidate_profile_id=profile.id, original_filename="r.pdf", stored_filename=f"m43-{user_id}.pdf", file_type="pdf",
                    mime_type="application/pdf", file_size=1, storage_path="unused", status="structured")
    db.add(resume)
    db.flush()
    db.add(StructuredResume(resume_id=resume.id, data=data))
    db.commit()
    return profile, resume


def ask(db: Session, user_id: int, message: str):
    conversation = create_conversation(db, user_id)
    return send_message(db, user_id, conversation.id, message, llm_provider=NullLLMProvider()).message


# --- Experiment 1: discovery uses the student's requested area ------------------

@pytest.mark.parametrize("message, expected", [
    ("Show me cloud computing internships", "cloud computing internships"),
    ("Can you find QA testing jobs for me?", "qa testing"),
    ("Search for mobile app developer roles", "mobile app developer"),
    ("Any machine learning opportunities?", "machine learning"),
])
def test_discovery_request_keeps_area_words(message: str, expected: str) -> None:
    assert extract_discovery_request(message) == expected


@pytest.mark.parametrize("message", [
    "Which internships fit my resume?", "Recommend jobs for me", "Find graduate roles", "What opportunities match my profile?",
])
def test_generic_discovery_requests_have_no_explicit_area(message: str) -> None:
    assert extract_discovery_request(message) is None


def test_discovery_retrieves_the_requested_area_and_scores_against_the_resume(db: Session) -> None:
    profile, _ = seed(db, BACKEND_STUDENT)
    mobile = ask(db, profile.user_id, "Search for mobile app developer roles")
    qa = ask(db, profile.user_id, "Find internships in software testing and QA")
    mobile_ids = [a.job_id for a in mobile.suggested_actions if a.job_id]
    qa_ids = [a.job_id for a in qa.suggested_actions if a.job_id]
    assert mobile_ids and qa_ids and set(mobile_ids).isdisjoint(qa_ids)
    assert {JOBS[j].domain for j in mobile_ids} == {"Mobile Development"}
    assert {JOBS[j].domain for j in qa_ids} == {"Software Testing / QA"}
    assert "scored against your resume" in mobile.content


def test_generic_discovery_still_ranks_by_the_resume(db: Session) -> None:
    profile, _ = seed(db, BACKEND_STUDENT)
    reply = ask(db, profile.user_id, "Which internships fit my resume?")
    assert reply.intent == "JOB_DISCOVERY"
    assert reply.content.startswith("Based on your resume")
    assert {JOBS[a.job_id].domain for a in reply.suggested_actions if a.job_id} == {"Python Backend"}


# --- Experiment 2: conversational routing and follow-up context -------------------

from app.services.assistant_intent import detect_intent  # noqa: E402


@pytest.mark.parametrize("message, job_id", [
    ("How do I stack up against JOB-0026?", "JOB-0026"),
    ("Compare my resume with JOB-0109", "JOB-0109"),
    ("me vs JOB-0121 — any good?", "JOB-0121"),
])
def test_self_comparison_is_a_fit_question_not_a_job_comparison(message: str, job_id: str) -> None:
    result = detect_intent(message, active_job_id=None)
    assert result["intent"] == "JOB_MATCH_EXPLANATION"
    assert result["job_id"] == job_id and result["second_job_id"] is None


@pytest.mark.parametrize("message, active", [
    ("Compare JOB-0026 against JOB-0109", None), ("Compare this with JOB-0109", "JOB-0026"), ("Compare these two roles for me", None),
])
def test_job_to_job_comparison_is_unchanged(message: str, active: str | None) -> None:
    assert detect_intent(message, active_job_id=active)["intent"] == "JOB_COMPARISON"


@pytest.mark.parametrize("message", [
    "What should I focus on first?", "Which one should I study first?", "Which of these is most important to practise?",
])
def test_learning_priority_follow_ups_route_to_learning_guidance(message: str) -> None:
    result = detect_intent(message, active_job_id="JOB-0026")
    assert result["intent"] == "LEARNING_GUIDANCE" and result["job_id"] == "JOB-0026"


@pytest.mark.parametrize("message", ["Tell me about machine learning", "I really enjoyed my deep learning course"])
def test_learning_rule_does_not_fire_on_learning_as_a_subject(message: str) -> None:
    assert detect_intent(message, active_job_id=None)["intent"] == "GENERAL_CAREER_CHAT"


@pytest.mark.parametrize("message", ["Can you find QA testing jobs for me?", "Suggest some cloud roles for me", "Any openings in data science?"])
def test_free_form_discovery_wording_routes_to_discovery(message: str) -> None:
    assert detect_intent(message, active_job_id=None)["intent"] == "JOB_DISCOVERY"


def test_next_action_and_small_talk_routing_is_unchanged() -> None:
    assert detect_intent("What should I do next?", active_job_id=None)["intent"] == "NEXT_BEST_ACTION"
    assert detect_intent("hello, how are you today?", active_job_id=None)["intent"] == "GENERAL_CAREER_CHAT"


def test_self_comparison_establishes_context_for_later_follow_ups(db: Session) -> None:
    profile, _ = seed(db, BACKEND_STUDENT)
    conversation = create_conversation(db, profile.user_id)
    turns = ["How do I stack up against JOB-0026?", "What skills am I lacking?", "Which one should I study first?"]
    replies = [send_message(db, profile.user_id, conversation.id, text, llm_provider=NullLLMProvider()).message for text in turns]
    assert [r.intent for r in replies] == ["JOB_MATCH_EXPLANATION", "SKILL_GAP", "LEARNING_GUIDANCE"]
    assert [r.job_id for r in replies] == ["JOB-0026"] * 3
    assert all(not r.content.startswith(("Which opportunity", "To compare two")) for r in replies)


# --- Experiment 3e: shared related-skill relationships in matching ----------------

from app.services.job_matching import MatchingProfile, score_preferred_skills, score_required_skills  # noqa: E402
from app.services.skill_relationships import related_terms  # noqa: E402


def _matching_profile(skills: list[str]) -> MatchingProfile:
    from app.services.job_matching import normalize_term
    return MatchingProfile(skills=[normalize_term(s) for s in skills], education_text="", experience_text="", project_texts=[],
                           project_skills=[], qualification_text="", retrieval_terms=[])


def test_related_terms_are_shared_and_bidirectional() -> None:
    assert "sql" in related_terms("mysql")            # forward entry
    assert "mysql" in related_terms("sql")            # inverse of mysql -> sql
    assert "kubernetes" in related_terms("docker")    # inverse of kubernetes -> docker
    assert "python" not in related_terms("pandas")    # deliberately excluded pairing stays excluded
    assert "sql" not in related_terms("sql")


def test_related_skills_earn_partial_preferred_credit_but_are_never_reported_as_matched() -> None:
    job = JOBS["JOB-0049"]  # Full Stack: preferred React, Node.js, MongoDB, REST APIs, Communication
    vue_dev = score_preferred_skills(_matching_profile(["Vue", "Express", "MySQL"]), job)
    nothing = score_preferred_skills(_matching_profile(["Photoshop"]), job)
    assert vue_dev.score > nothing.score == 0.0
    assert vue_dev.matched == []
    assert {skill for skill, _ in vue_dev.related} >= {"React", "Node.js", "MongoDB"}
    assert set(vue_dev.missing) >= {"React", "Node.js", "MongoDB"}


def test_required_skills_still_need_direct_evidence() -> None:
    job = JOBS["JOB-0049"]  # required JavaScript, HTML, CSS, Git
    result = score_required_skills(_matching_profile(["React", "Node.js"]), job)  # both relate to JavaScript
    assert result.score == 0.0 and result.related == []
    assert "JavaScript" in result.missing


def test_related_credit_is_explained_as_partial_in_the_reasoning() -> None:
    from app.schemas.job_chunk import JobSearchResult
    from app.services.job_matching import _result
    job = JOBS["JOB-0049"]
    stub = JobSearchResult(job_id=job.job_id, job_title=job.job_title, company=job.company, domain=job.domain, location=job.location, work_mode=job.work_mode,
                           employment_type=job.employment_type, required_skills=job.required_skills, preferred_skills=job.preferred_skills, similarity_score=0.0, matched_chunk_types=[])
    result = _result(job, stub, _matching_profile(["JavaScript", "Vue"]))
    assert "partial (not full) credit" in result.reasoning
    assert not any("React" in strength for strength in result.strengths)


# --- Experiment 4: one education assessment shared by matching and skill gap ------

from app.services.education_assessment import assess_education_text  # noqa: E402

FIELDS_OR_RELATED = "Bachelor's student in Computer Science or a related discipline."
NAMED_FIELDS_ONLY = "Undergraduate student in a relevant engineering or computing program."
ANY_DISCIPLINE = "Graduate in any discipline with an interest in technology."


@pytest.mark.parametrize("education, requirement, expected", [
    ("B.Sc Computer Science", NAMED_FIELDS_ONLY, "met"),                  # computing
    ("B.Tech Information Technology", NAMED_FIELDS_ONLY, "met"),          # IT is computing
    ("BE Mechanical Engineering", NAMED_FIELDS_ONLY, "met"),              # engineering
    ("B.Sc Statistics", NAMED_FIELDS_ONLY, "partial"),                    # technical, field not named
    ("B.Sc Statistics", FIELDS_OR_RELATED, "met"),                        # related-field wording
    ("BA English Literature", FIELDS_OR_RELATED, "not_met"),              # explicitly unrelated
    ("B.Sc Botany", FIELDS_OR_RELATED, "not_met"),                        # a B.Sc alone is not a field
    ("BA English Literature", ANY_DISCIPLINE, "met"),                     # any discipline
    ("", NAMED_FIELDS_ONLY, "unknown"),
])
def test_shared_education_assessment(education: str, requirement: str, expected: str) -> None:
    from app.services.job_matching import normalize_term
    assert assess_education_text(normalize_term(education), normalize_term(requirement)).level == expected


def test_bare_it_pronoun_is_not_read_as_information_technology() -> None:
    assert assess_education_text("completed it with distinction", NAMED_FIELDS_ONLY).level == "not_met"


@pytest.mark.parametrize("education, expected_match_score, expected_gap_type", [
    ("B.Tech Information Technology", 1.0, "demonstrated"),
    ("B.Sc Statistics", 0.5, "partial"),
    ("BA English Literature", 0.0, "missing"),
])
def test_matching_and_skill_gap_agree_on_the_same_education(db: Session, education: str, expected_match_score: float, expected_gap_type: str) -> None:
    from app.services.job_matching import normalize_profile, score_education
    from app.services.skill_gap_evidence import build_evidence_units
    from app.services.skill_gap_service import assess_education
    job = JOBS["JOB-0121"].model_copy(update={"education_requirements": NAMED_FIELDS_ONLY})
    profile, _ = seed(db, {**BACKEND_STUDENT, "education": []}, education=education)
    assert score_education(normalize_profile(profile, {"education": []}), job).score == expected_match_score
    assert assess_education(job, build_evidence_units(profile, {"education": []}))[0] == expected_gap_type


# --- Experiment 5: naming the target opportunity is not a skill claim -------------

from app.services.customization_validator import check_fabrication  # noqa: E402

NAMES = ("Docker Platform Intern", "Kubeworks Labs")
UNSUPPORTED = {"docker", "kubernetes"}


def test_naming_the_role_and_company_is_not_flagged() -> None:
    assert check_fabrication("I am excited to apply for the Docker Platform Intern role at Kubeworks Labs.", UNSUPPORTED, NAMES) is None


@pytest.mark.parametrize("sentence", [
    "I have professional Docker experience.",
    "For the Docker Platform Intern role, I bring hands-on Docker skills.",           # claim outside the masked name
    "At Kubeworks Labs I would apply my Kubernetes expertise.",
])
def test_unsupported_skill_claims_are_still_flagged_next_to_role_names(sentence: str) -> None:
    assert check_fabrication(sentence, UNSUPPORTED, NAMES) is not None


def test_default_behaviour_without_allowed_phrases_is_unchanged() -> None:
    assert check_fabrication("I am excited to apply for the Docker Platform Intern role.", UNSUPPORTED) is not None


def test_masking_never_hides_metric_or_leadership_fabrication() -> None:
    assert check_fabrication("As Docker Platform Intern I cut costs by 40%.", UNSUPPORTED, NAMES) is not None
    assert check_fabrication("At Kubeworks Labs I led a team of 6.", UNSUPPORTED, NAMES) is not None


def test_cover_letter_keeps_its_opening_when_the_title_contains_an_unsupported_skill(db: Session) -> None:
    from app.services.resume_customization_service import generate_customization
    data = {**BACKEND_STUDENT, "skills": ["Python", "SQL", "Pandas"], "projects": [
        {"title": "Survey Stats", "description": "Survey analysis with Python and Pandas.", "raw_text": "Survey Stats - Survey analysis with Python and Pandas.", "technologies": ["Python", "Pandas"]}]}
    profile, resume = seed(db, data)
    job = JOBS["JOB-0026"]  # "FastAPI Intern" — the student has no FastAPI
    result = generate_customization(db, resume.id, job.job_id, profile.user_id, llm_provider=NullLLMProvider())
    assert job.job_title in result.cover_letter_text
    assert not any(job.job_title in removed for removed in result.validation.removed_claims)
    assert "FastAPI" not in result.tailored_resume.skills
    assert all("fastapi" not in keyword.keyword.lower() or keyword.status != "supported" for keyword in result.keyword_classification)


# --- Experiment 6: query-coverage confidence (flag, never suppress) ---------------

from app.services.job_search_service import search_jobs  # noqa: E402
from app.services.retrieval_confidence import opportunity_vocabulary, query_confidence  # noqa: E402

# Held-out queries: none of these appear in data/evaluation/m4/cases.
HELD_OUT_GENUINE = ["Kotlin mobile developer graduate", "data visualization internship with Power BI", "deep learning research intern",
                    "selenium automation tester", "web developer HTML CSS internship", "ETL data engineer"]
HELD_OUT_OFFTOPIC = ["veterinary assistant", "barista coffee shop", "airline cabin crew", "fashion stylist", "yoga instructor", "hotel management trainee"]


@pytest.mark.parametrize("query", HELD_OUT_GENUINE)
def test_genuine_held_out_queries_are_confident(query: str) -> None:
    assert query_confidence(query) == "confident"


@pytest.mark.parametrize("query", HELD_OUT_OFFTOPIC)
def test_off_topic_held_out_queries_are_flagged(query: str) -> None:
    assert query_confidence(query) == "unsupported_area"


def test_vocabulary_comes_from_the_catalogue_not_a_hard_coded_list() -> None:
    vocabulary = opportunity_vocabulary()
    for job in list(JOBS.values())[:20]:
        assert any(word in vocabulary for word in job.domain.lower().replace("/", " ").split())
    assert "internship" not in vocabulary and "the" not in vocabulary


def test_flagged_searches_still_return_results() -> None:
    results = search_jobs("airline cabin crew", top_k=5)
    assert len(results) == 5
    assert {r.query_confidence for r in results} == {"unsupported_area"}
    assert {r.query_confidence for r in search_jobs("Kotlin mobile developer graduate", top_k=3)} == {"confident"}


def test_assistant_discovery_says_when_the_area_is_not_covered(db: Session) -> None:
    profile, _ = seed(db, BACKEND_STUDENT)
    reply = ask(db, profile.user_id, "Find internships in veterinary nursing")
    assert reply.intent == "JOB_DISCOVERY"
    assert reply.content.startswith("I couldn't find opportunities that closely match")
    covered = ask(db, profile.user_id, "Find internships in mobile app development")
    assert covered.content.startswith('Here are opportunities for "')


# --- Experiment 7: provenance of profile-only (self-reported) skills ---------------

def test_profile_only_skill_counts_but_is_described_as_self_reported(db: Session) -> None:
    from app.services.resume_customization_service import generate_customization
    from app.services.skill_gap_service import analyze_skill_gap
    # Terraform is typed into the profile only; Git is backed by the resume.
    data = {**BACKEND_STUDENT, "skills": ["Git", "Linux"]}
    profile, resume = seed(db, data, profile_skills=["Terraform"])
    job = JOBS["JOB-0110"]  # Cloud: required Linux, Networking, Cloud Fundamentals, Git; preferred AWS, Docker, Terraform, ...
    gap = analyze_skill_gap(db, resume.id, job.job_id, profile.user_id)
    terraform = next(item for item in gap.strengths if item.requirement == "Terraform")
    assert "self-reported" in terraform.reason and "demonstrated" not in terraform.reason
    git = next(item for item in gap.strengths if item.requirement == "Git")
    assert "self-reported" not in git.reason

    customization = generate_customization(db, resume.id, job.job_id, profile.user_id, llm_provider=NullLLMProvider())
    keyword = next(k for k in customization.keyword_classification if k.keyword == "Terraform")
    assert keyword.status == "supported" and "self-reported" in keyword.reason


def test_matching_reasoning_names_self_reported_skills_only() -> None:
    from types import SimpleNamespace
    from app.schemas.job_chunk import JobSearchResult
    from app.services.job_matching import _result, normalize_profile
    job = JOBS["JOB-0110"]
    profile = SimpleNamespace(skills=["Terraform"], education="B.Tech Computer Science", degree=None, specialization=None,
                              experience_level=None, career_interests=[], target_roles=[], career_goals=None)
    structured = {"skills": ["Git", "Linux"], "projects": [], "experience": [], "internships": []}
    stub = JobSearchResult(job_id=job.job_id, job_title=job.job_title, company=job.company, domain=job.domain, location=job.location, work_mode=job.work_mode,
                           employment_type=job.employment_type, required_skills=job.required_skills, preferred_skills=job.preferred_skills, similarity_score=0.0, matched_chunk_types=[])
    result = _result(job, stub, normalize_profile(profile, structured))
    assert "Terraform" in result.matched_preferred_skills
    assert "Self-reported in your career profile (no resume evidence yet): Terraform." in result.reasoning
    assert "Git" not in result.reasoning.split("Self-reported")[1]


def test_profile_skill_that_the_resume_also_mentions_is_not_self_reported() -> None:
    from types import SimpleNamespace
    from app.services.job_matching import normalize_profile
    profile = SimpleNamespace(skills=["Docker", "Kubernetes"], education=None, degree=None, specialization=None,
                              experience_level=None, career_interests=[], target_roles=[], career_goals=None)
    structured = {"skills": [], "projects": [{"title": "Deploy Bot", "raw_text": "Deploy Bot - containerised with Docker", "technologies": []}],
                  "experience": [], "internships": []}
    assert normalize_profile(profile, structured).self_reported_skills == ["kubernetes"]


# --- Experiment 8: chunk texts lead with title and opportunity type ---------------

@pytest.mark.parametrize("query, title, opportunity_type", [
    ("graduate mobile engineer", "Graduate Mobile Engineer", "Graduate Role"),
    ("QA engineering trainee", "QA Engineering Trainee", "Trainee"),
    ("junior java backend developer", "Junior Java Backend Developer", "Entry Level"),
    ("flutter intern entry level", "Flutter Intern", "Entry Level"),
    ("security apprentice role", "Security Apprentice", "Apprenticeship"),
])
def test_title_and_type_specific_queries_rank_the_right_posting_first(query: str, title: str, opportunity_type: str) -> None:
    top = search_jobs(query, top_k=1)[0]
    assert (top.job_title, top.employment_type) == (title, opportunity_type)


def test_overview_chunk_leads_with_title_and_type_and_the_canonical_index_matches() -> None:
    import json
    from app.services.job_chunking import chunk_job_posting
    from app.services.job_vector_store import INDEX_VERSION, METADATA_PATH
    job = JOBS["JOB-0095"]
    overview, requirements, responsibilities = chunk_job_posting(job)
    assert overview.text.startswith(f"{job.job_title} ({job.employment_type}). ")
    assert requirements.text.startswith("Requirements for") and responsibilities.text.startswith("Responsibilities for")
    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    assert metadata["index_version"] == INDEX_VERSION == "1.2"
    by_id = {chunk["chunk_id"]: chunk["text"] for chunk in metadata["chunks"]}
    assert by_id["JOB-0095::overview"] == chunk_job_posting(job)[0].text


# --- Experiment 9: local-first embedding model loading ---------------------------

from types import SimpleNamespace  # noqa: E402

import app.services.embedding_service as embedding_service  # noqa: E402


@pytest.fixture
def fake_model_loader(monkeypatch: pytest.MonkeyPatch):
    calls: list[dict] = []
    state = {"cached": True}

    class FakeSentenceTransformer:
        def __init__(self, name: str, **kwargs) -> None:
            calls.append({"name": name, **kwargs})
            if kwargs.get("local_files_only") and not state["cached"]:
                raise OSError("not in local cache")

    def use(cached: bool, allow_download: bool = True):
        state["cached"] = cached
        monkeypatch.setattr(embedding_service, "SentenceTransformer", FakeSentenceTransformer)
        monkeypatch.setattr(embedding_service, "get_settings", lambda: SimpleNamespace(embedding_model_name="org/model", embedding_allow_download=allow_download))
        embedding_service.get_embedding_model.cache_clear()
        return calls

    yield use
    embedding_service.get_embedding_model.cache_clear()  # the real model reloads lazily for later tests


def test_cached_model_loads_locally_without_any_network_attempt(fake_model_loader) -> None:
    calls = fake_model_loader(cached=True)
    embedding_service.get_embedding_model()
    assert calls == [{"name": "org/model", "local_files_only": True}]


def test_uncached_model_is_downloaded_only_when_allowed(fake_model_loader) -> None:
    calls = fake_model_loader(cached=False, allow_download=True)
    embedding_service.get_embedding_model()
    assert calls == [{"name": "org/model", "local_files_only": True}, {"name": "org/model"}]


def test_uncached_model_with_downloads_disabled_fails_clearly(fake_model_loader) -> None:
    calls = fake_model_loader(cached=False, allow_download=False)
    with pytest.raises(embedding_service.EmbeddingError, match="not in the local cache"):
        embedding_service.get_embedding_model()
    assert len(calls) == 1


# --- Experiment 10: in-process caches for the immutable dataset and index ----------

import json as _json  # noqa: E402
import os  # noqa: E402

import numpy as np  # noqa: E402

from app.schemas.job_chunk import JobChunk  # noqa: E402
from app.services import job_dataset_service, job_vector_store  # noqa: E402
from app.services.job_dataset_service import JobDatasetError, clear_job_postings_cache, load_job_postings  # noqa: E402


def test_cached_dataset_returns_the_same_content_in_a_fresh_list() -> None:
    first, second = load_job_postings(), load_job_postings()
    assert first == second and first is not second and len(first) == 320
    first.clear()
    assert len(load_job_postings()) == 320  # a caller mutating its list cannot affect others


def test_changed_dataset_file_is_reloaded_and_revalidated(tmp_path) -> None:
    path = tmp_path / "jobs.json"
    payload = _json.loads(job_dataset_service.DATASET_PATH.read_text(encoding="utf-8"))
    path.write_text(_json.dumps(payload), encoding="utf-8")
    assert len(load_job_postings(path)) == 320
    payload[0]["job_id"] = payload[1]["job_id"]
    path.write_text(_json.dumps(payload), encoding="utf-8")
    os.utime(path, ns=(path.stat().st_atime_ns, path.stat().st_mtime_ns + 1_000_000_000))  # guarantee a new mtime
    with pytest.raises(JobDatasetError, match="Duplicate job_id"):
        load_job_postings(path)
    clear_job_postings_cache()
    assert len(load_job_postings()) == 320


def _chunk(job_id: str, chunk_type: str) -> JobChunk:
    return JobChunk(chunk_id=f"{job_id}::{chunk_type}", job_id=job_id, job_title="T", company="C", domain="D", chunk_type=chunk_type,
                    text=f"{job_id} {chunk_type}", location="L", work_mode="Remote", employment_type="Internship")


def test_rebuilt_vector_store_is_picked_up_and_validated(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(job_vector_store, "VECTOR_STORE_DIRECTORY", tmp_path)
    monkeypatch.setattr(job_vector_store, "INDEX_PATH", tmp_path / "jobs.faiss")
    monkeypatch.setattr(job_vector_store, "METADATA_PATH", tmp_path / "jobs.json")
    monkeypatch.setattr(job_vector_store, "embedding_dimension", lambda: 3)
    monkeypatch.setattr(job_vector_store, "get_model_name", lambda: "test-model")
    job_vector_store.save_vector_store(job_vector_store.build_index(np.eye(3, dtype=np.float32)[:2]), [_chunk("J1", "overview"), _chunk("J1", "requirements")])
    assert job_vector_store.load_vector_store()[0].ntotal == 2
    job_vector_store.save_vector_store(job_vector_store.build_index(np.eye(3, dtype=np.float32)), [_chunk("J1", "overview"), _chunk("J1", "requirements"), _chunk("J2", "overview")])
    for target in (job_vector_store.INDEX_PATH, job_vector_store.METADATA_PATH):
        os.utime(target, ns=(target.stat().st_atime_ns, target.stat().st_mtime_ns + 1_000_000_000))
    assert job_vector_store.load_vector_store()[0].ntotal == 3
    # A metadata file that no longer matches the index is still rejected after caching.
    metadata = _json.loads(job_vector_store.METADATA_PATH.read_text(encoding="utf-8"))
    metadata["index_version"] = "0.9"
    job_vector_store.METADATA_PATH.write_text(_json.dumps(metadata), encoding="utf-8")
    os.utime(job_vector_store.METADATA_PATH, ns=(0, job_vector_store.METADATA_PATH.stat().st_mtime_ns + 2_000_000_000))
    with pytest.raises(job_vector_store.VectorStoreError, match="index version"):
        job_vector_store.load_vector_store()
    job_vector_store.clear_vector_store_cache()


# --- Token usage: captured only when the provider reports it (no live calls) -------

import httpx as _httpx  # noqa: E402

from app.services.llm_provider import OpenAICompatibleProvider  # noqa: E402


@pytest.mark.parametrize("body, expected", [
    ({"choices": [{"message": {"content": "{\"ok\": true}"}}], "usage": {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150}},
     {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150}),
    ({"choices": [{"message": {"content": "{\"ok\": true}"}}]}, None),
])
def test_provider_records_reported_token_usage_and_never_invents_it(monkeypatch: pytest.MonkeyPatch, body: dict, expected) -> None:
    monkeypatch.setattr(_httpx, "post", lambda *args, **kwargs: _httpx.Response(200, json=body))
    provider = OpenAICompatibleProvider("http://fake.invalid/v1", None, "fake-model", 1.0)
    assert provider.generate_json("system", {"x": 1}) == {"ok": True}
    assert provider.last_usage == expected


# --- Prompt/validator contract: the LLM letter may name the role it applies to -----

class _ScriptedProvider:
    name, model = "fake", "fake-model"

    def __init__(self, extra_paragraph: str | None = None) -> None:
        self.extra_paragraph = extra_paragraph

    def generate_json(self, system_prompt: str, payload: dict) -> dict:
        evidence_id = payload["allowed_evidence"][0]["evidence_id"]
        paragraphs = [
            {"text": f"I am applying for the {payload['job']['title']} role at {payload['job']['company']}.", "evidence_ids": []},
            {"text": "I have used Python and Pandas in my survey analysis project.", "evidence_ids": [evidence_id]},
            {"text": "Thank you for your consideration.", "evidence_ids": []},
        ]
        if self.extra_paragraph:
            paragraphs.insert(2, {"text": self.extra_paragraph, "evidence_ids": [evidence_id]})
        return {
            "summary": "Student with Python and Pandas project experience.", "summary_evidence_ids": [evidence_id],
            "bullets": [{"source_path": item["source_path"], "rewritten_text": item["original_text"], "evidence_ids": [evidence_id], "job_keywords_used": []}
                        for item in payload["bullets_to_rewrite"]],
            "cover_letter_paragraphs": paragraphs,
        }


@pytest.mark.parametrize("extra, expected_mode", [(None, "llm"), ("I have professional FastAPI experience.", "deterministic_fallback")])
def test_llm_letter_naming_the_role_is_accepted_but_skill_claims_are_not(db: Session, extra: str | None, expected_mode: str) -> None:
    from app.services.resume_customization_service import generate_customization
    data = {**BACKEND_STUDENT, "skills": ["Python", "SQL", "Pandas"], "projects": [
        {"title": "Survey Stats", "description": "Survey analysis with Python and Pandas.", "raw_text": "Survey Stats - Survey analysis with Python and Pandas.", "technologies": ["Python", "Pandas"]}]}
    profile, resume = seed(db, data)
    result = generate_customization(db, resume.id, "JOB-0026", profile.user_id, llm_provider=_ScriptedProvider(extra))  # "FastAPI Intern"
    assert result.generation.mode == expected_mode
    assert "professional FastAPI experience" not in result.cover_letter_text
