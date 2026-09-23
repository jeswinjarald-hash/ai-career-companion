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

from app.schemas.customization import CoverLetterSentence, ValidationResult
from app.services.job_matching import normalize_term

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


def check_fabrication(sentence: str, unsupported_terms: set[str]) -> str | None:
    """Scans arbitrary generated text (deterministic-template or LLM-produced) for an
    unsupported keyword or a fabricated metric/leadership/years-of-experience claim.
    Returns a human-readable reason, or `None` if the text is clean. Public so the
    LLM rewrite layer (`customization_llm.py`) can run the identical check on model
    output instead of duplicating these patterns.
    """
    unsupported_hit = _sentence_has_unsupported_keyword(sentence, unsupported_terms)
    if unsupported_hit:
        return f'references unsupported keyword "{unsupported_hit}"'
    if _METRIC_PATTERN.search(sentence):
        return "contains an unverified numeric metric claim"
    if _LEADERSHIP_PATTERN.search(sentence):
        return "contains an unverified leadership/team-size claim"
    if _YEARS_EXPERIENCE_PATTERN.search(sentence):
        return "contains an unverified years-of-experience claim"
    return None


def validate_summary(summary: str, unsupported_terms: set[str]) -> tuple[str, list[str], list[str]]:
    violation = check_fabrication(summary, unsupported_terms)
    if violation is None:
        return summary, [], []
    warning = f'Removed from summary: "{summary}" ({violation}).'
    return "", [warning], [summary]


def validate_cover_letter(
    sentences: list[CoverLetterSentence], unsupported_terms: set[str]
) -> tuple[list[CoverLetterSentence], list[str], list[str]]:
    kept: list[CoverLetterSentence] = []
    warnings: list[str] = []
    removed: list[str] = []
    for sentence in sentences:
        violation = check_fabrication(sentence.text, unsupported_terms)
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
    return ValidationResult(
        passed=not summary_removed and not letter_removed,
        warnings=warnings,
        removed_claims=list(summary_removed) + list(letter_removed),
    )
