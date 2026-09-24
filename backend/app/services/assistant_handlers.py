"""Milestone 3.4 — per-intent handlers.

Each handler takes the already-resolved `ResolvedContext` (real job/resume/profile
data, never trusted ids) and returns a `HandlerResult`: a deterministic, fully
grounded message (the fallback, always computed), a compact `facts` payload (what
the optional LLM synthesis step is allowed to reword — never anything beyond this),
the suggested action buttons, and which fabrication-check mode applies to this
intent's LLM-synthesized wording.

This module is a thin orchestration layer — it calls M2/M3.1/M3.2/M3.3's own
service functions directly and never reimplements their scoring/generation logic.
"""

from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.schemas.assistant import SuggestedAction
from app.services.assistant_context import ResolvedContext
from app.services.interview_evidence import best_effort_m2_match
from app.services.interview_prep_service import generate_interview_preparation, get_interview_preparation, list_interview_preparations
from app.services.job_matching import match_jobs_for_resume
from app.services.resume_customization_service import generate_customization, get_customization, list_customizations
from app.services.skill_gap_service import analyze_skill_gap, get_persisted_skill_gap


@dataclass
class HandlerResult:
    message: str
    facts: dict
    suggested_actions: list[SuggestedAction]
    unsupported_terms: set[str] = field(default_factory=set)
    # "strict": full check (unsupported keyword + metric + leadership + years) — for
    #   intents whose facts never legitimately include a job-gap term or a real score.
    # "scored": leadership/years only — for intents whose facts legitimately include
    #   a real, already-computed percentage (M3.1 readiness, M2 match score) and/or
    #   a named skill gap (mentioning a gap by term is the point, not a fabrication).
    grounding_mode: str = "strict"
    context_used: list[str] = field(default_factory=list)
    job_id: str | None = None
    resume_id: int | None = None
    stale_notice: str | None = None


def _get_or_generate_customization(db: Session, user_id: int, resume_id: int, job_id: str, structured_updated_at):
    existing = list_customizations(db, resume_id, job_id)
    if existing:
        latest = get_customization(db, resume_id, existing[0].id, structured_updated_at)
        if latest is not None and not latest.stale:
            return latest, False
    return generate_customization(db, resume_id, job_id, user_id), True


def _get_or_generate_interview_prep(db: Session, user_id: int, resume_id: int, job_id: str, structured_updated_at):
    existing = list_interview_preparations(db, resume_id, job_id)
    if existing:
        latest = get_interview_preparation(db, resume_id, existing[0].id, structured_updated_at)
        if latest is not None and not latest.stale:
            return latest, False
    return generate_interview_preparation(db, resume_id, job_id, user_id), True


def handle_job_discovery(db: Session, user_id: int, ctx: ResolvedContext, message: str) -> HandlerResult:
    matches = match_jobs_for_resume(db, ctx.resume.id, top_k=5)
    if not matches:
        return HandlerResult(
            "I couldn't find any internship matches for your resume yet. Try exploring Career Recommendations directly.",
            {"matches": []}, [SuggestedAction(label="View recommendations", action="view_recommendations")],
            context_used=["m2_job_match"], resume_id=ctx.resume.id,
        )
    lines = [f"{m.job_title} at {m.company} — {round(m.match_score)}% match" + (f" (matched: {', '.join(m.matched_required_skills[:3])})" if m.matched_required_skills else "") for m in matches]
    message_out = "Based on your resume, here are your top internship matches:\n" + "\n".join(f"- {line}" for line in lines)
    actions = [SuggestedAction(label=f"View {m.job_title}", action="view_job", job_id=m.job_id) for m in matches[:3]]
    actions.append(SuggestedAction(label="View all recommendations", action="view_recommendations"))
    facts = {"matches": [
        {"job_id": m.job_id, "job_title": m.job_title, "company": m.company, "match_score": round(m.match_score),
         "matched_required_skills": m.matched_required_skills, "missing_required_skills": m.missing_required_skills}
        for m in matches
    ]}
    return HandlerResult(message_out, facts, actions, grounding_mode="scored", context_used=["m2_job_match"], resume_id=ctx.resume.id)


