"""Suite-wide guard: no test may reach a live LLM provider.

`backend/.env` may hold a real provider key for manual validation, and
`get_settings()` reads it, so any test that generates content without passing an
explicit `llm_provider` would otherwise make real, billed calls. Every module that
binds its own `get_llm_provider` name (via `from ... import`) is patched to return
`NullLLMProvider`, i.e. the deterministic fallback path. Tests that need specific
LLM behaviour keep passing their own fake provider explicitly, which bypasses
`get_llm_provider` entirely.
"""

import pytest

import app.api.interview_prep as interview_prep_api
import app.services.assistant_service as assistant_service
import app.services.interview_prep_service as interview_prep_service
import app.services.resume_customization_service as resume_customization_service
from app.services.llm_provider import NullLLMProvider

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
