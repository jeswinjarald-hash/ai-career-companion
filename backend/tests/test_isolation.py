"""Guards the suite-wide isolation set up in conftest.py: tests must never open the
real application database or resume store, never resolve a live LLM provider from
`backend/.env`, never download a model, and never reach the network.

The negative tests below only *attempt* access in ways that would be harmless even if
the guard failed (a non-existent file name, a read-only SQLite URI, an unroutable
documentation-range address) — and assert the guard refuses before anything happens."""

import os
import socket
import sqlite3
from pathlib import Path

import pytest

from app.core.config import get_settings, resolve_backend_path
from app.core.database import engine
from app.services.llm_provider import NullLLMProvider, get_llm_provider
from conftest import ProtectedResourceError

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REAL_DB = (BACKEND_ROOT / "data" / "ai_career_companion.db").resolve()
REAL_STORE = (BACKEND_ROOT / "data" / "resumes").resolve()


def test_engine_does_not_target_the_real_database() -> None:
    test_db = Path(engine.url.database).resolve()
    assert test_db != REAL_DB
    assert BACKEND_ROOT / "data" not in test_db.parents


def test_resume_storage_is_not_the_real_store() -> None:
    storage = resolve_backend_path(get_settings().resume_storage_dir)
    assert storage != REAL_STORE


def test_settings_resolve_no_live_llm_provider() -> None:
    # The unpatched factory, read from settings alone — not the conftest monkeypatch.
    assert get_settings().llm_provider == "none"
    assert isinstance(get_llm_provider(get_settings()), NullLLMProvider)


def test_model_downloads_are_disabled() -> None:
    assert get_settings().embedding_allow_download is False
    assert os.environ["HF_HUB_OFFLINE"] == "1"
    assert os.environ["TRANSFORMERS_OFFLINE"] == "1"


def test_reading_the_real_resume_store_is_refused() -> None:
    with pytest.raises(ProtectedResourceError):
        (REAL_STORE / "isolation-probe-does-not-exist.pdf").read_bytes()
    with pytest.raises(ProtectedResourceError):
        os.listdir(REAL_STORE)
    if REAL_STORE.is_dir():
        with pytest.raises(ProtectedResourceError):
            list(REAL_STORE.glob("*.pdf"))
    else:
        # Path.glob checks is_dir() (a plain stat, no audit event) before scanning, so on
        # a machine without a resume store there is nothing to refuse — and nothing to read.
        assert list(REAL_STORE.glob("*.pdf")) == []


def test_opening_the_real_database_is_refused() -> None:
    with pytest.raises(ProtectedResourceError):
        sqlite3.connect(f"file:{REAL_DB.as_posix()}?mode=ro", uri=True)
    with pytest.raises(ProtectedResourceError):
        open(REAL_DB, "rb")  # noqa: SIM115 - refused before the file is opened


def test_non_loopback_network_connections_are_refused() -> None:
    with pytest.raises(ProtectedResourceError):
        socket.create_connection(("192.0.2.1", 9), timeout=1)  # TEST-NET-1, never routable


def test_loopback_connections_remain_allowed() -> None:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    try:
        socket.create_connection(listener.getsockname(), timeout=1).close()
    finally:
        listener.close()