def handle_job_match_explanation(db: Session, user_id: int, ctx: ResolvedContext, message: str) -> HandlerResult:
    job = ctx.job
    m2 = best_effort_m2_match(db, ctx.resume.id, job.job_id)
    gap = analyze_skill_gap(db, ctx.resume.id, job.job_id, user_id)
    strengths = [s.requirement for s in gap.strengths][:5]
    critical = [g.requirement for g in gap.critical_gaps][:5]
    partial = [g.requirement for g in gap.partial_gaps][:5]

    parts = [f"For {job.job_title} at {job.company}:"]
    if m2 is not None:
        parts.append(f"Your M2 match score is {round(m2.match_score)}%.")
    if strengths:
        parts.append(f"You already demonstrate: {', '.join(strengths)}.")
    if critical:
        parts.append(f"Missing (required): {', '.join(critical)}.")
    if partial:
        parts.append(f"Partially demonstrated: {', '.join(partial)}.")
    if not strengths and not critical and not partial:
        parts.append("No specific skill evidence was found to compare yet.")

    facts = {
        "job_title": job.job_title, "company": job.company,
        "match_score": round(m2.match_score) if m2 is not None else None,
        "strengths": strengths, "critical_gaps": critical, "partial_gaps": partial,
    }
    unsupported = {g.requirement.lower() for g in gap.critical_gaps if g.match_type == "missing"}
    actions = [SuggestedAction(label="View job", action="view_job", job_id=job.job_id), SuggestedAction(label="Analyze skill gaps", action="analyze_skill_gap", job_id=job.job_id)]
    context_used = ["job_posting", "m3.1_skill_gap"] + (["m2_job_match"] if m2 is not None else [])
    stale_notice = "Your skill gap analysis reflects an earlier version of your resume — consider refreshing it." if gap.stale else None
    return HandlerResult(" ".join(parts), facts, actions, unsupported, "scored", context_used, job.job_id, ctx.resume.id, stale_notice)


def handle_skill_gap(db: Session, user_id: int, ctx: ResolvedContext, message: str) -> HandlerResult:
    job = ctx.job
    gap = analyze_skill_gap(db, ctx.resume.id, job.job_id, user_id)
    critical = [g.requirement for g in gap.critical_gaps]
    partial = [g.requirement for g in gap.partial_gaps]
    preferred = [g.requirement for g in gap.preferred_gaps]

    parts = [f"For {job.job_title} at {job.company}, your readiness is {gap.summary.overall_readiness}%."]
    if not critical and not partial:
        parts.append("You meet all required skills.")
    else:
        if critical:
            parts.append(f"Critical gaps (required, missing): {', '.join(critical)}.")
        if partial:
            parts.append(f"Partially demonstrated: {', '.join(partial)}.")
    if preferred:
        parts.append(f"Preferred (non-mandatory) gaps: {', '.join(preferred)}.")

    facts = {"job_title": job.job_title, "readiness": gap.summary.overall_readiness, "critical_gaps": critical, "partial_gaps": partial, "preferred_gaps": preferred}
    unsupported = {g.requirement.lower() for g in (gap.critical_gaps + gap.preferred_gaps + gap.partial_gaps) if g.match_type == "missing"}
    actions = [SuggestedAction(label="View full skill gap analysis", action="analyze_skill_gap", job_id=job.job_id)]
    if critical or partial:
        actions.append(SuggestedAction(label="Review learning plan", action="view_learning_plan", job_id=job.job_id))
    stale_notice = "Your resume has changed since this skill gap analysis was generated." if gap.stale else None
    return HandlerResult(" ".join(parts), facts, actions, unsupported, "scored", ["m3.1_skill_gap"], job.job_id, ctx.resume.id, stale_notice)


