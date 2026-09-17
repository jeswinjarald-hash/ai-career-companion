import math
from dataclasses import dataclass
from typing import Any

from app.schemas.job_chunk import JobSearchResult
from app.services.job_dataset_service import load_job_postings
from app.services.job_matching import (
    MatchingProfile,
    _result,
    normalize_profile,
    score_required_skills,
)
from app.services.job_search_service import search_jobs


@dataclass(frozen=True)
class RetrievalEvaluationCase:
    query_id: str
    query: str
    primary_domains: list[str]
    secondary_domains: list[str]


@dataclass(frozen=True)
class RetrievalEvaluationResult:
    query_id: str
    query: str
    retrieved_job_ids: list[str]
    retrieved_domains: list[str]
    primary_hit: bool
    first_relevant_rank: int | None
    strict_precision: float
    relaxed_precision: float
    domain_recall: float
    reciprocal_rank: float
    ndcg: float


@dataclass(frozen=True)
class MatchingEvaluationResult:
    profile_id: str
    name: str
    retrieved_domains: list[str]
    top_match_score: float
    top_match_domain: str
    top1_correct: bool
    top3_hit: bool
    top5_relaxed_hit: bool
    reciprocal_rank: float
    score_behavior_pass: bool
    results: list[dict[str, Any]]


def _domain_gain(domain: str, primary: set[str], secondary: set[str]) -> int:
    if domain in primary:
        return 2
    if domain in secondary:
        return 1
    return 0


def _ndcg(domains: list[str], primary: set[str], secondary: set[str], k: int) -> float:
    unique_domains = list(dict.fromkeys(domains))
    gains = [_domain_gain(domain, primary, secondary) for domain in unique_domains[:k]]
    dcg = sum(gain / math.log2(rank + 2) for rank, gain in enumerate(gains))
    ideal_gains = sorted([2] * len(primary) + [1] * len(secondary), reverse=True)[:k]
    ideal = sum(gain / math.log2(rank + 2) for rank, gain in enumerate(ideal_gains))
    return dcg / ideal if ideal else 0.0


def calculate_retrieval_metrics(
    retrieved_domains: list[str],
    primary_domains: list[str],
    secondary_domains: list[str],
    k: int,
) -> dict[str, float]:
    if not 1 <= k <= len(retrieved_domains):
        raise ValueError("k must be between 1 and the number of retrieved domains.")
    primary = set(primary_domains)
    secondary = set(secondary_domains)
    top_domains = retrieved_domains[:k]
    primary_ranks = [index + 1 for index, domain in enumerate(top_domains) if domain in primary]
    relevant = primary | secondary
    return {
        "hit_rate": float(bool(primary_ranks)),
        "strict_precision": sum(domain in primary for domain in top_domains) / k,
        "relaxed_precision": sum(domain in relevant for domain in top_domains) / k,
        "domain_recall": len(set(top_domains) & relevant) / len(relevant) if relevant else 0.0,
        "reciprocal_rank": 1 / primary_ranks[0] if primary_ranks else 0.0,
        "ndcg": _ndcg(top_domains, primary, secondary, k),
    }


def evaluate_retrieval(cases: list[RetrievalEvaluationCase], top_k: int = 5) -> list[RetrievalEvaluationResult]:
    if not 1 <= top_k <= 20:
        raise ValueError("top_k must be between 1 and 20.")
    results: list[RetrievalEvaluationResult] = []
    for case in cases:
        retrieved = search_jobs(case.query, top_k=top_k)
        domains = [item.domain for item in retrieved]
        primary = set(case.primary_domains)
        secondary = set(case.secondary_domains)
        primary_ranks = [index + 1 for index, domain in enumerate(domains) if domain in primary]
        relevant_domains = primary | secondary
        metrics = calculate_retrieval_metrics(domains, case.primary_domains, case.secondary_domains, top_k)
        results.append(
            RetrievalEvaluationResult(
                query_id=case.query_id,
                query=case.query,
                retrieved_job_ids=[item.job_id for item in retrieved],
                retrieved_domains=domains,
                primary_hit=bool(primary_ranks),
                first_relevant_rank=min(primary_ranks) if primary_ranks else None,
                strict_precision=metrics["strict_precision"],
                relaxed_precision=metrics["relaxed_precision"],
                domain_recall=metrics["domain_recall"],
                reciprocal_rank=metrics["reciprocal_rank"],
                ndcg=metrics["ndcg"],
            )
        )
    return results


