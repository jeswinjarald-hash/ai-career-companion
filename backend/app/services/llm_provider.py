"""Milestone 3.2 — LLM provider abstraction.

A small interface so the customization pipeline never depends on a specific vendor
SDK: `OpenAICompatibleProvider` speaks the OpenAI chat-completions wire format (JSON
mode) over plain `httpx`, which works against OpenAI itself, Azure OpenAI's
OpenAI-compatible surface, or a locally hosted server (Ollama, vLLM, LM Studio, ...)
via `LLM_BASE_URL` — no new SDK dependency. `NullLLMProvider` is used whenever no
provider is configured, and raises immediately rather than silently pretending to
generate anything, so the caller always explicitly falls back to the deterministic
pipeline instead of hanging or guessing.
"""

import json
import logging
from typing import Protocol

import httpx

from app.core.config import Settings

logger = logging.getLogger(__name__)


class LLMUnavailableError(Exception):
    """Raised whenever no usable LLM response was obtained — no provider configured,
    a network/timeout error, a non-2xx response, or a response that isn't valid JSON.
    Callers must treat this uniformly as "fall back to the deterministic pipeline",
    never as a hard failure of the customization request itself.
    """


class LLMProvider(Protocol):
    name: str
    model: str | None

    def generate_json(self, system_prompt: str, user_payload: dict) -> dict:
        """Returns a parsed JSON object, or raises `LLMUnavailableError`."""
        ...


class NullLLMProvider:
    """Used when `settings.llm_provider == "none"` (the default) — no live model is
    configured, so this provider is unavailable by definition. Never silently
    fabricates a response.
    """

    name = "none"
    model = None

    def generate_json(self, system_prompt: str, user_payload: dict) -> dict:
        raise LLMUnavailableError("No LLM provider is configured (LLM_PROVIDER=none).")


class OpenAICompatibleProvider:
    name = "openai_compatible"

    def __init__(self, base_url: str, api_key: str | None, model: str, timeout_seconds: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    def generate_json(self, system_prompt: str, user_payload: dict) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload)},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
        }
        try:
            response = httpx.post(f"{self.base_url}/chat/completions", json=body, headers=headers, timeout=self.timeout_seconds)
        except httpx.TimeoutException as exc:
            raise LLMUnavailableError(f"LLM request timed out after {self.timeout_seconds}s.") from exc
        except httpx.HTTPError as exc:
            raise LLMUnavailableError(f"LLM request failed: {exc}") from exc

        if response.status_code >= 400:
            logger.warning("llm_provider_http_error status=%s", response.status_code)
            raise LLMUnavailableError(f"LLM provider returned HTTP {response.status_code}.")

        try:
            body_json = response.json()
            content = body_json["choices"][0]["message"]["content"]
            return json.loads(content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise LLMUnavailableError(f"LLM response was not valid structured JSON: {exc}") from exc


def get_llm_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "openai_compatible" and settings.llm_base_url and settings.llm_model:
        return OpenAICompatibleProvider(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            timeout_seconds=settings.llm_timeout_seconds,
        )
    return NullLLMProvider()
