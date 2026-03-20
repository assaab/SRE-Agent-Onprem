from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentRuntimeSettings(BaseSettings):
    """Configuration for agentic LLM and tool behavior (on-prem friendly)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    agentic_enabled: bool = Field(default=False, alias="AGENTIC_ENABLED")
    agentic_stub_fallback: bool = Field(
        default=True,
        alias="AGENTIC_STUB_FALLBACK",
        description="When false and AGENTIC_ENABLED=true, LLM failures do not fall back to static stub logic.",
    )
    llm_base_url: str = Field(default="https://api.openai.com/v1", alias="LLM_BASE_URL")
    llm_model: str = Field(default="gpt-4o-mini", alias="LLM_MODEL")
    llm_api_key: str = Field(default="", alias="LLM_API_KEY")
    llm_timeout_seconds: float = Field(default=60.0, alias="LLM_TIMEOUT_SECONDS")
    llm_max_tokens: int = Field(default=2048, alias="LLM_MAX_TOKENS")
    llm_max_calls_per_route: int = Field(default=20, alias="LLM_MAX_CALLS_PER_ROUTE")
    llm_max_tokens_per_route: int = Field(default=100000, alias="LLM_MAX_TOKENS_PER_ROUTE")
    telemetry_adapter: str = Field(default="stub", alias="TELEMETRY_ADAPTER")
    change_feed_adapter: str = Field(default="stub", alias="CHANGE_FEED_ADAPTER")
    sandbox_enabled: bool = Field(default=False, alias="SANDBOX_ENABLED")


@lru_cache
def get_agent_runtime_settings() -> AgentRuntimeSettings:
    return AgentRuntimeSettings()


def clear_agent_runtime_settings_cache() -> None:
    get_agent_runtime_settings.cache_clear()
