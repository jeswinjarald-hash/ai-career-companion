from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CandidateProfile, CandidateContext, Resume, StructuredResume


def _merge_unique(*groups: list[str]) -> list[str]:
    result = []
    seen = set()
    for group in groups:
        for value in group:
            key = value.casefold()
            if key not in seen:
                seen.add(key)
                result.append(value)
    return result


def get_candidate_context(db: Session, profile_id: int, resume_id: int) -> CandidateContext | None:
    return db.scalar(select(CandidateContext).where(CandidateContext.candidate_profile_id == profile_id, CandidateContext.resume_id == resume_id))


def build_candidate_context(db: Session, profile: CandidateProfile, resume: Resume) -> CandidateContext:
    structured = db.scalar(select(StructuredResume).where(StructuredResume.resume_id == resume.id))
    if structured is None:
        raise ValueError("A structured resume is required before generating candidate context.")
    data = structured.data
    profile_data = {
        "full_name": profile.full_name, "email": profile.email, "education": profile.education,
        "degree": profile.degree, "specialization": profile.specialization, "experience_level": profile.experience_level,
        "career_interests": profile.career_interests, "target_roles": profile.target_roles,
        "skills": profile.skills, "career_goals": profile.career_goals,
    }
    combined = {
        "skills": _merge_unique(profile.skills, data.get("skills", [])),
        "education": ([{"raw_text": profile.education, "degree": profile.degree, "specialization": profile.specialization}] if profile.education else []) + data.get("education", []),
        "experience": data.get("experience", []) + data.get("internships", []),
        "projects": data.get("projects", []),
        "career_interests": profile.career_interests,
        "target_roles": profile.target_roles,
    }
    payload = {"candidate_id": profile.id, "profile": profile_data, "resume": data, "combined": combined}
    context = get_candidate_context(db, profile.id, resume.id)
    if context is None:
        context = CandidateContext(candidate_profile_id=profile.id, resume_id=resume.id, context_json=payload)
        db.add(context)
    else:
        context.context_json = payload
    db.commit()
    db.refresh(context)
    return context
