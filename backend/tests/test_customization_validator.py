"""Unit tests for the M3.2 unsupported-claim validator — no DB/API needed.

Covers spec test cases D (fabricated metric rejection) and E (fabricated leadership
rejection), plus unsupported-keyword rejection and the "nothing to flag" pass case.
"""

from app.schemas.customization import CoverLetterSentence
from app.services.customization_validator import build_validation_result, validate_cover_letter, validate_summary


def test_grounded_summary_passes_validation() -> None:
    summary = "B.Tech Computer Science student with hands-on experience in Python, FastAPI, and SQL."
    corrected, warnings, removed = validate_summary(summary, unsupported_terms=set())
    assert corrected == summary
    assert warnings == []
    assert removed == []


def test_fabricated_metric_is_rejected() -> None:
    summary = "Improved API response time by 40% using FastAPI."
    corrected, warnings, removed = validate_summary(summary, unsupported_terms=set())
    assert corrected == ""
    assert removed == [summary]
    assert "metric" in warnings[0]


def test_fabricated_leadership_claim_is_rejected() -> None:
    sentence = CoverLetterSentence(text="I led a team of 5 engineers to deliver this project.", sources=[])
    kept, warnings, removed = validate_cover_letter([sentence], unsupported_terms=set())
    assert kept == []
    assert removed == [sentence.text]
    assert "leadership" in warnings[0]


def test_fabricated_years_of_experience_is_rejected() -> None:
    sentence = CoverLetterSentence(text="I have 5 years of professional experience in backend development.", sources=[])
    kept, warnings, removed = validate_cover_letter([sentence], unsupported_terms=set())
    assert kept == []
    assert removed == [sentence.text]


def test_unsupported_keyword_mention_is_rejected() -> None:
    sentence = CoverLetterSentence(text="I am proficient in AWS and Kubernetes deployment.", sources=[])
    kept, warnings, removed = validate_cover_letter([sentence], unsupported_terms={"aws"})
    assert kept == []
    assert removed == [sentence.text]
    assert "aws" in warnings[0]


def test_grounded_cover_letter_sentences_all_pass() -> None:
    sentences = [
        CoverLetterSentence(text="I am writing to express my interest in the Backend Intern position at Acme.", sources=[]),
        CoverLetterSentence(text="My experience includes hands-on work with Python and FastAPI.", sources=["structured_resume.skills[0]"]),
    ]
    kept, warnings, removed = validate_cover_letter(sentences, unsupported_terms={"docker"})
    assert kept == sentences
    assert warnings == []
    assert removed == []


def test_build_validation_result_reports_parser_warning_without_removal() -> None:
    result = build_validation_result([], [], [], [], parser_warning_notice="Resume structure contains parsing warnings. Review extracted profile before customization.")
    assert result.passed is True
    assert result.removed_claims == []
    assert len(result.warnings) == 1


def test_build_validation_result_fails_when_claims_were_removed() -> None:
    result = build_validation_result(["removed summary claim"], ["Improved by 40%"], [], [], parser_warning_notice=None)
    assert result.passed is False
    assert result.removed_claims == ["Improved by 40%"]
