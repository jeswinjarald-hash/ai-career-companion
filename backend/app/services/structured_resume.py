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


_TITLE_ANNOTATION_MAX_WORDS = 10


_LIST_SPLIT = re.compile(r",|/|\||\band\b", re.I)


def _looks_like_tech_annotation(tail: str) -> bool:
    """A structural, vocabulary-independent check for an inline tech annotation
    after a title delimiter ("Name — Built using X, Y and Z").

    Deliberately does NOT require every (or even any) item to match the curated
    skill vocabulary — that vocabulary can never be exhaustive (e.g. "Flutter" or
    "Firebase" aren't in it), and a strict skill-to-word ratio is also sensitive to
    incidental formatting ("Node,Express" vs "Node, Express" shifts the word count).
    Instead: a tail with 2+ comma/pipe/slash/"and"-separated short segments reads as
    a *list* regardless of whether the terms are recognized — that list *shape* is
    what a plain subtitle like "Backend Foundation" never has. A tail with only one
    segment (no list separator at all) is trusted only when it's essentially just a
    recognized skill name and nothing else, which is what keeps a non-technical
    phrase like "Machine Learning Project" (a recognized term buried in a longer
    noun phrase, not a list) from being misread as an annotation.
    """
    words = tail.split()
    if not words or len(words) > _TITLE_ANNOTATION_MAX_WORDS:
        return False
    # A bare "and" with no comma/pipe/slash anywhere is too weak a signal on its own
    # — "Resume and Job Matching Platform" is an ordinary subtitle, not a list. An
    # explicit separator must be present before "and" is trusted to close out the
    # last item of an enumeration ("Node, Express and MongoDB").
    has_explicit_separator = any(separator in tail for separator in (",", "|", "/"))
    if has_explicit_separator:
        segments = [segment.strip() for segment in _LIST_SPLIT.split(tail) if segment.strip()]
        if len(segments) >= 2:
            return all(len(segment.split()) <= 4 for segment in segments)
    return len(words) <= 2 and len(_skills(tail)) >= 1


def _split_title_and_annotation(line: str) -> tuple[str, str | None]:
    """Splits "Project Name — Built using X, Y and Z" into (title, annotation).

    Only splits when the trailing part actually reads as tech-stack content; otherwise
    the whole line is kept as the title. This is what lets "Society Finance Management
    — Built using Node, Express and MongoDB" split correctly while a title that simply
    contains a dash/colon with no tech annotation, e.g. "AI Career Companion - Backend
    Foundation", is left intact.
    """
    match = _TITLE_ANNOTATION_SPLIT.search(line)
    if not match:
        return line, None
    head, tail = line[: match.start()].strip(), line[match.end():].strip()
    if not head or not tail:
        return line, None
    if not _looks_like_tech_annotation(tail):
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


_PROJECT_TITLE_MAX_WORDS = 9


def _looks_like_project_title(line: str) -> bool:
    """Conservative, structural-first validation for "does this line start a NEW
    project" (used only as a fallback when a line is neither indented/bulleted nor a
    recognized tech-stack line). Rejects sentence-continuation fragments — the actual
    cause of a project description exploding into many bogus single-word/short-phrase
    "projects" — without requiring every resume to follow one exact format.

    This is deliberately a low-confidence, last-resort signal (blank-line block
    boundaries and explicit tech-annotation delimiters are the trusted ones); a false
    positive here is caught after the fact by `_merge_content_less_fragments`, which
    folds a title-only "project" this produced back into its neighbor.
    """
    stripped = line.strip()
    if not stripped or len(stripped) < 3:
        return False
    words = stripped.split()
    if len(words) > _PROJECT_TITLE_MAX_WORDS:
        return False  # a genuine title is short; a long line is prose, not a heading
    first_alpha = next((character for character in stripped if character.isalpha()), None)
    if first_alpha is not None and first_alpha.islower():
        return False  # a lowercase-led line is virtually always a sentence continuation
    if _ends_with_terminal_punctuation(stripped):
        return False  # a completed sentence, not a title
    first_word = re.sub(r"[^a-zA-Z]", "", words[0]).casefold()
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


_ANNOTATION_LEAD_IN = re.compile(r"(?i)^(?:built|developed|created|designed|implemented)?\s*(?:using|with)\s+")


