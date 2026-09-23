"""Milestone 3.2 — grounded cover letter generation.

Every sentence is template-assembled from known structured fields (job posting,
candidate profile, structured resume) and records its `sources` (evidence
`source_path`s) for provenance — nothing here is inferred or invented. A purely
connective/closing sentence (no factual claim) carries an empty `sources` list.
"""

from app.models import CandidateProfile
from app.schemas.customization import CoverLetterSentence, EvidenceRecord, KeywordClassification
from app.schemas.job_posting import JobPosting
from app.services.customization_evidence import relevance_score
from app.services.customization_keywords import partial_terms, supported_terms
from app.services.job_matching import normalize_term


def _education_phrase(profile: CandidateProfile, structured_data: dict) -> tuple[str, str | None]:
    if profile.degree:
        phrase = f"{profile.degree}{f' with a specialization in {profile.specialization}' if profile.specialization else ''}"
        return phrase, "profile.degree"
    education = structured_data.get("education", []) or []
    for index, entry in enumerate(education):
        if isinstance(entry, dict) and entry.get("raw_text"):
            return str(entry["raw_text"]).strip(), f"structured_resume.education[{index}].raw_text"
    return "my academic background", None


def _top_supported_skill_names(structured_data: dict, supported: set[str], limit: int) -> list[tuple[str, str]]:
    names: list[tuple[str, str]] = []
    for index, skill in enumerate(structured_data.get("skills", []) or []):
        if normalize_term(str(skill)) in supported:
            names.append((str(skill), f"structured_resume.skills[{index}]"))
    return names[:limit]


def _best_project(structured_data: dict, supported: set[str], partial: set[str]) -> tuple[dict, int, int] | None:
    projects = [p for p in structured_data.get("projects", []) or [] if isinstance(p, dict)]
    if not projects:
        return None
    scored = [
        (index, project, relevance_score(str(project.get("raw_text") or project.get("description") or ""), project.get("technologies", []) or [], supported, partial))
        for index, project in enumerate(projects)
    ]
    scored.sort(key=lambda item: (-item[2], item[0]))
    best_index, best_project, _score = scored[0]
    return best_project, best_index, (scored[1][1] if len(scored) > 1 else None)


def build_cover_letter(
    profile: CandidateProfile,
    structured_data: dict,
    job: JobPosting,
    evidence_records: list[EvidenceRecord],
    classifications: list[KeywordClassification],
) -> list[CoverLetterSentence]:
    supported = supported_terms(classifications)
    partial = partial_terms(classifications)
    sentences: list[CoverLetterSentence] = []

    # Paragraph 1 — role/company + interest.
    sentences.append(CoverLetterSentence(
        text=f"I am writing to express my interest in the {job.job_title} position at {job.company}.",
        sources=[],
    ))
    education_phrase, education_source = _education_phrase(profile, structured_data)
    interest_line = f"As a {education_phrase} student, I am drawn to this {job.domain} opportunity." if profile.degree else f"With a background in {education_phrase}, I am drawn to this {job.domain} opportunity."
    sentences.append(CoverLetterSentence(text=interest_line, sources=[education_source] if education_source else []))

    # Paragraph 2 — strongest relevant evidence: top supported skills + best project.
    top_skills = _top_supported_skill_names(structured_data, supported, limit=4)
    if top_skills:
        skill_names = [name for name, _source in top_skills]
        joined = ", ".join(skill_names[:-1]) + (f" and {skill_names[-1]}" if len(skill_names) > 1 else skill_names[0])
        sentences.append(CoverLetterSentence(
            text=f"My experience includes hands-on work with {joined}, which directly relates to this role's requirements.",
            sources=[source for _name, source in top_skills],
        ))

    best = _best_project(structured_data, supported, partial)
    if best is not None:
        project, index, _second = best
        title = str(project.get("title") or "a project").strip()
        # `raw_text` is "{title} - {description}" — `description` alone is used here
        # since `title` is already quoted separately in the sentence.
        raw = str(project.get("description") or project.get("raw_text") or "").strip()
        source_path = f"structured_resume.projects[{index}].raw_text"
        # A colon-citation ("Project X: <verbatim text>") is used instead of splicing
        # the citation into one grammatical sentence — forcing a lowercase join reads
        # naturally only when the source text happens to start mid-clause, and breaks
        # (or worse, reads as an invented continuation) for text that doesn't.
        project_line = f'One of my most relevant projects, "{title}," demonstrates this directly: {raw}' if raw else f'One of my most relevant projects is "{title}."'
        sentences.append(CoverLetterSentence(text=project_line, sources=[source_path]))

    # Paragraph 3 — secondary strengths: experience/internship evidence, if any.
    for key, phrase in (("internships", "My internship experience adds further practical grounding"), ("experience", "My work experience adds further practical grounding")):
        items = [item for item in structured_data.get(key, []) or [] if isinstance(item, dict) and item.get("raw_text")]
        if items:
            index = (structured_data.get(key) or []).index(items[0])
            raw = str(items[0]["raw_text"]).strip()
            sentences.append(CoverLetterSentence(
                text=f"{phrase}: {raw}",
                sources=[f"structured_resume.{key}[{index}].raw_text"],
            ))
            break

    # Closing — no factual claim, no sources required.
    sentences.append(CoverLetterSentence(
        text=f"I would welcome the opportunity to bring this experience to the {job.job_title} role at {job.company}, and I appreciate your consideration.",
        sources=[],
    ))

    return sentences
