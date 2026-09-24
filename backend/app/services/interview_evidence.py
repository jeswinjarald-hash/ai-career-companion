"""Milestone 3.3 — grounded interview-preparation context builder.

Reuses, never duplicates: `customization_evidence.build_evidence_records` for the
claim-provenance evidence pool (same `EvidenceRecord`/`evidence_id` scheme M3.2
already established), `skill_gap_service.analyze_skill_gap` for M3.1's own
strengths/critical-gaps/partial-gaps/preferred-gaps/experience-gaps/qualification-gaps
(never re-scored here), and `job_matching.match_jobs_for_resume` for a best-effort M2
match result (M2's retrieval is similarity-based, so the selected job is not always
present in the top results — this is treated as optional supplementary context, the
same way the existing Job Details page already does).
"""

import logging

from sqlalchemy.orm import Session

from app.models import CandidateProfile
from app.schemas.customization import EvidenceRecord
from app.schemas.job_match import JobMatchResult
from app.schemas.job_posting import JobPosting
from app.schemas.skill_gap import SkillGapAnalysis
from app.services.customization_evidence import build_evidence_records, relevance_score
from app.services.job_matching import match_jobs_for_resume, normalize_term
from app.services.skill_gap_service import analyze_skill_gap

logger = logging.getLogger(__name__)


def best_effort_m2_match(db: Session, resume_id: int, job_id: str) -> JobMatchResult | None:
    """M2's retrieval is semantic-similarity-based, so an arbitrary selected job is
    not guaranteed to appear even at the maximum `top_k` — the existing Job Details
    page already treats a missing match the same way ("not found in your ranked
    matches"). Never raises; a missing/failed match just means this optional context
    is omitted, not that interview-prep generation fails.
    """
    try:
        results = match_jobs_for_resume(db, resume_id, top_k=20)
    except (LookupError, ValueError):
        return None
    return next((r for r in results if r.job_id == job_id), None)


def ranked_projects(structured_data: dict, supported: set[str], partial: set[str]) -> list[tuple[dict, int, int]]:
    """Returns (project, index, score) sorted by job relevance, most relevant first —
    the same ranking `resume_customization_service`/`cover_letter_service` use, so a
    student sees the same "most relevant project" in interview prep as in their
    tailored resume.
    """
    projects = [p for p in structured_data.get("projects", []) or [] if isinstance(p, dict)]
    scored = [
        (project, index, relevance_score(str(project.get("raw_text") or project.get("description") or ""), project.get("technologies", []) or [], supported, partial))
        for index, project in enumerate(projects)
    ]
    scored.sort(key=lambda item: (-item[2], item[1]))
    return scored


def evidence_by_source_type(evidence_records: list[EvidenceRecord], source_type: str) -> list[EvidenceRecord]:
    return [e for e in evidence_records if e.source_type == source_type]


class InterviewContext:
    """The fully-assembled grounded context for one (resume, job) pair — everything
    the deterministic question generator and the LLM prompt builder need, computed
    once and shared.
    """

    def __init__(
        self,
        profile: CandidateProfile,
        structured_data: dict,
        job: JobPosting,
        skill_gap: SkillGapAnalysis,
        m2_match: JobMatchResult | None,
        evidence_records: list[EvidenceRecord],
    ) -> None:
        self.profile = profile
        self.structured_data = structured_data
        self.job = job
        self.skill_gap = skill_gap
        self.m2_match = m2_match
        self.evidence_records = evidence_records

        # Skill classification reused directly from M3.1's own analysis — never
        # re-derived or re-scored here.
        self.supported_terms = {normalize_term(s.requirement) for s in skill_gap.strengths if s.requirement_type in ("required_skill", "preferred_skill")}
        self.partial_terms = {normalize_term(g.requirement) for g in (skill_gap.partial_gaps + skill_gap.preferred_gaps) if g.requirement_type in ("required_skill", "preferred_skill")}

        self.projects_ranked = ranked_projects(structured_data, self.supported_terms, self.partial_terms)
