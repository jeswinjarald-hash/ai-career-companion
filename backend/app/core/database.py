import logging
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings, resolve_backend_path

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


def _resolve_sqlite_url(raw_url: str) -> str:
    """Rewrites a relative `sqlite:///...` path to an absolute one anchored at the
    backend root (see `resolve_backend_path`). Non-sqlite URLs (e.g. Postgres) and
    already-absolute or in-memory sqlite URLs pass through unchanged.
    """
    if not raw_url.startswith("sqlite:///"):
        return raw_url
    path_part = raw_url.removeprefix("sqlite:///")
    if path_part == ":memory:":
        return raw_url
    return f"sqlite:///{resolve_backend_path(path_part).as_posix()}"


def _database_url() -> str:
    configured = get_settings().database_url or "sqlite:///./data/ai_career_companion.db"
    return _resolve_sqlite_url(configured)


def _safe_url_for_logging(database_url: str) -> str:
    # SQLite URLs are plain file paths (safe to log); any other backend's URL may
    # embed a username/password, so only the scheme+host shape is logged for those.
    if database_url.startswith("sqlite"):
        return database_url
    scheme = database_url.split("://", 1)[0]
    return f"{scheme}://<redacted>"


def _create_engine() -> Engine:
    database_url = _database_url()
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}

    if database_url.startswith("sqlite"):
        database_path = database_url.removeprefix("sqlite:///")
        if database_path != ":memory:":
            Path(database_path).parent.mkdir(parents=True, exist_ok=True)

    return create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)


engine = _create_engine()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def init_db() -> None:
    from app.models import CandidateProfile, Resume, ResumeExtraction, ResumeSection, StructuredResume, CandidateContext, User, AuthSession, SelectedJob, SkillGap, LearningRoadmap, RoadmapItem, ProgressEvent, ApplicationCustomization, InterviewPreparation, Conversation, ConversationMessage  # noqa: F401

    logger.info("Database initialized: %s", _safe_url_for_logging(_database_url()))
    # create_all only creates tables that don't already exist — it never drops or
    # clears existing tables/rows, so existing users/resumes/sessions are preserved.
    Base.metadata.create_all(bind=engine)
    if engine.dialect.name == "sqlite":
        _add_profile_columns_for_existing_sqlite_database()


def _add_profile_columns_for_existing_sqlite_database() -> None:
    existing_columns = {
        column["name"] for column in inspect(engine).get_columns("candidate_profiles")
    }
    profile_columns = {
        "user_id": "INTEGER",
        "degree": "VARCHAR(255)",
        "specialization": "VARCHAR(255)",
        "target_roles": "JSON",
        "skills": "JSON",
        "career_goals": "TEXT",
    }

    with engine.begin() as connection:
        for column_name, column_type in profile_columns.items():
            if column_name not in existing_columns:
                connection.execute(
                    text(f"ALTER TABLE candidate_profiles ADD COLUMN {column_name} {column_type}")
                )
        connection.execute(text("UPDATE candidate_profiles SET target_roles = '[]' WHERE target_roles IS NULL"))
        connection.execute(text("UPDATE candidate_profiles SET skills = '[]' WHERE skills IS NULL"))


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()