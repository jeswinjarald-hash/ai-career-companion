"""Milestone 4.2 baseline tests over the current system (null LLM, synthetic data).

Three kinds of assertion, deliberately kept apart:

1. Correctness invariants (must always hold): no grounding violations, consistent
   job/resume identity across service handoffs, unchanged candidate evidence, no
   high-severity Matching <-> Skill Gap contradictions.
2. Regression floors: measured quality must not drop below the M4.2 baseline
   (floors sit slightly under the measured values in data/evaluation/m4/results/).
3. Known weaknesses: strict xfail tests that assert the DESIRED behaviour. They xfail
   today as baseline evidence for M4.3; if a later change fixes the behaviour the
   test XPASSes, which strict mode reports as a failure so the marker gets removed.
"""

import pytest

from app.services import m4_evaluation

KNOWN_WEAKNESS = "M4.2 baseline weakness, recorded for M4.3 (see data/evaluation/m4/README.md)"


@pytest.fixture(scope="module")
def cases() -> dict:
    return {
        "positive": m4_evaluation.load_case_file("retrieval_positive.json")["queries"],
        "negative": m4_evaluation.load_case_file("retrieval_negative.json")["queries"],
        "candidates": m4_evaluation.load_case_file("candidates.json"),
        "conversations": m4_evaluation.load_case_file("conversations.json"),
    }


@pytest.fixture(scope="module")
def positive(cases) -> dict:
    return m4_evaluation.evaluate_positive_retrieval(cases["positive"])


@pytest.fixture(scope="module")
def negative(cases, positive) -> dict:
    return m4_evaluation.evaluate_negative_retrieval(cases["negative"], positive["summary"])


@pytest.fixture(scope="module")
def scenarios(cases) -> dict:
    return m4_evaluation.evaluate_matching_scenarios(cases["candidates"]["matching_scenarios"])


@pytest.fixture(scope="module")
def consistency(cases) -> dict:
    return m4_evaluation.evaluate_consistency_and_grounding(cases["candidates"]["candidates"])


@pytest.fixture(scope="module")
def conversation(cases) -> dict:
    sb = next(c for c in cases["candidates"]["candidates"] if c["candidate_id"] == "SB")
    return m4_evaluation.evaluate_conversations(cases["conversations"], sb)


def _conversation(conversation: dict, conversation_id: str) -> dict:
    return next(c for c in conversation["conversations"] if c["conversation_id"] == conversation_id)


# --- RAG ----------------------------------------------------------------------

def test_positive_retrieval_reports_every_metric_for_every_query(positive, cases) -> None:
    assert len(positive["rows"]) == len(cases["positive"])
    for row in positive["rows"]:
        assert len(row["retrieved_job_ids"]) == m4_evaluation.RETRIEVAL_TOP_K
        assert set(row["metrics"]) == {f"@{k}" for k in m4_evaluation.RETRIEVAL_KS}


def test_positive_retrieval_does_not_regress_below_baseline(positive) -> None:
    summary = positive["summary"]
    assert summary["hit@5"] >= 0.95
    assert summary["hit@1"] >= 0.80
    assert summary["mrr@10"] >= 0.85
    assert summary["ndcg@10"] >= 0.85
    assert summary["top1_domain_accuracy"] >= 0.95


def test_negative_retrieval_is_measured_separately_from_positive_metrics(negative, cases) -> None:
    assert len(negative["rows"]) == len(cases["negative"])
    for row in negative["rows"]:
        assert row["top_score"] is not None and row["displayed_relevance_percent"] == round(row["top_score"] * 100)
    assert set(negative["summary"]["by_category"]) == {"unrelated", "nonsense", "out_of_coverage"}


# Resolved in M4.3 Experiment 6 (was a strict xfail asserting "no results"). The accepted
# strategy labels low-coverage queries instead of suppressing results, so the desired
# behaviour is now "suppressed or clearly flagged", and genuine queries stay unflagged.
def test_unrelated_and_nonsense_queries_are_suppressed_or_flagged(negative, positive) -> None:
    offenders = [row["query"] for row in negative["rows"]
                 if row["category"] in ("unrelated", "nonsense") and row["returned_count"] > 0 and row["query_confidence"] != "unsupported_area"]
    assert offenders == []
    assert positive["summary"]["flagged_unsupported_area"] == []