def handle_resume_customization(db: Session, user_id: int, ctx: ResolvedContext, message: str) -> HandlerResult:
    job = ctx.job
    customization, generated = _get_or_generate_customization(db, user_id, ctx.resume.id, job.job_id, ctx.structured.updated_at)
    summary = customization.tailored_resume.summary
    top_skills = customization.tailored_resume.skills[:5]
    if generated:
        text = f'I\'ve tailored your resume for {job.job_title} at {job.company} (version {customization.version}). Your summary now reads: "{summary}" Open Customize Application to review, edit, and export it.'
    else:
        text = f'You already have a tailored resume for {job.job_title} (version {customization.version}). Its summary: "{summary}" Open Customize Application to review or regenerate it.'
    facts = {"job_title": job.job_title, "version": customization.version, "summary": summary, "top_skills": top_skills}
    actions = [SuggestedAction(label="Open Customize Application", action="customize_application", job_id=job.job_id)]
    stale_notice = "This tailored resume is based on an earlier version of your resume." if customization.stale else None
    return HandlerResult(text, facts, actions, context_used=["m3.2_customization"], job_id=job.job_id, resume_id=ctx.resume.id, stale_notice=stale_notice)


def handle_cover_letter(db: Session, user_id: int, ctx: ResolvedContext, message: str) -> HandlerResult:
    job = ctx.job
    customization, generated = _get_or_generate_customization(db, user_id, ctx.resume.id, job.job_id, ctx.structured.updated_at)
    letter = customization.cover_letter_text
    preview = letter if len(letter) <= 300 else letter[:297] + "..."
    intro = f"I've drafted a cover letter for {job.job_title} at {job.company}" if generated else f"You already have a cover letter for {job.job_title} at {job.company}"
    text = f"{intro} (version {customization.version}):\n\n{preview}\n\nOpen Customize Application to review, edit, and export it."
    facts = {"job_title": job.job_title, "version": customization.version, "cover_letter_preview": preview}
    actions = [SuggestedAction(label="Open Customize Application", action="customize_application", job_id=job.job_id)]
    stale_notice = "This cover letter is based on an earlier version of your resume." if customization.stale else None
    return HandlerResult(text, facts, actions, context_used=["m3.2_customization"], job_id=job.job_id, resume_id=ctx.resume.id, stale_notice=stale_notice)


def handle_interview_prep(db: Session, user_id: int, ctx: ResolvedContext, message: str) -> HandlerResult:
    job = ctx.job
    prep, generated = _get_or_generate_interview_prep(db, user_id, ctx.resume.id, job.job_id, ctx.structured.updated_at)
    categories = Counter(q.category for q in prep.questions)
    cat_summary = ", ".join(f"{count} {category}" for category, count in categories.items())
    top_priority = prep.revision_plan[0] if prep.revision_plan else None

    text = f"Interview preparation for {job.job_title} at {job.company} (version {prep.version}) is ready: {cat_summary} questions."
    if top_priority is not None:
        text += f" Top revision priority: {top_priority.topic} — {top_priority.reason}"
    text += " Open Interview Preparation to review every question and practice."

    facts = {"job_title": job.job_title, "version": prep.version, "question_categories": dict(categories), "top_priority": top_priority.topic if top_priority is not None else None}
    actions = [SuggestedAction(label="Open Interview Preparation", action="prepare_interview", job_id=job.job_id)]
    stale_notice = "This interview preparation is based on an earlier version of your resume." if prep.stale else None
    return HandlerResult(text, facts, actions, grounding_mode="scored", context_used=["m3.3_interview_prep"], job_id=job.job_id, resume_id=ctx.resume.id, stale_notice=stale_notice)


def handle_learning_guidance(db: Session, user_id: int, ctx: ResolvedContext, message: str) -> HandlerResult:
    job = ctx.job
    gap = analyze_skill_gap(db, ctx.resume.id, job.job_id, user_id)
    ordered = gap.critical_gaps + gap.partial_gaps + gap.preferred_gaps
    top = ordered[:3]

    if not top:
        text = f"You already meet every required and preferred skill listed for {job.job_title}. Focus on deepening your strongest projects for interview readiness instead."
    else:
        lines = [f"{item.requirement} ({item.priority} priority): {item.recommendation}" for item in top]
        text = f"Based on your skill gap analysis for {job.job_title}, focus on:\n" + "\n".join(f"- {line}" for line in lines)

    facts = {"job_title": job.job_title, "priorities": [{"requirement": item.requirement, "priority": item.priority, "recommendation": item.recommendation} for item in top]}
    unsupported = {item.requirement.lower() for item in top if item.match_type == "missing"}
    actions = [SuggestedAction(label="View full skill gap analysis", action="analyze_skill_gap", job_id=job.job_id), SuggestedAction(label="Review learning plan", action="view_learning_plan", job_id=job.job_id)]
    stale_notice = "Your resume has changed since this skill gap analysis was generated." if gap.stale else None
    return HandlerResult(text, facts, actions, unsupported, "scored", ["m3.1_skill_gap"], job.job_id, ctx.resume.id, stale_notice)


