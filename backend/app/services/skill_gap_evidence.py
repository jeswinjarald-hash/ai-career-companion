"""Deterministic, grounded evidence extraction and requirement matching for Milestone 3.1.

Reuses the M2.3 term normalization (`app.services.job_matching.normalize_term`) so that
skill vocabulary stays consistent across job matching and skill gap analysis. Every match
this module reports is traceable to an explicit student-provided source (profile skills,
resume skills section, a project, an experience/internship entry, a certification, an
achievement, or a listed qualification) — nothing here is inferred from an LLM.
"""

import re
from dataclasses import dataclass, field

from app.models import CandidateProfile
from app.schemas.skill_gap import EvidenceItem, MatchType
from app.services.job_matching import normalize_term

# Technologies that are conceptually related to a requirement but must never be treated
# as an exact/equivalent match (e.g. TensorFlow experience does not demonstrate PyTorch).
# A hit here only ever produces a "partial" match, and the evidence always names the
# related technology that was actually found so the student is never misled.
RELATED_TERMS: dict[str, set[str]] = {
    "fastapi": {"rest apis", "flask", "django", "web framework", "backend framework"},
    "flask": {"rest apis", "fastapi", "django", "web framework"},
    "django": {"rest apis", "fastapi", "flask", "web framework"},
    "aws": {"cloud", "azure", "gcp", "deployment"},
    "azure": {"cloud", "aws", "gcp", "deployment"},
    "gcp": {"cloud", "aws", "azure", "deployment"},
    "docker": {"deployment", "containerization", "devops", "cloud"},
    "kubernetes": {"docker", "containerization", "devops", "deployment"},
    "pytorch": {"tensorflow", "deep learning", "machine learning", "neural network"},
    "tensorflow": {"pytorch", "deep learning", "machine learning", "neural network"},
    "react": {"javascript", "frontend", "angular", "vue", "web development"},
    "angular": {"javascript", "frontend", "react", "vue", "web development"},
    "vue": {"javascript", "frontend", "react", "angular", "web development"},
    "mongodb": {"database", "sql", "mysql", "postgresql", "nosql"},
    "mysql": {"database", "sql", "postgresql", "mongodb"},
    "postgresql": {"database", "sql", "mysql", "mongodb"},
    "node.js": {"javascript", "backend", "express", "web development"},
    "express": {"node.js", "javascript", "backend"},
    "kotlin": {"java", "android", "mobile development"},
    "swift": {"ios", "mobile development", "objective-c"},
    "spring boot": {"java", "backend framework", "rest apis"},
    "graphql": {"rest apis", "api development"},
    "ci/cd": {"devops", "automation", "deployment"},
    "scikit-learn": {"machine learning", "python", "data science"},
    "pandas": {"data science", "python", "numpy"},
    "numpy": {"data science", "python", "pandas"},
}

EvidenceSource = str

_BOUNDARY_BEFORE = r"(?<![\w+#.])"
_BOUNDARY_AFTER = r"(?![\w+#])"


def mentions_term(term: str, normalized_haystack: str) -> bool:
    if not term or not normalized_haystack:
        return False
    pattern = _BOUNDARY_BEFORE + re.escape(term) + _BOUNDARY_AFTER
    return re.search(pattern, normalized_haystack) is not None


@dataclass(frozen=True)
class EvidenceUnit:
    source: EvidenceSource
    source_name: str
    raw_text: str
    normalized_text: str
    explicit_terms: set[str] = field(default_factory=set)


def _unit_from_text(source: str, source_name: str, raw_text: str) -> EvidenceUnit | None:
    text = raw_text.strip()
    if not text:
        return None
    return EvidenceUnit(source=source, source_name=source_name, raw_text=text, normalized_text=normalize_term(text))


def build_evidence_units(profile: CandidateProfile, structured_data: dict) -> list[EvidenceUnit]:
    units: list[EvidenceUnit] = []

    if profile.skills:
        blob = ", ".join(profile.skills)
        terms = {normalize_term(skill) for skill in profile.skills if normalize_term(skill)}
        units.append(EvidenceUnit("profile_skills", "Career Profile Skills", blob, normalize_term(blob), terms))

    resume_skills = structured_data.get("skills", []) or []
    if resume_skills:
        blob = ", ".join(str(skill) for skill in resume_skills)
        terms = {normalize_term(str(skill)) for skill in resume_skills if normalize_term(str(skill))}
        units.append(EvidenceUnit("resume_skills", "Resume Skills Section", blob, normalize_term(blob), terms))

    profile_education_bits = [value for value in (profile.education, profile.degree, profile.specialization) if value]
    if profile_education_bits:
        unit = _unit_from_text("education", "Career Profile Education", " ".join(profile_education_bits))
        if unit:
            units.append(unit)
    for entry in structured_data.get("education", []) or []:
        if not isinstance(entry, dict):
            continue
        unit = _unit_from_text("education", "Resume Education Section", str(entry.get("raw_text") or ""))
        if unit:
            units.append(unit)

    for project in structured_data.get("projects", []) or []:
        if not isinstance(project, dict):
            continue
        title = str(project.get("title") or "Project").strip() or "Project"
        raw = str(project.get("raw_text") or project.get("description") or title)
        terms = {normalize_term(str(tech)) for tech in project.get("technologies", []) if normalize_term(str(tech))}
        unit = _unit_from_text("project", title, raw)
        if unit:
            units.append(EvidenceUnit(unit.source, unit.source_name, unit.raw_text, unit.normalized_text, terms))

    for key, source, label in (("experience", "experience", "Experience entry"), ("internships", "internship", "Internship entry")):
        for item in structured_data.get(key, []) or []:
            if not isinstance(item, dict):
                continue
            unit = _unit_from_text(source, label, str(item.get("raw_text") or ""))
            if unit:
                units.append(unit)

    for key, source, label in (
        ("certifications", "certification", "Certification"),
        ("achievements", "achievement", "Achievement"),
        ("qualifications", "qualification", "Listed qualification"),
    ):
        for item in structured_data.get(key, []) or []:
            if not isinstance(item, dict):
                continue
            unit = _unit_from_text(source, label, str(item.get("raw_text") or ""))
            if unit:
                units.append(unit)

    if profile.career_goals:
        unit = _unit_from_text("qualification", "Career goals", profile.career_goals)
        if unit:
            units.append(unit)

    return units