def _annotation_terms(annotation: str) -> list[str]:
    """Resolves an already-confirmed tech annotation ("Built using Node, Express and
    MongoDB", "Flutter, Firebase") into a technologies list.

    This must NOT be re-classified through the generic per-line heuristics (tech-line
    detection, title detection, ...) — an annotation containing an unrecognized term
    like "Flutter" or "Firebase" would fail `_technology_terms` (not in the curated
    vocabulary) and then incorrectly pass `_looks_like_project_title`, splitting the
    real project into a bogus extra one. Recognized terms are canonicalized via
    `_skills`; an unrecognized short segment is kept verbatim rather than silently
    dropped, mirroring `_explicit_skill_items`'s treatment of an explicit Skills
    section — the curated vocabulary can never name every technology.
    """
    segments = [segment.strip() for segment in _LIST_SPLIT.split(annotation) if segment.strip()]
    if not segments:
        segments = [annotation.strip()] if annotation.strip() else []
    terms: list[str] = []
    seen: set[str] = set()
    for segment in segments:
        cleaned = _ANNOTATION_LEAD_IN.sub("", segment).strip()
        if not cleaned or not _is_meaningful_entry(cleaned):
            continue
        recognized = _skills(cleaned)
        value = recognized[0] if recognized else cleaned
        key = value.casefold()
        if key not in seen:
            seen.add(key)
            terms.append(value)
    return terms


def _new_project(line: str) -> dict:
    title, annotation = _split_title_and_annotation(line)
    technologies = _annotation_terms(annotation) if annotation else []
    return {"title": title, "description": "", "technologies": technologies, "raw_text": title}


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
            # tech annotation after a dash/colon/pipe is split off and resolved
            # directly into `technologies` (see `_new_project`/`_annotation_terms`).
            current = _new_project(line)
            description_lines = []
            continue

        is_labeled_tech_line = _TECH_LABEL_PATTERN.match(line.strip()) is not None
        # An explicit label ("Technologies:", "Tech Stack:", ...) is unambiguous even
        # on an indented/bulleted line — handle it before anything else.
        if is_labeled_tech_line:
            current["technologies"] = _technology_terms(line) or current["technologies"]
            continue
        if indented:
            description_lines.append(_strip_bullet_prefix(line))
            continue

        # Unindented: check whether this is actually a NEW project's title with an
        # inline tech annotation ("E-commerce Management — Built using X, Y, Z")
        # *before* checking whether the whole line reads as a bare tech-stack list.
        # Checking tech-list-ness first would let a new title with several
        # technologies named after it get misread as more technologies for the
        # *current* (about-to-be-closed) project instead of starting a new one.
        title, annotation = _split_title_and_annotation(line)
        if annotation is not None and _looks_like_project_title(title):
            finalize()
            current = {"title": title, "description": "", "technologies": _annotation_terms(annotation), "raw_text": title}
            description_lines = []
            continue

        technologies = _technology_terms(line)
        # Without a label, only treat an unindented line as a tech-stack line — a
        # bulleted sentence that merely *mentions* two technologies in prose ("Used
        # Python, FastAPI and Git.") is still a description line, not a dedicated
        # tech-stack line, and must stay part of the description; that case is
        # already excluded here because it's indented.
        if technologies is not None:
            current["technologies"] = technologies
            continue
        if _looks_like_project_title(line):
            finalize()
            current = _new_project(line)
            description_lines = []
            continue
        # Neither a recognized tech line nor a plausible new title — a sentence
        # fragment (a wrapped continuation, or a description with no bullet marker
        # at all) that belongs to the current project's description.
        description_lines.append(line)
    finalize()
    return _merge_content_less_fragments(projects)


def _merge_content_less_fragments(projects: list[dict]) -> list[dict]:
    """Folds a title-only "project" (no description, no technologies — nothing
    attached at all) back into the previous project's description.

    `_looks_like_project_title` is a deliberately low-confidence, last-resort
    signal — on a resume whose bullets have no marker and use an action verb this
    module doesn't recognize as a continuation-starter, a short unbulleted sentence
    fragment can still slip through it and open a bogus "project". A genuine project
    almost always has *something* beyond a bare title (a description sentence or an
    explicit technology list); one that has neither is far more likely a stray
    fragment than a real, separate project, so it is merged rather than kept.
    """
    merged: list[dict] = []
    for project in projects:
        is_content_less = not project["description"] and not project["technologies"]
        if is_content_less and merged:
            previous = merged[-1]
            previous["description"] = (previous["description"] + " " + project["title"]).strip()
            previous["raw_text"] = previous["title"] + (f" - {previous['description']}" if previous["description"] else "")
            for skill in _skills(project["title"]):
                if skill not in previous["technologies"]:
                    previous["technologies"].append(skill)
            continue
        merged.append(project)
    return merged


def _projects(sections: list[ResumeSection]) -> list[dict]:
    projects = []
    for section in sections:
        if section.name != "projects":
            continue
        for block in _split_into_blank_line_blocks(section.content):
            projects.extend(_group_project_block(_reflow_lines(block.splitlines())))
    return projects