def handle_job_comparison(db: Session, user_id: int, ctx: ResolvedContext, message: str) -> HandlerResult:
    a, b = ctx.job, ctx.second_job
    lines = [
        f"{a.job_title} ({a.company}) vs {b.job_title} ({b.company}):",
        f"Location/mode: {a.location}/{a.work_mode} vs {b.location}/{b.work_mode}.",
        f"Required skills: {', '.join(a.required_skills)} vs {', '.join(b.required_skills)}.",
        f"Preferred skills: {', '.join(a.preferred_skills) or 'none'} vs {', '.join(b.preferred_skills) or 'none'}.",
    ]
    facts: dict = {
        "job_a": {"job_id": a.job_id, "job_title": a.job_title, "company": a.company, "required_skills": a.required_skills, "preferred_skills": a.preferred_skills, "location": a.location, "work_mode": a.work_mode},
        "job_b": {"job_id": b.job_id, "job_title": b.job_title, "company": b.company, "required_skills": b.required_skills, "preferred_skills": b.preferred_skills, "location": b.location, "work_mode": b.work_mode},
    }
    unsupported: set[str] = set()
    context_used = ["job_posting_a", "job_posting_b"]

    if ctx.resume is not None and ctx.resume_is_processed:
        gap_a = analyze_skill_gap(db, ctx.resume.id, a.job_id, user_id)
        gap_b = analyze_skill_gap(db, ctx.resume.id, b.job_id, user_id)
        met_a = len(a.required_skills) - len(gap_a.critical_gaps)
        met_b = len(b.required_skills) - len(gap_b.critical_gaps)
        lines.append(f"Your readiness: {gap_a.summary.overall_readiness}% for {a.job_title} vs {gap_b.summary.overall_readiness}% for {b.job_title}.")
        lines.append(f"Required skills currently demonstrated: {met_a}/{len(a.required_skills)} for {a.job_title}, {met_b}/{len(b.required_skills)} for {b.job_title}.")
        facts["readiness_a"] = gap_a.summary.overall_readiness
        facts["readiness_b"] = gap_b.summary.overall_readiness
        unsupported = {g.requirement.lower() for g in (gap_a.critical_gaps + gap_b.critical_gaps) if g.match_type == "missing"}
        context_used.append("m3.1_skill_gap")

    actions = [SuggestedAction(label=f"View {a.job_title}", action="view_job", job_id=a.job_id), SuggestedAction(label=f"View {b.job_title}", action="view_job", job_id=b.job_id)]
    return HandlerResult("\n".join(lines), facts, actions, unsupported, "scored", context_used, a.job_id, ctx.resume.id if ctx.resume else None)


def handle_profile_summary(db: Session, user_id: int, ctx: ResolvedContext, message: str) -> HandlerResult:
    data = ctx.structured.data
    skills = data.get("skills", []) or []
    projects = [p for p in (data.get("projects", []) or []) if isinstance(p, dict)]
    project_names = [str(p.get("title") or (p.get("raw_text", "")[:60] + "...")) for p in projects[:5]]

    parts = []
    if skills:
        parts.append(f"Your resume lists {len(skills)} skills: {', '.join(skills[:10])}.")
    if project_names:
        parts.append(f"Your projects: {', '.join(project_names)}.")
    if ctx.profile is not None and ctx.profile.target_roles:
        parts.append(f"Your target roles: {', '.join(ctx.profile.target_roles)}.")
    if not parts:
        parts.append("Your resume is processed, but no skills or projects were extracted from it yet.")

    facts = {"skills": skills, "projects": project_names, "target_roles": ctx.profile.target_roles if ctx.profile is not None else []}
    actions = [SuggestedAction(label="View resume results", action="view_resume")]
    return HandlerResult(" ".join(parts), facts, actions, context_used=["resume", "profile"], resume_id=ctx.resume.id)


