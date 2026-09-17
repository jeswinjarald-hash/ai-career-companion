from dataclasses import dataclass
import re

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Resume, ResumeSection


ALIASES = {
    "summary": {"summary", "professional summary", "profile", "about me", "career summary"},
    "objective": {"objective", "career objective", "professional objective"},
    "skills": {"skills", "technical skills", "core skills", "key skills", "technologies", "technical proficiencies"},
    "education": {"education", "academic background", "academic qualifications", "educational qualifications", "academics"},
    "experience": {"experience", "work experience", "professional experience", "employment history", "work history"},
    "internships": {"internship", "internships", "internship experience"},
    "projects": {"projects", "academic projects", "personal projects", "key projects", "project experience"},
    "certifications": {"certifications", "certificates", "certifications & courses", "courses & certifications"},
    "achievements": {"achievements", "awards", "honors", "awards & achievements"},
    "interests": {"interests", "career interests", "areas of interest"},
    "publications": {"publications", "papers", "research publications"},
    "activities": {"activities", "extracurricular activities", "co-curricular activities"},
}

_ALIAS_TO_CANONICAL = {alias.casefold(): name for name, aliases in ALIASES.items() for alias in aliases}
_SENTENCE_PUNCTUATION = re.compile(r"[.!?;,]\s*$")


@dataclass(frozen=True)
class DetectedSection:
    name: str
    original_heading: str | None
    content: str


def _heading_text(line: str) -> str:
    return line.strip().rstrip(":").strip(" -|_").strip()


def _canonical_heading(line: str) -> str | None:
    heading = _heading_text(line)
    if not heading or len(heading) > 80 or _SENTENCE_PUNCTUATION.search(heading):
        return None
    canonical = _ALIAS_TO_CANONICAL.get(heading.casefold())
    if canonical:
        return canonical

    words = heading.split()
    if len(words) <= 6 and heading.upper() == heading and any(character.isalpha() for character in heading):
        return "custom"
    return None


def detect_resume_sections(normalized_text: str) -> list[DetectedSection]:
    lines = normalized_text.splitlines()
    heading_indexes = []
    for index, line in enumerate(lines):
        canonical = _canonical_heading(line)
        if canonical:
            heading_indexes.append((index, canonical, _heading_text(line)))

    if not heading_indexes:
        content = normalized_text.strip()
        return [DetectedSection("header", None, content)] if content else []

    sections: list[DetectedSection] = []
    first_heading_index = heading_indexes[0][0]
    preamble = "\n".join(lines[:first_heading_index]).strip()
    if preamble:
        sections.append(DetectedSection("header", None, preamble))

    for item_index, (line_index, canonical, original_heading) in enumerate(heading_indexes):
        next_line_index = heading_indexes[item_index + 1][0] if item_index + 1 < len(heading_indexes) else len(lines)
        content = "\n".join(lines[line_index + 1 : next_line_index]).strip()
        if content:
            sections.append(DetectedSection(canonical, original_heading, content))
        else:
            sections.append(DetectedSection(canonical, original_heading, ""))
    return sections


def get_resume_sections(db: Session, resume_id: int) -> list[ResumeSection]:
    statement = select(ResumeSection).where(ResumeSection.resume_id == resume_id).order_by(ResumeSection.position)
    return list(db.scalars(statement))


def persist_resume_sections(db: Session, resume: Resume, normalized_text: str) -> list[ResumeSection]:
    detected_sections = detect_resume_sections(normalized_text)
    db.execute(delete(ResumeSection).where(ResumeSection.resume_id == resume.id))
    sections = [
        ResumeSection(
            resume_id=resume.id,
            name=section.name,
            original_heading=section.original_heading,
            content=section.content,
            position=position,
        )
        for position, section in enumerate(detected_sections)
    ]
    db.add_all(sections)
    db.commit()
    for section in sections:
        db.refresh(section)
    return sections