# --- Matching -------------------------------------------------------------------

def test_required_skills_outweigh_preferred_skills(scenarios) -> None:
    score = {row["scenario_id"]: row["match_score"] for row in scenarios["rows"]}
    assert score["A_required_strong"] > score["B_preferred_strong"]
    assert score["D_unsuitable"] == min(score.values()) and score["D_unsuitable"] < 40


# Resolved in M4.3 Experiment 3e (was a strict xfail in the M4.2 baseline).
def test_semantically_related_profile_scores_above_unsuitable_profile(scenarios) -> None:
    score = {row["scenario_id"]: row["match_score"] for row in scenarios["rows"]}
    assert score["C_semantic_not_exact"] > score["D_unsuitable"]


def test_m2_profile_matching_still_holds_on_current_dataset() -> None:
    result = m4_evaluation.evaluate_m2_profiles_on_current_dataset()
    assert result["top1_domain_accuracy"] >= 0.85
    assert result["top3_hit_rate"] >= 0.95


# --- Consistency & grounding ----------------------------------------------------

def test_no_grounding_violations_in_any_service(consistency) -> None:
    summary = consistency["grounding_summary"]
    assert summary["pairs_checked"] >= 8
    assert summary["checks_run"] > 500
    assert summary["violations"] == [], summary["violations"]


def test_no_high_severity_matching_skill_gap_contradictions(consistency) -> None:
    summary = consistency["consistency_summary"]
    high = [f for f in summary["findings"] if f["severity"] == "high"]
    assert high == []
    assert "candidate_evidence_mutated" not in summary["findings_by_type"]


# Resolved in M4.3 Experiment 4 (was a strict xfail in the M4.2 baseline).
def test_matching_and_skill_gap_agree_on_education(consistency) -> None:
    assert consistency["consistency_summary"]["findings_by_type"].get("education_disagreement", 0) == 0


def test_absent_skills_are_reported_as_gaps_and_interview_topics(consistency) -> None:
    ga_pairs = [p for p in consistency["pairs"] if p["candidate_id"] == "GA"]
    assert len(ga_pairs) == 3
    assert all(not p["grounding"]["violations"] for p in ga_pairs)


def test_service_handoff_keeps_resume_and_job_identity(cases) -> None:
    sb = next(c for c in cases["candidates"]["candidates"] if c["candidate_id"] == "SB")
    handoff = m4_evaluation.evaluate_handoff_chain(sb, "JOB-0035")
    failed = [c for c in handoff["checks"] if not c["holds"]]
    assert failed == []
    assert len(handoff["checks"]) >= 10


# --- Conversation ---------------------------------------------------------------

@pytest.mark.parametrize("conversation_id", [
    "CV02_context_retention_supported_phrasing", "CV03_job_switch", "CV04_short_follow_up",
    "CV05_profile_awareness", "CV07_explicit_comparison",
])
def test_supported_conversation_patterns_retain_and_switch_context(conversation, conversation_id) -> None:
    result = _conversation(conversation, conversation_id)
    failures = [(t["message"], t["outcomes"]) for t in result["turns"] if not t["passed"]]
    assert failures == []


# Resolved in M4.3 Experiment 2 (was a strict xfail in the M4.2 baseline).
def test_compare_me_with_job_phrasing_keeps_context_across_follow_ups(conversation) -> None:
    assert _conversation(conversation, "CV01_context_retention_compare_phrasing")["passed"]


@pytest.mark.xfail(strict=True, reason=f"{KNOWN_WEAKNESS}: free-form career questions receive a fixed capability message; "
                   "a substantive answer needs the LLM path, which the deterministic evaluation cannot measure (M4.3 Experiment 2b, deferred)")
def test_general_career_question_gets_a_substantive_answer(conversation) -> None:
    assert _conversation(conversation, "CV06_general_question")["passed"]


# Resolved in M4.3 Experiment 1 (was a strict xfail in the M4.2 baseline).
def test_job_discovery_uses_the_requested_area(conversation) -> None:
    discovery = conversation["job_discovery"]
    assert not discovery["identical_results_for_different_queries"]
    assert discovery["expected_domain_hit_rate"] >= 0.67
