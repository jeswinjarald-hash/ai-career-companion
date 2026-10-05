"""Milestone 4.2 — integrity of the evaluation framework itself: case files are
grounded in the real 320-record dataset, labels still reproduce from their stated
rules, the metric arithmetic is right, the grounding/consistency checkers actually
detect injected faults (so a "0 violations" result is meaningful), and the null-LLM
guard restores the patched bindings.
"""

import copy
from types import SimpleNamespace

import pytest

import app.services.assistant_service as assistant_service
from app.schemas.skill_gap import SkillGapSummary
from app.services import m4_evaluation
from app.services.job_dataset_service import load_job_postings
from app.services.llm_provider import NullLLMProvider

JOBS = {job.job_id: job for job in load_job_postings()}


def _rule_ids(rule: dict) -> set[str]:
    return {
        job.job_id for job in JOBS.values()
        if (not rule.get("domain") or job.domain == rule["domain"])
        and (not rule.get("domains") or job.domain in rule["domains"])
        and (not rule.get("titles") or job.job_title in rule["titles"])
        and (not rule.get("types") or job.employment_type in rule["types"])
    }


def test_positive_retrieval_labels_reference_real_jobs_and_reproduce_from_their_rules() -> None:
    cases = m4_evaluation.load_case_file("retrieval_positive.json")["queries"]
    assert len(cases) >= 20
    assert len({case["query_id"] for case in cases}) == len(cases)
    for case in cases:
        relevant, acceptable = set(case["relevant_job_ids"]), set(case["acceptable_job_ids"])
        assert relevant, case["query_id"]
        assert relevant | acceptable <= set(JOBS), case["query_id"]
        assert not relevant & acceptable, case["query_id"]
        assert relevant == _rule_ids(case["relevant_rule"]), f"{case['query_id']} labels drifted from the dataset"
        assert acceptable == _rule_ids(case["acceptable_rule"]) - relevant, case["query_id"]
        assert all(JOBS[job_id].domain == case["expected_domain"] for job_id in relevant), case["query_id"]
    covered = {case["expected_domain"] for case in cases}
    assert len(covered) >= 12, f"positive queries cover only {len(covered)} domains"


def test_negative_queries_are_labelled_by_category_without_relevant_jobs() -> None:
    cases = m4_evaluation.load_case_file("retrieval_negative.json")["queries"]
    assert {case["category"] for case in cases} == {"unrelated", "nonsense", "out_of_coverage"}
    for case in cases:
        assert "relevant_job_ids" not in case
    assert any(case["query"] == "zzzz qqqq" for case in cases)


def test_candidate_fixtures_target_real_jobs_and_use_the_persisted_resume_shape() -> None:
    cases = m4_evaluation.load_case_file("candidates.json")
    for candidate in cases["candidates"]:
        assert set(candidate["target_job_ids"]) <= set(JOBS)
        data = candidate["structured_data"]
        for key in ("skills", "education", "experience", "internships", "projects", "certifications", "learning"):
            assert key in data, (candidate["candidate_id"], key)
        assert all(isinstance(item, dict) and "raw_text" in item for item in data["learning"]), "learning entries must match the parser's {raw_text} shape"
        claimed = {skill.casefold() for skill in data["skills"] + candidate["profile"]["skills"]}
        assert not claimed & {term.casefold() for term in candidate["must_not_claim"]}, candidate["candidate_id"]
    scenarios = cases["matching_scenarios"]
    assert scenarios["target_job_id"] in JOBS
    assert {s["scenario_id"] for s in scenarios["scenarios"]} == {"A_required_strong", "B_preferred_strong", "C_semantic_not_exact", "D_unsuitable"}


def test_conversation_cases_reference_real_jobs() -> None:
    spec = m4_evaluation.load_case_file("conversations.json")
    for conversation in spec["conversations"]:
        for turn in conversation["turns"]:
            expect = turn.get("expect", {})
            for job_id in [expect.get("job_id")] + expect.get("must_not_mention_job_titles_of", []) + expect.get("must_mention_job_titles_of", []):
                assert job_id is None or job_id in JOBS
    domains = {job.domain for job in JOBS.values()}
    assert all(probe["expected_domain"] in domains for probe in spec["job_discovery_probe"]["messages"])


def test_job_level_metrics_match_hand_computed_values() -> None:
    retrieved = ["J1", "J9", "J2", "J8", "J3"]
    relevant, acceptable = {"J2", "J3", "J4"}, {"J1"}
    at3 = m4_evaluation.job_level_metrics(retrieved, relevant, acceptable, 3)
    assert at3["hit"] == 1.0
    assert at3["precision"] == pytest.approx(1 / 3)
    assert at3["relaxed_precision"] == pytest.approx(2 / 3)
    assert at3["recall"] == pytest.approx(1 / 3)
    assert at3["reciprocal_rank"] == pytest.approx(1 / 3)
    # gains: rank1 grade1 -> 1/log2(2)=1; rank3 grade2 -> 3/log2(4)=1.5; ideal: 3/1 + 3/log2(3) + 3/2
    import math
    assert at3["ndcg"] == pytest.approx(2.5 / (3 + 3 / math.log2(3) + 1.5))
    miss = m4_evaluation.job_level_metrics(["X", "Y"], {"J2"}, set(), 2)
    assert miss["hit"] == 0.0 and miss["reciprocal_rank"] == 0.0 and miss["ndcg"] == 0.0


