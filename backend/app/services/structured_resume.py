import logging
import re
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Resume, ResumeSection, StructuredResume

logger = logging.getLogger(__name__)

SKILL_ALIASES = {
    "js": "JavaScript", "javascript": "JavaScript", "ts": "TypeScript", "typescript": "TypeScript",
    "python": "Python", "java": "Java", "c++": "C++", "c#": "C#", "go": "Go", "rust": "Rust",
    "html": "HTML", "css": "CSS", "react": "React", "angular": "Angular", "vue": "Vue",
    "fastapi": "FastAPI", "fast api": "FastAPI", "flask": "Flask", "django": "Django", "node.js": "Node.js", "nodejs": "Node.js", "express": "Express", "spring boot": "Spring Boot", "rest api": "REST APIs", "rest apis": "REST APIs", "restful api": "REST APIs", "graphql": "GraphQL",
    "sql": "SQL", "postgres": "PostgreSQL", "postgresql": "PostgreSQL", "mysql": "MySQL", "sqlite": "SQLite", "sqlalchemy": "SQLAlchemy", "mongodb": "MongoDB", "redis": "Redis",
    "git": "Git", "github": "GitHub", "docker": "Docker", "kubernetes": "Kubernetes", "aws": "AWS", "azure": "Azure", "gcp": "GCP", "ci/cd": "CI/CD", "linux": "Linux",
    "machine learning": "Machine Learning", "deep learning": "Deep Learning", "pandas": "Pandas", "numpy": "NumPy", "scikit-learn": "Scikit-learn", "sklearn": "Scikit-learn", "tensorflow": "TensorFlow", "pytorch": "PyTorch", "statistics": "Statistics", "matplotlib": "Matplotlib",
    "data structures": "Data Structures", "algorithms": "Algorithms", "oop": "OOP", "dbms": "DBMS", "operating systems": "Operating Systems", "computer networks": "Computer Networks", "system design": "System Design",
    "postman": "Postman", "vs code": "VS Code", "visual studio code": "VS Code", "sdlc": "Software Development Lifecycle", "software development lifecycle": "Software Development Lifecycle",
}


