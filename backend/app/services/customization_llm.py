"""Milestone 3.2 — grounded LLM rewrite layer.

The evidence layer built by `customization_evidence.py` remains the sole source of
truth. This module never sends a free-form "rewrite this resume" prompt: the model
is given a restricted payload (the target job, supported/partial/unsupported skill
classifications, the deterministic baseline summary, the exact bullets to rewrite,
and a fixed `allowed_evidence` list with stable `evidence_id`s) and told, in the
system prompt, exactly what it may and may not do. Its JSON response is validated
against the same fabrication checks the deterministic pipeline already uses
(`customization_validator`) plus a new check that every cited `evidence_id`/
`source_path` actually exists in what was offered. One repair attempt is made on a
validation failure; a second failure (or any provider-level failure — timeout,
network error, non-JSON response) falls back to the deterministic pipeline, which is
always fully computed first and never blocked on the LLM.
"""

import logging

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.schemas.customization import EvidenceRecord, KeywordClassification, TailoredResume
from app.schemas.job_posting import JobPosting
from app.services.customization_validator import check_fabrication
from app.services.llm_provider import LLMProvider, LLMUnavailableError, NullLLMProvider

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a resume and cover-letter rewriting assistant for a student job-application tool.

You are given: a target job, the candidate's supported/partial/unsupported skill classifications \
for that job, a baseline professional summary, a list of resume bullets to rewrite, and a \
restricted "allowed_evidence" list — each item has a stable evidence_id and real text taken \
directly from the candidate's own resume/profile.

