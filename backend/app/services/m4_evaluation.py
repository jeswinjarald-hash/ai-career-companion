"""Milestone 4.2 — evaluation framework (measurement only, no behaviour changes).

Extends the Milestone 2.4 harness (`m2_4_evaluation.py`) for the current 320-record
dataset with:

- job-level graded retrieval metrics (relevant = 2, acceptable = 1) next to the
  existing domain-level metrics;
- off-topic / nonsense / out-of-coverage retrieval measurement (scores shown to the
  student, overlap with genuine queries) — no threshold exists and none is added;
- per-job matching scenarios (required vs preferred, semantic vs exact, unsuitable);
- Job Matching <-> Skill Gap contradiction detection for the same candidate + job;
- structured grounding checks over matching, skill gap, customization, cover letter,
  interview preparation and the assistant for candidates with known absent skills;
- a resume -> match -> gap -> customization -> interview-prep handoff chain;
- multi-turn assistant scripts and a job-discovery query-sensitivity probe.

Everything runs against a throw-away in-memory database seeded with synthetic
candidates from `data/evaluation/m4/cases/`, and always under `null_llm()` so no
live LLM provider can be reached regardless of `backend/.env`. Results are
observations: a failed "desired" check is baseline evidence for M4.3, never a reason
to change production behaviour here.
"""

import copy
import json
import math
import re
import statistics
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import Base
from app.models import CandidateProfile, Resume, StructuredResume
from app.schemas.job_chunk import JobSearchResult
from app.schemas.job_posting import JobPosting
from app.services.customization_validator import check_fabrication, check_fabrication_patterns
from app.services.job_dataset_service import load_job_postings
from app.services.job_matching import (
    MATCH_WEIGHTS, _result, match_jobs_for_profile, normalize_profile, normalize_term, score_education, score_experience,
)
from app.services.job_search_service import search_jobs
from app.services.llm_provider import NullLLMProvider

BACKEND_ROOT = Path(__file__).resolve().parents[2]
M4_EVALUATION_DIR = BACKEND_ROOT / "data" / "evaluation" / "m4"
CASES_DIR = M4_EVALUATION_DIR / "cases"
RESULTS_DIR = M4_EVALUATION_DIR / "results"
M2_EVALUATION_DIR = BACKEND_ROOT / "data" / "evaluation"

RETRIEVAL_KS = (1, 3, 5, 10)
RETRIEVAL_TOP_K = 10
CONTEXT_REQUEST_PREFIXES = ("Which opportunity would you like", "To compare two opportunities", "I couldn't find an opportunity")
GENERAL_FALLBACK_PREFIX = "I can help with job recommendations"


def load_case_file(name: str) -> dict[str, Any]:
    return json.loads((CASES_DIR / name).read_text(encoding="utf-8"))


def _jobs_by_id() -> dict[str, JobPosting]:
    return {job.job_id: job for job in load_job_postings()}


# --------------------------------------------------------------------------- LLM safety

@contextmanager
def null_llm() -> Iterator[None]:
    """Forces every module that binds its own `get_llm_provider` to return the null
    provider for the duration of the evaluation (the same bindings the test-suite
    guard in `tests/conftest.py` patches), then restores them."""
    import app.api.interview_prep as interview_prep_api
    import app.services.assistant_service as assistant_service
    import app.services.interview_prep_service as interview_prep_service
    import app.services.resume_customization_service as resume_customization_service

    modules = (resume_customization_service, interview_prep_service, interview_prep_api, assistant_service)
    originals = [module.get_llm_provider for module in modules]
    try:
        for module in modules:
            module.get_llm_provider = lambda _settings: NullLLMProvider()
        yield
    finally:
        for module, original in zip(modules, originals):
            module.get_llm_provider = original


# --------------------------------------------------------------------------- retrieval

def grade(job_id: str, relevant: set[str], acceptable: set[str]) -> int:
    return 2 if job_id in relevant else 1 if job_id in acceptable else 0


def job_level_metrics(retrieved: list[str], relevant: set[str], acceptable: set[str], k: int) -> dict[str, float]:
    """Graded job-level metrics at cut-off k. Precision/hit/recall/MRR count only
    grade-2 (relevant) jobs; `relaxed_precision` also counts grade-1 (acceptable);
    nDCG uses both grades, with the ideal ranking built from the labels themselves."""
    top = retrieved[:k]
    grades = [grade(job_id, relevant, acceptable) for job_id in top]
    relevant_ranks = [rank for rank, value in enumerate(grades, start=1) if value == 2]
    dcg = sum((2 ** value - 1) / math.log2(rank + 1) for rank, value in enumerate(grades, start=1))
    ideal_grades = ([2] * len(relevant) + [1] * len(acceptable))[:k]
    idcg = sum((2 ** value - 1) / math.log2(rank + 1) for rank, value in enumerate(ideal_grades, start=1))
    return {
        "hit": float(bool(relevant_ranks)),
        "precision": len(relevant_ranks) / k,
        "relaxed_precision": sum(1 for value in grades if value >= 1) / k,
        "recall": len(relevant_ranks) / len(relevant) if relevant else 0.0,
        # Recall bounded by what fits in k — a fairer view when a label set is larger than k.
        "capped_recall": len(relevant_ranks) / min(len(relevant), k) if relevant else 0.0,
        "reciprocal_rank": 1 / relevant_ranks[0] if relevant_ranks else 0.0,
        "ndcg": dcg / idcg if idcg else 0.0,
    }


def _timed_search(query: str, top_k: int) -> tuple[list[JobSearchResult], float]:
    start = time.perf_counter()
    results = search_jobs(query, top_k=top_k)
    return results, (time.perf_counter() - start) * 1000