def _profile_namespace(profile_data: dict[str, Any]) -> Any:
    class Profile:
        pass

    profile = Profile()
    for field in ("skills", "education", "degree", "specialization", "experience_level", "career_interests", "target_roles", "career_goals"):
        setattr(profile, field, profile_data.get(field, [] if field in {"skills", "career_interests", "target_roles"} else ""))
    return profile


def evaluate_matching(profiles: list[dict[str, Any]], top_k: int = 5) -> list[MatchingEvaluationResult]:
    results: list[MatchingEvaluationResult] = []
    for profile_data in profiles:
        profile = _profile_namespace(profile_data)
        structured = {
            "skills": [],
            "education": [],
            "experience": [],
            "projects": profile_data.get("projects", []),
            "certifications": [],
            "achievements": [],
        }
        from app.services.job_matching import match_jobs_for_profile

        matches = match_jobs_for_profile(profile, structured, top_k=top_k)
        primary = set(profile_data.get("primary_expected_domains", []))
        secondary = set(profile_data.get("secondary_expected_domains", []))
        domains = [match.domain for match in matches]
        primary_ranks = [index + 1 for index, domain in enumerate(domains) if domain in primary]
        threshold = profile_data.get("expected_score_behavior", {}).get("strong_match_minimum", 0)
        weak_maximum = profile_data.get("expected_score_behavior", {}).get("weak_unrelated_maximum", 100)
        score_behavior_pass = (not primary or matches[0].match_score >= threshold) and matches[0].match_score <= weak_maximum if not primary else matches[0].match_score >= threshold
        results.append(
            MatchingEvaluationResult(
                profile_id=profile_data["profile_id"],
                name=profile_data["name"],
                retrieved_domains=domains,
                top_match_score=matches[0].match_score if matches else 0.0,
                top_match_domain=matches[0].domain if matches else "",
                top1_correct=bool(matches and matches[0].domain in primary),
                top3_hit=bool(set(domains[:3]) & primary),
                top5_relaxed_hit=bool(set(domains[:5]) & (primary | secondary)),
                reciprocal_rank=1 / min(primary_ranks) if primary_ranks else 0.0,
                score_behavior_pass=score_behavior_pass,
                results=[match.model_dump() for match in matches],
            )
        )
    return results


def evaluate_skill_matching(cases: list[dict[str, Any]]) -> dict[str, Any]:
    jobs = load_job_postings()
    template = next(job for job in jobs if len(job.required_skills) >= 2)
    correct = 0
    total = 0
    alias_cases = 0
    negative_alias_cases = 0
    case_results = []
    for case in cases:
        job = template.model_copy(update={"required_skills": case["job_required_skills"]})
        profile = MatchingProfile(
            skills=[_normalise_skill(value) for value in case["student_skills"]],
            education_text="", experience_text="", project_texts=[], project_skills=[], qualification_text="", retrieval_terms=[]
        )
        result = score_required_skills(profile, job)
        actual_matched = set(result.matched)
        actual_missing = set(result.missing)
        expected_matched = set(case["expected_matched"])
        expected_missing = set(case["expected_missing"])
        matched_ok = actual_matched == expected_matched
        missing_ok = actual_missing == expected_missing
        correct += int(matched_ok) * len(expected_matched) + int(missing_ok) * len(expected_missing)
        total += len(expected_matched) + len(expected_missing)
        if case["case_id"] == "SC002":
            alias_cases += 1
        if case["case_id"] == "SC003":
            negative_alias_cases += 1
        case_results.append({"case_id": case["case_id"], "matched_ok": matched_ok, "missing_ok": missing_ok, "actual_matched": sorted(actual_matched), "actual_missing": sorted(actual_missing)})
    return {"cases": len(cases), "correct_classifications": correct, "total_classifications": total, "accuracy": correct / total if total else 0.0, "alias_cases": alias_cases, "negative_alias_cases": negative_alias_cases, "case_results": case_results}


