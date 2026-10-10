"""Milestone 3.2 — unsupported claim validator.

Runs as a second, independent pass over already-generated text (never trusted as
"safe by construction just because it came from a template"): it scans the
professional summary and cover letter sentences for (a) any job keyword this
resume/profile does not support, and (b) fabricated-metric / fabricated-leadership
phrasing that the deterministic generator never intentionally produces. Anything it
flags is stripped from the output — never silently returned — and recorded in
`ValidationResult.removed_claims` so the caller (and the frontend's "Review
required" notice) can see exactly what was removed and why.
"""

import re
from dataclasses import dataclass

from app.schemas.customization import CoverLetterSentence, EvidenceRecord, ValidationResult
from app.schemas.job_posting import JobPosting
from app.services.job_matching import normalize_term
from app.services.structured_resume import _DEGREE_PATTERN, _skills

# Deliberately conservative: only fires on the specific fabrication shapes named in
# the M3.2 spec (invented percentages/metrics, invented team leadership/size). A
# template-generated sentence should never contain these, so a hit here means either
# a template bug or a future generation path that isn't yet grounded — either way,
# the sentence is removed rather than shipped.
_METRIC_PATTERN = re.compile(r"\b\d+(\.\d+)?\s*%|\bby\s+\d+(\.\d+)?\s*(percent|x|times)\b", re.I)
_LEADERSHIP_PATTERN = re.compile(r"\bled\s+(a\s+)?team\b|\bteam\s+of\s+\d+\b|\bmanaged\s+a\s+team\b", re.I)
_YEARS_EXPERIENCE_PATTERN = re.compile(r"\b\d+\+?\s*years?\s+of\s+(professional\s+|production\s+)?experience\b", re.I)


def _sentence_has_unsupported_keyword(sentence: str, unsupported_terms: set[str]) -> str | None:
    normalized = normalize_term(sentence)
    for term in unsupported_terms:
        if not term:
            continue
        pattern = r"(?<![\w+#.])" + re.escape(term) + r"(?![\w+#])"
        if re.search(pattern, normalized):
            return term
    return None


def check_fabrication_patterns(sentence: str) -> str | None:
    """The metric/leadership/years-of-experience half of `check_fabrication`, without
    the unsupported-keyword check. Used where merely *mentioning* an unsupported
    skill is legitimate and expected — e.g. Milestone 3.3's interview questions
    about a job's real required skills, or a `skill_gap`-category question whose
    entire purpose is to name a gap by term — but an invented metric/leadership/
    years claim is never legitimate regardless of category.
    """
    if _METRIC_PATTERN.search(sentence):
        return "contains an unverified numeric metric claim"
    if _LEADERSHIP_PATTERN.search(sentence):
        return "contains an unverified leadership/team-size claim"
    if _YEARS_EXPERIENCE_PATTERN.search(sentence):
        return "contains an unverified years-of-experience claim"
    return None


def check_fabrication_patterns_excluding_metrics(sentence: str) -> str | None:
    """Same leadership/years-of-experience checks as `check_fabrication_patterns`,
    but never flags a bare numeric percentage. Milestone 3.4's Career Assistant
    legitimately states real, already-computed scores in its responses (a Milestone
    3.1 skill-gap readiness percentage, a Milestone 2 job-match percentage) — unlike
    M3.2's resume/cover-letter bullets, where any percentage is inherently suspect
    unless byte-traceable to evidence, a percentage the assistant states is one it
    was explicitly given in `facts` (the LLM is only ever rewording an already-
    computed baseline answer, never composing a claim from scratch), so the metric
    check would otherwise reject entirely legitimate, grounded output. An invented
    leadership/team-size or years-of-experience claim is still never legitimate here.
    """
    if _LEADERSHIP_PATTERN.search(sentence):
        return "contains an unverified leadership/team-size claim"
    if _YEARS_EXPERIENCE_PATTERN.search(sentence):
        return "contains an unverified years-of-experience claim"
    return None