def handle_next_best_action(db: Session, user_id: int, ctx: ResolvedContext, message: str) -> HandlerResult:
    if ctx.resume is None:
        return HandlerResult("You haven't uploaded a resume yet. Upload one to get started.", {}, [SuggestedAction(label="Upload resume", action="upload_resume")])
    if not ctx.resume_is_processed:
        return HandlerResult("Your resume is uploaded but not yet processed. Process it to extract your skills and experience.", {}, [SuggestedAction(label="Process resume", action="process_resume")], resume_id=ctx.resume.id)
    if ctx.job is None:
        return HandlerResult("You haven't selected a target internship yet. Explore recommendations to find one that fits you.", {}, [SuggestedAction(label="Explore recommendations", action="view_recommendations")], resume_id=ctx.resume.id)

    job = ctx.job
    gap = get_persisted_skill_gap(db, user_id, job.job_id, ctx.structured.updated_at)
    if gap is None:
        return HandlerResult(f"You've selected {job.job_title} but haven't analyzed your skill gaps yet.", {}, [SuggestedAction(label="Analyze skill gaps", action="analyze_skill_gap", job_id=job.job_id)], job_id=job.job_id, resume_id=ctx.resume.id)
    if gap.critical_gaps or gap.partial_gaps:
        return HandlerResult(f"Your skill gap analysis for {job.job_title} shows gaps to address. Review your learning priorities next.", {}, [SuggestedAction(label="Review learning plan", action="view_learning_plan", job_id=job.job_id)], job_id=job.job_id, resume_id=ctx.resume.id)

    existing_customization = list_customizations(db, ctx.resume.id, job.job_id)
    if not existing_customization:
        return HandlerResult(f"You meet the required skills for {job.job_title}. Customize your application next.", {}, [SuggestedAction(label="Customize application", action="customize_application", job_id=job.job_id)], job_id=job.job_id, resume_id=ctx.resume.id)

    existing_prep = list_interview_preparations(db, ctx.resume.id, job.job_id)
    if not existing_prep:
        return HandlerResult(f"Your application for {job.job_title} is customized. Prepare for the interview next.", {}, [SuggestedAction(label="Prepare for interview", action="prepare_interview", job_id=job.job_id)], job_id=job.job_id, resume_id=ctx.resume.id)

    return HandlerResult(f"You've completed customization and interview preparation for {job.job_title}. Keep reviewing your interview preparation to sharpen your answers.", {}, [SuggestedAction(label="Prepare for interview", action="prepare_interview", job_id=job.job_id)], job_id=job.job_id, resume_id=ctx.resume.id)


def handle_general_career_chat(db: Session, user_id: int, ctx: ResolvedContext, message: str) -> HandlerResult:
    text = "I can help with job recommendations, skill gaps, resume customization, cover letters, and interview preparation. Try asking about a specific internship, or ask what you should do next."
    actions: list[SuggestedAction] = []
    if ctx.resume is None:
        actions.append(SuggestedAction(label="Upload resume", action="upload_resume"))
    elif ctx.job is None:
        actions.append(SuggestedAction(label="Explore recommendations", action="view_recommendations"))
    return HandlerResult(text, {}, actions, job_id=ctx.job.job_id if ctx.job else None, resume_id=ctx.resume.id if ctx.resume else None)


HANDLERS = {
    "JOB_DISCOVERY": handle_job_discovery,
    "JOB_MATCH_EXPLANATION": handle_job_match_explanation,
    "SKILL_GAP": handle_skill_gap,
    "RESUME_CUSTOMIZATION": handle_resume_customization,
    "COVER_LETTER": handle_cover_letter,
    "INTERVIEW_PREP": handle_interview_prep,
    "LEARNING_GUIDANCE": handle_learning_guidance,
    "JOB_COMPARISON": handle_job_comparison,
    "PROFILE_SUMMARY": handle_profile_summary,
    "NEXT_BEST_ACTION": handle_next_best_action,
    "GENERAL_CAREER_CHAT": handle_general_career_chat,
}
