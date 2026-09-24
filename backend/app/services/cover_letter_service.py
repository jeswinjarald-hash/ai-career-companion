"""Milestone 3.2 — grounded cover letter generation.

Every sentence is template-assembled from known structured fields (job posting,
candidate profile, structured resume) and records its `sources` (evidence
`source_path`s) for provenance — nothing here is inferred or invented. A purely
connective/closing sentence (no factual claim) carries an empty `sources` list.

Structure: opening -> current background -> strongest relevant evidence ->
role alignment -> closing, targeting roughly 250-400 words. Project/experience
evidence is *summarized* (`customization_evidence.summarize_clause` — a verbatim
truncation, never a paraphrase) rather than the full raw text dumped in.
"""

from app.models import CandidateProfile
from app.schemas.customization import CoverLetterSentence, EvidenceRecord, KeywordClassification
from app.schemas.job_posting import JobPosting
from app.services.customization_evidence import join_terms, relevance_score, short_education_phrase, summarize_clause
from app.services.customization_keywords import partial_terms, supported_terms
from app.services.job_matching import normalize_term


def _top_supported_skill_names(structured_data: dict, supported: set[str], limit: int) -> list[tuple[str, str]]:
    names: list[tuple[str, str]] = []
    for index, skill in enumerate(structured_data.get("skills", []) or []):
        if normalize_term(str(skill)) in supported:
            names.append((str(skill), f"structured_resume.skills[{index}]"))
    return names[:limit]


def _ranked_projects(structured_data: dict, supported: set[str], partial: set[str]) -> list[tuple[dict, int]]:
    projects = [p for p in structured_data.get("projects", []) or [] if isinstance(p, dict)]
    scored = [
        (index, project, relevance_score(str(project.get("raw_text") or project.get("description") or ""), project.get("technologies", []) or [], supported, partial))
        for index, project in enumerate(projects)
    ]
    scored.sort(key=lambda item: (-item[2], item[0]))
    return [(project, index) for index, project, _score in scored]


def _best_experience(structured_data: dict) -> tuple[str, str, str] | None:
    """Returns (raw_text, source_path, label) for the first internship, else the
    first work-experience entry — internships are usually the most directly
    relevant professional evidence for a student applicant."""
    for key, label in (("internships", "internship"), ("experience", "work experience")):
        for index, item in enumerate(structured_data.get(key, []) or []):
            if isinstance(item, dict) and item.get("raw_text"):
                return str(item["raw_text"]).strip(), f"structured_resume.{key}[{index}].raw_text", label
    return None


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

    # Opening — role/company, no candidate claim, no invented recipient name.
    sentences.append(CoverLetterSentence(text="Dear Hiring Team,", sources=[]))
    sentences.append(CoverLetterSentence(
        text=(
            f"I am writing to express my interest in the {job.job_title} position at {job.company}. "
            f"I was drawn to this opportunity in {job.domain}, and I am excited about the possibility of "
            f"contributing my skills and project experience to your team."
        ),
        sources=[],
    ))

    # Current background — education (short form) + top supported skills, in one
    # natural sentence rather than two separate, choppy blocks.
    education_phrase, education_sources = short_education_phrase(profile, structured_data)
    top_skills = _top_supported_skill_names(structured_data, supported, limit=5)
    if top_skills:
        skill_names = [name for name, _source in top_skills]
        background = (
            f"As a {education_phrase} student, I have built hands-on experience in {join_terms(skill_names)} "
            f"through coursework and independent project work, and I enjoy applying these skills to solve "
            f"practical, real-world problems."
        )
        background_sources = list(education_sources) + [source for _name, source in top_skills]
    else:
        background = f"As a {education_phrase} student, I have been building practical, project-based experience in software development."
        background_sources = list(education_sources)
    sentences.append(CoverLetterSentence(text=background, sources=background_sources))

    # Strongest relevant evidence — summarized (not dumped) citations for the two
    # most job-relevant projects, plus an experience/internship citation if one
    # exists, so this paragraph carries real substance rather than a single line.
    ranked_projects = _ranked_projects(structured_data, supported, partial)
    for rank, (project, index) in enumerate(ranked_projects[:2]):
        title = str(project.get("title") or "a project").strip()
        raw = str(project.get("description") or project.get("raw_text") or "").strip()
        summarized = summarize_clause(raw)
        source_path = f"structured_resume.projects[{index}].raw_text"
        if not summarized:
            opener = f'One project I am particularly proud of is "{title}."' if rank == 0 else f'I have also worked on "{title}."'
            sentences.append(CoverLetterSentence(text=opener, sources=[source_path]))
            continue
        opener = f'One project I am particularly proud of is "{title},"' if rank == 0 else f'I have also worked on "{title},"'
        sentences.append(CoverLetterSentence(
            text=f'{opener} where I {summarized[0].lower() + summarized[1:]}.',
            sources=[source_path],
        ))

    best_experience = _best_experience(structured_data)
    if best_experience is not None:
        raw, source_path, label = best_experience
        summarized = summarize_clause(raw)
        if summarized:
            sentences.append(CoverLetterSentence(
                text=f"My {label} gave me additional real-world exposure: {summarized}.",
                sources=[source_path],
            ))

    # Role alignment — connects supported skills to the job's own stated domain/
    # responsibilities, quoting the job's real text rather than asserting a new
    # claim about the candidate.
    alignment_skills = [name for name, _source in top_skills[:4]] if top_skills else []
    matching_responsibilities = [r for r in job.responsibilities if any(normalize_term(term) and normalize_term(term) in normalize_term(r) for term in alignment_skills)]
    responsibilities = (matching_responsibilities or job.responsibilities)[:2]
    if alignment_skills and responsibilities:
        responsibilities_text = join_terms([f'"{r}"' for r in responsibilities])
        sentences.append(CoverLetterSentence(
            text=(
                f"My background in {join_terms(alignment_skills)} aligns directly with this role's focus on "
                f"{responsibilities_text}, and I am confident I can contribute effectively from day one."
            ),
            sources=[],
        ))
    elif alignment_skills:
        sentences.append(CoverLetterSentence(
            text=f"My background in {join_terms(alignment_skills)} aligns well with what this role requires, and I am confident I can contribute effectively from day one.",
            sources=[],
        ))

    # Closing — no factual claim, no invented recipient name. The candidate's own
    # name (real, grounded data) signs off the letter.
    sentences.append(CoverLetterSentence(
        text=f"Thank you for considering my application. I would welcome the opportunity to discuss how my background can contribute to {job.company}.",
        sources=[],
    ))
    candidate_name = (profile.full_name or "").strip()
    sentences.append(CoverLetterSentence(
        text=f"Sincerely,\n{candidate_name}" if candidate_name else "Sincerely,",
        sources=["profile.full_name"] if candidate_name else [],
    ))

    return sentences
