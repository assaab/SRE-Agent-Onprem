"""Compare triage stub output vs agentic LLM output for the same incident (live API when enabled)."""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.triage.agent import TriageAgent
from libs.agent_runtime.llm import clear_llm_client_cache
from libs.agent_runtime.settings import clear_agent_runtime_settings_cache, get_agent_runtime_settings
from libs.contracts.models import IncidentEnvelope, IncidentRecord


def _incident() -> IncidentRecord:
    # No "cpu" in symptom: stub -> incident_type general, probable_domains [application], priority p2 for severity critical
    envelope = IncidentEnvelope(
        source="alertmanager",
        severity="critical",
        service="checkout-api",
        resource="postgres-primary",
        symptom="database connection pool exhausted; timeouts to dependency inventory",
        occurred_at=datetime.utcnow(),
        dedupe_key="verify-llm-vs-stub-1",
    )
    return IncidentRecord(incident_id="verify-llm-1", metadata=envelope)


async def _run_with_agentic(enabled: bool) -> dict[str, object]:
    import os

    clear_agent_runtime_settings_cache()
    clear_llm_client_cache()
    os.environ["AGENTIC_ENABLED"] = "true" if enabled else "false"
    clear_agent_runtime_settings_cache()
    clear_llm_client_cache()
    agent = TriageAgent()
    return await agent.run(_incident())


async def main() -> None:
    clear_agent_runtime_settings_cache()
    clear_llm_client_cache()
    s = get_agent_runtime_settings()
    if not s.agentic_enabled or not s.llm_api_key:
        print("Set AGENTIC_ENABLED=true and LLM_API_KEY in .env first.")
        sys.exit(1)

    stub_out = await _run_with_agentic(False)
    llm_out = await _run_with_agentic(True)

    print("STUB (AGENTIC_ENABLED=false):")
    print(json.dumps(stub_out, indent=2))
    print()
    print("AGENTIC (AGENTIC_ENABLED=true, live LLM):")
    print(json.dumps(llm_out, indent=2))
    print()

    if stub_out == llm_out:
        print(
            "WARNING: Outputs are identical. Either the model matched the stub exactly, "
            "or the LLM call failed and triage fell back to the stub (check router logs for triage_llm_fallback)."
        )
        sys.exit(2)

    print("OK: LLM path produced different output than the static stub for this incident.")


if __name__ == "__main__":
    asyncio.run(main())
