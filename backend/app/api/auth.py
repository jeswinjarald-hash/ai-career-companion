from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import CandidateProfile
from app.schemas.auth import AuthResponse, LoginRequest, RegisterRequest, UserResponse
from app.schemas.profile import CandidateProfileResponse
from app.services.auth import authenticate_user, clear_session, create_session, get_current_user, register_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _auth_response(db: Session, user) -> AuthResponse:
    profile = db.scalar(select(CandidateProfile).where(CandidateProfile.user_id == user.id))
    return AuthResponse(user=UserResponse.model_validate(user), profile=CandidateProfileResponse.model_validate(profile) if profile else None)


@router.post("/register", response_model=AuthResponse, status_code=201)
def register(payload: RegisterRequest, response: Response, db: Session = Depends(get_db)) -> AuthResponse:
    if payload.password != payload.confirm_password:
        raise HTTPException(status_code=422, detail="Passwords do not match.")
    try:
        user = register_user(db, payload.full_name, payload.email, payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    create_session(db, user, response)
    return _auth_response(db, user)


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)) -> AuthResponse:
    user = authenticate_user(db, payload.email, payload.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    create_session(db, user, response)
    return _auth_response(db, user)


@router.get("/me", response_model=AuthResponse)
def me(request: Request, db: Session = Depends(get_db)) -> AuthResponse:
    user = get_current_user(request, db)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return _auth_response(db, user)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> Response:
    clear_session(request, response, db)
    response.status_code = 204
    return response
