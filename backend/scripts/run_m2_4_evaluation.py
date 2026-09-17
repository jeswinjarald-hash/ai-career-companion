import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.job_dataset_service import load_job_postings
from app.services.m2_4_evaluation import (
    RetrievalEvaluationCase,
    evaluate_consistency,
    evaluate_matching,
    evaluate_retrieval,
    evaluate_skill_matching,
    validate_explanations,
)
from app.services.job_matching import MATCH_WEIGHTS
from app.core.config import get_settings

DATA_DIRECTORY = Path(__file__).resolve().parents[1] / "data" / "evaluation"
RESULTS_DIRECTORY = DATA_DIRECTORY / "results"
JSON_REPORT_PATH = RESULTS_DIRECTORY / "m2_4_results.json"
MARKDOWN_REPORT_PATH = RESULTS_DIRECTORY / "M2_4_EVALUATION_REPORT.md"


def _load(name: str) -> dict:
    return json.loads((DATA_DIRECTORY / name).read_text(encoding="utf-8"))


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _retrieval_summary(results, k: int) -> dict[str, float]:
    return {
        "hit_rate_primary": _mean([float(result.first_relevant_rank is not None and result.first_relevant_rank <= k) for result in results]),
        "strict_precision": _mean([sum(domain in set(case_primary) for domain in result.retrieved_domains[:k]) / k for result, case_primary in zip(results, PRIMARY_BY_QUERY)]),
        "relaxed_precision": _mean([sum(domain in set(case_primary + case_secondary) for domain in result.retrieved_domains[:k]) / k for result, case_primary, case_secondary in zip(results, PRIMARY_BY_QUERY, SECONDARY_BY_QUERY)]),
        "domain_recall": _mean([_domain_recall(result.retrieved_domains[:k], case_primary, case_secondary) for result, case_primary, case_secondary in zip(results, PRIMARY_BY_QUERY, SECONDARY_BY_QUERY)]),
    }


def _domain_recall(domains: list[str], primary: list[str], secondary: list[str]) -> float:
    expected = set(primary + secondary)
    return len(set(domains) & expected) / len(expected) if expected else 0.0


def _retrieval_rows(results, cases) -> list[dict]:
    rows = []
    for result, case in zip(results, cases):
        rows.append({
            "query_id": result.query_id,
            "query": result.query,
            "expected_primary_domains": case.primary_domains,
            "expected_secondary_domains": case.secondary_domains,
            "retrieved_job_ids": result.retrieved_job_ids,
            "retrieved_domains": result.retrieved_domains,
            "primary_hit": result.primary_hit,
            "first_relevant_rank": result.first_relevant_rank,
            "strict_precision_at_5": result.strict_precision,
            "relaxed_precision_at_5": result.relaxed_precision,
            "domain_recall_at_5": result.domain_recall,
            "reciprocal_rank": result.reciprocal_rank,
            "ndcg_at_5": result.ndcg,
            "pass": result.primary_hit,
        })
    return rows


def _matching_rows(results, profiles) -> list[dict]:
    by_id = {profile["profile_id"]: profile for profile in profiles}
    rows = []
    for result in results:
        profile = by_id[result.profile_id]
        rows.append({
            "profile_id": result.profile_id,
            "name": result.name,
            "expected_primary_domains": profile["primary_expected_domains"],
            "expected_secondary_domains": profile["secondary_expected_domains"],
            "retrieved_domains": result.retrieved_domains,
            "top_match_domain": result.top_match_domain,
            "top_match_score": result.top_match_score,
            "top1_correct": result.top1_correct,
            "top3_hit": result.top3_hit,
            "top5_relaxed_hit": result.top5_relaxed_hit,
            "reciprocal_rank": result.reciprocal_rank,
            "score_behavior_pass": result.score_behavior_pass,
            "results": result.results,
        })
    return rows


