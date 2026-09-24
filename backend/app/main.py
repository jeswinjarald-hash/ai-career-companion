import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.health import router as health_router
from app.api.profile import router as profile_router
from app.api.resume import router as resume_router
from app.api.context import router as context_router
from app.api.jobs import router as jobs_router
from app.api.auth import router as auth_router
from app.api.skill_gap import router as skill_gap_router
from app.api.customization import router as customization_router
from app.api.interview_prep import router as interview_prep_router
from app.api.assistant import router as assistant_router
from app.core.config import get_settings
from app.core.database import init_db

logger = logging.getLogger(__name__)
settings = get_settings()


def _log_llm_config_status() -> None:
    # Logs only booleans/identifiers — LLM_API_KEY's value is never logged, printed,
    # or otherwise surfaced here, only whether one is present. Also printed directly
    # (not just logged): this app has no global `logging.basicConfig`/handler setup,
    # so a plain `logger.info` call — like every other one already in this codebase —
    # is silently dropped by Python's default root-logger level (WARNING) unless the
    # deployment environment separately configures logging; `print` guarantees this
    # specific startup confirmation is actually visible without requiring that.
    if settings.llm_provider == "none":
        message = "llm_config_status provider=none (deterministic-only pipeline)"
    else:
        message = (
            f"llm_config_status provider={settings.llm_provider} "
            f"model_configured={bool(settings.llm_model)} "
            f"base_url_configured={bool(settings.llm_base_url)} "
            f"api_key_present={bool(settings.llm_api_key)}"
        )
    logger.info(message)
    print(message, flush=True)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    _log_llm_config_status()
    yield

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    debug=settings.debug,
    lifespan=lifespan,
)

# A fixed, finite list of guessed dev ports ("5173".."5176") is fragile: Vite picks
# the next free port whenever a prior dev server is still holding one, so the
# frontend's real origin can drift past any hardcoded list — the browser then sends
# a preflight from an origin CORSMiddleware doesn't recognize, and Starlette
# rejects it with 400 "Disallowed CORS origin" before the request ever reaches
# `/api/auth/me`. In development, allow any localhost/127.0.0.1 port via regex
# instead of enumerating ports; `allow_origins=["*"]` is never used here since this
# app authenticates with a credentialed cookie, and the CORS spec (correctly
# enforced by browsers) forbids combining a wildcard origin with credentials. The
# configured `frontend_url` is always allowed by exact match too, so a
# non-development deployment (where the permissive regex is intentionally not
# applied) still works via that explicit origin.
LOCAL_DEV_ORIGIN_REGEX = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"


def cors_origin_regex_for_env(app_env: str) -> str | None:
    return LOCAL_DEV_ORIGIN_REGEX if app_env == "development" else None


app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_origin_regex=cors_origin_regex_for_env(settings.app_env),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


app.include_router(health_router)
app.include_router(profile_router)
app.include_router(resume_router)
app.include_router(context_router)
app.include_router(jobs_router)
app.include_router(auth_router)
app.include_router(skill_gap_router)
app.include_router(customization_router)
app.include_router(interview_prep_router)
app.include_router(assistant_router)