def _normalise_skill(value: str) -> str:
    from app.services.job_matching import normalize_term

    return normalize_term(value)


def evaluate_consistency(case: dict[str, Any]) -> dict[str, Any]:
    jobs = load_job_postings()
    job = next((item for item in jobs if case["added_skill"] in item.required_skills), jobs[0])
    base = MatchingProfile(skills=[_normalise_skill(value) for value in case["base_skills"]], education_text="B.Tech Computer Science", experience_text="No prior experience", project_texts=[], project_skills=[], qualification_text="", retrieval_terms=[])
    added = MatchingProfile(skills=base.skills + [_normalise_skill(case["added_skill"])], education_text=base.education_text, experience_text=base.experience_text, project_texts=[], project_skills=[], qualification_text="", retrieval_terms=[])
    removed = MatchingProfile(skills=[value for value in base.skills if value != _normalise_skill(case["removed_skill"])], education_text=base.education_text, experience_text=base.experience_text, project_texts=[], project_skills=[], qualification_text="", retrieval_terms=[])
    unrelated = MatchingProfile(skills=base.skills + [_normalise_skill(case["unrelated_skill"])], education_text=base.education_text, experience_text=base.experience_text, project_texts=[], project_skills=[], qualification_text="", retrieval_terms=[])
    retrieval = JobSearchResult(job_id=job.job_id, job_title=job.job_title, company=job.company, domain=job.domain, location=job.location, work_mode=job.work_mode, employment_type=job.employment_type, required_skills=job.required_skills, preferred_skills=job.preferred_skills, similarity_score=0.5, matched_chunk_types=[])
    scores = [_result(job, retrieval, profile).match_score for profile in (base, added, removed, unrelated, base)]
    return {"base_score": scores[0], "added_score": scores[1], "removed_score": scores[2], "unrelated_score": scores[3], "repeat_score": scores[4], "determinism": scores[0] == scores[4], "addition_monotonic": scores[1] >= scores[0], "removal_monotonic": scores[2] <= scores[0], "unrelated_robust": scores[3] == scores[0]}


def validate_explanations(matching_results: list[MatchingEvaluationResult]) -> dict[str, Any]:
    checked = 0
    failures = []
    for evaluation in matching_results:
        for result in evaluation.results:
            checked += 1
            allowed_matched = set(result["matched_required_skills"] + result["matched_preferred_skills"])
            allowed_missing = set(result["missing_required_skills"] + result["missing_preferred_skills"])
            claims = result["strengths"] + result["gaps"]
            invalid = []
            for claim in claims:
                if claim.endswith(" preferred skill matched"):
                    skill = claim.removesuffix(" preferred skill matched")
                    if skill not in allowed_matched:
                        invalid.append(claim)
                elif claim.endswith(" matched"):
                    skill = claim.removesuffix(" matched")
                    if skill not in allowed_matched:
                        invalid.append(claim)
                elif claim.endswith(" preferred skill not found"):
                    skill = claim.removesuffix(" preferred skill not found")
                    if skill not in allowed_missing:
                        invalid.append(claim)
                elif claim.endswith(" missing"):
                    skill = claim.removesuffix(" missing")
                    if skill not in allowed_missing:
                        invalid.append(claim)
            if result["relevant_projects"] and result["relevant_projects"][0] not in result["reasoning"]:
                invalid.append("project explanation mismatch")
            if invalid:
                failures.append({"profile_id": evaluation.profile_id, "job_id": result["job_id"], "claims": invalid})
    return {"checked": checked, "failures": failures, "unsupported_claims": len(failures), "factuality_pass_rate": (checked - len(failures)) / checked if checked else 0.0}
