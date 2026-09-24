"""Milestone 3.3 — deterministic interview question and revision-plan generation.

No LLM is used here (this is the always-computed baseline / fallback, matching M2/
M3.1/M3.2's convention). Every question is grounded: a question that presupposes the
student has hands-on experience with something only cites skills/projects/experience
the student's own evidence actually supports; a job-required skill the student does
not demonstrate is asked about conceptually (never "how have you used X"), and the
dedicated `skill_gap` category is the only place a gap is explicitly surfaced as a
gap to the student, per the spec's grounding rule.
"""

from app.schemas.interview_prep import InterviewQuestion, RevisionItem
from app.services.interview_evidence import InterviewContext
from app.services.job_matching import normalize_term
from app.services.skill_gap_evidence import mentions_term

# Reuses the same normalized-term buckets `skill_gap_service._recommendation_for`
# already curates for M3.1 (so a skill's "how it's typically tested" guidance stays
# consistent across skill-gap recommendations and interview-prep questions), with
# interview-specific question templates instead of "build evidence" guidance.
_TOPIC_QUESTIONS: dict[frozenset[str], dict[str, str]] = {
    frozenset({"docker", "kubernetes"}): {
        "conceptual": "What problem does containerization solve, and how does {term} help with consistent deployment across environments?",
        "practical": "Walk through the steps you'd take to containerize a backend service with {term}.",
        "scenario": "A containerized service works locally but fails in production with a missing-dependency error. How would you debug this with {term}?",
    },
    frozenset({"aws", "azure", "gcp"}): {
        "conceptual": "What are the core building blocks (compute, storage, networking) {term} provides for hosting a backend application?",
        "practical": "How would you deploy a simple REST API to {term} and make it publicly reachable?",
        "scenario": "Your {term}-hosted service is returning intermittent 502 errors under load. What would you check first?",
    },
    frozenset({"fastapi", "flask", "django", "spring boot", "express", "node.js"}): {
        "conceptual": "What are the key design differences between {term} and other web frameworks you're aware of?",
        "practical": "How would you structure a new {term} project with multiple resource endpoints and a database layer?",
        "scenario": "An endpoint built with {term} is slow under concurrent load. How would you investigate the bottleneck?",
    },
    frozenset({"react", "angular", "vue"}): {
        "conceptual": "How does {term} manage component state, and why does that matter for a growing application?",
        "practical": "How would you structure a {term} application that consumes a REST API and handles loading/error states?",
        "scenario": "A {term} component re-renders far more often than expected. How would you diagnose and fix it?",
    },
    frozenset({"pytorch", "tensorflow", "scikit-learn", "machine learning", "deep learning"}): {
        "conceptual": "How would you decide between a simple model and a more complex one (e.g. using {term}) for a given problem?",
        "practical": "Walk through your typical workflow for training and evaluating a model with {term}.",
        "scenario": "A model built with {term} performs well on training data but poorly on new data. What would you check?",
    },
    frozenset({"sql", "postgresql", "mysql", "mongodb", "dbms"}): {
        "conceptual": "What's the difference between a relational schema and a document-based one, and when would you choose {term}?",
        "practical": "How would you design a schema in {term} for a system with users, resources, and a many-to-many relationship?",
        "scenario": "A query against {term} is running slowly on a large table. What would you look at first?",
    },
    frozenset({"git", "github", "ci/cd"}): {
        "conceptual": "Why does a clean commit history and branch strategy matter when working with {term} on a team?",
        "practical": "Walk through how you'd resolve a merge conflict using {term}.",
        "scenario": "A teammate's branch and yours both modified the same file using {term}. How do you handle the merge safely?",
    },
    frozenset({"rest apis", "api development"}): {
        "conceptual": "What makes an API design 'RESTful', and why do those conventions matter?",
        "practical": "How would you design the endpoints for a resource that supports create, read, update, and delete?",
        "scenario": "A client reports that your API silently returns incomplete data instead of an error. How would you improve it?",
    },
}


def _topic_templates(term: str) -> dict[str, str] | None:
    normalized = normalize_term(term)
    for bucket, templates in _TOPIC_QUESTIONS.items():
        if normalized in bucket:
            return templates
    return None


_GENERIC_TEMPLATES = {
    "conceptual": "What is {term}, and in what kind of situation would you reach for it?",
    "practical": "How would you apply {term} in a small backend project?",
    "scenario": "Something built with {term} isn't behaving as expected. How would you start investigating?",
}


