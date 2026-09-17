from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


def _database_url() -> str:
    return get_settings().database_url or "sqlite:///./data/ai_career_companion.db"


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
    from app.models import CandidateProfile, Resume, ResumeExtraction, ResumeSection, StructuredResume, CandidateContext, User, AuthSession, SelectedJob, SkillGap, LearningRoadmap, RoadmapItem, ProgressEvent  # noqa: F401

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