"""Shared test helpers."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from libs.agent_runtime.llm import clear_llm_client_cache
from libs.agent_runtime.settings import clear_agent_runtime_settings_cache


@pytest.fixture(autouse=True)
def _disable_agentic_for_non_integration_tests(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep unit tests deterministic and offline when developers have AGENTIC_ENABLED=true in .env."""
    if request.node.get_closest_marker("integration"):
        yield
    else:
        monkeypatch.setenv("AGENTIC_ENABLED", "false")
        clear_agent_runtime_settings_cache()
        clear_llm_client_cache()
        yield


def load_dotenv_into_os_environ(env_path: Path, *, override: bool = False) -> None:
    """Minimal .env loader (no python-dotenv dependency). Skips comments and blank lines."""
    if not env_path.is_file():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key:
            continue
        if not override and key in os.environ and os.environ[key]:
            continue
        os.environ[key] = value