def evaluate_positive_retrieval(cases: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for case in cases:
        results, elapsed_ms = _timed_search(case["query"], RETRIEVAL_TOP_K)
        retrieved = [item.job_id for item in results]
        relevant, acceptable = set(case["relevant_job_ids"]), set(case["acceptable_job_ids"])
        rows.append({
            "query_id": case["query_id"], "query": case["query"], "expected_domain": case["expected_domain"],
            "relevant_count": len(relevant), "retrieved_job_ids": retrieved,
            "retrieved_grades": [grade(job_id, relevant, acceptable) for job_id in retrieved],
            "retrieved_domains": [item.domain for item in results],
            "top1_score": round(results[0].similarity_score, 4) if results else None,
            "top1_domain_correct": bool(results) and results[0].domain == case["expected_domain"],
            "query_confidence": getattr(results[0], "query_confidence", "confident") if results else None,
            "metrics": {f"@{k}": job_level_metrics(retrieved, relevant, acceptable, k) for k in RETRIEVAL_KS},
            "latency_ms": round(elapsed_ms, 1),
        })
    summary: dict[str, Any] = {"query_count": len(rows)}
    for k in RETRIEVAL_KS:
        for name in ("hit", "precision", "relaxed_precision", "recall", "capped_recall", "ndcg"):
            summary[f"{name}@{k}"] = round(statistics.mean(row["metrics"][f"@{k}"][name] for row in rows), 4)
    summary["mrr@10"] = round(statistics.mean(row["metrics"]["@10"]["reciprocal_rank"] for row in rows), 4)
    summary["top1_domain_accuracy"] = round(statistics.mean(float(row["top1_domain_correct"]) for row in rows), 4)
    top1_scores = [row["top1_score"] for row in rows if row["top1_score"] is not None]
    summary["top1_score"] = {"min": min(top1_scores), "median": round(statistics.median(top1_scores), 4), "max": max(top1_scores)}
    summary["top1_scores"] = top1_scores
    summary["flagged_unsupported_area"] = [row["query_id"] for row in rows if row["query_confidence"] == "unsupported_area"]
    summary["latency_ms"] = {"median": round(statistics.median(row["latency_ms"] for row in rows), 1), "max": max(row["latency_ms"] for row in rows)}
    weak = [row for row in rows if row["metrics"]["@5"]["hit"] == 0 or row["metrics"]["@1"]["hit"] == 0]
    return {"rows": rows, "summary": summary, "weak_cases": [
        {"query_id": row["query_id"], "query": row["query"], "first_relevant_rank": next((rank for rank, value in enumerate(row["retrieved_grades"], 1) if value == 2), None),
         "top5_grades": row["retrieved_grades"][:5], "top1_domain": row["retrieved_domains"][0] if row["retrieved_domains"] else None}
        for row in weak
    ]}


def evaluate_negative_retrieval(cases: list[dict[str, Any]], positive_summary: dict[str, Any], top_k: int = 5) -> dict[str, Any]:
    """Measures what an off-topic query shows the student. The Careers page renders
    `round(similarity_score * 100)%` as "relevance", so that is reported too."""
    positive_min = positive_summary["top1_score"]["min"]
    rows = []
    for case in cases:
        results, elapsed_ms = _timed_search(case["query"], top_k)
        scores = [round(item.similarity_score, 4) for item in results]
        rows.append({
            "query_id": case["query_id"], "query": case["query"], "category": case["category"],
            "returned_count": len(results), "top_score": scores[0] if scores else None,
            "displayed_relevance_percent": round(scores[0] * 100) if scores else None,
            "scores": scores, "top_results": [f"{item.job_id} {item.job_title} ({item.domain})" for item in results[:3]],
            "above_weakest_positive_top1": bool(scores) and scores[0] >= positive_min,
            "query_confidence": getattr(results[0], "query_confidence", "confident") if results else None,
            "latency_ms": round(elapsed_ms, 1),
        })
    by_category: dict[str, Any] = {}
    for category in sorted({row["category"] for row in rows}):
        members = [row for row in rows if row["category"] == category]
        by_category[category] = {
            "count": len(members),
            "always_returned_results": all(row["returned_count"] == top_k for row in members),
            "top_score_max": max(row["top_score"] for row in members),
            "top_score_median": round(statistics.median(row["top_score"] for row in members), 4),
        }
    negatives = [row for row in rows if row["category"] in ("unrelated", "nonsense")]
    max_negative = max(row["top_score"] for row in negatives)
    max_any = max(row["top_score"] for row in rows)
    positive_top1 = positive_summary["top1_scores"]
    return {
        "rows": rows,
        "summary": {
            "query_count": len(rows),
            "queries_returning_results": sum(1 for row in rows if row["returned_count"] > 0),
            "by_category": by_category,
            "positive_top1_score_min": positive_min,
            "unrelated_or_nonsense_top_score_max": max_negative,
            "score_ranges_overlap": max_negative >= positive_min,
            "gap_between_ranges": round(positive_min - max_negative, 4),
            "out_of_coverage_top_score_max": max(row["top_score"] for row in rows if row["category"] == "out_of_coverage"),
            # Genuine labelled queries whose best result scores below the best result of
            # some off-topic query — i.e. a threshold that hid every off-topic result would
            # also hide these genuine ones.
            "positive_queries_below_max_offtopic_score": sum(1 for score in positive_top1 if score < max_any),
            "positive_query_count": len(positive_top1),
            # Results are labelled, never removed: "flagged" = query_confidence unsupported_area.
            "confidence": {
                "negatives_flagged_or_suppressed": sum(1 for row in rows if row["returned_count"] == 0 or row["query_confidence"] == "unsupported_area"),
                "negative_query_count": len(rows),
                "negatives_not_flagged": [row["query_id"] for row in rows if row["returned_count"] and row["query_confidence"] != "unsupported_area"],
                "positives_flagged_or_suppressed": len(positive_summary.get("flagged_unsupported_area", [])),
                "positives_flagged": positive_summary.get("flagged_unsupported_area", []),
            },
        },
    }


# --------------------------------------------------------------------------- candidates

def new_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


@dataclass
class SeededCandidate:
    candidate: dict[str, Any]
    user_id: int
    profile: CandidateProfile
    resume: Resume
    structured: StructuredResume


def seed_candidate(db: Session, candidate: dict[str, Any], user_id: int) -> SeededCandidate:
    fields = candidate["profile"]
    profile = CandidateProfile(
        user_id=user_id, full_name=candidate["structured_data"].get("header") or candidate["candidate_id"],
        email=f"m4-eval-{candidate['candidate_id'].lower()}-{user_id}@example.com",
        education=fields.get("education"), degree=fields.get("degree"), specialization=fields.get("specialization"),
        experience_level=fields.get("experience_level"), career_interests=fields.get("career_interests", []),
        target_roles=fields.get("target_roles", []), skills=fields.get("skills", []), career_goals=fields.get("career_goals"),
    )
    db.add(profile)
    db.flush()
    resume = Resume(
        candidate_profile_id=profile.id, original_filename="synthetic.pdf", stored_filename=f"m4-eval-{user_id}.pdf",
        file_type="pdf", mime_type="application/pdf", file_size=1, storage_path="unused", status="structured",
    )
    db.add(resume)
    db.flush()
    structured = StructuredResume(resume_id=resume.id, data=copy.deepcopy(candidate["structured_data"]))
    db.add(structured)
    db.commit()
    return SeededCandidate(candidate, user_id, profile, resume, structured)


def candidate_corpus(candidate: dict[str, Any]) -> str:
    """All text the candidate actually supplied, normalized for containment checks."""
    parts: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, dict):
            for item in value.values():
                walk(item)

    walk(candidate["structured_data"])
    walk(candidate["profile"])
    return _norm_text(" ".join(parts))


def _norm_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def absent_terms(candidate: dict[str, Any]) -> set[str]:
    return {normalize_term(term) for term in candidate.get("must_not_claim", [])}


# --------------------------------------------------------------------------- matching

def match_for_job(profile: Any, structured_data: dict, job: JobPosting) -> dict[str, Any]:
    """The production per-job scorer (`job_matching._result`) applied to one chosen
    job, so a scenario's score does not depend on whether retrieval surfaced it."""
    normalized = normalize_profile(profile, structured_data)
    stub = JobSearchResult(
        job_id=job.job_id, job_title=job.job_title, company=job.company, domain=job.domain, location=job.location,
        work_mode=job.work_mode, employment_type=job.employment_type, required_skills=job.required_skills,
        preferred_skills=job.preferred_skills, similarity_score=0.0, matched_chunk_types=[],
    )
    result = _result(job, stub, normalized).model_dump()
    # Raw component values: `_result` reports an excluded (None) component as 0.0.
    result["raw_education_score"] = score_education(normalized, job).score
    result["raw_experience_score"] = score_experience(normalized, job).score
    return result


