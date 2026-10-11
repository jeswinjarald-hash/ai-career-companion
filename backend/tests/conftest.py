"""Suite-wide guards: no live LLM, no real user data, no network.

`backend/.env` may hold a real provider key for manual validation, and
`get_settings()` reads it, so any test that generates content without passing an
explicit `llm_provider` would otherwise make real, billed calls. Every module that
binds its own `get_llm_provider` name (via `from ... import`) is patched to return
`NullLLMProvider`, i.e. the deterministic fallback path. Tests that need specific
LLM behaviour keep passing their own fake provider explicitly, which bypasses
`get_llm_provider` entirely.

It also keeps the suite off the real application database and resume store. The
engine in `app.core.database` is created at import time from `get_settings()`, and
every `with TestClient(app)` runs the app lifespan (`init_db()`) on that engine — so
without this, the suite would open and run DDL against `backend/data/*.db`. Process
environment variables take precedence over `backend/.env` in pydantic-settings, so
they are set here, before any `app` module is imported, and restored when the
session ends; the temporary database and resume store are deleted then too.

Configuration alone is not trusted: a Python audit hook (installed before any `app`
import) refuses, for the whole test process, any attempt to open the real database or
anything in the real resume store (via `open`, `Path.read_bytes`, `os.scandir`/`glob`
or `sqlite3.connect`), and any network connection to a non-loopback address.
Hugging Face libraries are additionally put in offline mode, so a missing embedding
model fails fast instead of being downloaded.
"""

import ipaddress
import os
import shutil
import sys
import tempfile
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_REAL_DATABASE = os.path.normcase(str(_BACKEND_ROOT / "data" / "ai_career_companion.db"))
_REAL_RESUME_STORE = os.path.normcase(str(_BACKEND_ROOT / "data" / "resumes"))
_TEST_DATA_DIR = Path(tempfile.mkdtemp(prefix="ai-career-pytest-"))

_TEST_ENVIRONMENT = {
    "DATABASE_URL": f"sqlite:///{(_TEST_DATA_DIR / 'test.db').as_posix()}",
    "RESUME_STORAGE_DIR": str(_TEST_DATA_DIR / "resumes"),
    "LLM_PROVIDER": "none",
    "LLM_API_KEY": "",
    "LLM_BASE_URL": "",
    "EMBEDDING_ALLOW_DOWNLOAD": "false",
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
}
_ORIGINAL_ENVIRONMENT = {name: os.environ.get(name) for name in _TEST_ENVIRONMENT}
os.environ.update(_TEST_ENVIRONMENT)


class ProtectedResourceError(RuntimeError):
    """Raised when a test tries to touch real user data or the network. Deliberately not
    a PermissionError/OSError: pathlib's glob and similar helpers silently swallow those."""


def _is_protected_path(raw: object) -> bool:
    if isinstance(raw, int) or raw is None:  # file descriptors / anonymous
        return False
    try:
        text = os.fsdecode(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    if text.startswith("file:"):  # SQLite URI form, e.g. file:/path/app.db?mode=ro
        text = text.removeprefix("file:").split("?", 1)[0].lstrip("/") if os.name == "nt" else text.removeprefix("file:").split("?", 1)[0]
    if text in ("", ":memory:"):
        return False
    path = os.path.normcase(os.path.abspath(text))
    return path.startswith(_REAL_DATABASE) or path == _REAL_RESUME_STORE or path.startswith(_REAL_RESUME_STORE + os.sep)


_guard_active = True


def _audit(event: str, args: tuple) -> None:
    if not _guard_active:
        return
    if event in ("open", "os.scandir", "os.listdir", "glob.glob", "sqlite3.connect"):
        target = args[0] if args else None
        if event == "glob.glob":  # args: (pattern, recursive) — check the directory part
            target = os.path.dirname(os.fsdecode(target)) if target is not None else None
        if _is_protected_path(target):
            raise ProtectedResourceError(f"Tests must not access real user data ({event}).")
    elif event == "socket.connect":
        address = args[1] if len(args) > 1 else None
        if isinstance(address, tuple) and address:
            try:
                loopback = ipaddress.ip_address(str(address[0]).split("%")[0]).is_loopback
            except ValueError:
                loopback = False
            if not loopback:
                raise ProtectedResourceError(f"Tests must not open network connections (attempted {address[0]}).")


sys.addaudithook(_audit)

import pytest  # noqa: E402

import app.api.interview_prep as interview_prep_api  # noqa: E402
import app.services.assistant_service as assistant_service  # noqa: E402
import app.services.interview_prep_service as interview_prep_service  # noqa: E402
import app.services.resume_customization_service as resume_customization_service  # noqa: E402
from app.services.llm_provider import NullLLMProvider  # noqa: E402

_GET_LLM_PROVIDER_BINDINGS = (
    resume_customization_service,
    interview_prep_service,
    interview_prep_api,
    assistant_service,
)


@pytest.fixture(autouse=True)
def no_live_llm_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    for module in _GET_LLM_PROVIDER_BINDINGS:
        monkeypatch.setattr(module, "get_llm_provider", lambda _settings: NullLLMProvider())


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    # Audit hooks cannot be removed, so the guard is switched off instead.
    global _guard_active
    _guard_active = False
    from app.core.database import engine

    engine.dispose()  # releases the SQLite file handle so the directory can be removed on Windows
    shutil.rmtree(_TEST_DATA_DIR, ignore_errors=True)
    for name, value in _ORIGINAL_ENVIRONMENT.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value