def _technical_questions(context: InterviewContext) -> list[InterviewQuestion]:
    job = context.job
    questions: list[InterviewQuestion] = []
    required = list(dict.fromkeys(job.required_skills))
    preferred = list(dict.fromkeys(job.preferred_skills))

    for skill in required + preferred:
        normalized = normalize_term(skill)
        is_required = skill in required
        templates = _topic_templates(skill) or _GENERIC_TEMPLATES
        demonstrated = normalized in context.supported_terms
        evidence_ids: list[str] = []

        if demonstrated:
            # A project/experience record that actually mentions this skill — safe
            # to ask "how have you used it" since real evidence backs the claim.
            matching_evidence = [
                e for e in context.evidence_records
                if e.source_type in ("project", "experience", "internship") and mentions_term(normalized, normalize_term(e.raw_text))
            ]
            if matching_evidence:
                evidence_ids = [matching_evidence[0].evidence_id]
                text = f"Explain how you used {skill} in \"{matching_evidence[0].source_name}\": what was your approach, and what would you do differently now?"
                difficulty = "medium"
            else:
                text = templates["practical"].format(term=skill)
                difficulty = "medium"
        else:
            # No direct evidence — conceptual framing only, never presupposing
            # hands-on use the student hasn't demonstrated.
            text = templates["conceptual"].format(term=skill)
            difficulty = "easy" if not is_required else "medium"

        questions.append(InterviewQuestion(
            question=text, category="technical", difficulty=difficulty,
            why_asked=f'"{skill}" is listed as a {"required" if is_required else "preferred"} skill for the {job.job_title} role.',
            what_interviewer_is_testing=f"Whether you understand {skill} well enough to apply it on the job" + (", and can speak concretely about how you've already used it" if demonstrated else " conceptually, even without direct hands-on experience yet"),
            preparation_guidance=(f'Be ready to walk through your work in "{matching_evidence[0].source_name}" in detail.' if demonstrated and evidence_ids else f"Review the fundamentals of {skill} — you don't have direct hands-on evidence of this yet, so focus on explaining concepts clearly rather than claiming production experience."),
            topics_to_review=[skill],
            source_requirements=[skill],
            source_evidence_ids=evidence_ids,
        ))

        if is_required and demonstrated and len(questions) < 40:
            # A second, scenario-based question for demonstrated required skills —
            # required skills get deeper coverage than preferred ones.
            questions.append(InterviewQuestion(
                question=templates["scenario"].format(term=skill), category="technical", difficulty="hard",
                why_asked=f'"{skill}" is a required skill — interviewers often probe required skills with a debugging/design scenario.',
                what_interviewer_is_testing="Your problem-solving process under a realistic, somewhat ambiguous scenario, not just textbook recall.",
                preparation_guidance=f"Think through a structured troubleshooting approach for {skill} (reproduce, isolate, check logs/metrics, form a hypothesis, verify).",
                topics_to_review=[skill], source_requirements=[skill], source_evidence_ids=[],
            ))

    return questions


def _resume_questions(context: InterviewContext) -> list[InterviewQuestion]:
    questions: list[InterviewQuestion] = []

    for entry in context.evidence_records:
        if entry.source_type == "education":
            questions.append(InterviewQuestion(
                question=f"Your background includes \"{entry.raw_text[:120]}\" — what coursework or academic work is most relevant to this role, and why?",
                category="resume", difficulty="easy",
                why_asked="Interviewers use education background to understand your foundation and what you've been recently exposed to.",
                what_interviewer_is_testing="Whether you can connect your academic background to the specific role you're applying for.",
                preparation_guidance="Pick one or two courses/topics that are genuinely relevant to this role and be ready to explain the connection specifically.",
                topics_to_review=[], source_requirements=[], source_evidence_ids=[entry.evidence_id],
            ))
        elif entry.source_type == "certification":
            questions.append(InterviewQuestion(
                question=f"How has your certification (\"{entry.raw_text[:120]}\") been useful in practice, if at all?",
                category="resume", difficulty="easy",
                why_asked="A listed certification invites a follow-up on whether it translated into practical understanding.",
                what_interviewer_is_testing="Whether you can speak beyond the certificate name to what you actually learned.",
                preparation_guidance="Recall one or two concrete concepts or skills from this certification you can describe in your own words.",
                topics_to_review=[], source_requirements=[], source_evidence_ids=[entry.evidence_id],
            ))
        elif entry.source_type == "achievement":
            questions.append(InterviewQuestion(
                question=f"Tell me more about this: \"{entry.raw_text[:120]}\" — what did that involve?",
                category="resume", difficulty="easy",
                why_asked="A listed achievement is an easy, natural opening for an interviewer to learn more about you.",
                what_interviewer_is_testing="How clearly and specifically you can describe your own accomplishments.",
                preparation_guidance="Prepare a short, specific explanation of what this achievement involved and what it took to earn it.",
                topics_to_review=[], source_requirements=[], source_evidence_ids=[entry.evidence_id],
            ))

    return questions[:6]