def _mask_phrases(sentence: str, phrases: tuple[str, ...]) -> str:
    # Only exact (case-insensitive) occurrences of a whole phrase are masked, so a
    # skill mentioned anywhere outside the opportunity's own name is still checked.
    for phrase in sorted((p for p in phrases if p and p.strip()), key=len, reverse=True):
        sentence = re.sub(re.escape(phrase.strip()), " ", sentence, flags=re.I)
    return sentence


@dataclass(frozen=True)
class EvidenceCorpus:
    """Everything the candidate's own resume/profile evidence actually says, in the
    forms the claim checks below compare against."""

    text: str
    technologies: frozenset[str]
    has_work_experience: bool
    # The target opportunity's own text: generated content may quote the posting
    # (this role involves "Build backend APIs..."), which is not a candidate claim.
    job_text: str = ""


def build_evidence_corpus(evidence_records: list[EvidenceRecord], job: JobPosting | None = None) -> EvidenceCorpus:
    text = " \n".join(
        " ".join([record.source_name, record.raw_text, *record.canonical_terms]) for record in evidence_records
    )
    job_text = ""
    if job is not None:
        job_text = _claim_key(" \n".join([job.job_title, job.company, job.raw_text, *job.responsibilities, *job.qualifications]))
    return EvidenceCorpus(
        text=_claim_key(text),
        technologies=frozenset(_skills(text)),
        has_work_experience=any(record.source_type in ("experience", "internship") for record in evidence_records),
        job_text=job_text,
    )


# Aliases that are also everyday English words ("express my interest", "go further"):
# only their capitalized, proper-noun use names the technology.
_AMBIGUOUS_TECHNOLOGY_NAMES = {"Express", "Go", "Rust", "Statistics", "Algorithms"}


def _claimed_technologies(text: str) -> list[str]:
    return [
        term for term in _skills(text)
        if term not in _AMBIGUOUS_TECHNOLOGY_NAMES or re.search(r"(?<![\w.])" + re.escape(term) + r"(?![\w+#])", text)
    ]