def _markdown(report: dict) -> str:
    retrieval = report["retrieval"]
    matching = report["matching"]
    lines = [
        "# Milestone 2.4 Evaluation Report", "",
        "## 1. Evaluation Setup", "",
        f"- Dataset size: {report['dataset_size']}",
        f"- Retrieval queries: {report['retrieval_query_count']}",
        f"- Student profiles: {report['profile_count']}",
        "- Retrieval K values: 1, 3, 5",
        f"- Embedding model: {report['embedding_model']}",
        f"- Matching weights: {MATCH_WEIGHTS}", "",
        "## 2. Retrieval Evaluation", "",
        "| Query | Expected Primary | Top-1 Domain | Precision@5 | Recall@5 | First Relevant Rank | Pass |",
        "|---|---|---|---:|---:|---:|---|",
    ]
    for row in retrieval["rows"]:
        lines.append(f"| {row['query_id']} | {', '.join(row['expected_primary_domains']) or 'None'} | {row['retrieved_domains'][0] if row['retrieved_domains'] else 'None'} | {row['strict_precision_at_5']:.3f} | {row['domain_recall_at_5']:.3f} | {row['first_relevant_rank'] or '-'} | {'PASS' if row['pass'] else 'FAIL'} |")
    lines += ["", "| Metric | Value |", "|---|---:|"]
    for key, value in retrieval["summary"].items():
        lines.append(f"| {key} | {value:.3f} |")
    lines += ["", "## 3. Matching Evaluation", "", "| Profile | Expected Primary | Top Domain | Top Score | Top-1 | Top-3 | Top-5 Relaxed |", "|---|---|---|---:|---|---|---|"]
    for row in matching["rows"]:
        lines.append(f"| {row['profile_id']} {row['name']} | {', '.join(row['expected_primary_domains']) or 'None'} | {row['top_match_domain']} | {row['top_match_score']:.1f} | {'PASS' if row['top1_correct'] else 'FAIL'} | {'PASS' if row['top3_hit'] else 'FAIL'} | {'PASS' if row['top5_relaxed_hit'] else 'FAIL'} |")
    lines += ["", "| Metric | Value |", "|---|---:|"]
    for key, value in matching["summary"].items():
        lines.append(f"| {key} | {value:.3f} |")
    lines += ["", "## 4. Skill Matching Accuracy", "", f"- Cases: {report['skill_matching']['cases']}", f"- Accuracy: {report['skill_matching']['accuracy']:.3f}", f"- Alias cases: {report['skill_matching']['alias_cases']}", f"- Negative alias cases: {report['skill_matching']['negative_alias_cases']}", "", "## 5. Score Consistency", ""]
    for key, value in report["consistency"].items():
        if key.endswith("_score"):
            lines.append(f"- {key}: {value}")
        else:
            lines.append(f"- {key}: {'PASS' if value else 'FAIL'}")
    lines += ["", "## 6. Explanation Quality", "", f"- Explanations checked: {report['explanations']['checked']}", f"- Unsupported claims: {report['explanations']['unsupported_claims']}", f"- Factuality pass rate: {report['explanations']['factuality_pass_rate']:.3f}", "", "## 7. Failures / Limitations", ""]
    if report["expectation_failures"]:
        lines.append("Independently authored expectation failures:")
        lines.extend(f"- {failure}" for failure in report["expectation_failures"])
    else:
        lines.append("- No ground-truth expectation failures.")
    lines += ["- Relevance is domain-level and uses synthetic postings.", "- Education and experience checks are conservative rule-based heuristics.", "- Retrieval results can mix adjacent technical domains.", "- M2.4 does not tune M2.2 or M2.3 and does not implement external-market evaluation.", "", "## 8. Conclusion", "", f"**{'M2.4 COMPLETE' if report['overall_pass'] else 'M2.4 NOT COMPLETE'}**"]
    return "\n".join(lines) + "\n"