def _project_questions(context: InterviewContext) -> list[InterviewQuestion]:
    questions: list[InterviewQuestion] = []
    for project, index, _score in context.projects_ranked[:3]:
        title = str(project.get("title") or "your project").strip()
        raw = str(project.get("description") or project.get("raw_text") or "").strip()
        technologies = [str(t) for t in project.get("technologies", []) or []]
        source_path = f"structured_resume.projects[{index}].raw_text"
        evidence_id = next((e.evidence_id for e in context.evidence_records if e.source_path == source_path), None)
        evidence_ids = [evidence_id] if evidence_id else []

        prompts = [
            (f'Walk me through the architecture of "{title}": what are its main components, and how do they fit together?', "architecture", "medium"),
            (f'What technology choices did you make in "{title}" ({", ".join(technologies) if technologies else "your stack"}), and why those specifically?', "technology choices", "medium"),
            (f'What was the hardest challenge you ran into while building "{title}", and how did you resolve it?', "challenges", "medium"),
            (f'If you had more time, what would you improve or refactor in "{title}"?', "trade-offs and improvements", "easy"),
            (f'How did you test "{title}", and how would you approach testing it more thoroughly?', "testing", "medium"),
        ]
        for text, topic, difficulty in prompts:
            questions.append(InterviewQuestion(
                question=text, category="project", difficulty=difficulty,
                why_asked=f'"{title}" is one of your most job-relevant projects for this role.',
                what_interviewer_is_testing=f"Your depth of understanding of your own project — specifically its {topic}, not just that you can describe what it does.",
                preparation_guidance=f'Review "{title}" before the interview: {raw[:160]}{"..." if len(raw) > 160 else ""}',
                topics_to_review=technologies, source_requirements=[], source_evidence_ids=evidence_ids,
            ))
    return questions


def _role_questions(context: InterviewContext) -> list[InterviewQuestion]:
    job = context.job
    questions: list[InterviewQuestion] = []
    for responsibility in job.responsibilities[:5]:
        questions.append(InterviewQuestion(
            question=f'This role involves "{responsibility}." How would you approach that kind of work?',
            category="role", difficulty="medium",
            why_asked=f'"{responsibility}" is one of the stated responsibilities for the {job.job_title} role.',
            what_interviewer_is_testing="Whether you understand what the day-to-day work actually involves, not just the job title.",
            preparation_guidance=f'Think through how your existing skills/projects relate to "{responsibility}", even if not identical to what you\'ve done before.',
            topics_to_review=[], source_requirements=[responsibility], source_evidence_ids=[],
        ))
    return questions


_HR_QUESTION_BANK = [
    ("Tell me about yourself.", "This is almost always the opening question, used to see how you frame your own background.", "How clearly and concisely you can summarize your background and interest in the role.", "Prepare a brief, structured summary: your field of study, your strongest relevant skills, and why this role interests you — in that order."),
    ("Why are you interested in this role?", "Interviewers want to see genuine, specific interest rather than a generic answer.", "Whether you've actually thought about why this specific role/company fits you.", "Reference something specific and real about the role (its domain, responsibilities, or tech stack) rather than a generic answer."),
    ("Describe a time you worked as part of a team.", "Most internships involve close collaboration, so teamwork is almost always asked about.", "Whether you can communicate and contribute effectively in a group setting.", "Recall a real group project, course assignment, or collaborative activity and be ready to describe your specific role in it."),
    ("Tell me about a challenge you faced and how you handled it.", "This reveals your problem-solving approach and resilience.", "Your ability to stay structured and constructive when something doesn't go smoothly.", "Pick a real, specific challenge (technical or otherwise) with a clear before/after, not a vague generality."),
    ("How do you approach learning a new technology?", "Internships often require picking up unfamiliar tools quickly.", "Your learning process and self-direction, not just whether you've used a specific tool before.", "Describe your actual process — docs, small experiments, a reference project — using a real example if you have one."),
    ("What are your strengths and areas for improvement?", "A classic self-awareness question.", "Honest self-reflection rather than a rehearsed, generic answer.", "Pick a genuine strength you can back with a real example, and an area you're actively working on."),
]


def _hr_questions(context: InterviewContext) -> list[InterviewQuestion]:
    questions: list[InterviewQuestion] = []
    for question, why, testing, guidance in _HR_QUESTION_BANK:
        questions.append(InterviewQuestion(
            question=question, category="hr", difficulty="easy",
            why_asked=why, what_interviewer_is_testing=testing, preparation_guidance=guidance,
            topics_to_review=[], source_requirements=[], source_evidence_ids=[],
        ))
    return questions