def _skills(text: str) -> list[str]:
    lowered = text.casefold()
    found = []
    for alias, canonical in sorted(SKILL_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        if re.search(r"(?<![\w+#])" + re.escape(alias) + r"(?![\w+#])", lowered) and canonical not in found:
            found.append(canonical)
    return found


# Deliberately small and conservative: only well-established, unambiguous soft-skill
# terms a resume states about itself (never inferred from unrelated evidence). Kept
# separate from SKILL_ALIASES/_skills() so soft-skill terms never leak into project
# "technologies" detection (`_technology_terms`), which must stay strictly technical.
SOFT_SKILL_ALIASES = {
    "problem solving": "Problem Solving", "problem-solving": "Problem Solving",
    "team collaboration": "Team Collaboration", "teamwork": "Team Collaboration", "team work": "Team Collaboration",
    "communication": "Communication", "verbal communication": "Communication", "written communication": "Communication",
    "adaptability": "Adaptability", "adaptable": "Adaptability",
    "time management": "Time Management",
    "leadership": "Leadership",
    "critical thinking": "Critical Thinking",
    "attention to detail": "Attention to Detail",
    "collaboration": "Collaboration",
}


def _soft_skills(text: str) -> list[str]:
    lowered = text.casefold()
    found = []
    for alias, canonical in sorted(SOFT_SKILL_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        if re.search(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", lowered) and canonical not in found:
            found.append(canonical)
    return found


def _explicit_skill_items(text: str) -> list[str]:
    """Splits a dedicated Skills section's content into individual self-declared
    items (one per line, or comma-separated within a line). A known item is
    canonicalized via `_skills`/`_soft_skills`; an item that matches neither
    vocabulary (e.g. "Frontend Development", a stated concept rather than a named
    technology) is preserved verbatim rather than silently dropped.

    A curated Skills section is, by resume convention, already an intentional list
    of self-declared competencies — unlike free prose (where blindly keeping every
    unmatched phrase would flatten unrelated nouns into fake "skills"), every item
    here is meaningful and deserves to survive.
    """
    items: list[str] = []
    seen: set[str] = set()
    for raw_line in text.splitlines():
        for fragment in raw_line.split(","):
            candidate = _strip_bullet_prefix(fragment.strip()).strip()
            if not candidate or not _is_meaningful_entry(candidate):
                continue
            technical = _skills(candidate)
            soft = _soft_skills(candidate)
            resolved = technical[0] if technical else (soft[0] if soft else candidate)
            key = resolved.casefold()
            if key not in seen:
                seen.add(key)
                items.append(resolved)
    return items


_MEANINGFUL_ENTRY_MIN_LENGTH = 3


def _is_meaningful_entry(text: str) -> bool:
    """Rejects degenerate fragments (a bare "in", a stray punctuation mark, ...) that
    should never surface as a structured entry regardless of which stage produced
    them — a defensive floor, not the primary correctness mechanism."""
    stripped = text.strip()
    if len(stripped) < _MEANINGFUL_ENTRY_MIN_LENGTH:
        return False
    return any(character.isalnum() for character in stripped)


def _entries(sections: list[ResumeSection], names: set[str]) -> list[dict]:
    return [
        {"raw_text": section.content}
        for section in sections
        if section.name in names and _is_meaningful_entry(section.content)
    ]


def _line_entries(sections: list[ResumeSection], names: set[str]) -> list[dict]:
    """Splits a section's content into one entry per non-blank line.

    Certifications, achievements, and areas-currently-learning are conventionally one
    item per line. Grouping a whole such section into a single blob (as `_entries`
    correctly does for genuinely multi-line entries like a job's title + bullets)
    would cite an unrelated certification's title as "evidence" for a different,
    unrelated skill match downstream.
    """
    entries: list[dict] = []
    for section in sections:
        if section.name not in names:
            continue
        for raw_line in section.content.splitlines():
            line = _strip_bullet_prefix(raw_line.strip()).strip()
            if _is_meaningful_entry(line):
                entries.append({"raw_text": line})
    return entries


_DEGREE_PATTERN = re.compile(
    r"\b(B\.?Tech|B\.?E\.?|M\.?Tech|MCA|BCA|B\.?Sc|M\.?Sc|Ph\.?D|Diploma|12th|10th|"
    r"Bachelor of [A-Za-z]+(?: [A-Za-z]+)?|Master of [A-Za-z]+(?: [A-Za-z]+)?)\b",
    re.I,
)
_YEAR_PATTERN = re.compile(r"\b(19|20)\d{2}\b")


def _finalize_education_entry(degree: str | None, lines: list[str]) -> dict:
    raw_text = " ".join(lines)
    years = [int(match.group()) for match in _YEAR_PATTERN.finditer(raw_text)]
    # A graduation year is the latest year mentioned (e.g. the end of a "2023 - 2027"
    # range, or the single year in "Expected Graduation: 2027"), not the first digits
    # matched, which would wrongly pick up an enrollment/start year instead.
    return {"degree": degree, "graduation_year": years[-1] if years else None, "raw_text": raw_text}


def _education_block(lines: list[str]) -> list[dict]:
    entries: list[dict] = []
    current_lines: list[str] = []
    current_degree: str | None = None
    for line in lines:
        degree_match = _DEGREE_PATTERN.search(line)
        # A second degree line — one seen after this entry already has a degree —
        # starts a new education entry. An institution/heading line that happens to
        # come *before* its own degree line (e.g. "Loyola ICAM College of..." then
        # "B.Tech Information Technology" on the next line) must NOT split into two
        # entries just because a line was already accumulated; only a genuinely new
        # degree closes the currently open one.
        if degree_match and current_degree is not None:
            entries.append(_finalize_education_entry(current_degree, current_lines))
            current_lines = []
            current_degree = None
        if degree_match:
            current_degree = degree_match.group(1)
        current_lines.append(line)
    if current_lines:
        entries.append(_finalize_education_entry(current_degree, current_lines))
    return entries


def _education(sections: list[ResumeSection]) -> list[dict]:
    entries: list[dict] = []
    for section in sections:
        if section.name != "education":
            continue
        for block in _split_into_blank_line_blocks(section.content):
            lines = [line.strip() for line in block.splitlines() if line.strip()]
            if lines:
                entries.extend(_education_block(lines))
    return entries


_BULLET_PREFIXES = ("-", "•")


def _is_bullet_or_indented(raw_line: str) -> bool:
    if raw_line[:1] in (" ", "\t"):
        return True
    return raw_line.lstrip().startswith(_BULLET_PREFIXES)


def _ends_with_terminal_punctuation(text: str) -> bool:
    return text.rstrip().endswith((".", "!", "?", ":"))


def _starts_lowercase(text: str) -> bool:
    first_letter = next((character for character in text if character.isalpha()), None)
    return first_letter is not None and first_letter.islower()


def _reflow_lines(raw_lines: list[str]) -> list[tuple[str, bool]]:
    """Rejoins PDF line-wrap fragments into logical lines before grouping.

    PDF text extraction breaks a wrapped sentence across physical lines with no
    reliable marker of its own; a fragment that continues a bullet ("...exposes
    REST" / "endpoints.") must not be mistaken for the start of a new entry. A
    physical line is treated as a continuation of the previous logical line only
    when it is itself not a bullet/indented line, the previous logical line does
    not yet end with terminal punctuation (i.e. it looks unfinished), AND the
    physical line starts with a lowercase letter — the standard signal that it
    continues mid-sentence rather than starting a new heading or list line (a new
    title or a tech-stack list reads "Python, FastAPI, ...", never "python...").

    Returns (text, is_bullet_or_indented) pairs, where the flag reflects the first
    physical line of that logical line.
    """
    logical_parts: list[list[str]] = []
    logical_indent: list[bool] = []
    for raw_line in raw_lines:
        if not raw_line.strip():
            continue
        starts_new_segment = _is_bullet_or_indented(raw_line)
        stripped = raw_line.strip()
        is_continuation = (
            logical_parts
            and not starts_new_segment
            and not _ends_with_terminal_punctuation(logical_parts[-1][-1])
            and _starts_lowercase(stripped)
        )
        if is_continuation:
            logical_parts[-1].append(stripped)
        else:
            logical_parts.append([stripped])
            logical_indent.append(starts_new_segment)
    return [(" ".join(parts), indent) for parts, indent in zip(logical_parts, logical_indent)]


def _strip_bullet_prefix(line: str) -> str:
    return line.lstrip("".join(_BULLET_PREFIXES) + " \t")


_TECH_LABEL_PATTERN = re.compile(r"(?i)^(technologies(?:\s+used)?|tech(?:nical)?\s*stack|tools?(?:\s+used)?|stack)\s*[:\-]\s*(.+)$")


def _technology_terms(line: str) -> list[str] | None:
    """Returns this line's technology terms if it reads as a tech-stack line, else None.

    A tech-stack line is either an explicit label ("Technologies:", "Tech Stack:",
    "Tools:", ...) or a short, unlabeled comma/pipe/slash-separated list that is mostly
    made of recognized skills. It can appear anywhere in a project entry — many resumes
    put it after the bullet list, not only directly under the title — so callers must
    check for it on every line, not just the first.

    The unlabeled case is deliberately conservative: a long prose sentence that merely
    *mentions* a couple of technologies in passing ("...independently using HTML, CSS,
    JavaScript, Node.js, Express.js, and MongoDB. The project was designed to manage
    members, payments...") must stay a description line, not be swallowed whole as a
    "tech-stack line" just because it contains a comma and two recognized words.
    """
    stripped = line.strip()
    label_match = _TECH_LABEL_PATTERN.match(stripped)
    candidate = label_match.group(2) if label_match else stripped
    if label_match:
        return _skills(candidate)
    if not any(separator in candidate for separator in (",", "|", "/")):
        return None
    words = candidate.split()
    if len(words) > 12:
        return None
    terms = _skills(candidate)
    if len(terms) < 2 or len(terms) < max(2, len(words) // 2):
        return None
    return terms


_TITLE_ANNOTATION_SPLIT = re.compile(r"\s+[-–—|]\s+|:\s+(?=\S)")


def _split_title_and_annotation(line: str) -> tuple[str, str | None]:
    """Splits "Project Name — Built using X, Y and Z" into (title, annotation).

    Only splits when the trailing part actually reads as tech-stack content (checked
    via `_technology_terms`); otherwise the whole line is kept as the title. This is
    what lets "Society Finance Management — Built using Node,Express and MongoDB"
    split correctly while a title that simply contains a dash/colon with no tech
    annotation, e.g. "AI Career Companion - Backend Foundation", is left intact.
    """
    match = _TITLE_ANNOTATION_SPLIT.search(line)
    if not match:
        return line, None
    head, tail = line[: match.start()].strip(), line[match.end():].strip()
    if not head or not tail:
        return line, None
    if _technology_terms(tail) is None:
        return line, None
    return head, tail


_TITLE_CONTINUATION_STARTS = {
    "a", "an", "the", "and", "or", "but", "with", "for", "to", "of", "in", "on", "as", "at", "by", "from",
    "that", "this", "these", "those", "it", "its", "is", "are", "was", "were", "be", "been", "being",
    "using", "used", "use", "built", "build", "developed", "develop", "designed", "design",
    "created", "create", "implemented", "implement", "worked", "work", "led", "lead", "managed", "manage",
    "collaborated", "collaborate", "contributed", "contribute", "assisted", "assist", "wrote", "write",
    "added", "add", "includes", "include", "features", "feature", "enables", "enable", "allows", "allow",
    "responsible", "involved", "helped", "help", "supported", "support",
}


def _looks_like_project_title(line: str) -> bool:
    """Conservative, structural-first validation for "does this line start a NEW
    project" (used only as a fallback when a line is neither indented/bulleted nor a
    recognized tech-stack line). Rejects sentence-continuation fragments — the actual
    cause of a project description exploding into many bogus single-word/short-phrase
    "projects" — without requiring every resume to follow one exact format.
    """
    stripped = line.strip()
    if not stripped or len(stripped) < 3:
        return False
    first_alpha = next((character for character in stripped if character.isalpha()), None)
    if first_alpha is not None and first_alpha.islower():
        return False  # a lowercase-led line is virtually always a sentence continuation
    if _ends_with_terminal_punctuation(stripped):
        return False  # a completed sentence, not a title
    first_word = re.sub(r"[^a-zA-Z]", "", stripped.split()[0]).casefold()
    if first_word in _TITLE_CONTINUATION_STARTS:
        return False
    return True


def _split_into_blank_line_blocks(content: str) -> list[str]:
    """Splits project-section content on blank lines.

    A blank line between entries is the most reliable, resume-format-agnostic signal
    that one project has ended and the next begins — it doesn't depend on a bullet
    glyph or a specific tech-list wording surviving PDF/DOCX text extraction. Content
    with no blank lines (or where extraction collapsed them) comes back as one block,
    and `_group_project_block` falls back to per-line heuristics for that block.
    """
    blocks = re.split(r"\n[ \t]*\n", content)
    return [block for block in blocks if block.strip()]


def _new_project(line: str) -> tuple[dict, str | None]:
    title, annotation = _split_title_and_annotation(line)
    project = {"title": title, "description": "", "technologies": [], "raw_text": title}
    return project, annotation


def _group_project_block(lines: list[tuple[str, bool]]) -> list[dict]:
    projects: list[dict] = []
    current: dict | None = None
    description_lines: list[str] = []

    def finalize() -> None:
        if current is None:
            return
        current["description"] = " ".join(description_lines)
        current["raw_text"] = current["title"] + (f" - {current['description']}" if current["description"] else "")
        # A tech-stack line (if any) is the most explicit signal, but a description
        # can legitimately mention further recognized technologies in prose (e.g.
        # "...using HTML, CSS, JavaScript, Node.js, Express.js, and MongoDB.") that
        # never appeared in a dedicated line — surface those too, deduplicated.
        for skill in _skills(current["description"]):
            if skill not in current["technologies"]:
                current["technologies"].append(skill)
        projects.append(current)

    pending: list[tuple[str, bool]] = list(lines)
    while pending:
        line, indented = pending.pop(0)
        if current is None:
            # The first line of a project block is always its heading; an inline
            # tech annotation after a dash/colon/pipe is split off and processed like
            # any other line rather than folded into the title.
            current, annotation = _new_project(line)
            description_lines = []
            if annotation:
                pending.insert(0, (annotation, False))
            continue

        technologies = _technology_terms(line)
        # An explicit label ("Technologies:", "Tech Stack:", ...) is unambiguous even on
        # an indented/bulleted line. Without a label, only treat an unindented line as a
        # tech-stack line — a bulleted sentence that merely *mentions* two technologies
        # in prose ("Used Python, FastAPI and Git.") is still a description line, not a
        # dedicated tech-stack line, and must stay part of the description.
        if technologies is not None and (not indented or _TECH_LABEL_PATTERN.match(line.strip())):
            current["technologies"] = technologies
            continue
        if indented:
            description_lines.append(_strip_bullet_prefix(line))
            continue
        if _looks_like_project_title(line):
            finalize()
            current, annotation = _new_project(line)
            description_lines = []
            if annotation:
                pending.insert(0, (annotation, False))
            continue
        # Neither a recognized tech line nor a plausible new title — a sentence
        # fragment (a wrapped continuation, or a description with no bullet marker
        # at all) that belongs to the current project's description.
        description_lines.append(line)
    finalize()
    return projects


def _projects(sections: list[ResumeSection]) -> list[dict]:
    projects = []
    for section in sections:
        if section.name != "projects":
            continue
        for block in _split_into_blank_line_blocks(section.content):
            projects.extend(_group_project_block(_reflow_lines(block.splitlines())))
    return projects


def build_structured_data(sections: list[ResumeSection]) -> dict:
    all_text = "\n".join(section.content for section in sections)
    skills_section_text = "\n".join(section.content for section in sections if section.name == "skills")
    if skills_section_text:
        # A dedicated Skills section: every self-declared item is preserved (known
        # ones canonicalized), not just the subset matching a closed vocabulary.
        combined_skills = _explicit_skill_items(skills_section_text)
    else:
        # No dedicated section — fall back to conservative vocabulary-matched
        # scanning of the whole resume; blindly keeping every phrase here would
        # flatten unrelated prose nouns into fake "skills".
        technical_skills = _skills(all_text)
        combined_skills = technical_skills + [skill for skill in _soft_skills(all_text) if skill not in technical_skills]
    return {
        "header": next((section.content for section in sections if section.name == "header"), ""),
        "summary": next((section.content for section in sections if section.name == "summary"), None),
        "skills": combined_skills,
        "education": _education(sections),
        "experience": _entries(sections, {"experience"}),
        "internships": _entries(sections, {"internships"}),
        "projects": _projects(sections),
        "certifications": _line_entries(sections, {"certifications"}),
        "achievements": _line_entries(sections, {"achievements"}),
        "qualifications": _entries(sections, {"qualifications"}),
        "interests": _line_entries(sections, {"interests"}),
        # Learning-only exposure (e.g. an "Areas Currently Learning" heading) is kept
        # entirely separate from `skills` — it must never be reported as demonstrated.
        "learning": _line_entries(sections, {"learning"}),
        # Spoken/written languages (e.g. "English", "Tamil") are kept in their own
        # field — never technologies, projects, or experience evidence.
        "languages": _line_entries(sections, {"languages"}),
        "sections": [{"name": s.name, "original_heading": s.original_heading, "content": s.content, "position": s.position} for s in sections],
    }


def get_structured_resume(db: Session, resume_id: int) -> StructuredResume | None:
    return db.scalar(select(StructuredResume).where(StructuredResume.resume_id == resume_id))


_COMMON_STOPWORDS = {"in", "on", "at", "to", "of", "a", "an", "the", "and", "or", "but", "is", "are", "was", "were", "it", "as"}


def _parser_warnings(data: dict) -> list[str]:
    """Conservative, non-destructive sanity checks over freshly-structured resume
    data. These only ever produce a warning to log for developer diagnostics — they
    never reject or silently alter a legitimate (if unusual) resume.
    """
    warnings: list[str] = []

    projects = data.get("projects", [])
    if len(projects) > 12:
        warnings.append(f"Unusually high project count ({len(projects)}); output may be fragmented.")
    suspicious_titles = [p["title"] for p in projects if p["title"].strip().casefold() in _COMMON_STOPWORDS]
    if suspicious_titles:
        warnings.append(f"Suspicious stop-word project titles: {suspicious_titles}")

    for category in ("experience", "internships"):
        for entry in data.get(category, []):
            text = str(entry.get("raw_text", "")).strip()
            if len(text) < 3 or text.casefold() in _COMMON_STOPWORDS:
                warnings.append(f"Suspicious {category} entry: {text!r}")

    for entry in data.get("education", []):
        raw_text = str(entry.get("raw_text", "")).strip()
        if len(raw_text) < 5:
            warnings.append(f"Education entry looks incomplete: {raw_text!r}")

    return warnings


def structure_resume(db: Session, resume: Resume) -> StructuredResume:
    sections = list(db.scalars(select(ResumeSection).where(ResumeSection.resume_id == resume.id).order_by(ResumeSection.position)))
    if not sections:
        raise ValueError("Resume sections must be detected before structuring.")
    result = get_structured_resume(db, resume.id)
    if result is None:
        result = StructuredResume(resume_id=resume.id, data={})
        db.add(result)

    data = build_structured_data(sections)
    warnings = _parser_warnings(data)
    # Diagnostic only — never the full resume text, per privacy/logging requirements.
    logger.info(
        "resume_structuring_completed resume_id=%s sections=%s education_count=%s project_count=%s "
        "experience_count=%s internship_count=%s skills_count=%s warnings=%s",
        resume.id, [section.name for section in sections], len(data.get("education", [])), len(data.get("projects", [])),
        len(data.get("experience", [])), len(data.get("internships", [])), len(data.get("skills", [])), warnings,
    )

    result.data = data
    resume.status = "structured"
    db.commit()
    db.refresh(result)
    return result
