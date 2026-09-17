import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, Response
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import AuthSession, CandidateProfile, User

SESSION_COOKIE = "ai_career_session"
SESSION_DAYS = 14
password_hash = PasswordHash.recommended()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def register_user(db: Session, full_name: str, email: str, password: str) -> User:
    email = email.strip().casefold()
    if db.scalar(select(User).where(User.email == email)) is not None:
        raise ValueError("An account with this email already exists.")
    user = User(full_name=full_name.strip(), email=email, password_hash=password_hash.hash(password))
    db.add(user)
    db.flush()
    db.add(CandidateProfile(user_id=user.id, full_name=user.full_name, email=user.email, career_interests=[], target_roles=[], skills=[]))
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.email == email.strip().casefold()))
    if user is None or not password_hash.verify(password, user.password_hash):
        return None
    return user


def create_session(db: Session, user: User, response: Response) -> None:
    raw_token = secrets.token_urlsafe(48)
    session = AuthSession(user_id=user.id, token_hash=_token_hash(raw_token), expires_at=datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS))
    db.add(session)
    db.commit()
    response.set_cookie(SESSION_COOKIE, raw_token, httponly=True, samesite="lax", secure=False, max_age=SESSION_DAYS * 86400)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def get_current_user(request: Request, db: Session) -> User | None:
    raw_token = request.cookies.get(SESSION_COOKIE)
    if not raw_token:
        return None
    session = db.scalar(select(AuthSession).where(AuthSession.token_hash == _token_hash(raw_token)))
    if session is None or _as_utc(session.expires_at) <= datetime.now(timezone.utc):
        return None
    return db.get(User, session.user_id)


def clear_session(request: Request, response: Response, db: Session) -> None:
    raw_token = request.cookies.get(SESSION_COOKIE)
    if raw_token:
        session = db.scalar(select(AuthSession).where(AuthSession.token_hash == _token_hash(raw_token)))
        if session:
            db.delete(session)
            db.commit()
    response.delete_cookie(SESSION_COOKIE)


def require_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = get_current_user(request, db)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return user