def _skill_gap_questions(context: InterviewContext) -> list[InterviewQuestion]:
    questions: list[InterviewQuestion] = []
    gap = context.skill_gap

    # Required/partial gaps first (higher priority), then preferred gaps — every
    # match_type in this category is, by construction, a gap: the question always
    # names it as one, never presupposes the student already has it.
    gap_items = [(item, "medium") for item in (gap.critical_gaps + gap.partial_gaps)] + [(item, "easy") for item in gap.preferred_gaps]
    for item, difficulty in gap_items[:8]:
        if item.requirement_type not in ("required_skill", "preferred_skill"):
            continue
        status_phrase = "does not show hands-on experience with" if item.match_type == "missing" else "shows only partial/related evidence for"
        emphasis = "prefers" if item.requirement_type == "preferred_skill" else "requires"
        questions.append(InterviewQuestion(
            question=f'Your target role {emphasis} "{item.requirement}", but your resume {status_phrase} it. How would you prepare to answer a question about "{item.requirement}" in this interview?',
            category="skill_gap", difficulty=difficulty,
            why_asked=f'"{item.requirement}" is a real gap identified by your Skill Gap Analysis for this role — interviewers may probe it directly.',
            what_interviewer_is_testing="How honestly and proactively you handle a gap, rather than whether you already have the skill.",
            preparation_guidance=item.recommendation,
            topics_to_review=[item.requirement], source_requirements=[item.requirement], source_evidence_ids=[],
        ))

    return questions


def generate_questions(context: InterviewContext) -> list[InterviewQuestion]:
    return (
        _technical_questions(context)
        + _resume_questions(context)
        + _project_questions(context)
        + _role_questions(context)
        + _hr_questions(context)
        + _skill_gap_questions(context)
    )


def build_revision_plan(context: InterviewContext) -> list[RevisionItem]:
    gap = context.skill_gap
    plan: list[RevisionItem] = []

    for item in gap.critical_gaps:
        if item.requirement_type not in ("required_skill", "preferred_skill"):
            continue
        plan.append(RevisionItem(
            priority="high", topic=item.requirement,
            reason=f'Required skill with no evidence in your resume/profile: {item.reason}',
            suggested_revision=item.recommendation,
            estimated_focus="High priority — review this before the interview.",
        ))
    for item in gap.partial_gaps:
        if item.requirement_type not in ("required_skill", "preferred_skill"):
            continue
        plan.append(RevisionItem(
            priority="medium", topic=item.requirement,
            reason=f"Related evidence exists but isn't fully confirmed: {item.reason}",
            suggested_revision=item.recommendation,
            estimated_focus="Medium priority — review key concepts and be ready to clarify your actual depth.",
        ))
    for item in gap.preferred_gaps:
        plan.append(RevisionItem(
            priority="low", topic=item.requirement,
            reason=f"Preferred (non-mandatory) skill not yet demonstrated: {item.reason}",
            suggested_revision=item.recommendation,
            estimated_focus="Lower priority — worth a light review if time allows.",
        ))
    for item in gap.experience_gaps:
        plan.append(RevisionItem(
            priority="medium", topic="Experience expectations",
            reason=item.reason,
            suggested_revision=item.recommendation,
            estimated_focus="Prepare a concrete story or example that addresses this, even if not a perfect match.",
        ))

    # Strongest projects are also worth deliberate revision — being ready to speak
    # fluently about them is as important as covering gaps.
    for project, _index, score in context.projects_ranked[:2]:
        if score <= 0:
            continue
        title = str(project.get("title") or "your project").strip()
        plan.append(RevisionItem(
            priority="medium", topic=title,
            reason="One of your most job-relevant projects — likely to come up in project-based questions.",
            suggested_revision=f'Re-familiarize yourself with the full implementation of "{title}" so you can discuss it fluently, including decisions you made and challenges you solved.',
            estimated_focus="Review before the interview so you can speak fluently without re-reading your own resume.",
        ))

    priority_order = {"high": 0, "medium": 1, "low": 2}
    plan.sort(key=lambda item: priority_order[item.priority])
    return plan


def build_preparation_summary(context: InterviewContext) -> str:
    job = context.job
    strong_count = len(context.skill_gap.strengths)
    gap_count = len(context.skill_gap.critical_gaps) + len(context.skill_gap.partial_gaps)
    return (
        f"Interview preparation for the {job.job_title} role at {job.company}. "
        f"Your Skill Gap Analysis shows {strong_count} demonstrated strength(s) and {gap_count} area(s) to review before the interview. "
        f"Focus your preparation on the questions and revision topics below, prioritized from your actual resume, projects, and this role's real requirements."
    )