def main() -> None:
    global PRIMARY_BY_QUERY, SECONDARY_BY_QUERY
    retrieval_data = _load("retrieval_queries.json")
    profile_data = _load("student_profiles.json")
    expectation_data = _load("matching_expectations.json")
    retrieval_cases = [RetrievalEvaluationCase(item["query_id"], item["query"], item["primary_relevant_domains"], item["secondary_relevant_domains"]) for item in retrieval_data["queries"]]
    PRIMARY_BY_QUERY = [case.primary_domains for case in retrieval_cases]
    SECONDARY_BY_QUERY = [case.secondary_domains for case in retrieval_cases]
    retrieval_results = evaluate_retrieval(retrieval_cases, top_k=5)
    matching_results = evaluate_matching(profile_data["profiles"], top_k=5)
    skill_matching = evaluate_skill_matching(expectation_data["skill_cases"])
    consistency = evaluate_consistency(expectation_data["consistency_pairs"][0])
    explanations = validate_explanations(matching_results)
    retrieval_rows = _retrieval_rows(retrieval_results, retrieval_cases)
    matching_rows = _matching_rows(matching_results, profile_data["profiles"])
    retrieval_summary = {f"hit_rate_at_{k}": _retrieval_summary(retrieval_results, k)["hit_rate_primary"] for k in (1, 3, 5)}
    retrieval_summary.update({"strict_precision_at_5": _retrieval_summary(retrieval_results, 5)["strict_precision"], "relaxed_precision_at_5": _retrieval_summary(retrieval_results, 5)["relaxed_precision"], "domain_recall_at_5": _retrieval_summary(retrieval_results, 5)["domain_recall"], "mrr": _mean([result.reciprocal_rank for result in retrieval_results]), "ndcg_at_5": _mean([result.ndcg for result in retrieval_results])})
    matching_summary = {"top1_domain_accuracy": _mean([float(result.top1_correct) for result in matching_results]), "top3_hit_rate": _mean([float(result.top3_hit) for result in matching_results]), "top5_relaxed_hit_rate": _mean([float(result.top5_relaxed_hit) for result in matching_results]), "mrr": _mean([result.reciprocal_rank for result in matching_results])}
    expectation_failures = []
    expectation_failures.extend(f"{row['query_id']} retrieval primary-domain hit" for row in retrieval_rows if not row["pass"])
    expectation_failures.extend(f"{row['profile_id']} top-1 expected primary domain" for row in matching_rows if row["expected_primary_domains"] and not row["top1_correct"])
    expectation_failures.extend(f"{row['profile_id']} score behavior threshold" for row in matching_rows if not row["score_behavior_pass"])
    framework_checks_pass = all(consistency[key] for key in ("determinism", "addition_monotonic", "removal_monotonic", "unrelated_robust")) and skill_matching["accuracy"] == 1.0 and explanations["unsupported_claims"] == 0
    report = {"dataset_size": len(load_job_postings()), "retrieval_query_count": len(retrieval_cases), "profile_count": len(profile_data["profiles"]), "embedding_model": get_settings().embedding_model_name, "retrieval": {"summary": retrieval_summary, "rows": retrieval_rows}, "matching": {"summary": matching_summary, "rows": matching_rows}, "skill_matching": skill_matching, "consistency": consistency, "explanations": explanations, "expectation_failures": expectation_failures, "framework_checks_pass": framework_checks_pass, "overall_pass": framework_checks_pass}
    RESULTS_DIRECTORY.mkdir(parents=True, exist_ok=True)
    JSON_REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    MARKDOWN_REPORT_PATH.write_text(_markdown(report), encoding="utf-8")
    print(json.dumps({"status": "PASS" if report["overall_pass"] else "FAIL", "json_report": str(JSON_REPORT_PATH), "markdown_report": str(MARKDOWN_REPORT_PATH), "retrieval": retrieval_summary, "matching": matching_summary, "skill_accuracy": skill_matching["accuracy"], "explanation_factuality": explanations["factuality_pass_rate"], "consistency": consistency}, indent=2))


if __name__ == "__main__":
    main()
