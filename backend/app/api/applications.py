from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import User
from app.schemas.application import (
    ApplicationCreate,
    ApplicationRemindersResponse,
    ApplicationResponse,
    ApplicationSort,
    ApplicationStatus,
    ApplicationSummary,
    ApplicationUpdate,
)
from app.services.application_service import (
    DEFAULT_REMINDER_WINDOW_DAYS,
    MAX_REMINDER_WINDOW_DAYS,
    DuplicateApplicationError,
    build_reminders,
    build_summary,
    create_application,
    delete_application,
    get_owned_application,
    list_applications,
    update_application,
)
from app.services.auth import require_current_user

router = APIRouter(prefix="/api/applications", tags=["applications"])


@router.post("", response_model=ApplicationResponse, status_code=status.HTTP_201_CREATED)
def create_tracked_application(
    payload: ApplicationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user),
) -> ApplicationResponse:
    try:
        return create_application(db, current_user.id, payload)
    except DuplicateApplicationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("", response_model=list[ApplicationResponse])
def read_applications(
    status_filter: list[ApplicationStatus] | None = Query(None, alias="status"),
    q: str | None = Query(None, max_length=255),
    active: bool | None = None,
    deadline_from: date | None = None,
    deadline_to: date | None = None,
    applied_from: date | None = None,
    applied_to: date | None = None,
    sort: ApplicationSort = "updated_desc",
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user),
) -> list[ApplicationResponse]:
    try:
        return list_applications(
            db, current_user.id, statuses=status_filter, q=q, active=active,
            deadline_from=deadline_from, deadline_to=deadline_to,
            applied_from=applied_from, applied_to=applied_to, sort=sort,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/summary", response_model=ApplicationSummary)
def read_application_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user),
) -> ApplicationSummary:
    return build_summary(db, current_user.id)


@router.get("/reminders", response_model=ApplicationRemindersResponse)
def read_application_reminders(
    days: int = Query(DEFAULT_REMINDER_WINDOW_DAYS, ge=1, le=MAX_REMINDER_WINDOW_DAYS),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user),
) -> ApplicationRemindersResponse:
    return build_reminders(db, current_user.id, days)


@router.get("/{application_id}", response_model=ApplicationResponse)
def read_application(
    application_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user),
) -> ApplicationResponse:
    application = get_owned_application(db, application_id, current_user.id)
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found.")
    return application


@router.patch("/{application_id}", response_model=ApplicationResponse)
def update_tracked_application(
    application_id: int,
    payload: ApplicationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user),
) -> ApplicationResponse:
    application = get_owned_application(db, application_id, current_user.id)
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found.")
    try:
        return update_application(db, application, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/{application_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tracked_application(
    application_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user),
) -> Response:
    application = get_owned_application(db, application_id, current_user.id)
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found.")
    delete_application(db, application)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
