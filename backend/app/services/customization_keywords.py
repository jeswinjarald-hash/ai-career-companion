"""Milestone 3.2 — job keyword extraction and grounded classification.

Reuses Milestone 3.1's exact evidence-matching logic (`skill_gap_evidence.
build_evidence_units` + `match_requirement`) for the supported/partial/unsupported
*decision* rather than re-implementing skill matching a second time: a keyword is
`supported` only if M3.1 would call it `demonstrated`, `partial` if M3.1 would call
it `partial` or `learning_only` (worded conservatively either way — never presented
as hands-on), and `unsupported` if M3.1 would call it `missing`. Only required/
preferred skills are classified here (the codebase's only structured, single-term
job keywords); the job's free-text responsibilities/qualifications are surfaced to
the customizer through the evidence layer instead of forced into single-keyword
classification.
"""

from app.models import CandidateProfile
from app.schemas.customization import EvidenceRecord, KeywordClassification
from app.schemas.job_posting import JobPosting
from app.services.job_matching import normalize_term
from app.services.skill_gap_evidence import RELATED_TERMS, build_evidence_units, match_requirement, mentions_term


def _unique_preserve(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = normalize_term(value)
        if key and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _matched_evidence_ids(keyword: str, evidence_records: list[EvidenceRecord]) -> list[str]:
    """Finds which of this module's own `EvidenceRecord`s support `keyword`, using the
    same term primitives M3.1 uses (exact term / `RELATED_TERMS`), so the ids returned
    always point at real, displayable evidence regardless of which branch of
    `match_requirement` produced the status.
    """
    keyword_norm = normalize_term(keyword)
    related_pool = RELATED_TERMS.get(keyword_norm, set())
    matched: list[str] = []
    for record in evidence_records:
        normalized_text = normalize_term(record.raw_text)
        if keyword_norm in record.canonical_terms or mentions_term(keyword_norm, normalized_text):
            matched.append(record.evidence_id)
        elif related_pool and (set(record.canonical_terms) & related_pool or any(mentions_term(term, normalized_text) for term in related_pool)):
            matched.append(record.evidence_id)
    return matched


def _classify(keyword: str, requirement_type: str, units, evidence_records: list[EvidenceRecord]) -> KeywordClassification:
    match_type, _confidence, _evidence_items, reason = match_requirement(keyword, units)
    status = "supported" if match_type == "demonstrated" else "unsupported" if match_type == "missing" else "partial"
    return KeywordClassification(
        keyword=keyword, requirement_type=requirement_type, status=status, reason=reason,
        matched_evidence_ids=_matched_evidence_ids(keyword, evidence_records),
    )


def classify_job_keywords(
    profile: CandidateProfile,
    structured_data: dict,
    job: JobPosting,
    evidence_records: list[EvidenceRecord],
) -> list[KeywordClassification]:
    units = build_evidence_units(profile, structured_data)
    classifications: list[KeywordClassification] = []
    for keyword in _unique_preserve(job.required_skills):
        classifications.append(_classify(keyword, "required_skill", units, evidence_records))
    for keyword in _unique_preserve(job.preferred_skills):
        classifications.append(_classify(keyword, "preferred_skill", units, evidence_records))
    return classifications


def supported_terms(classifications: list[KeywordClassification]) -> set[str]:
    return {normalize_term(c.keyword) for c in classifications if c.status == "supported"}


def partial_terms(classifications: list[KeywordClassification]) -> set[str]:
    return {normalize_term(c.keyword) for c in classifications if c.status == "partial"}


def unsupported_terms(classifications: list[KeywordClassification]) -> set[str]:
    return {normalize_term(c.keyword) for c in classifications if c.status == "unsupported"}
