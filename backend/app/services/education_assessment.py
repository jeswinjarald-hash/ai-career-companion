"""Shared, deterministic education assessment used by both Job Matching (M2) and Skill
Gap Analysis (M3.1), so the same degree is never judged differently against the same
requirement (M4.3 Experiment 4).

Fields are recognised on whole words in the student's education text and in the job's
requirement text:

- met:      the requirement accepts any discipline, or names one of the student's
            fields, or accepts a "related field/discipline" and the student has one of
            the recognised technical fields;
- partial:  the student has a recognised technical field, but not one the requirement
            names (e.g. Mathematics for "an engineering or computing program");
- not_met:  no recognised technical field (e.g. History, Chemistry, Commerce);
- unknown:  no education evidence at all (callers exclude the component).

"Relevant engineering or computing program" names fields; "relevant" is not treated as
"or a related field". A bare degree abbreviation without a field (e.g. "B.Sc") is not a
field on its own, so unrelated qualifications are not over-credited. The bare
abbreviation "IT" is not matched because it is indistinguishable from the pronoun
after normalisation. No LLM judgement.
"""

import re
from dataclasses import dataclass
from typing import Literal

EducationLevel = Literal["met", "partial", "not_met", "unknown"]

FIELD_PATTERNS: dict[str, re.Pattern[str]] = {
    "computing": re.compile(r"\b(computer|computers|computing|information technology|software|data science|bca|mca|cse)\b"),
    "engineering": re.compile(r"\b(engineering|b\.?\s?tech|m\.?\s?tech|b\.e|m\.e)\b"),
    "electronics": re.compile(r"\b(electronics|electrical|ece|eee)\b"),
    "mathematics": re.compile(r"\b(mathematics|maths|math|statistics)\b"),
}
_ANY_DISCIPLINE = re.compile(r"\bany\s+(discipline|field|degree|stream|background)\b")
_RELATED_FIELD = re.compile(r"\brelated\s+(field|fields|discipline|disciplines|area|subject|stream)\b")


@dataclass(frozen=True)
class EducationAssessment:
    level: EducationLevel
    student_fields: frozenset[str]
    requirement_fields: frozenset[str]
    reason: str


def _fields(text: str) -> frozenset[str]:
    return frozenset(name for name, pattern in FIELD_PATTERNS.items() if pattern.search(text))


def assess_education_text(student_text: str, requirement_text: str) -> EducationAssessment:
    student = (student_text or "").casefold().strip()
    requirement = (requirement_text or "").casefold()
    if not student:
        return EducationAssessment("unknown", frozenset(), _fields(requirement), "No education evidence is available.")
    student_fields, requirement_fields = _fields(student), _fields(requirement)
    if _ANY_DISCIPLINE.search(requirement):
        return EducationAssessment("met", student_fields, requirement_fields, "The requirement accepts any discipline.")
    if student_fields & requirement_fields:
        return EducationAssessment("met", student_fields, requirement_fields,
                                   f"Education in {', '.join(sorted(student_fields & requirement_fields))} matches a field the requirement names.")
    if student_fields and _RELATED_FIELD.search(requirement):
        return EducationAssessment("met", student_fields, requirement_fields, "The requirement accepts a related field, and the education is in a related technical field.")
    if student_fields:
        return EducationAssessment("partial", student_fields, requirement_fields,
                                   "The education is technical but not in a field the requirement names.")
    return EducationAssessment("not_met", student_fields, requirement_fields, "The available education does not clearly satisfy the stated requirement.")
