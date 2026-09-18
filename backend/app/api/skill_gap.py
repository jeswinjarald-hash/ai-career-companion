import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import StructuredResume, User
from app.schemas.skill_gap import SkillGapAnalysis
from app.services.auth import require_current_user
from app.services.resume import get_owned_resume
from app.services.skill_gap_service import analyze_skill_gap, get_persisted_skill_gap

router = APIRouter(tags=["skill-gap"])
logger = logging.getLogger(__name__)


@router.post("/api/resumes/{resume_id}/skill-gap", response_model=SkillGapAnalysis)
def run_skill_gap_analysis(
    resume_id: int,
    job_id: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user),
) -> SkillGapAnalysis:
    if get_owned_resume(db, resume_id, current_user.id) is None:
        raise HTTPException(status_code=404, detail="Resume not found.")
    try:
        return analyze_skill_gap(db, resume_id, job_id, current_user.id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception:
        logger.exception("skill_gap_analysis_failed resume_id=%s job_id=%s", resume_id, job_id)
        raise


@router.get("/api/resumes/{resume_id}/skill-gap/{job_id}", response_model=SkillGapAnalysis)
def read_skill_gap_analysis(
    resume_id: int,
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user),
) -> SkillGapAnalysis:
    if get_owned_resume(db, resume_id, current_user.id) is None:
        raise HTTPException(status_code=404, detail="Resume not found.")
    structured = db.scalar(select(StructuredResume).where(StructuredResume.resume_id == resume_id))
    if structured is None:
        raise HTTPException(status_code=409, detail="A structured student profile is required before skill gap analysis.")
    result = get_persisted_skill_gap(db, current_user.id, job_id, structured.updated_at)
    if result is None:
        raise HTTPException(status_code=404, detail="No skill gap analysis found for this internship yet.")
    return result
