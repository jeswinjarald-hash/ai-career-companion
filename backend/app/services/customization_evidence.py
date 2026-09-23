"""Milestone 3.2 — grounded evidence extraction for resume/cover-letter customization.

Builds the "claim provenance layer": every candidate evidence unit records exactly
where in the student's own profile/resume it came from (`source_path`), so every
downstream generated claim can be traced back to real, student-provided text. This
mirrors `app.services.skill_gap_evidence.build_evidence_units` (same sources, same
"no LLM, no inference" policy) but additionally tracks the indexed field path each
unit was read from, which M3.1's evidence units don't need but M3.2's provenance
requirement does.
"""

from app.models import CandidateProfile
from app.schemas.customization import EvidenceRecord
from app.services.job_matching import normalize_term
from app.services.skill_gap_evidence import mentions_term


def relevance_score(text: str, technologies: list[str], supported: set[str], partial: set[str]) -> int:
    """Ranks a project/bullet's relevance to a job's supported/partially-supported
    keywords — used to order (never filter out) projects by job relevance."""
    normalized_text = normalize_term(text)
    tech_terms = {normalize_term(t) for t in technologies}
    score = 0
    score += 2 * len(tech_terms & supported)
    score += 1 * len(tech_terms & partial)
    score += 2 * sum(1 for term in supported if mentions_term(term, normalized_text))
    score += 1 * sum(1 for term in partial if mentions_term(term, normalized_text))
    return score


def _terms(*values: str) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        term = normalize_term(value)
        if term and term not in seen:
            seen.add(term)
            result.append(term)
    return result


class _IdCounter:
    def __init__(self) -> None:
        self._n = 0

    def next(self) -> str:
        self._n += 1
        return f"EV-{self._n:03d}"


def build_evidence_records(profile: CandidateProfile, structured_data: dict) -> list[EvidenceRecord]:
    ids = _IdCounter()
    records: list[EvidenceRecord] = []

    for index, skill in enumerate(profile.skills or []):
        text = str(skill).strip()
        if not text:
            continue
        records.append(EvidenceRecord(
            evidence_id=ids.next(), source_type="skill", source_name="Career Profile Skills",
            source_path=f"profile.skills[{index}]", raw_text=text,
            canonical_terms=_terms(text), confidence_type="direct",
        ))

    for index, skill in enumerate(structured_data.get("skills", []) or []):
        text = str(skill).strip()
        if not text:
            continue
        records.append(EvidenceRecord(
            evidence_id=ids.next(), source_type="skill", source_name="Resume Skills Section",
            source_path=f"structured_resume.skills[{index}]", raw_text=text,
            canonical_terms=_terms(text), confidence_type="direct",
        ))

    profile_education_bits = [value for value in (profile.education, profile.degree, profile.specialization) if value]
    if profile_education_bits:
        text = " ".join(profile_education_bits).strip()
        records.append(EvidenceRecord(
            evidence_id=ids.next(), source_type="education", source_name="Career Profile Education",
            source_path="profile.education", raw_text=text,
            canonical_terms=_terms(*profile_education_bits), confidence_type="direct",
        ))

    for index, entry in enumerate(structured_data.get("education", []) or []):
        if not isinstance(entry, dict):
            continue
        text = str(entry.get("raw_text") or "").strip()
        if not text:
            continue
        records.append(EvidenceRecord(
            evidence_id=ids.next(), source_type="education", source_name="Resume Education Section",
            source_path=f"structured_resume.education[{index}].raw_text", raw_text=text,
            canonical_terms=_terms(text), confidence_type="direct",
        ))

    for index, project in enumerate(structured_data.get("projects", []) or []):
        if not isinstance(project, dict):
            continue
        title = str(project.get("title") or "Project").strip() or "Project"
        raw = str(project.get("raw_text") or project.get("description") or title).strip()
        if not raw:
            continue
        technologies = [str(tech) for tech in project.get("technologies", []) or [] if str(tech).strip()]
        records.append(EvidenceRecord(
            evidence_id=ids.next(), source_type="project", source_name=title,
            source_path=f"structured_resume.projects[{index}].raw_text", raw_text=raw,
            canonical_terms=_terms(title, *technologies), confidence_type="direct",
        ))

    for key, source_type, label in (("experience", "experience", "Experience entry"), ("internships", "internship", "Internship entry")):
        for index, item in enumerate(structured_data.get(key, []) or []):
            if not isinstance(item, dict):
                continue
            text = str(item.get("raw_text") or "").strip()
            if not text:
                continue
            records.append(EvidenceRecord(
                evidence_id=ids.next(), source_type=source_type, source_name=label,
                source_path=f"structured_resume.{key}[{index}].raw_text", raw_text=text,
                canonical_terms=_terms(text), confidence_type="direct",
            ))

    for key, source_type, label in (
        ("certifications", "certification", "Certification"),
        ("achievements", "achievement", "Achievement"),
        ("qualifications", "qualification", "Listed qualification"),
    ):
        for index, item in enumerate(structured_data.get(key, []) or []):
            if not isinstance(item, dict):
                continue
            text = str(item.get("raw_text") or "").strip()
            if not text:
                continue
            records.append(EvidenceRecord(
                evidence_id=ids.next(), source_type=source_type, source_name=label,
                source_path=f"structured_resume.{key}[{index}].raw_text", raw_text=text,
                canonical_terms=_terms(text), confidence_type="direct",
            ))

    # "Areas Currently Learning" is real evidence of exposure, but never of hands-on
    # capability — every record from this source is marked `learning_only` so the
    # customizer/cover-letter builder can word it conservatively and never claim it
    # as demonstrated experience (mirrors M3.1's `learning_only` match type).
    for index, item in enumerate(structured_data.get("learning", []) or []):
        if not isinstance(item, dict):
            continue
        text = str(item.get("raw_text") or "").strip()
        if not text:
            continue
        parts = [part.strip() for part in text.split(",") if part.strip()]
        records.append(EvidenceRecord(
            evidence_id=ids.next(), source_type="skill", source_name="Areas Currently Learning",
            source_path=f"structured_resume.learning[{index}].raw_text", raw_text=text,
            canonical_terms=_terms(*(parts or [text])), confidence_type="learning_only",
        ))

    if profile.career_goals:
        text = profile.career_goals.strip()
        if text:
            records.append(EvidenceRecord(
                evidence_id=ids.next(), source_type="qualification", source_name="Career goals",
                source_path="profile.career_goals", raw_text=text,
                canonical_terms=_terms(text), confidence_type="supporting",
            ))

    return records
