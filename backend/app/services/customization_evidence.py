"""Milestone 3.2 — grounded evidence extraction for resume/cover-letter customization.

Builds the "claim provenance layer": every candidate evidence unit records exactly
where in the student's own profile/resume it came from (`source_path`), so every
downstream generated claim can be traced back to real, student-provided text. This
mirrors `app.services.skill_gap_evidence.build_evidence_units` (same sources, same
"no LLM, no inference" policy) but additionally tracks the indexed field path each
unit was read from, which M3.1's evidence units don't need but M3.2's provenance
requirement does.
"""

import re

from app.models import CandidateProfile
from app.schemas.customization import EvidenceRecord
from app.services.job_matching import normalize_term
from app.services.skill_gap_evidence import mentions_term

# M1's Skills-section parser deliberately preserves every self-declared line/item
# verbatim, including one that isn't a recognized skill/soft-skill term (see
# `structured_resume._explicit_skill_items`'s docstring) — a documented, intentional
# choice so a legitimate-but-unrecognized skill (e.g. "Frontend Development") is
# never silently dropped. The tradeoff: a resume formatted with bare category
# headers on their own line ("Programming" / "Backend" / "Databases", each followed
# by a comma-separated list on the next line) has those headers preserved as if they
# were skills too. Rather than changing M1's intentionally permissive parsing (which
# would risk the exact under-extraction it was built to avoid), M3.2 filters this
# small, conservative, explicitly-named set of category-header words out of its own
# *tailored/exported* skill list and evidence pool only — `structured_resume.data`
# itself, and the "original order" skill list the frontend shows for transparency,
# are never touched.
CATEGORY_LABEL_TERMS: set[str] = {
    "programming", "programming languages", "languages", "language",
    "backend", "back end", "frontend", "front end", "full stack", "fullstack",
    "databases", "database", "web", "web development", "web technologies",
    "tools", "tools and technologies", "tools & technologies", "technologies", "technology",
    "frameworks", "framework", "libraries", "library",
    "devops", "cloud", "cloud technologies", "platforms", "operating systems", "os",
    "concepts", "core concepts", "methodologies", "testing", "version control",
    "soft skills", "technical skills", "core skills", "other skills", "other",
    "others", "miscellaneous", "misc", "general", "skills", "skill",
}


def is_category_label(name: str) -> bool:
    return normalize_term(name) in CATEGORY_LABEL_TERMS


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
        if not text or is_category_label(text):
            continue
        records.append(EvidenceRecord(
            evidence_id=ids.next(), source_type="skill", source_name="Career Profile Skills",
            source_path=f"profile.skills[{index}]", raw_text=text,
            canonical_terms=_terms(text), confidence_type="direct",
        ))

    for index, skill in enumerate(structured_data.get("skills", []) or []):
        text = str(skill).strip()
        if not text or is_category_label(text):
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


def short_education_phrase(profile: CandidateProfile, structured_data: dict) -> tuple[str, list[str]]:
    """A SHORT education descriptor (degree + field only) for a concise summary/
    cover letter — never the institution name, graduation year, CGPA, or coursework
    that a full resume education line typically also contains.
    """
    if profile.degree:
        sources = ["profile.degree"]
        phrase = profile.degree
        if profile.specialization:
            phrase += f" in {profile.specialization}"
            sources.append("profile.specialization")
        return phrase, sources

    for index, entry in enumerate(structured_data.get("education", []) or []):
        if not isinstance(entry, dict):
            continue
        raw = str(entry.get("raw_text") or "").strip()
        if not raw:
            continue
        # A resume education line is conventionally "{degree/field}, {institution},
        # {years}" or "{degree/field} - {institution}" — keeping only the clause
        # before the first separator drops the institution/year/CGPA tail without
        # rewording the degree/field clause itself.
        first_clause = re.split(r"[,–—-]", raw, maxsplit=1)[0].strip()
        return (first_clause or raw), [f"structured_resume.education[{index}].raw_text"]

    return "Student", []


def join_terms(terms: list[str]) -> str:
    """Natural English list joining: no comma for two items ("X and Y"), an Oxford
    comma for three or more ("X, Y, and Z") — used anywhere a skill/keyword list is
    rendered into a sentence, so the phrasing reads correctly regardless of count.
    """
    if not terms:
        return ""
    if len(terms) == 1:
        return terms[0]
    if len(terms) == 2:
        return f"{terms[0]} and {terms[1]}"
    return ", ".join(terms[:-1]) + f", and {terms[-1]}"


_TITLE_DATE_LINE_PATTERN = re.compile(
    r"\b(19|20)\d{2}\b|\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b", re.I,
)


def _looks_like_title_date_line(candidate: str) -> bool:
    # An experience/internship entry's `raw_text` conventionally starts with a
    # short "{title} at {company}, {dates}" sentence before the substantive work
    # description (M1's `_entries()` merges the title line and description into
    # one block). A short sentence containing a year or month name and no obvious
    # sentence-length prose is that title/dates line, not a work description.
    return bool(_TITLE_DATE_LINE_PATTERN.search(candidate)) and len(candidate.split()) <= 14


def summarize_clause(text: str, max_words: int = 28) -> str:
    """Extracts a single grounded clause from raw evidence text without paraphrasing
    — splits at the first sentence boundary (or a comma-joined "including ..." tail,
    a common M1 project-block artifact) and hard-caps at `max_words`. Every word
    returned is a verbatim substring of the original text; this shortens, it never
    rewords. A leading title/dates-only sentence (see `_looks_like_title_date_line`)
    is skipped in favor of the next sentence, so a citation carries the actual work
    description rather than just the job title and dates.
    """
    stripped = text.strip()
    if not stripped:
        return stripped
    boundaries = [m.start() for m in re.finditer(r"[.!?](?:\s|$)", stripped)]
    start = 0
    for boundary_end in boundaries:
        candidate = stripped[start:boundary_end].strip()
        if not _looks_like_title_date_line(candidate) or boundary_end == boundaries[-1]:
            clause = candidate
            break
        start = boundary_end + 1
    else:
        clause = stripped[start:]
    including_split = re.split(r",\s*including\b", clause, maxsplit=1, flags=re.I)
    clause = including_split[0].strip()
    words = clause.split()
    if len(words) > max_words:
        clause = " ".join(words[:max_words]).rstrip(".,;:") + "..."
    return clause.rstrip(".,;: ")