def evidence_item(unit: EvidenceUnit, requirement: str | None = None) -> EvidenceItem:
    # A skills-list unit's raw_text is the whole comma-separated list (needed for term
    # matching), which would repeat the entire list as "evidence" for every single skill
    # matched from it. Cite the specific requirement instead of dumping the full list.
    if requirement and unit.source in ("profile_skills", "resume_skills"):
        location = "profile skills" if unit.source == "profile_skills" else "resume skills section"
        return EvidenceItem(source=unit.source, source_name=unit.source_name, evidence=f'"{requirement}" is listed in your {location}.')
    text = unit.raw_text.strip()
    snippet = text if len(text) <= 240 else text[:237].rstrip() + "..."
    return EvidenceItem(source=unit.source, source_name=unit.source_name, evidence=snippet or unit.source_name)


def related_evidence_item(unit: EvidenceUnit, related_pool: set[str]) -> EvidenceItem:
    matched_term = next(iter(unit.explicit_terms & related_pool), None)
    if matched_term is None:
        matched_term = next((term for term in related_pool if mentions_term(term, unit.normalized_text)), "a related technology")
    if unit.source in ("profile_skills", "resume_skills"):
        location = "profile skills" if unit.source == "profile_skills" else "resume skills section"
        return EvidenceItem(source=unit.source, source_name=unit.source_name, evidence=f'"{matched_term}" is listed in your {location} — related, but not the same as the requirement.')
    text = unit.raw_text.strip()
    snippet = text if len(text) <= 240 else text[:237].rstrip() + "..."
    return EvidenceItem(source=unit.source, source_name=unit.source_name, evidence=snippet or unit.source_name)


def match_requirement(requirement: str, units: list[EvidenceUnit]) -> tuple[MatchType, float, list[EvidenceItem], str]:
    """Classifies a single job requirement against the student's evidence.

    Layered matching, in order: (1) normalized exact/alias term match against explicitly
    declared skills (profile + resume skills section + project technologies), (2) exact
    term mention found in free-text evidence (project/experience descriptions), (3) related
    -but-not-equivalent technology found via `RELATED_TERMS` -> partial, (4) no evidence at
    all -> missing. Confidence is a fixed, documented value per branch, never LLM-guessed.
    """
    req_term = normalize_term(requirement)
    if not req_term:
        return "missing", 0.5, [], "This requirement could not be normalized for comparison."

    explicit_hits = [unit for unit in units if req_term in unit.explicit_terms]
    text_hits = [unit for unit in units if unit not in explicit_hits and mentions_term(req_term, unit.normalized_text)]
    exact_hits = explicit_hits + text_hits
    if exact_hits:
        evidence = [evidence_item(unit, requirement) for unit in exact_hits[:3]]
        confidence = 0.95 if any(unit.source in ("profile_skills", "resume_skills") for unit in exact_hits) else 0.85
        location = exact_hits[0].source_name if exact_hits[0].source not in ("profile_skills", "resume_skills") else "profile"
        reason = f'"{requirement}" is explicitly demonstrated, evidenced in your {location}.'
        return "demonstrated", confidence, evidence, reason

    related_pool = RELATED_TERMS.get(req_term, set())
    partial_hits: list[EvidenceUnit] = []
    if related_pool:
        for unit in units:
            if unit.explicit_terms & related_pool or any(mentions_term(term, unit.normalized_text) for term in related_pool):
                partial_hits.append(unit)
    if partial_hits:
        evidence = [related_evidence_item(unit, related_pool) for unit in partial_hits[:3]]
        reason = (
            f'Related evidence exists in your {partial_hits[0].source_name}, '
            f'but "{requirement}" itself is not explicitly demonstrated. Treated as partially demonstrated, not a confirmed match.'
        )
        return "partial", 0.6, evidence, reason

    return "missing", 0.95, [], "No explicit evidence found in the current resume/profile."
