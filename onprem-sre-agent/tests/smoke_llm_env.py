"""Optional live LLM smoke (no secrets printed). Run from repo root: python scripts/smoke_llm_env.py"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Ensure repo root on path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import BaseModel

from libs.agent_runtime.llm import clear_llm_client_cache, get_llm_client
from libs.agent_runtime.settings import clear_agent_runtime_settings_cache, get_agent_runtime_settings


class PingOut(BaseModel):
    ok: bool


async def main() -> None:
    clear_agent_runtime_settings_cache()
    clear_llm_client_cache()
    s = get_agent_runtime_settings()
    print("AGENTIC_ENABLED:", s.agentic_enabled)
    print("LLM_BASE_URL:", s.llm_base_url)
    print("LLM_MODEL:", s.llm_model)
    print("LLM_API_KEY set:", bool(s.llm_api_key))
    if not s.agentic_enabled:
        print("Live LLM smoke: SKIPPED (set AGENTIC_ENABLED=true in .env)")
        return
    if not s.llm_api_key:
        print("Live LLM smoke: SKIPPED (no LLM_API_KEY)")
        return
    c = get_llm_client()
    out = await c.complete_json(
        system='Reply with JSON only: {"ok": true}',
        user="ping",
        response_model=PingOut,
        agent_name="smoke-test",
    )
    print("Live LLM smoke: OK", out.model_dump())


if __name__ == "__main__":
    asyncio.run(main())
