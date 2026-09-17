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


def _entries(sections: list[ResumeSection], names: set[str]) -> list[dict]:
    return [{"raw_text": section.content} for section in sections if section.name in names and section.content.strip()]


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


def _projects(sections: list[ResumeSection]) -> list[dict]:
    projects = []
    for section in sections:
        if section.name != "projects":
            continue
        current: dict | None = None
        description_lines: list[str] = []
        for line, indented in _reflow_lines(section.content.splitlines()):
            if current is None:
                # The first line of the section is always a project heading.
                current = {"title": line, "description": "", "technologies": [], "raw_text": line}
            elif indented:
                description_lines.append(_strip_bullet_prefix(line))
            elif not description_lines and "," in line and len(_skills(line)) >= 2:
                # An unbulleted, un-indented line directly under a title that reads
                # like a technology list ("Python, FastAPI, ...") describes the
                # current project rather than starting a new one.
                current["technologies"] = _skills(line)
            else:
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


def build_structured_data(sections: list[ResumeSection]) -> dict:
    all_text = "\n".join(section.content for section in sections)
    return {
        "header": next((section.content for section in sections if section.name == "header"), ""),
        "summary": next((section.content for section in sections if section.name == "summary"), None),
        "skills": _skills("\n".join(section.content for section in sections if section.name == "skills") or all_text),
        "education": _education(sections),
        "experience": _entries(sections, {"experience"}),
        "internships": _entries(sections, {"internships"}),
        "projects": _projects(sections),
        "certifications": _entries(sections, {"certifications"}),
        "achievements": _entries(sections, {"achievements"}),
        "qualifications": _entries(sections, {"qualifications"}),
        "interests": _entries(sections, {"interests"}),
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