_MAX_TRUSTED_EXPLICIT_SKILL_ITEMS = 25


def _vocabulary_matched_skills(text: str) -> list[str]:
    technical = _skills(text)
    return technical + [skill for skill in _soft_skills(text) if skill not in technical]


def _resolve_skills(skills_section_text: str, all_text: str) -> list[str]:
    if not skills_section_text:
        # No dedicated section — fall back to conservative vocabulary-matched
        # scanning of the whole resume; blindly keeping every phrase here would
        # flatten unrelated prose nouns into fake "skills".
        return _vocabulary_matched_skills(all_text)

    # A dedicated Skills section: every self-declared item is preserved (known ones
    # canonicalized), not just the subset matching a closed vocabulary.
    explicit_items = _explicit_skill_items(skills_section_text)
    if len(explicit_items) <= _MAX_TRUSTED_EXPLICIT_SKILL_ITEMS:
        return explicit_items

    # An implausibly long "skills" list is a strong signal this section's content
    # isn't a clean, curated list — most likely a later, unrecognized heading's
    # content (e.g. an uncommon "Areas of Expertise" spelling) silently ran into it
    # and every one of its words got preserved verbatim. Fall back to only
    # vocabulary-matched technical/soft skills rather than trusting every fragment.
    return _vocabulary_matched_skills(skills_section_text)


def build_structured_data(sections: list[ResumeSection]) -> dict:
    all_text = "\n".join(section.content for section in sections)
    skills_section_text = "\n".join(section.content for section in sections if section.name == "skills")
    combined_skills = _resolve_skills(skills_section_text, all_text)
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
_COMMON_PROSE_WORDS = {
    "and", "using", "with", "the", "a", "an", "for", "to", "of", "in", "on", "built", "developed",
    "such", "this", "that", "page", "success", "project", "knowledge", "application", "features",
}
_PROJECT_COUNT_WARNING_THRESHOLD = 15
_SKILLS_COUNT_WARNING_THRESHOLD = 30


def _parser_warnings(data: dict) -> list[str]:
    """Conservative, non-destructive sanity checks over freshly-structured resume
    data. These only ever produce a warning to log (and are persisted alongside the
    structured data for API/UI visibility) for developer/user diagnostics — they
    never reject or silently alter a legitimate (if unusual) resume.
    """
    warnings: list[str] = []

    projects = data.get("projects", [])
    if len(projects) > _PROJECT_COUNT_WARNING_THRESHOLD:
        warnings.append(f"suspicious_project_count: {len(projects)} projects found on one resume; output may be fragmented.")
    single_word_titles = [p["title"] for p in projects if len(p["title"].split()) == 1]
    if projects and len(single_word_titles) / len(projects) > 0.5:
        warnings.append(f"many_single_word_project_titles: {single_word_titles}")
    stopword_titles = [p["title"] for p in projects if p["title"].strip().casefold() in _COMMON_STOPWORDS]
    if stopword_titles:
        warnings.append(f"suspicious_stopword_project_titles: {stopword_titles}")

    skills = data.get("skills", [])
    if len(skills) > _SKILLS_COUNT_WARNING_THRESHOLD:
        warnings.append(f"excessive_skill_count: {len(skills)} skills found; output may include unrelated content.")
    prose_skills = [skill for skill in skills if skill.strip().casefold() in _COMMON_PROSE_WORDS]
    if prose_skills:
        warnings.append(f"excessive_unrecognized_skills: prose words present in skills: {prose_skills}")

    for category in ("experience", "internships"):
        for entry in data.get(category, []):
            text = str(entry.get("raw_text", "")).strip()
            if len(text) < 3 or text.casefold() in _COMMON_STOPWORDS:
                warnings.append(f"suspicious_{category}_entry: {text!r}")

    for entry in data.get("education", []):
        raw_text = str(entry.get("raw_text", "")).strip()
        if len(raw_text) < 5:
            warnings.append(f"truncated_education_entry: {raw_text!r}")

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
        "experience_count=%s internship_count=%s skills_count=%s warning_count=%s warnings=%s",
        resume.id, [section.name for section in sections], len(data.get("education", [])), len(data.get("projects", [])),
        len(data.get("experience", [])), len(data.get("internships", [])), len(data.get("skills", [])), len(warnings), warnings,
    )
    # Persisted (not just logged) so the API response / frontend can surface a
    # "processed with warnings" notice instead of silently feeding pathological
    # structure downstream to M2/M3 as if it were clean.
    data["parser_warnings"] = warnings

    result.data = data
    resume.status = "structured"
    db.commit()
    db.refresh(result)
    return result
