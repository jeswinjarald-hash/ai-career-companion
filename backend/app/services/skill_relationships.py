"""Shared, deterministic skill relationships used by both Job Matching (M2) and Skill
Gap Analysis (M3.1), so the two services judge related experience the same way.

Technologies that are conceptually related to a requirement but must never be treated
as an exact/equivalent match (e.g. TensorFlow experience does not demonstrate PyTorch).
A related hit only ever produces partial credit / a "partial" match, and callers always
name the related technology that was actually found so the student is never misled.

Lookups normalize the table with `job_matching.normalize_term`, so entries may use
display spellings ("node.js"). No module-level app imports, so `job_matching` and
`skill_gap_evidence` can both depend on this module.
"""

from functools import lru_cache

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
    # Deliberately excludes "python": Python alone is far too general-purpose to imply
    # hands-on Pandas/NumPy/Scikit-learn work — only an explicit data-science/ML signal
    # (or the sibling library itself) counts as related evidence for these.
    "scikit-learn": {"machine learning", "data science"},
    "pandas": {"data science", "numpy"},
    "numpy": {"data science", "pandas"},
}


@lru_cache(maxsize=1)
def _normalized_table() -> dict[str, frozenset[str]]:
    # Normalized with the same `normalize_term` callers use for requirements and
    # evidence (it maps e.g. "node.js" -> "nodejs"), so table spellings can never drift
    # from lookup spellings. Imported lazily: job_matching imports this module.
    from app.services.job_matching import normalize_term

    return {normalize_term(term): frozenset(normalize_term(value) for value in related) for term, related in RELATED_TERMS.items()}


def related_terms(requirement: str) -> set[str]:
    """Terms whose evidence partially supports `requirement` (already normalized), in
    both directions of the table: what the requirement lists as related, plus every
    technology that lists the requirement as related (MySQL lists SQL, so MySQL
    evidence partially supports a SQL requirement). Never includes the requirement."""
    table = _normalized_table()
    forward = set(table.get(requirement, frozenset()))
    inverse = {term for term, related in table.items() if requirement in related}
    return (forward | inverse) - {requirement}
