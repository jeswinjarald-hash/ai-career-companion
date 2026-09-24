"""Milestone 3.4 — deterministic intent-detection unit tests. Pure functions, no DB."""

from app.services.assistant_intent import detect_intent, extract_job_ids


def test_job_id_extraction_is_case_insensitive_and_deduplicated():
    assert extract_job_ids("compare job-0035 and JOB-0036, then JOB-0035 again") == ["JOB-0035", "JOB-0036"]
    assert extract_job_ids("no ids here") == []


def test_job_discovery_intent():
    result = detect_intent("Which internships fit my resume?", active_job_id=None)
    assert result["intent"] == "JOB_DISCOVERY"
    assert result["requires_resume_context"] is True
    assert result["requires_job_context"] is False


def test_job_match_explanation_intent_uses_explicit_job_id():
    result = detect_intent("Why does JOB-0035 fit me?", active_job_id=None)
    assert result["intent"] == "JOB_MATCH_EXPLANATION"
    assert result["job_id"] == "JOB-0035"
    assert result["requires_job_context"] is True
    assert result["requires_resume_context"] is True


def test_skill_gap_intent():
    result = detect_intent("What skills am I missing?", active_job_id="JOB-0035")
    assert result["intent"] == "SKILL_GAP"
    assert result["job_id"] == "JOB-0035"


def test_resume_customization_intent():
    result = detect_intent("How should I improve my resume for this job?", active_job_id="JOB-0035")
    assert result["intent"] == "RESUME_CUSTOMIZATION"


def test_cover_letter_intent():
    result = detect_intent("Write a cover letter for this role.", active_job_id="JOB-0035")
    assert result["intent"] == "COVER_LETTER"


def test_interview_prep_intent():
    result = detect_intent("Prepare me for the interview.", active_job_id="JOB-0035")
    assert result["intent"] == "INTERVIEW_PREP"


def test_learning_guidance_intent():
    result = detect_intent("What should I learn next?", active_job_id="JOB-0035")
    assert result["intent"] == "LEARNING_GUIDANCE"


def test_profile_summary_intent():
    result = detect_intent("Tell me about my strongest projects.", active_job_id=None)
    assert result["intent"] == "PROFILE_SUMMARY"
    assert result["requires_job_context"] is False


def test_next_best_action_intent():
    result = detect_intent("What should I do next?", active_job_id=None)
    assert result["intent"] == "NEXT_BEST_ACTION"
    assert result["requires_job_context"] is False
    assert result["requires_resume_context"] is False


def test_general_career_chat_is_the_catch_all():
    result = detect_intent("hello, how are you today?", active_job_id=None)
    assert result["intent"] == "GENERAL_CAREER_CHAT"


def test_job_comparison_requires_two_job_ids():
    result = detect_intent("Compare JOB-0035 and JOB-0036", active_job_id=None)
    assert result["intent"] == "JOB_COMPARISON"
    assert result["job_id"] == "JOB-0035"
    assert result["second_job_id"] == "JOB-0036"
    assert result["requires_second_job_context"] is True


def test_job_comparison_with_one_id_uses_active_job_as_the_other():
    result = detect_intent("Compare this with JOB-0036", active_job_id="JOB-0035")
    assert result["intent"] == "JOB_COMPARISON"
    assert {result["job_id"], result["second_job_id"]} == {"JOB-0035", "JOB-0036"}


def test_job_comparison_with_no_ids_and_no_active_job_stays_unresolved():
    result = detect_intent("Compare these two roles for me", active_job_id=None)
    assert result["intent"] == "JOB_COMPARISON"
    assert result["job_id"] is None
    assert result["second_job_id"] is None


def test_active_job_id_carries_over_when_message_names_no_job():
    result = detect_intent("What am I missing for this role?", active_job_id="JOB-0035")
    assert result["job_id"] == "JOB-0035"


def test_explicit_job_id_in_message_overrides_active_job():
    result = detect_intent("Prepare me for JOB-0099 instead.", active_job_id="JOB-0035")
    assert result["job_id"] == "JOB-0099"