class _ProfileFields:
    def __init__(self, **values: Any) -> None:
        self.__dict__.update(values)


def evaluate_matching_scenarios(spec: dict[str, Any]) -> dict[str, Any]:
    job = _jobs_by_id()[spec["target_job_id"]]
    rows = []
    for scenario in spec["scenarios"]:
        profile = _ProfileFields(
            skills=scenario["skills"], education="B.Tech Computer Science", degree="B.Tech", specialization="Computer Science",
            experience_level="Fresher", career_interests=[], target_roles=[], career_goals=None,
        )
        structured = {"skills": scenario["skills"], "education": [], "experience": [], "internships": [],
                      "projects": [{"title": scenario["project"]["title"], "raw_text": scenario["project"]["title"],
                                    "description": scenario["project"]["description"], "technologies": scenario["project"]["technologies"]}],
                      "certifications": [], "achievements": [], "qualifications": []}
        start = time.perf_counter()
        result = match_for_job(profile, structured, job)
        retrieval = search_jobs(" ".join(scenario["skills"]), top_k=5)
        rows.append({
            "scenario_id": scenario["scenario_id"], "description": scenario["description"],
            "match_score": result["match_score"], "required_skills_score": result["required_skills_score"],
            "preferred_skills_score": result["preferred_skills_score"], "project_relevance_score": result["project_relevance_score"],
            "matched_required": result["matched_required_skills"], "missing_required": result["missing_required_skills"],
            "matched_preferred": result["matched_preferred_skills"],
            "semantic_top5_domains": [item.domain for item in retrieval],
            "semantic_target_domain_in_top5": job.domain in [item.domain for item in retrieval],
            "latency_ms": round((time.perf_counter() - start) * 1000, 1),
        })
    score = {row["scenario_id"]: row["match_score"] for row in rows}
    desired = [
        {"property": "A_required_strong scores above B_preferred_strong", "holds": score["A_required_strong"] > score["B_preferred_strong"],
         "values": [score["A_required_strong"], score["B_preferred_strong"]]},
        {"property": "D_unsuitable scores lowest and below 40", "holds": score["D_unsuitable"] == min(score.values()) and score["D_unsuitable"] < 40,
         "values": [score["D_unsuitable"]]},
        {"property": "C_semantic_not_exact scores above D_unsuitable", "holds": score["C_semantic_not_exact"] > score["D_unsuitable"],
         "values": [score["C_semantic_not_exact"], score["D_unsuitable"]]},
    ]
    return {"target_job_id": job.job_id, "weights": MATCH_WEIGHTS, "rows": rows, "desired_properties": desired}


def evaluate_m2_profiles_on_current_dataset() -> dict[str, Any]:
    """Re-runs the M2.4 profile-matching evaluation (reused unchanged) on today's dataset."""
    from app.services.m2_4_evaluation import evaluate_matching

    profiles = json.loads((M2_EVALUATION_DIR / "student_profiles.json").read_text(encoding="utf-8"))["profiles"]
    results = evaluate_matching(profiles, top_k=5)
    labelled = [result for result, profile in zip(results, profiles) if profile.get("primary_expected_domains")]
    return {
        "profile_count": len(results),
        "labelled_profile_count": len(labelled),
        "top1_domain_accuracy": round(statistics.mean(float(r.top1_correct) for r in labelled), 4),
        "top3_hit_rate": round(statistics.mean(float(r.top3_hit) for r in labelled), 4),
        "mrr": round(statistics.mean(r.reciprocal_rank for r in labelled), 4),
        "rows": [{"profile_id": r.profile_id, "top_domain": r.top_match_domain, "top_score": r.top_match_score,
                  "top1_correct": r.top1_correct, "score_behavior_pass": r.score_behavior_pass} for r in results],
    }


# --------------------------------------------------------------------------- consistency

def compare_match_and_skill_gap(match: dict[str, Any], gap: Any, job: JobPosting) -> list[dict[str, Any]]:
    """Flags meaningful semantic disagreements between M2 matching and M3.1 skill gap
    for the same candidate + job. Different algorithms are expected to differ in
    degree; only conflicting statements of fact or large score gaps are reported."""
    findings: list[dict[str, Any]] = []
    critical = {normalize_term(item.requirement) for item in gap.critical_gaps}
    weaker = {normalize_term(item.requirement): item.match_type for item in gap.partial_gaps + gap.preferred_gaps}
    strengths = {normalize_term(item.requirement) for item in gap.strengths}

    for skill in match["matched_required_skills"]:
        key = normalize_term(skill)
        if key in critical:
            findings.append({"type": "matched_vs_missing", "severity": "high", "skill": skill,
                             "detail": f"Matching counts required skill '{skill}' as matched; skill gap lists it as a critical (missing) gap."})
        elif key in weaker:
            findings.append({"type": "matched_vs_weaker", "severity": "low", "skill": skill,
                             "detail": f"Matching counts '{skill}' as fully matched; skill gap grades it '{weaker[key]}'."})
    for skill in match["missing_required_skills"]:
        if normalize_term(skill) in strengths:
            findings.append({"type": "missing_vs_demonstrated", "severity": "medium", "skill": skill,
                             "detail": f"Matching lists required skill '{skill}' as missing; skill gap reports it as a demonstrated strength."})

    required_ratio = gap.summary.required_requirements_met / gap.summary.required_requirements_total if gap.summary.required_requirements_total else 1.0
    if match["match_score"] >= 60 and required_ratio < 0.5:
        findings.append({"type": "high_score_most_required_missing", "severity": "high",
                         "detail": f"Match score {match['match_score']} while skill gap finds only {gap.summary.required_requirements_met}/{gap.summary.required_requirements_total} required skills met."})
    if abs(match["match_score"] - gap.summary.overall_readiness) >= 25:
        findings.append({"type": "score_divergence", "severity": "medium",
                         "detail": f"Match score {match['match_score']} vs skill-gap readiness {gap.summary.overall_readiness} (difference >= 25 points)."})

    gap_education = next((c for c in gap.summary.score_breakdown if c.component == "education"), None)
    if match["raw_education_score"] is not None and gap_education is not None and gap_education.included and gap_education.score is not None:
        if (match["raw_education_score"] >= 0.5) != (gap_education.score >= 0.5):
            findings.append({"type": "education_disagreement", "severity": "medium",
                             "detail": f"Matching education score {match['raw_education_score']} vs skill-gap education score {gap_education.score}."})
    experience_gaps = len(gap.experience_gaps)
    if match["raw_experience_score"] == 1.0 and experience_gaps:
        findings.append({"type": "experience_disagreement", "severity": "low",
                         "detail": f"Matching treats experience as fully satisfied; skill gap reports {experience_gaps} experience gap(s)."})
    return findings


