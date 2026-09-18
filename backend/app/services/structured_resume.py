import re
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Resume, ResumeSection, StructuredResume

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


def _entries(sections: list[ResumeSection], names: set[str]) -> list[dict]:
    return [{"raw_text": section.content} for section in sections if section.name in names and section.content.strip()]


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
            if line:
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


def _education(sections: list[ResumeSection]) -> list[dict]:
    entries: list[dict] = []
    for section in sections:
        if section.name != "education":
            continue
        current_lines: list[str] = []
        current_degree: str | None = None
        for raw_line in section.content.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            degree_match = _DEGREE_PATTERN.search(line)
            # A new degree line starts a new education entry; everything else
            # (institution name, graduation date, CGPA, coursework, ...) is
            # metadata that belongs to whichever degree entry is currently open.
            if degree_match and current_lines:
                entries.append(_finalize_education_entry(current_degree, current_lines))
                current_lines = []
                current_degree = None
            if degree_match:
                current_degree = degree_match.group(1)
            current_lines.append(line)
        if current_lines:
            entries.append(_finalize_education_entry(current_degree, current_lines))
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
    "Tools:", ...) or an unlabeled comma/pipe/slash-separated list containing at least
    two recognized skills. It can appear anywhere in a project entry — many resumes put
    it after the bullet list, not only directly under the title — so callers must check
    for it on every line, not just the first.
    """
    stripped = line.strip()
    label_match = _TECH_LABEL_PATTERN.match(stripped)
    candidate = label_match.group(2) if label_match else stripped
    if not label_match and not any(separator in candidate for separator in (",", "|", "/")):
        return None
    terms = _skills(candidate)
    if label_match:
        return terms
    return terms if len(terms) >= 2 else None


def _split_into_project_blocks(content: str) -> list[str]:
    """Splits project-section content on blank lines.

    A blank line between entries is the most reliable, resume-format-agnostic signal
    that one project has ended and the next begins — it doesn't depend on a bullet
    glyph or a specific tech-list wording surviving PDF/DOCX text extraction. Content
    with no blank lines (or where extraction collapsed them) comes back as one block,
    and `_group_project_block` falls back to per-line heuristics for that block.
    """
    blocks = re.split(r"\n[ \t]*\n", content)
    return [block for block in blocks if block.strip()]


def _group_project_block(lines: list[tuple[str, bool]]) -> list[dict]:
    projects: list[dict] = []
    current: dict | None = None
    description_lines: list[str] = []
    for line, indented in lines:
        if current is None:
            # The first line of a project block is always its heading.
            current = {"title": line, "description": "", "technologies": [], "raw_text": line}
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
        current["description"] = " ".join(description_lines)
        current["raw_text"] = current["title"] + (f" - {current['description']}" if current["description"] else "")
        projects.append(current)
        current = {"title": line, "description": "", "technologies": [], "raw_text": line}
        description_lines = []
    if current is not None:
        current["description"] = " ".join(description_lines)
        current["raw_text"] = current["title"] + (f" - {current['description']}" if current["description"] else "")
        projects.append(current)
    return projects


def _projects(sections: list[ResumeSection]) -> list[dict]:
    projects = []
    for section in sections:
        if section.name != "projects":
            continue
        for block in _split_into_project_blocks(section.content):
            projects.extend(_group_project_block(_reflow_lines(block.splitlines())))
    return projects


def build_structured_data(sections: list[ResumeSection]) -> dict:
    all_text = "\n".join(section.content for section in sections)
    skills_text = "\n".join(section.content for section in sections if section.name == "skills") or all_text
    technical_skills = _skills(skills_text)
    soft_skills = [skill for skill in _soft_skills(skills_text) if skill not in technical_skills]
    return {
        "header": next((section.content for section in sections if section.name == "header"), ""),
        "summary": next((section.content for section in sections if section.name == "summary"), None),
        "skills": technical_skills + soft_skills,
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
        "sections": [{"name": s.name, "original_heading": s.original_heading, "content": s.content, "position": s.position} for s in sections],
    }


def get_structured_resume(db: Session, resume_id: int) -> StructuredResume | None:
    return db.scalar(select(StructuredResume).where(StructuredResume.resume_id == resume_id))


def structure_resume(db: Session, resume: Resume) -> StructuredResume:
    sections = list(db.scalars(select(ResumeSection).where(ResumeSection.resume_id == resume.id).order_by(ResumeSection.position)))
    if not sections:
        raise ValueError("Resume sections must be detected before structuring.")
    result = get_structured_resume(db, resume.id)
    if result is None:
        result = StructuredResume(resume_id=resume.id, data={})
        db.add(result)
    result.data = build_structured_data(sections)
    resume.status = "structured"
    db.commit()
    db.refresh(result)
    return result
