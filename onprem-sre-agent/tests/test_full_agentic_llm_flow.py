"""
End-to-end flow: ingest -> POST /route -> POST /plan with live LLMs only (no stub fallback).

Requires LLM credentials: set LLM_API_KEY (and AGENTIC_ENABLED=true) in environment or repo `.env`.
Skip if missing. Run explicitly: pytest tests/test_full_agentic_llm_flow.py -v
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from libs.agent_runtime.llm import OpenAICompatibleClient, clear_llm_client_cache
from libs.agent_runtime.settings import clear_agent_runtime_settings_cache, get_agent_runtime_settings
from services.approval_api.app import app as approval_app
from services.ingress.app import app as ingress_app
from services.router.app import app as router_app
from tests.conftest import load_dotenv_into_os_environ


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _credentials_available() -> bool:
    load_dotenv_into_os_environ(_repo_root() / ".env", override=False)
    clear_agent_runtime_settings_cache()
    clear_llm_client_cache()

    s = get_agent_runtime_settings()
    return bool(s.llm_api_key) and s.agentic_enabled


@pytest.mark.integration
def test_full_flow_ingest_route_plan_uses_llm_only(monkeypatch: pytest.MonkeyPatch) -> None:
    if not _credentials_available():
        pytest.skip("Set LLM_API_KEY and AGENTIC_ENABLED=true in .env (or environment)")

    load_dotenv_into_os_environ(_repo_root() / ".env", override=False)
    monkeypatch.setenv("AGENTIC_ENABLED", "true")
    monkeypatch.setenv("AGENTIC_STUB_FALLBACK", "false")
    clear_agent_runtime_settings_cache()
    clear_llm_client_cache()

    assert get_agent_runtime_settings().agentic_enabled is True
    assert get_agent_runtime_settings().agentic_stub_fallback is False

    llm_http_posts: list[object] = []
    original_post = OpenAICompatibleClient._post

    async def counting_post(
        self: OpenAICompatibleClient,
        url: str,
        headers: dict[str, str],
        payload: dict[str, object],
    ) -> tuple[str, int]:
        llm_http_posts.append(payload)
        return await original_post(self, url, headers, payload)

    monkeypatch.setattr(OpenAICompatibleClient, "_post", counting_post)
    clear_llm_client_cache()

    async def run_flow() -> None:
        ingress_transport = ASGITransport(app=ingress_app)
        router_transport = ASGITransport(app=router_app)
        approval_transport = ASGITransport(app=approval_app)
        token = uuid4().hex[:8]
        symptom = f"cpu spike and error spike on checkout ({token})"

        async with AsyncClient(transport=ingress_transport, base_url="http://test") as ingress_client:
            ingest_response = await ingress_client.post(
                "/ingest",
                json={
                    "source": "webhook",
                    "severity": "critical",
                    "service": "checkout-api",
                    "resource": "k8s-checkout",
                    "symptom": symptom,
                },
            )
        assert ingest_response.status_code == 200
        incident = ingest_response.json()
        incident_id = incident["incident_id"]

        route_posts_before = len(llm_http_posts)
        async with AsyncClient(transport=router_transport, base_url="http://test") as router_client:
            route_response = await router_client.post(f"/route/{incident_id}")
        assert route_response.status_code == 200
        routed = route_response.json()
        route_llm_calls = len(llm_http_posts) - route_posts_before
        assert route_llm_calls >= 4, "expected triage, evidence, change_correlation, rca LLM calls"

        hypotheses = routed.get("hypotheses") or []
        assert len(hypotheses) >= 1
        triage_blocks = [h for h in hypotheses if "triage" in h]
        assert triage_blocks, "triage agent output missing from incident"

        evidence = routed.get("evidence") or []
        assert len(evidence) >= 1

        plan_posts_before = len(llm_http_posts)
        async with AsyncClient(transport=router_transport, base_url="http://test") as router_client:
            plan_response = await router_client.post(f"/plan/{incident_id}")
        assert plan_response.status_code == 200
        graph = plan_response.json()
        plan_llm_calls = len(llm_http_posts) - plan_posts_before
        assert plan_llm_calls >= 1, "expected planner LLM call"
        assert graph.get("actions"), "planner produced no actions"

        async with AsyncClient(transport=approval_transport, base_url="http://test") as approval_client:
            approval_response = await approval_client.post(
                f"/incidents/{incident_id}/approvals",
                json={
                    "approver": "oncall@example.local",
                    "action_id": graph["actions"][0]["action_id"],
                    "approved": True,
                    "reason": "validated",
                },
            )
        assert approval_response.status_code == 200
        approval_id = approval_response.json()["approval"]["approval_id"]

        async with AsyncClient(transport=router_transport, base_url="http://test") as router_client:
            execute_response = await router_client.post(
                f"/execute/{incident_id}",
                json={
                    "action": graph["actions"][0],
                    "autonomous": False,
                    "approval_id": approval_id,
                },
            )
        assert execute_response.status_code == 200
        body = execute_response.json()
        assert body["result"]["success"] is True

        assert len(llm_http_posts) >= 5

    asyncio.run(run_flow())
