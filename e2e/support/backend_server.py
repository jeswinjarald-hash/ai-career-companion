"""Starts an isolated FastAPI backend for the Playwright suite.

Isolation is enforced here, not assumed:
  * the database and resume store live under e2e/.tmp/backend-data (recreated each run);
  * LLM_PROVIDER=none with every LLM field blanked, so no request can leave the machine;
  * EMBEDDING_ALLOW_DOWNLOAD=false and Hugging Face offline mode, so the embedding model is
    only read from the local cache;
  * a Python audit hook, installed before the app is imported, refuses for the whole server
    process any non-loopback network connection and any access to the real database or
    resume store — so isolation does not depend on configuration alone.
Process environment variables take precedence over backend/.env in pydantic-settings.
Before uvicorn starts, the effective settings are re-read through the application's own
code and the process exits if they do not resolve to the isolated paths and a null LLM
provider. Nothing secret is printed — only file paths and booleans.

The vector index under backend/data/vector_store is read-only shared data and is used as-is.

Usage (from the repository root): .venv/Scripts/python.exe e2e/support/backend_server.py --port 8100
"""

import argparse
import ipaddress
import json
import os
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
TMP_ROOT = REPO_ROOT / "e2e" / ".tmp"
DATA_DIR = TMP_ROOT / "backend-data"
REAL_DB = (BACKEND_ROOT / "data" / "ai_career_companion.db").resolve()
REAL_RESUMES = (BACKEND_ROOT / "data" / "resumes").resolve()


def _install_process_guard() -> None:
    protected = (os.path.normcase(str(REAL_DB)), os.path.normcase(str(REAL_RESUMES)))

    def is_protected(raw: object) -> bool:
        if isinstance(raw, int) or raw is None:
            return False
        try:
            text = os.fsdecode(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return False
        if text.startswith("file:"):
            text = text.removeprefix("file:").split("?", 1)[0].lstrip("/") if os.name == "nt" else text.removeprefix("file:").split("?", 1)[0]
        if text in ("", ":memory:"):
            return False
        path = os.path.normcase(os.path.abspath(text))
        return path.startswith(protected[0]) or path == protected[1] or path.startswith(protected[1] + os.sep)

    def audit(event: str, args: tuple) -> None:
        if event in ("open", "os.scandir", "os.listdir", "sqlite3.connect") and args and is_protected(args[0]):
            raise RuntimeError(f"e2e backend must not access real user data ({event}).")
        if event == "socket.connect" and len(args) > 1 and isinstance(args[1], tuple) and args[1]:
            try:
                loopback = ipaddress.ip_address(str(args[1][0]).split("%")[0]).is_loopback
            except ValueError:
                loopback = False
            if not loopback:
                raise RuntimeError(f"e2e backend must not open network connections (attempted {args[1][0]}).")

    sys.addaudithook(audit)


def _process_guard_refuses() -> bool:
    """Self-test with harmless probes: a non-existent name in the real store, a read-only
    SQLite URI, and an unroutable documentation-range address (TEST-NET-1)."""
    import socket
    import sqlite3

    probes = (
        lambda: open(REAL_RESUMES / "e2e-guard-probe-does-not-exist.pdf", "rb"),
        lambda: os.listdir(REAL_RESUMES),
        lambda: sqlite3.connect(f"file:{REAL_DB.as_posix()}?mode=ro", uri=True),
        lambda: socket.create_connection(("192.0.2.1", 9), timeout=1),
    )
    for probe in probes:
        try:
            probe()
        except RuntimeError:
            continue
        except OSError:
            return False
        return False
    return True


def _reset_data_dir() -> None:
    resolved = DATA_DIR.resolve()
    # Never delete anything outside the suite's own scratch directory.
    if TMP_ROOT.resolve() not in resolved.parents:
        sys.exit(f"Refusing to reset {resolved}: not inside {TMP_ROOT.resolve()}")
    if resolved.exists():
        shutil.rmtree(resolved)
    resolved.mkdir(parents=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8100)
    parser.add_argument("--frontend-url", default="http://localhost:5174")
    args = parser.parse_args()

    _reset_data_dir()
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from make_synthetic_resume import MARKETING_LINES, build

    build(DATA_DIR / "fixtures" / "synthetic-resume.docx")
    build(DATA_DIR / "fixtures" / "synthetic-resume-marketing.docx", MARKETING_LINES)
    database_path = (DATA_DIR / "e2e.db").resolve()
    os.environ.update({
        "DATABASE_URL": f"sqlite:///{database_path.as_posix()}",
        "RESUME_STORAGE_DIR": str(DATA_DIR / "resumes"),
        "LLM_PROVIDER": "none",
        "LLM_MODEL": "",
        "LLM_BASE_URL": "",
        "LLM_API_KEY": "",
        "EMBEDDING_ALLOW_DOWNLOAD": "false",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "APP_ENV": "development",
        "FRONTEND_URL": args.frontend_url,
    })

    _install_process_guard()
    os.chdir(BACKEND_ROOT)
    sys.path.insert(0, str(BACKEND_ROOT))
    from app.core.config import get_settings, resolve_backend_path
    from app.core.database import engine
    from app.services.llm_provider import NullLLMProvider, get_llm_provider

    settings = get_settings()
    effective_db = Path(engine.url.database).resolve()
    effective_resumes = resolve_backend_path(settings.resume_storage_dir)
    checks = {
        "database_is_isolated": effective_db == database_path and effective_db != REAL_DB,
        "resume_store_is_isolated": effective_resumes != REAL_RESUMES and DATA_DIR.resolve() in effective_resumes.parents,
        "llm_provider_is_null": settings.llm_provider == "none" and isinstance(get_llm_provider(settings), NullLLMProvider),
        "embedding_download_disabled": settings.embedding_allow_download is False and os.environ.get("HF_HUB_OFFLINE") == "1",
        "process_guard_refuses_real_data_and_network": _process_guard_refuses(),
    }
    report = {"database_path": str(effective_db), "resume_storage_dir": str(effective_resumes), "checks": checks}
    (TMP_ROOT / "isolation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"e2e backend isolation: {json.dumps(checks)}", flush=True)
    if not all(checks.values()):
        sys.exit("e2e backend isolation check failed; refusing to start.")

    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