def _claim_key(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9+#]+", " ", text.casefold()).split())


def _in_text(phrase: str, haystack: str) -> bool:
    key = _claim_key(phrase)
    return bool(key) and re.search(r"(?<![a-z0-9])" + re.escape(key) + r"(?![a-z0-9])", haystack) is not None


def _in_corpus(phrase: str, corpus: EvidenceCorpus) -> bool:
    return _in_text(phrase, corpus.text)


_QUOTED_NAME_PATTERN = re.compile(r"[\"“]([^\"“”]{3,80})[\"”]")
_EMPLOYER_PATTERN = re.compile(
    r"\b(?:interned|internship|worked|working|employed|employment|experience|role|position)\s+(?:at|with|for)\s+"
    r"((?:[A-Z][\w&.\-]*)(?:\s+(?:[A-Z][\w&.\-]*|of|&))*)"
)
_WORK_EXPERIENCE_PATTERN = re.compile(r"\b(?:professional|work|industry|industrial|internship)\s+experience\b|\binterned\s+(?:at|with)\b", re.I)
# Case-sensitive on purpose: the parser's case-insensitive degree pattern would read
# the everyday word "be" as a "B.E." degree claim.
_CLAIM_DEGREE_PATTERN = re.compile(_DEGREE_PATTERN.pattern)
_ACHIEVEMENT_PATTERN = re.compile(r"\b(?:won|winner|winning|award(?:ed|s)?|prize|first place|runner[- ]up|ranked|scholarship|hackathon|medal)\b", re.I)


def check_unsupported_claims(sentence: str, corpus: EvidenceCorpus, allowed_phrases: tuple[str, ...] = ()) -> str | None:
    """Checks a candidate claim against the candidate's own evidence, beyond the job
    keyword check: every named technology, degree, quoted project/title name,
    employer, work-experience claim and award/achievement must be traceable to
    resume/profile evidence. The target opportunity's own title/company are masked
    (naming the role is not a claim about the candidate)."""
    masked = _mask_phrases(sentence, allowed_phrases)
    unsupported_technologies = [term for term in _claimed_technologies(masked) if term not in corpus.technologies]
    if unsupported_technologies:
        return f'names technology not found in resume/profile evidence: "{unsupported_technologies[0]}"'
    for match in _CLAIM_DEGREE_PATTERN.finditer(masked):
        if not _in_corpus(match.group(1), corpus):
            return f'names a qualification not found in resume/profile evidence: "{match.group(1)}"'
    for name in _QUOTED_NAME_PATTERN.findall(masked):
        if not _in_corpus(name, corpus) and not _in_text(name, corpus.job_text):
            return f'names a project/title not found in resume/profile evidence: "{name}"'
    for match in _EMPLOYER_PATTERN.finditer(masked):
        if not _in_corpus(match.group(1), corpus):
            return f'names an employer/organization not found in resume/profile evidence: "{match.group(1)}"'
    if not corpus.has_work_experience and _WORK_EXPERIENCE_PATTERN.search(masked):
        return "claims work/internship experience, but the resume/profile has no experience or internship entry"
    for match in _ACHIEVEMENT_PATTERN.finditer(masked):
        if not _in_corpus(match.group(0), corpus):
            return f'claims an achievement ("{match.group(0)}") not found in resume/profile evidence'
    return None


def check_fabrication(
    sentence: str, unsupported_terms: set[str], allowed_phrases: tuple[str, ...] = (), corpus: EvidenceCorpus | None = None,
) -> str | None:
    """Scans arbitrary generated text (deterministic-template or LLM-produced) for an
    unsupported keyword or a fabricated metric/leadership/years-of-experience claim.
    Returns a human-readable reason, or `None` if the text is clean. Public so the
    LLM rewrite layer (`customization_llm.py`) can run the identical check on model
    output instead of duplicating these patterns.

    `allowed_phrases` are names the text may legitimately repeat without claiming a
    skill — the target opportunity's title and company ("the FastAPI Intern role at
    Acme" names the role; it does not claim FastAPI experience). They are masked only
    for the unsupported-keyword check; metric/leadership/years checks see the full text.

    `corpus`, when given, additionally runs `check_unsupported_claims` against the
    candidate's own evidence.
    """
    unsupported_hit = _sentence_has_unsupported_keyword(_mask_phrases(sentence, allowed_phrases), unsupported_terms)
    if unsupported_hit:
        return f'references unsupported keyword "{unsupported_hit}"'
    pattern_hit = check_fabrication_patterns(sentence)
    if pattern_hit or corpus is None:
        return pattern_hit
    return check_unsupported_claims(sentence, corpus, allowed_phrases)


def validate_summary(
    summary: str, unsupported_terms: set[str], allowed_phrases: tuple[str, ...] = (), corpus: EvidenceCorpus | None = None,
) -> tuple[str, list[str], list[str]]:
    violation = check_fabrication(summary, unsupported_terms, allowed_phrases, corpus)
    if violation is None:
        return summary, [], []
    warning = f'Removed from summary: "{summary}" ({violation}).'
    return "", [warning], [summary]


def validate_cover_letter(
    sentences: list[CoverLetterSentence], unsupported_terms: set[str], allowed_phrases: tuple[str, ...] = (),
    corpus: EvidenceCorpus | None = None,
) -> tuple[list[CoverLetterSentence], list[str], list[str]]:
    kept: list[CoverLetterSentence] = []
    warnings: list[str] = []
    removed: list[str] = []
    for sentence in sentences:
        violation = check_fabrication(sentence.text, unsupported_terms, allowed_phrases, corpus)
        if violation is None:
            kept.append(sentence)
        else:
            warnings.append(f'Removed from cover letter: "{sentence.text}" ({violation}).')
            removed.append(sentence.text)
    return kept, warnings, removed


def build_validation_result(summary_warnings: list[str], summary_removed: list[str], letter_warnings: list[str], letter_removed: list[str], parser_warning_notice: str | None) -> ValidationResult:
    warnings = list(summary_warnings) + list(letter_warnings)
    if parser_warning_notice:
        warnings.append(parser_warning_notice)
    # Evidence validation is only as reliable as the evidence: when the resume's own
    # structure was flagged as unreliable, the check cannot be reported as passed.
    return ValidationResult(
        passed=not summary_removed and not letter_removed and not parser_warning_notice,
        warnings=warnings,
        removed_claims=list(summary_removed) + list(letter_removed),
    )
