from types import SimpleNamespace

from app.services.skill_gap_evidence import build_evidence_units, match_requirement


def profile(skills: list[str] | None = None, education: str | None = None, degree: str | None = None, specialization: str | None = None, career_goals: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(skills=skills or [], education=education, degree=degree, specialization=specialization, career_goals=career_goals)


def structured(**overrides) -> dict:
    base = {
        "skills": [], "education": [], "experience": [], "internships": [],
        "projects": [], "certifications": [], "achievements": [], "qualifications": [], "learning": [],
    }
    base.update(overrides)
    return base


def test_exact_skill_match_from_skills_list_is_demonstrated() -> None:
    units = build_evidence_units(profile(skills=["Python"]), structured(skills=["Python"]))

    match_type, confidence, evidence, reason = match_requirement("Python", units)

    assert match_type == "demonstrated"
    assert confidence >= 0.9
    assert evidence
    assert evidence[0].source in ("profile_skills", "resume_skills")


def test_missing_skill_with_no_evidence_is_missing() -> None:
    units = build_evidence_units(profile(skills=["Python"]), structured(skills=["Python"]))

    match_type, confidence, evidence, reason = match_requirement("Docker", units)

    assert match_type == "missing"
    assert evidence == []
    assert "No explicit evidence" in reason


def test_preferred_missing_skill_is_still_classified_missing_not_hidden() -> None:
    units = build_evidence_units(profile(skills=[]), structured())

    match_type, *_ = match_requirement("AWS", units)

    assert match_type == "missing"


def test_generic_rest_api_evidence_is_partial_for_fastapi_not_an_exact_match() -> None:
    project = {"title": "Career API", "raw_text": "Built REST APIs using Python", "technologies": []}
    units = build_evidence_units(profile(skills=["Python"]), structured(projects=[project]))

    match_type, confidence, evidence, reason = match_requirement("FastAPI", units)

    assert match_type == "partial"
    assert 0 < confidence < 0.9
    assert evidence
    assert "career api" in evidence[0].source_name.lower() or evidence[0].source == "project"


def test_generic_cloud_evidence_is_partial_for_aws_not_an_exact_match() -> None:
    project = {"title": "Deployment Project", "raw_text": "Deployed projects to cloud platforms", "technologies": []}
    units = build_evidence_units(profile(skills=[]), structured(projects=[project]))

    match_type, confidence, evidence, reason = match_requirement("AWS", units)

    assert match_type == "partial"
    assert evidence


def test_related_but_different_ml_framework_is_partial_not_exact() -> None:
    units = build_evidence_units(profile(skills=["TensorFlow", "Machine Learning"]), structured(skills=["TensorFlow", "Machine Learning"]))

    match_type, confidence, evidence, reason = match_requirement("PyTorch", units)

    assert match_type == "partial"
    assert confidence < 0.9


def test_related_but_different_technologies_never_become_exact_matches() -> None:
    cases = [
        (["TensorFlow"], "PyTorch"),
        (["AWS"], "Azure"),
        (["React"], "Angular"),
        (["MySQL"], "MongoDB"),
    ]
    for student_skills, requirement in cases:
        units = build_evidence_units(profile(skills=student_skills), structured(skills=student_skills))
        match_type, *_ = match_requirement(requirement, units)
        assert match_type != "demonstrated", f"{requirement} must not be an exact match from {student_skills}"


def test_exact_match_found_in_project_free_text_even_without_technologies_list() -> None:
    project = {"title": "AI Career Companion", "raw_text": "Developed REST APIs using FastAPI", "technologies": []}
    units = build_evidence_units(profile(skills=[]), structured(projects=[project]))

    match_type, confidence, evidence, reason = match_requirement("FastAPI", units)

    assert match_type == "demonstrated"
    assert evidence[0].source_name == "AI Career Companion"
    assert "FastAPI" in evidence[0].evidence


def test_skill_alias_javascript_variants_match_exactly() -> None:
    units = build_evidence_units(profile(skills=["JS"]), structured(skills=["JS"]))

    match_type, *_ = match_requirement("JavaScript", units)

    assert match_type == "demonstrated"


def test_matching_is_deterministic_across_repeated_calls() -> None:
    units = build_evidence_units(profile(skills=["Python", "SQL"]), structured(skills=["Python", "SQL"]))

    first = match_requirement("Docker", units)
    second = match_requirement("Docker", units)

    assert first == second


# ---------------------------------------------------------------------------
# Regression tests for the M3.1 manual-review fixes (real Sam resume review).
# ---------------------------------------------------------------------------


def test_teamwork_qualification_is_partial_not_missing_from_soft_skill_and_experience_evidence() -> None:
    units = build_evidence_units(
        profile(skills=["Team Collaboration"]),
        structured(
            skills=["Team Collaboration"],
            experience=[{"raw_text": "Collaborated with classmates during project development, testing, and version control."}],
        ),
    )

    match_type, confidence, evidence, reason = match_requirement("Ability to work effectively in a team", units)

    assert match_type != "missing"
    assert match_type == "partial"
    evidence_text = " ".join(item.evidence for item in evidence)
    assert "collaborat" in evidence_text.lower()


def test_unrelated_qualifications_are_never_bridged_to_evidence() -> None:
    # Leadership/communication/problem-solving must never be inferred just because a
    # loosely related term exists — only the explicitly-approved teamwork concept is.
    units = build_evidence_units(profile(skills=["Team Collaboration", "Communication"]), structured(skills=["Team Collaboration", "Communication"]))

    match_type, *_ = match_requirement("Strong leadership and ownership of technical decisions", units)

    assert match_type == "missing"


def test_docker_from_learning_only_section_is_learning_only_not_partial() -> None:
    units = build_evidence_units(
        profile(skills=[]),
        structured(learning=[{"raw_text": "Advanced Backend Development, Cloud Deployment, Containerization, System Design"}]),
    )

    match_type, confidence, evidence, reason = match_requirement("Docker", units)

    assert match_type == "learning_only"
    assert match_type != "partial"
    assert match_type != "demonstrated"
    assert evidence
    assert evidence[0].source == "learning"
    assert "Areas Currently Learning" in evidence[0].source_name


def test_learning_only_evidence_never_upgrades_an_exact_term_to_demonstrated() -> None:
    units = build_evidence_units(profile(skills=[]), structured(learning=[{"raw_text": "Kubernetes"}]))

    match_type, *_ = match_requirement("Kubernetes", units)

    assert match_type == "learning_only"


def test_python_alone_does_not_demonstrate_pandas_or_numpy() -> None:
    units = build_evidence_units(profile(skills=["Python"]), structured(skills=["Python"]))

    for requirement in ("Pandas", "NumPy"):
        match_type, *_ = match_requirement(requirement, units)
        assert match_type != "demonstrated", f"{requirement} must not be demonstrated from Python alone"
        assert match_type == "missing"


def test_pandas_and_numpy_can_still_relate_to_each_other_when_both_hinted() -> None:
    # A sibling data-science library is still a legitimate (partial, not exact) signal.
    units = build_evidence_units(profile(skills=["Pandas"]), structured(skills=["Pandas"]))

    match_type, *_ = match_requirement("NumPy", units)

    assert match_type == "partial"


def test_sql_evidence_does_not_include_unrelated_certification_titles() -> None:
    certifications = [
        {"raw_text": "Python Programming Fundamentals - Demo Learning Platform"},
        {"raw_text": "SQL and Relational Databases - Demo Learning Platform"},
        {"raw_text": "Introduction to Machine Learning - Demo Learning Platform"},
    ]
    units = build_evidence_units(profile(skills=["SQL"]), structured(skills=["SQL"], certifications=certifications))

    match_type, confidence, evidence, reason = match_requirement("SQL", units)

    assert match_type == "demonstrated"
    evidence_text = " ".join(item.evidence for item in evidence)
    assert "Python Programming Fundamentals" not in evidence_text
    assert "Introduction to Machine Learning" not in evidence_text