Rules you must follow exactly:
- You may reword, clarify, reorder, shorten, and prioritize bullets for relevance to the job. A \
good rewrite genuinely improves clarity and professional tone while preserving every fact exactly \
— for example "Built backend REST APIs using FastAPI and integrated structured resume processing." \
may become "Developed FastAPI-based REST APIs for an AI career platform, supporting structured \
resume processing and backend application workflows." — same facts, more polished, nothing added.
- You may emphasize supported_skills and job-relevant terms already present in allowed_evidence.
- You must NEVER invent or imply any skill, technology, tool, metric/percentage, year or duration \
of experience, team size, leadership role, production/business impact, company name, job title, \
date, certification, or achievement that is not explicitly present in the allowed_evidence text \
you were given. Concretely, never add things like "improved performance by 40%", "using AWS", \
"using Docker", "led a team of 5", or "3 years of experience" unless that exact fact is already in \
allowed_evidence.
- You must NEVER present a skill from unsupported_skills_do_not_use as something the candidate has.
- Every rewritten bullet and every cover-letter paragraph that makes a factual claim must cite the \
evidence_id(s) (from allowed_evidence only) that support it.
- "summary" must be a concise, professional 2-3 sentence paragraph — state the candidate's field of \
study (degree/specialization only, never the institution name, graduation year, CGPA, or \
coursework) and their most job-relevant supported skills, optionally naming one relevant project. \
Do not copy a full raw education or project line verbatim into the summary.
- "cover_letter_paragraphs" must read as one natural, professional cover letter, not a list of \
disconnected facts, targeting roughly 250-400 words total across all paragraphs, structured as: \
(1) an opening naming the real job title and company, (2) a paragraph on the candidate's current \
background (education field + top skills, phrased naturally, not copy-pasted), (3) a paragraph on \
the strongest relevant project/experience evidence, summarized in the candidate's own words rather \
than the full raw text dumped in, (4) a paragraph connecting the candidate's skills to the role's \
actual stated focus/responsibilities, and (5) a brief, professional closing. Never invent the \
recipient's name — use a generic address like "Dear Hiring Team," if a greeting is included.
- Respond with ONLY a single JSON object, no prose, no markdown code fences, in exactly this shape:
{
  "summary": "...",
  "summary_evidence_ids": ["EV-001"],
  "bullets": [
    {"source_path": "...", "rewritten_text": "...", "evidence_ids": ["EV-002"], "job_keywords_used": ["..."]}
  ],
  "cover_letter_paragraphs": [
    {"text": "...", "evidence_ids": ["EV-002"]}
  ]
}
- "bullets" must contain exactly one entry per source_path listed in bullets_to_rewrite, using the \
identical source_path string.
- "cover_letter_paragraphs" must contain 4 to 7 entries forming one coherent cover letter of \
roughly 250-400 words in total."""


class LLMBulletRewrite(BaseModel):
    model_config = ConfigDict(extra="ignore")

    source_path: str
    rewritten_text: str
    evidence_ids: list[str] = Field(default_factory=list)
    job_keywords_used: list[str] = Field(default_factory=list)


class LLMCoverLetterParagraph(BaseModel):
    model_config = ConfigDict(extra="ignore")

    text: str
    evidence_ids: list[str] = Field(default_factory=list)


class LLMRewriteResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    summary: str
    summary_evidence_ids: list[str] = Field(default_factory=list)
    bullets: list[LLMBulletRewrite] = Field(default_factory=list)
    cover_letter_paragraphs: list[LLMCoverLetterParagraph] = Field(default_factory=list)


def build_grounded_llm_input(
    job: JobPosting,
    classifications: list[KeywordClassification],
    evidence_records: list[EvidenceRecord],
    tailored_resume: TailoredResume,
) -> tuple[dict, set[str], set[str]]:
    supported = [c.keyword for c in classifications if c.status == "supported"]
    partial = [c.keyword for c in classifications if c.status == "partial"]
    unsupported = [c.keyword for c in classifications if c.status == "unsupported"]

    allowed_evidence = [
        {"evidence_id": e.evidence_id, "source_path": e.source_path, "source_type": e.source_type, "text": e.raw_text, "confidence": e.confidence_type}
        for e in evidence_records
    ]
    allowed_ids = {e.evidence_id for e in evidence_records}

    bullets_to_rewrite = [
        {"source_path": project.source_path, "kind": "project", "title": project.title, "original_text": project.original_text}
        for project in tailored_resume.projects
    ] + [
        {"source_path": bullet.source_path, "kind": "experience", "original_text": bullet.original_text}
        for bullet in tailored_resume.experience + tailored_resume.internships
    ]
    expected_source_paths = {item["source_path"] for item in bullets_to_rewrite}

    payload = {
        "job": {
            "title": job.job_title, "company": job.company, "domain": job.domain,
            "required_skills": job.required_skills, "preferred_skills": job.preferred_skills,
            "responsibilities": job.responsibilities,
        },
        "supported_skills": supported,
        "partial_or_learning_skills": partial,
        "unsupported_skills_do_not_use": unsupported,
        "baseline_summary": tailored_resume.summary,
        "bullets_to_rewrite": bullets_to_rewrite,
        "allowed_evidence": allowed_evidence,
    }
    return payload, allowed_ids, expected_source_paths


def validate_llm_response(
    response: LLMRewriteResponse,
    allowed_evidence_ids: set[str],
    expected_source_paths: set[str],
    unsupported_terms: set[str],
) -> list[str]:
    violations: list[str] = []

    if not response.summary.strip():
        violations.append("summary must not be empty")
    else:
        hit = check_fabrication(response.summary, unsupported_terms)
        if hit:
            violations.append(f"summary: {hit}")
    unknown = [i for i in response.summary_evidence_ids if i not in allowed_evidence_ids]
    if unknown:
        violations.append(f"summary cites unknown evidence_ids: {unknown}")

    seen_paths = {bullet.source_path for bullet in response.bullets}
    missing_paths = expected_source_paths - seen_paths
    if missing_paths:
        violations.append(f"missing rewrites for source_path(s): {sorted(missing_paths)}")

    for bullet in response.bullets:
        if bullet.source_path not in expected_source_paths:
            violations.append(f"bullet cites unknown source_path: {bullet.source_path}")
            continue
        if not bullet.rewritten_text.strip():
            violations.append(f"bullet {bullet.source_path}: rewritten_text must not be empty")
            continue
        hit = check_fabrication(bullet.rewritten_text, unsupported_terms)
        if hit:
            violations.append(f"bullet {bullet.source_path}: {hit}")
        unknown = [i for i in bullet.evidence_ids if i not in allowed_evidence_ids]
        if unknown:
            violations.append(f"bullet {bullet.source_path} cites unknown evidence_ids: {unknown}")

    if not response.cover_letter_paragraphs:
        violations.append("cover_letter_paragraphs must not be empty")
    for index, paragraph in enumerate(response.cover_letter_paragraphs):
        if not paragraph.text.strip():
            violations.append(f"cover_letter_paragraphs[{index}]: text must not be empty")
            continue
        hit = check_fabrication(paragraph.text, unsupported_terms)
        if hit:
            violations.append(f"cover_letter_paragraphs[{index}]: {hit}")
        unknown = [i for i in paragraph.evidence_ids if i not in allowed_evidence_ids]
        if unknown:
            violations.append(f"cover_letter_paragraphs[{index}] cites unknown evidence_ids: {unknown}")

    return violations


def rewrite_with_llm(
    provider: LLMProvider,
    job: JobPosting,
    classifications: list[KeywordClassification],
    evidence_records: list[EvidenceRecord],
    tailored_resume: TailoredResume,
    unsupported_terms: set[str],
) -> tuple[LLMRewriteResponse | None, dict]:
    """Returns `(response, metadata)`. `response` is `None` whenever the deterministic
    fallback must be used — metadata always explains why via `fallback_reason`.
    """
    meta: dict = {
        "attempted_llm": not isinstance(provider, NullLLMProvider),
        "provider": provider.name, "model": provider.model,
        "repair_attempted": False, "fallback_reason": None,
    }
    if isinstance(provider, NullLLMProvider):
        meta["fallback_reason"] = "no_provider_configured"
        return None, meta

    payload, allowed_ids, expected_paths = build_grounded_llm_input(job, classifications, evidence_records, tailored_resume)

    try:
        raw = provider.generate_json(SYSTEM_PROMPT, payload)
    except LLMUnavailableError as exc:
        logger.warning("customization_llm_provider_unavailable provider=%s error=%s", provider.name, exc)
        meta["fallback_reason"] = f"provider_unavailable: {exc}"
        return None, meta

    response, violations = _parse_and_validate(raw, allowed_ids, expected_paths, unsupported_terms)

    if violations:
        meta["repair_attempted"] = True
        logger.info("customization_llm_repair_attempted provider=%s violation_count=%s", provider.name, len(violations))
        try:
            repaired_raw = provider.generate_json(
                SYSTEM_PROMPT,
                {**payload, "previous_response": raw, "violations_to_fix": violations},
            )
        except LLMUnavailableError as exc:
            meta["fallback_reason"] = f"repair_call_failed: {exc}"
            return None, meta
        response, violations = _parse_and_validate(repaired_raw, allowed_ids, expected_paths, unsupported_terms)

    if violations:
        logger.warning("customization_llm_validation_failed_after_repair provider=%s violation_count=%s", provider.name, len(violations))
        meta["fallback_reason"] = f"validation_failed: {violations[:5]}"
        return None, meta

    return response, meta


def _parse_and_validate(
    raw: dict, allowed_ids: set[str], expected_paths: set[str], unsupported_terms: set[str]
) -> tuple[LLMRewriteResponse | None, list[str]]:
    try:
        response = LLMRewriteResponse.model_validate(raw)
    except ValidationError as exc:
        return None, [f"response did not match the required JSON schema: {exc}"]
    return response, validate_llm_response(response, allowed_ids, expected_paths, unsupported_terms)
