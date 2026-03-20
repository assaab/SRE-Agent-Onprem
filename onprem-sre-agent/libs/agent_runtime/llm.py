from __future__ import annotations

import json
from functools import lru_cache
from typing import Any, Protocol, TypeVar

import httpx
import orjson
from pydantic import BaseModel, ValidationError

from libs.agent_runtime.budgets import get_llm_budget
from libs.agent_runtime.redaction import redact_for_logging
from libs.agent_runtime.settings import get_agent_runtime_settings

try:
    from opentelemetry import trace

    _tracer = trace.get_tracer("agent_runtime.llm", "0.1.0")
except Exception:  # pragma: no cover
    _tracer = None


class StructuredLLMError(RuntimeError):
    pass


T = TypeVar("T", bound=BaseModel)


def _is_openai_gpt5_family_model(model: str) -> bool:
    """GPT-5 models default chat reasoning to medium; temperature/top_p/logprobs require reasoning_effort=none."""
    return model.lower().startswith("gpt-5")


def _openai_host(base_url: str) -> bool:
    return "openai.com" in base_url.lower()


class LLMClient(Protocol):
    async def complete_json(
        self,
        *,
        system: str,
        user: str,
        response_model: type[T],
        agent_name: str,
    ) -> T:
        ...


class OpenAICompatibleClient:
    """OpenAI-compatible chat completions (vLLM, Ollama, Azure OpenAI with compat API)."""

    def __init__(self) -> None:
        self._settings = get_agent_runtime_settings()

    async def complete_json(
        self,
        *,
        system: str,
        user: str,
        response_model: type[T],
        agent_name: str,
    ) -> T:
        budget = get_llm_budget()
        url = self._settings.llm_base_url.rstrip("/") + "/chat/completions"
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._settings.llm_api_key:
            headers["Authorization"] = f"Bearer {self._settings.llm_api_key}"

        model = self._settings.llm_model
        base = self._settings.llm_base_url
        use_openai_gpt5 = _is_openai_gpt5_family_model(model) and _openai_host(base)
        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
        }
        if use_openai_gpt5:
            payload["max_completion_tokens"] = self._settings.llm_max_tokens
            payload["reasoning_effort"] = "none"
            payload["temperature"] = 0.2
        else:
            payload["max_tokens"] = self._settings.llm_max_tokens
            payload["temperature"] = 0.2

        span_attrs = {
            "agent.name": agent_name,
            "llm.model": self._settings.llm_model,
        }
        if _tracer is not None:
            with _tracer.start_as_current_span("llm.chat_completions", attributes=span_attrs):
                raw_text, usage_tokens = await self._post(url, headers, payload)
        else:
            raw_text, usage_tokens = await self._post(url, headers, payload)

        if budget is not None:
            budget.record_call(usage_tokens)

        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise StructuredLLMError(
                f"LLM returned non-JSON: {redact_for_logging(raw_text[:500])}"
            ) from exc

        try:
            return response_model.model_validate(data)
        except ValidationError as exc:
            raise StructuredLLMError(f"LLM JSON did not match schema: {exc}") from exc

    async def _post(self, url: str, headers: dict[str, str], payload: dict[str, Any]) -> tuple[str, int]:
        timeout = httpx.Timeout(self._settings.llm_timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, headers=headers, content=orjson.dumps(payload))
            if response.status_code == 400 and "response_format" in str(response.content):
                payload.pop("response_format", None)
                response = await client.post(url, headers=headers, content=orjson.dumps(payload))
            response.raise_for_status()
            body = response.json()
        choice0 = body.get("choices", [{}])[0]
        message = choice0.get("message", {})
        content = message.get("content", "")
        usage = body.get("usage") or {}
        total_tokens = int(usage.get("total_tokens") or usage.get("completion_tokens") or 0)
        return content if isinstance(content, str) else str(content), total_tokens


@lru_cache
def get_llm_client() -> OpenAICompatibleClient:
    return OpenAICompatibleClient()


def clear_llm_client_cache() -> None:
    get_llm_client.cache_clear()
