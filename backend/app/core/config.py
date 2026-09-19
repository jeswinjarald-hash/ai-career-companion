from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> backend/ — the same __file__-anchored convention
# already used by app/services/job_dataset_service.py and job_vector_store.py.
BACKEND_ROOT = Path(__file__).resolve().parents[2]


def resolve_backend_path(raw_path: str) -> Path:
    """Resolves a path against the backend project root, not the process's current
    working directory.

    A relative path (the default for both the SQLite database file and the resume
    storage directory) would otherwise be resolved against whatever directory the
    process happened to be launched from. Two launches from different directories
    then silently point at two different files/folders on disk — same code, same
    "successful" startup, but a user who registered under one working directory
    appears not to exist when the app is next started from another. Anchoring to
    the backend root keeps exactly one physical location regardless of launch cwd.
    """
    path = Path(raw_path)
    return path if path.is_absolute() else (BACKEND_ROOT / path).resolve()


class Settings(BaseSettings):
    app_name: str = "AI Career Companion API"
    app_env: str = "development"
    debug: bool = False
    frontend_url: str = "http://localhost:5173"
    database_url: str | None = None
    resume_storage_dir: str = "./data/resumes"
    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()