def _clean_outputs(job_id: str = "JOB-0035"):
    """Minimal, internally consistent service outputs for a candidate who has Python only."""
    job = JOBS[job_id]
    match = {"matched_required_skills": ["Python"], "matched_preferred_skills": [], "missing_required_skills": [s for s in job.required_skills if s != "Python"],
             "strengths": ["Python matched"], "match_score": 30.0, "raw_education_score": None, "raw_experience_score": 1.0}
    summary = SkillGapSummary(overall_readiness=35, required_requirements_met=1, required_requirements_total=4, preferred_requirements_met=0,
                              preferred_requirements_total=5, critical_gap_count=3, partial_gap_count=0, preferred_gap_count=5,
                              experience_gap_count=0, qualification_gap_count=0, score_breakdown=[])
    gap_item = lambda req: SimpleNamespace(requirement=req, match_type="missing")  # noqa: E731
    gap = SimpleNamespace(summary=summary, strengths=[SimpleNamespace(requirement="Python", evidence=[SimpleNamespace(source="resume_skills", evidence='"Python" is listed in your resume skills section.')])],
                          critical_gaps=[gap_item(s) for s in job.required_skills if s != "Python"], partial_gaps=[], preferred_gaps=[], experience_gaps=[])
    tailored = SimpleNamespace(skills=["Python"], summary="Student with Python experience.", projects=[], experience=[], internships=[], education=[], certifications=[])
    customization = SimpleNamespace(tailored_resume=tailored, evidence=[SimpleNamespace(evidence_id="E1")], keyword_classification=[],
                                    cover_letter=[SimpleNamespace(text="I have used Python in coursework.", evidence_ids=["E1"])],
                                    validation=SimpleNamespace(removed_claims=[], passed=True))
    prep = SimpleNamespace(evidence=[], preparation_summary="Review the job requirements.", revision_plan=[SimpleNamespace(topic=s) for s in job.required_skills],
                           questions=[], validation=SimpleNamespace(passed=True))
    candidate = {"profile": {"skills": []}, "structured_data": {"skills": ["Python"], "projects": [], "learning": []},
                 "must_not_claim": ["Docker", "FastAPI", "REST APIs"]}
    return candidate, job, match, gap, customization, prep


def test_grounding_checker_passes_clean_outputs() -> None:
    result = m4_evaluation.grounding_checks(*_clean_outputs())
    assert result["violations"] == []
    assert result["checks_run"] > 0


@pytest.mark.parametrize("mutation, expected", [
    (lambda c, j, m, g, cu, p: m["matched_preferred_skills"].append("Docker"), ("matching", "absent_skill_matched")),
    (lambda c, j, m, g, cu, p: g.strengths.append(SimpleNamespace(requirement="FastAPI", evidence=[])), ("skill_gap", "absent_skill_as_strength")),
    (lambda c, j, m, g, cu, p: g.strengths[0].evidence.append(SimpleNamespace(source="project", evidence="Built a Kubernetes operator")), ("skill_gap", "evidence_not_in_candidate_data")),
    (lambda c, j, m, g, cu, p: cu.tailored_resume.skills.append("Docker"), ("customization", "absent_skill_in_tailored_skills")),
    (lambda c, j, m, g, cu, p: setattr(cu.tailored_resume, "summary", "Student who led a team of 5 engineers."), ("customization", "fabrication_in_summary")),
    (lambda c, j, m, g, cu, p: cu.tailored_resume.certifications.append("AWS Certified Developer"), ("customization", "invented_certification")),
    (lambda c, j, m, g, cu, p: cu.cover_letter.append(SimpleNamespace(text="I deployed services with Docker.", evidence_ids=[])), ("cover_letter", "fabrication_in_sentence")),
    (lambda c, j, m, g, cu, p: cu.cover_letter.append(SimpleNamespace(text="I enjoy learning.", evidence_ids=["E404"])), ("cover_letter", "unknown_evidence_id")),
    # Naming the role is allowed, but a skill claim in the same sentence is still caught (M4.3 Experiment 5).
    (lambda c, j, m, g, cu, p: cu.cover_letter.append(SimpleNamespace(text=f"For the {j.job_title} role at {j.company}, I bring Docker experience.", evidence_ids=[])), ("cover_letter", "fabrication_in_sentence")),
    (lambda c, j, m, g, cu, p: setattr(p, "revision_plan", []), ("interview_prep", "missing_required_skill_not_a_prep_topic")),
])
def test_grounding_checker_detects_injected_fabrication(mutation, expected) -> None:
    outputs = list(copy.deepcopy(_clean_outputs()))
    mutation(*outputs)
    violations = {(v["service"], v["check"]) for v in m4_evaluation.grounding_checks(*outputs)["violations"]}
    assert expected in violations


def test_consistency_checker_flags_contradictions_and_ignores_agreement() -> None:
    candidate, job, match, gap, _, _ = _clean_outputs()
    assert m4_evaluation.compare_match_and_skill_gap(match, gap, job) == []

    contradictory = dict(match, matched_required_skills=["Python", "SQL"], match_score=80.0)
    types = {f["type"] for f in m4_evaluation.compare_match_and_skill_gap(contradictory, gap, job)}
    assert {"matched_vs_missing", "high_score_most_required_missing", "score_divergence"} <= types


def test_null_llm_guard_forces_and_restores_provider_bindings() -> None:
    original = assistant_service.get_llm_provider
    with m4_evaluation.null_llm():
        assert isinstance(assistant_service.get_llm_provider(None), NullLLMProvider)
    assert assistant_service.get_llm_provider is original