def evaluate_consistency_and_grounding(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """For every candidate x target job: run matching, skill gap, customization (with
    cover letter) and interview preparation, then check cross-service consistency and
    grounding. Each candidate is seeded in its own in-memory database."""
    from app.services.interview_prep_service import generate_interview_preparation
    from app.services.resume_customization_service import generate_customization
    from app.services.skill_gap_service import analyze_skill_gap

    jobs = _jobs_by_id()
    pairs = []
    with null_llm():
        for index, candidate in enumerate(candidates, start=1):
            db = new_session()
            try:
                seeded = seed_candidate(db, candidate, user_id=index)
                before = copy.deepcopy(seeded.structured.data)
                for job_id in candidate["target_job_ids"]:
                    job = jobs[job_id]
                    match = match_for_job(seeded.profile, seeded.structured.data, job)
                    gap = analyze_skill_gap(db, seeded.resume.id, job_id, seeded.user_id)
                    customization = generate_customization(db, seeded.resume.id, job_id, seeded.user_id, llm_provider=NullLLMProvider())
                    prep = generate_interview_preparation(db, seeded.resume.id, job_id, seeded.user_id, llm_provider=NullLLMProvider())
                    pairs.append({
                        "candidate_id": candidate["candidate_id"], "job_id": job_id, "job_title": job.job_title,
                        "match_score": match["match_score"], "skill_gap_readiness": gap.summary.overall_readiness,
                        "required_met": f"{gap.summary.required_requirements_met}/{gap.summary.required_requirements_total}",
                        "consistency_findings": compare_match_and_skill_gap(match, gap, job),
                        "grounding": grounding_checks(candidate, job, match, gap, customization, prep),
                    })
                db.refresh(seeded.structured)
                if seeded.structured.data != before:
                    pairs.append({"candidate_id": candidate["candidate_id"], "job_id": None, "consistency_findings": [
                        {"type": "candidate_evidence_mutated", "severity": "high", "detail": "StructuredResume.data changed during downstream generation."}], "grounding": {}})
            finally:
                db.close()
    findings = [finding | {"candidate_id": pair["candidate_id"], "job_id": pair["job_id"]} for pair in pairs for finding in pair["consistency_findings"]]
    violations = [violation | {"candidate_id": pair["candidate_id"], "job_id": pair["job_id"]}
                  for pair in pairs for violation in pair["grounding"].get("violations", [])]
    review = [item | {"candidate_id": pair["candidate_id"], "job_id": pair["job_id"]}
              for pair in pairs for item in pair["grounding"].get("needs_review", [])]
    services = ["matching", "skill_gap", "customization", "cover_letter", "interview_prep"]
    return {
        "pairs": pairs,
        "consistency_summary": {
            "pairs_checked": len([p for p in pairs if p["job_id"]]),
            "findings_by_type": {t: sum(1 for f in findings if f["type"] == t) for t in sorted({f["type"] for f in findings})},
            "high_severity": sum(1 for f in findings if f["severity"] == "high"),
            "findings": findings,
        },
        "grounding_summary": {
            "pairs_checked": len([p for p in pairs if p["job_id"]]),
            "checks_run": sum(p["grounding"].get("checks_run", 0) for p in pairs),
            "violations": violations,
            "violations_by_service": {service: sum(1 for v in violations if v["service"] == service) for service in services},
            "needs_human_review": review,
        },
    }


def _skill_gap_evidence_is_grounded(evidence: Any, candidate: dict[str, Any], corpus: str) -> bool:
    """Skills-list evidence is a sentence citing one skill ('"X" is listed in your
    resume skills section.'), so it is grounded when X really is in that list; any
    other evidence is a (possibly truncated) quote of the candidate's own text."""
    if evidence.source in ("profile_skills", "resume_skills"):
        quoted = re.match(r'^"([^"]+)"', evidence.evidence)
        listed = candidate["profile"].get("skills", []) if evidence.source == "profile_skills" else candidate["structured_data"].get("skills", [])
        return quoted is not None and normalize_term(quoted.group(1)) in {normalize_term(skill) for skill in listed}
    return _norm_text(evidence.evidence.removesuffix("...")) in corpus


def grounding_checks(candidate: dict[str, Any], job: JobPosting, match: dict[str, Any], gap: Any, customization: Any, prep: Any) -> dict[str, Any]:
    """Structured (not prose-matching) checks that no service attributes an absent
    skill, invented experience/project/certification/education, or an evidence
    reference that does not exist. `needs_review` holds heuristic flags that are
    reported for a human to judge rather than counted as violations."""
    absent = absent_terms(candidate)
    corpus = candidate_corpus(candidate)
    candidate_projects = {_norm_text(p.get("title", "")) for p in candidate["structured_data"].get("projects", [])}
    violations: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    checks = 0

    def violate(service: str, check: str, detail: str) -> None:
        violations.append({"service": service, "check": check, "detail": detail})

    # Matching
    for skill in match["matched_required_skills"] + match["matched_preferred_skills"]:
        checks += 1
        if normalize_term(skill) in absent:
            violate("matching", "absent_skill_matched", skill)
    for line in match["strengths"]:
        checks += 1
        if any(re.search(rf"(?<![\w+#.]){re.escape(term)}(?![\w+#])", normalize_term(line)) for term in absent):
            violate("matching", "absent_skill_in_strengths", line)

    # Skill gap
    for item in gap.strengths:
        checks += 1
        if normalize_term(item.requirement) in absent:
            violate("skill_gap", "absent_skill_as_strength", item.requirement)
        for evidence in item.evidence:
            checks += 1
            if not _skill_gap_evidence_is_grounded(evidence, candidate, corpus):
                violate("skill_gap", "evidence_not_in_candidate_data", f"{item.requirement}: {evidence.evidence[:80]}")
    absent_required = [skill for skill in job.required_skills if normalize_term(skill) in absent]
    gap_requirements = {normalize_term(item.requirement) for item in gap.critical_gaps + gap.partial_gaps}
    for skill in absent_required:
        checks += 1
        if normalize_term(skill) not in gap_requirements:
            violate("skill_gap", "absent_required_skill_not_reported_as_gap", skill)

    # Customization (tailored resume)
    tailored = customization.tailored_resume
    evidence_ids = {record.evidence_id for record in customization.evidence}
    for skill in tailored.skills:
        checks += 1
        if normalize_term(skill) in absent:
            violate("customization", "absent_skill_in_tailored_skills", skill)
    for keyword in customization.keyword_classification:
        if normalize_term(keyword.keyword) in absent:
            checks += 1
            if keyword.status == "supported":
                violate("customization", "absent_skill_classified_supported", keyword.keyword)
    # Naming the target opportunity is not a skill claim (same rule as the product
    # validator since M4.3 Experiment 5); claims elsewhere in the sentence still count.
    opportunity_names = (job.job_title, job.company)
    texts = [("summary", tailored.summary)] + [("project", p.tailored_text) for p in tailored.projects] + \
            [("experience", b.tailored_text) for b in tailored.experience + tailored.internships]
    for label, text in texts:
        if not text:
            continue
        checks += 1
        reason = check_fabrication(text, absent, opportunity_names)
        if reason:
            violate("customization", f"fabrication_in_{label}", f"{reason}: {text[:100]}")
    for project in tailored.projects:
        checks += 1
        if _norm_text(project.title) not in candidate_projects:
            violate("customization", "invented_project", project.title)
    for bullet in tailored.experience + tailored.internships:
        checks += 1
        if bullet.introduced_claims:
            violate("customization", "introduced_claims_on_bullet", "; ".join(bullet.introduced_claims))
        if _norm_text(bullet.original_text) not in corpus:
            violate("customization", "experience_not_in_candidate_data", bullet.original_text[:100])
    for entry in tailored.education:
        checks += 1
        if _norm_text(entry.raw_text) not in corpus:
            violate("customization", "education_not_in_candidate_data", entry.raw_text[:100])
    for certification in tailored.certifications:
        checks += 1
        if _norm_text(certification) not in corpus:
            violate("customization", "invented_certification", certification)

    # Cover letter
    for sentence in customization.cover_letter:
        checks += 1
        reason = check_fabrication(sentence.text, absent, opportunity_names)
        if reason:
            violate("cover_letter", "fabrication_in_sentence", f"{reason}: {sentence.text[:100]}")
        checks += 1
        unknown = [eid for eid in sentence.evidence_ids if eid not in evidence_ids]
        if unknown:
            violate("cover_letter", "unknown_evidence_id", ", ".join(unknown))
    # Learning-only skills: exposure, never demonstrated capability, in any service.
    learning_terms = {normalize_term(part) for item in candidate["structured_data"].get("learning", []) or []
                      for part in str(item.get("raw_text", "") if isinstance(item, dict) else item).split(",") if normalize_term(part)}
    for term in learning_terms:
        checks += 4
        if term in {normalize_term(s) for s in match["matched_required_skills"] + match["matched_preferred_skills"]}:
            violate("matching", "learning_only_skill_matched", term)
        if term in {normalize_term(item.requirement) for item in gap.strengths}:
            violate("skill_gap", "learning_only_skill_as_strength", term)
        if any(normalize_term(k.keyword) == term and k.status == "supported" for k in customization.keyword_classification):
            violate("customization", "learning_only_skill_classified_supported", term)
        if term in {normalize_term(s) for s in tailored.skills}:
            violate("customization", "learning_only_skill_in_tailored_skills", term)

    # Profile-only skills (typed into the career profile, absent from every resume
    # section) are user-declared, so using them is not fabrication — but whether each
    # service presents them as demonstrated is recorded for review.
    resume_terms = {normalize_term(s) for s in candidate["structured_data"].get("skills", [])} | {
        normalize_term(t) for p in candidate["structured_data"].get("projects", []) for t in p.get("technologies", [])}
    job_terms = {normalize_term(s) for s in job.required_skills + job.preferred_skills}
    for term in {normalize_term(s) for s in candidate["profile"].get("skills", [])} - resume_terms:
        if term not in job_terms:
            continue
        # Since M4.3 Experiment 7 the skill may still count, but every service must say it
        # is self-reported; only an unqualified "demonstrated" presentation is flagged.
        self_reported = "self-reported"
        treated = [name for name, unqualified in (
            ("matching", term in {normalize_term(s) for s in match["matched_required_skills"] + match["matched_preferred_skills"]}
             and self_reported not in match["reasoning"].lower()),
            ("skill_gap", any(normalize_term(item.requirement) == term and self_reported not in item.reason.lower() for item in gap.strengths)),
            ("customization", any(normalize_term(k.keyword) == term and k.status == "supported" and self_reported not in k.reason.lower()
                                  for k in customization.keyword_classification)),
        ) if unqualified]
        if treated:
            review.append({"service": ",".join(treated), "check": "profile_only_skill_treated_as_demonstrated",
                           "detail": f"'{term}' appears only in the career profile (no resume evidence) but is presented as demonstrated, without saying it is self-reported, by: {', '.join(treated)}"})

    if customization.validation.removed_claims:
        review.append({"service": "customization", "check": "validator_removed_claims",
                       "detail": f"{len(customization.validation.removed_claims)} generated sentence(s) removed by the existing validator, e.g. \"{customization.validation.removed_claims[0][:120]}\" — reasons: {customization.validation.warnings[:1]}"})

    # Interview preparation
    job_requirements = {normalize_term(v) for v in job.required_skills + job.preferred_skills + job.qualifications + job.responsibilities + [job.experience_requirements, job.education_requirements, job.job_title, job.domain]}
    prep_evidence_ids = {record.evidence_id for record in prep.evidence}
    for text in [prep.preparation_summary] + [q.preparation_guidance for q in prep.questions]:
        checks += 1
        reason = check_fabrication_patterns(text)
        if reason:
            violate("interview_prep", "fabrication_pattern", f"{reason}: {text[:100]}")
    for question in prep.questions:
        checks += 1
        foreign = [req for req in question.source_requirements if normalize_term(req) not in job_requirements]
        if foreign:
            review.append({"service": "interview_prep", "check": "source_requirement_not_in_job_fields", "detail": f"{question.category}: {foreign}"})
        unknown = [eid for eid in question.source_evidence_ids if eid not in prep_evidence_ids]
        if unknown:
            violate("interview_prep", "unknown_evidence_id", ", ".join(unknown))
        if question.category in ("resume", "project"):
            normalized_question = normalize_term(question.question)
            hit = next((term for term in absent if re.search(rf"(?<![\w+#.]){re.escape(term)}(?![\w+#])", normalized_question)), None)
            if hit:
                review.append({"service": "interview_prep", "check": "absent_skill_in_resume_or_project_question", "detail": f"'{hit}': {question.question[:120]}"})
    prep_topics = {normalize_term(t) for q in prep.questions for t in q.topics_to_review + q.source_requirements} | {normalize_term(item.topic) for item in prep.revision_plan}
    prep_text = normalize_term(" ".join(q.question for q in prep.questions) + " " + " ".join(item.topic for item in prep.revision_plan))
    for skill in absent_required:
        checks += 1
        if normalize_term(skill) not in prep_topics and normalize_term(skill) not in prep_text:
            violate("interview_prep", "missing_required_skill_not_a_prep_topic", skill)
    return {"checks_run": checks, "violations": violations, "needs_review": review,
            "customization_validation_passed": customization.validation.passed, "interview_validation_passed": prep.validation.passed}


# --------------------------------------------------------------------------- handoff chain

def evaluate_handoff_chain(candidate: dict[str, Any], job_id: str) -> dict[str, Any]:
    """resume -> candidate context -> match -> skill gap -> customization -> interview
    prep for one candidate + job, checking identity and immutability at each step."""
    from app.services.candidate_context import build_candidate_context
    from app.services.interview_prep_service import generate_interview_preparation
    from app.services.job_matching import match_jobs_for_resume
    from app.services.resume_customization_service import generate_customization
    from app.services.skill_gap_service import analyze_skill_gap

    job = _jobs_by_id()[job_id]
    checks: list[dict[str, Any]] = []

    def check(name: str, holds: bool, detail: str = "") -> None:
        checks.append({"check": name, "holds": bool(holds), "detail": detail})

    with null_llm():
        db = new_session()
        try:
            seeded = seed_candidate(db, candidate, user_id=1)
            before = copy.deepcopy(seeded.structured.data)
            context = build_candidate_context(db, seeded.profile, seeded.resume)
            check("context_belongs_to_resume", context.resume_id == seeded.resume.id and context.candidate_profile_id == seeded.profile.id)
            matches = match_jobs_for_resume(db, seeded.resume.id, top_k=10)
            check("matches_reference_canonical_jobs", all(m.job_id in _jobs_by_id() for m in matches))
            matched = next((m for m in matches if m.job_id == job_id), None)
            check("target_job_retrieved_in_top10", matched is not None, f"retrieved: {[m.job_id for m in matches]}")
            gap = analyze_skill_gap(db, seeded.resume.id, job_id, seeded.user_id)
            check("skill_gap_same_job", gap.job_id == job_id and gap.job_title == job.job_title and gap.company == job.company)
            check("skill_gap_same_resume", gap.resume_id == seeded.resume.id and gap.profile_id == seeded.profile.id)
            customization = generate_customization(db, seeded.resume.id, job_id, seeded.user_id, llm_provider=NullLLMProvider())
            check("customization_same_job", customization.job_id == job_id and customization.job_title == job.job_title and customization.company == job.company)
            check("customization_same_resume", customization.resume_id == seeded.resume.id)
            check("cover_letter_present_in_same_customization", bool(customization.cover_letter_text.strip()) and bool(customization.cover_letter))
            prep = generate_interview_preparation(db, seeded.resume.id, job_id, seeded.user_id, llm_provider=NullLLMProvider())
            check("interview_prep_same_job", prep.job_id == job_id and prep.job_title == job.job_title and prep.company == job.company)
            check("interview_prep_same_resume", prep.resume_id == seeded.resume.id)
            db.refresh(seeded.structured)
            check("candidate_evidence_unchanged", seeded.structured.data == before)
            if matched is not None:
                check("matched_skills_agree_with_customization_supported_keywords",
                      {normalize_term(s) for s in matched.matched_required_skills} <= {normalize_term(k.keyword) for k in customization.keyword_classification if k.status == "supported"},
                      f"match: {matched.matched_required_skills}; supported: {[k.keyword for k in customization.keyword_classification if k.status == 'supported']}")
        finally:
            db.close()
    return {"candidate_id": candidate["candidate_id"], "job_id": job_id, "checks": checks, "all_hold": all(c["holds"] for c in checks)}


# --------------------------------------------------------------------------- conversation

def _job_mentions(content: str, job: JobPosting) -> bool:
    return job.job_title.casefold() in content.casefold()


def evaluate_conversations(spec: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    from app.services.assistant_service import create_conversation, send_message

    jobs = _jobs_by_id()
    absent = absent_terms(candidate)
    conversation_rows = []
    with null_llm():
        db = new_session()
        try:
            seeded = seed_candidate(db, candidate, user_id=1)
            for script in spec["conversations"]:
                conversation = create_conversation(db, seeded.user_id)
                turns = []
                for turn in script["turns"]:
                    response = send_message(db, seeded.user_id, conversation.id, turn["message"], llm_provider=NullLLMProvider())
                    message = response.message
                    expect = turn.get("expect", {})
                    asked_for_context = message.content.startswith(CONTEXT_REQUEST_PREFIXES)
                    outcomes: dict[str, bool] = {}
                    if "intent" in expect:
                        outcomes["intent"] = message.intent == expect["intent"]
                    if "job_id" in expect:
                        outcomes["job_id"] = message.job_id == expect["job_id"]
                    if expect.get("not_asking_for_context"):
                        outcomes["not_asking_for_context"] = not asked_for_context
                    for other in expect.get("must_not_mention_job_titles_of", []):
                        # Only meaningful when the other job's title differs from the expected one.
                        current = jobs.get(expect.get("job_id", ""))
                        if current is None or current.job_title != jobs[other].job_title:
                            outcomes[f"no_mention_of_{other}"] = not _job_mentions(message.content, jobs[other])
                    for other in expect.get("must_mention_job_titles_of", []):
                        outcomes[f"mentions_{other}"] = _job_mentions(message.content, jobs[other])
                    if "must_mention_any" in expect:
                        outcomes["mentions_expected_profile_fact"] = any(value.casefold() in message.content.casefold() for value in expect["must_mention_any"])
                    if expect.get("must_not_claim_skills"):
                        outcomes["no_absent_skill_claimed"] = check_fabrication(message.content, absent) is None
                    if expect.get("substantive_answer"):
                        outcomes["substantive_answer"] = not message.content.startswith(GENERAL_FALLBACK_PREFIX)
                    turns.append({"message": turn["message"], "intent": message.intent, "job_id": message.job_id,
                                  "active_job_id": response.active_job_id, "asked_for_context": asked_for_context,
                                  "response_preview": message.content[:220], "outcomes": outcomes,
                                  "passed": all(outcomes.values())})
                conversation_rows.append({"conversation_id": script["conversation_id"], "purpose": script["purpose"],
                                          "turns": turns, "passed": all(t["passed"] for t in turns)})
            discovery = _job_discovery_probe(db, seeded, spec["job_discovery_probe"]["messages"])
        finally:
            db.close()
    turn_total = sum(len(c["turns"]) for c in conversation_rows)
    return {
        "conversations": conversation_rows,
        "summary": {
            "conversations": len(conversation_rows),
            "conversations_fully_passing": sum(1 for c in conversation_rows if c["passed"]),
            "turns": turn_total,
            "turns_passing": sum(1 for c in conversation_rows for t in c["turns"] if t["passed"]),
        },
        "job_discovery": discovery,
    }


def _job_discovery_probe(db: Session, seeded: SeededCandidate, probes: list[dict[str, Any]]) -> dict[str, Any]:
    from app.services.assistant_service import create_conversation, send_message

    jobs = _jobs_by_id()
    rows = []
    for probe in probes:
        conversation = create_conversation(db, seeded.user_id)
        response = send_message(db, seeded.user_id, conversation.id, probe["message"], llm_provider=NullLLMProvider())
        listed = [action.job_id for action in response.message.suggested_actions if action.job_id]
        # The reply lists titles; recover every listed job from the facts-backed lines.
        titles_in_reply = [line[2:].split(" at ")[0] for line in response.message.content.splitlines() if line.startswith("- ")]
        domains = sorted({jobs[job_id].domain for job_id in listed})
        rows.append({"message": probe["message"], "expected_domain": probe["expected_domain"], "intent": response.message.intent,
                     "suggested_job_ids": listed, "listed_titles": titles_in_reply, "suggested_domains": domains,
                     "expected_domain_present": probe["expected_domain"] in domains})
    distinct_results = {tuple(row["listed_titles"]) for row in rows}
    return {"rows": rows, "identical_results_for_different_queries": len(distinct_results) == 1,
            "expected_domain_hit_rate": round(statistics.mean(float(row["expected_domain_present"]) for row in rows), 4)}


# --------------------------------------------------------------------------- runner

def dataset_fingerprint() -> dict[str, Any]:
    from app.core.config import get_settings
    from app.services.job_vector_store import INDEX_PATH, load_vector_store

    index, chunks = load_vector_store()
    return {
        "dataset_file": "backend/data/internships/career_opportunities_320.json",
        "dataset_size": len(load_job_postings()),
        "chunk_count": len(chunks), "vector_count": int(index.ntotal), "index_type": type(index).__name__,
        "similarity": "inner product on L2-normalised embeddings (cosine)",
        "embedding_model": get_settings().embedding_model_name, "embedding_dimension": int(index.d),
        "index_file": INDEX_PATH.relative_to(BACKEND_ROOT).as_posix(),
        "retrieval": ("all chunks searched; per-job score = best chunk + 0.05 x sum(other chunks); no score threshold "
                      "(results are never suppressed); each result carries a query-coverage confidence flag (M4.3 E6)"),
    }


METRIC_DEFINITIONS = {
    "hit@k": "1 if any grade-2 (relevant) job is in the top k, averaged over queries.",
    "precision@k": "grade-2 jobs in the top k divided by k.",
    "relaxed_precision@k": "grade-1 or grade-2 jobs in the top k divided by k.",
    "recall@k": "grade-2 jobs in the top k divided by all grade-2 jobs for the query (bounded by k / label count).",
    "capped_recall@k": "grade-2 jobs in the top k divided by min(label count, k).",
    "mrr@10": "mean of 1 / rank of the first grade-2 job within the top 10 (0 if none).",
    "ndcg@k": "graded nDCG with gains 3 (relevant) and 1 (acceptable); ideal ranking built from the labels.",
    "top1_domain_accuracy": "top-ranked job's domain equals the query's expected domain.",
    "negative: above_weakest_positive_top1": "an off-topic query's top score is at least the lowest top-1 score of any genuine labelled query, i.e. no single threshold could separate them.",
}


def run_m4_evaluation() -> dict[str, Any]:
    started = time.perf_counter()
    positive_cases = load_case_file("retrieval_positive.json")
    negative_cases = load_case_file("retrieval_negative.json")
    candidate_cases = load_case_file("candidates.json")
    conversation_cases = load_case_file("conversations.json")
    candidates = {c["candidate_id"]: c for c in candidate_cases["candidates"]}

    with null_llm():
        positive = evaluate_positive_retrieval(positive_cases["queries"])
        negative = evaluate_negative_retrieval(negative_cases["queries"], positive["summary"])
        scenarios = evaluate_matching_scenarios(candidate_cases["matching_scenarios"])
        m2_profiles = evaluate_m2_profiles_on_current_dataset()
        consistency = evaluate_consistency_and_grounding(candidate_cases["candidates"])
        handoff = evaluate_handoff_chain(candidates["SB"], "JOB-0035")
        conversation = evaluate_conversations(conversation_cases, candidates["SB"])

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "evaluation_version": positive_cases["version"],
        "llm_mode": "null provider (deterministic pipeline only)",
        "configuration": dataset_fingerprint(),
        "case_counts": {
            "positive_queries": len(positive_cases["queries"]),
            "relevant_job_labels": sum(len(c["relevant_job_ids"]) for c in positive_cases["queries"]),
            "acceptable_job_labels": sum(len(c["acceptable_job_ids"]) for c in positive_cases["queries"]),
            "negative_queries": len(negative_cases["queries"]),
            "candidates": len(candidate_cases["candidates"]),
            "candidate_job_pairs": sum(len(c["target_job_ids"]) for c in candidate_cases["candidates"]),
            "matching_scenarios": len(candidate_cases["matching_scenarios"]["scenarios"]),
            "conversations": len(conversation_cases["conversations"]),
            "conversation_turns": sum(len(c["turns"]) for c in conversation_cases["conversations"]),
            "job_discovery_probes": len(conversation_cases["job_discovery_probe"]["messages"]),
        },
        "metric_definitions": METRIC_DEFINITIONS,
        "retrieval_positive": positive,
        "retrieval_negative": negative,
        "matching_scenarios": scenarios,
        "matching_m2_profiles": m2_profiles,
        "consistency": consistency["consistency_summary"],
        "grounding": consistency["grounding_summary"],
        "pairs": consistency["pairs"],
        "handoff": handoff,
        "conversation": conversation,
        "runtime_seconds": round(time.perf_counter() - started, 1),
    }


FROZEN_BASELINE_NAMES = frozenset({"m4_2_baseline_results.json", "M4_2_BASELINE_REPORT.md"})


def key_metrics(report: dict[str, Any]) -> dict[str, Any]:
    """The headline numbers each M4.3 experiment is judged on, flattened for diffing.
    Works on the frozen M4.2 baseline JSON too (fields added later are omitted)."""
    pos = report["retrieval_positive"]["summary"]
    neg = report["retrieval_negative"]
    scenarios = {row["scenario_id"]: row["match_score"] for row in report["matching_scenarios"]["rows"]}
    conversation = report["conversation"]
    metrics: dict[str, Any] = {f"retrieval.{k}": pos[k] for k in (
        "hit@1", "hit@3", "hit@5", "hit@10", "precision@1", "precision@5", "recall@5", "recall@10", "ndcg@5", "ndcg@10", "mrr@10", "top1_domain_accuracy")}
    metrics["negative.queries_returning_results"] = neg["summary"]["queries_returning_results"]
    if "confidence" in neg["summary"]:
        metrics["negative.flagged_or_suppressed"] = neg["summary"]["confidence"]["negatives_flagged_or_suppressed"]
        metrics["positive.flagged_or_suppressed"] = neg["summary"]["confidence"]["positives_flagged_or_suppressed"]
    metrics.update({f"matching.{k}": v for k, v in scenarios.items()})
    metrics["matching.m2_top1_domain_accuracy"] = report["matching_m2_profiles"]["top1_domain_accuracy"]
    metrics["consistency.findings"] = report["consistency"]["findings_by_type"]
    metrics["grounding.violations"] = len(report["grounding"]["violations"])
    metrics["grounding.needs_review"] = sorted({item["check"] for item in report["grounding"]["needs_human_review"]})
    metrics["handoff.all_hold"] = report["handoff"]["all_hold"]
    metrics["conversation.turns_passing"] = f"{conversation['summary']['turns_passing']}/{conversation['summary']['turns']}"
    metrics["discovery.expected_domain_hit_rate"] = conversation["job_discovery"]["expected_domain_hit_rate"]
    metrics["discovery.identical_results"] = conversation["job_discovery"]["identical_results_for_different_queries"]
    metrics["runtime_seconds"] = report["runtime_seconds"]
    return metrics


def compare_with_baseline(baseline: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    before, after = key_metrics(baseline), key_metrics(current)
    return {key: {"baseline": before.get(key), "current": value} for key, value in after.items()
            if key != "runtime_seconds" and before.get(key) != value}


def render_markdown(report: dict[str, Any], title: str = "Milestone 4 Evaluation Report") -> str:
    cfg, pos, neg = report["configuration"], report["retrieval_positive"]["summary"], report["retrieval_negative"]
    lines = [
        f"# {title}", "",
        f"Generated {report['generated_at']} by `scripts/run_m4_evaluation.py` (LLM mode: {report['llm_mode']}). "
        "All values are measured by this run. Compare with the frozen M4.2 baseline (`results/m4_2_baseline_results.json`); "
        "accepted and rejected M4.3 changes are recorded in `results/m4_3_experiments.json`. "
        "Historical M2.4 results remain in `data/evaluation/results/`.", "",
        "## Configuration", "",
        f"- Dataset: `{cfg['dataset_file']}` — {cfg['dataset_size']} postings",
        f"- Index: {cfg['index_type']} ({cfg['similarity']}), {cfg['vector_count']} vectors / {cfg['chunk_count']} chunks, `{cfg['index_file']}`",
        f"- Embedding model: {cfg['embedding_model']} ({cfg['embedding_dimension']} dims)",
        f"- Retrieval: {cfg['retrieval']}",
        f"- Cases: {json.dumps(report['case_counts'])}", "",
        "## Positive retrieval (job-level labels)", "",
        "| Metric | @1 | @3 | @5 | @10 |", "|---|---:|---:|---:|---:|",
    ]
    for name in ("hit", "precision", "relaxed_precision", "recall", "capped_recall", "ndcg"):
        lines.append(f"| {name} | " + " | ".join(f"{pos[f'{name}@{k}']:.3f}" for k in RETRIEVAL_KS) + " |")
    lines += ["", f"- MRR@10: {pos['mrr@10']:.3f}; top-1 domain accuracy: {pos['top1_domain_accuracy']:.3f}",
              f"- Top-1 similarity scores of labelled queries: min {pos['top1_score']['min']}, median {pos['top1_score']['median']}, max {pos['top1_score']['max']}",
              f"- Search latency (warm): median {pos['latency_ms']['median']} ms, max {pos['latency_ms']['max']} ms", "",
              "Weak cases (no relevant job at rank 1 or none in top 5):", ""]
    for case in report["retrieval_positive"]["weak_cases"]:
        lines.append(f"- {case['query_id']} \"{case['query']}\": first relevant rank {case['first_relevant_rank']}, top-5 grades {case['top5_grades']}, top-1 domain {case['top1_domain']}")
    lines += ["", "## Negative / off-topic retrieval", "", "| Query | Category | Top score | Shown as | Top result |", "|---|---|---:|---:|---|"]
    for row in neg["rows"]:
        lines.append(f"| {row['query']} | {row['category']} | {row['top_score']} | {row['displayed_relevance_percent']}% | {row['top_results'][0] if row['top_results'] else '-'} |")
    ns = neg["summary"]
    lines += ["", f"- Every query returned results: {all(r['returned_count'] > 0 for r in neg['rows'])}. "
              f"Highest unrelated/nonsense score {ns['unrelated_or_nonsense_top_score_max']} vs lowest genuine top-1 {ns['positive_top1_score_min']} "
              f"(ranges overlap: {ns['score_ranges_overlap']}, gap {ns['gap_between_ranges']}).",
              f"- Out-of-coverage queries reach {ns['out_of_coverage_top_score_max']}; {ns['positive_queries_below_max_offtopic_score']} of {ns['positive_query_count']} genuine queries have a best score below the best off-topic score, "
              "so no single similarity threshold separates them.",
              *([f"- Query-confidence flag (results are labelled, never removed): {ns['confidence']['negatives_flagged_or_suppressed']}/{ns['confidence']['negative_query_count']} "
                 f"off-topic queries flagged (not flagged: {', '.join(ns['confidence']['negatives_not_flagged']) or 'none'}); "
                 f"{ns['confidence']['positives_flagged_or_suppressed']}/{ns['positive_query_count']} genuine queries flagged."] if "confidence" in ns else []),
              "",
              "## Matching", "", f"Per-job scenarios against {report['matching_scenarios']['target_job_id']} (weights {report['matching_scenarios']['weights']}):", "",
              "| Scenario | Match score | Required | Preferred | Matched required | Semantic retrieval finds target domain |", "|---|---:|---:|---:|---|---|"]
    for row in report["matching_scenarios"]["rows"]:
        lines.append(f"| {row['scenario_id']} | {row['match_score']} | {row['required_skills_score']:.2f} | {row['preferred_skills_score']:.2f} | {', '.join(row['matched_required']) or '-'} | {row['semantic_target_domain_in_top5']} |")
    lines.append("")
    for prop in report["matching_scenarios"]["desired_properties"]:
        lines.append(f"- {'HOLDS' if prop['holds'] else 'DOES NOT HOLD'}: {prop['property']} ({prop['values']})")
    m2 = report["matching_m2_profiles"]
    lines += ["", f"M2.4 profiles re-run on the 320-record dataset: top-1 domain accuracy {m2['top1_domain_accuracy']:.3f}, top-3 hit {m2['top3_hit_rate']:.3f}, MRR {m2['mrr']:.3f} ({m2['labelled_profile_count']} labelled profiles).", "",
              "## Matching <-> Skill Gap consistency", "",
              f"Pairs checked: {report['consistency']['pairs_checked']}; findings by type: {report['consistency']['findings_by_type']}; high severity: {report['consistency']['high_severity']}.", ""]
    for finding in report["consistency"]["findings"]:
        lines.append(f"- [{finding['severity']}] {finding['candidate_id']} x {finding['job_id']}: {finding['detail']}")
    g = report["grounding"]
    lines += ["", "## Grounding", "", f"Pairs: {g['pairs_checked']}; structured checks run: {g['checks_run']}; violations by service: {g['violations_by_service']}.", ""]
    lines += [f"- VIOLATION {v['service']}/{v['check']} ({v['candidate_id']} x {v['job_id']}): {v['detail']}" for v in g["violations"]] or ["- No violations."]
    if g["needs_human_review"]:
        lines += ["", "Needs human review (heuristic flags, not counted as violations):", ""]
        lines += [f"- {r['service']}/{r['check']} ({r['candidate_id']} x {r['job_id']}): {r['detail']}" for r in g["needs_human_review"]]
    h = report["handoff"]
    lines += ["", "## Service handoff chain", "", f"{h['candidate_id']} x {h['job_id']}: all checks hold = {h['all_hold']}", ""]
    lines += [f"- {'OK' if c['holds'] else 'FAIL'} {c['check']}" + (f" — {c['detail']}" if not c["holds"] and c["detail"] else "") for c in h["checks"]]
    conv = report["conversation"]
    lines += ["", "## Conversation", "", f"Turns passing desired behaviour: {conv['summary']['turns_passing']}/{conv['summary']['turns']}; conversations fully passing: {conv['summary']['conversations_fully_passing']}/{conv['summary']['conversations']}.", ""]
    for c in conv["conversations"]:
        lines.append(f"- {c['conversation_id']}: {'PASS' if c['passed'] else 'FAIL'}")
        for t in c["turns"]:
            if not t["passed"]:
                failed = [name for name, ok in t["outcomes"].items() if not ok]
                lines.append(f"  - \"{t['message']}\" -> intent {t['intent']}, job {t['job_id']}; failed {failed}; reply: \"{t['response_preview'][:120]}\"")
    d = conv["job_discovery"]
    lines += ["", f"Job discovery: identical results for different queries = {d['identical_results_for_different_queries']}; expected-domain hit rate {d['expected_domain_hit_rate']:.3f}.", ""]
    lines += [f"- \"{r['message']}\" -> {r['listed_titles']}" for r in d["rows"]]
    lines += ["", "## Metric definitions", ""] + [f"- **{k}**: {v}" for k, v in report["metric_definitions"].items()]
    lines += ["", f"Evaluation runtime: {report['runtime_seconds']} s.", ""]
    return "\n".join(lines)
