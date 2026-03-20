from __future__ import annotations

import asyncio

from httpx import ASGITransport, AsyncClient

from services.approval_api.app import app as approval_app
from services.ingress.app import app as ingress_app
from services.router.app import app as router_app


def test_ingest_route_plan_approve_execute_flow() -> None:
    async def run_flow() -> None:
        ingress_transport = ASGITransport(app=ingress_app)
        router_transport = ASGITransport(app=router_app)
        approval_transport = ASGITransport(app=approval_app)

        async with AsyncClient(transport=ingress_transport, base_url="http://test") as ingress_client:
            ingest_response = await ingress_client.post(
                "/ingest",
                json={
                    "source": "webhook",
                    "severity": "critical",
                    "service": "checkout-api",
                    "resource": "k8s-checkout",
                    "symptom": "cpu spike and error spike",
                },
            )
        assert ingest_response.status_code == 200
        incident = ingest_response.json()
        incident_id = incident["incident_id"]

        async with AsyncClient(transport=router_transport, base_url="http://test") as router_client:
            route_response = await router_client.post(f"/route/{incident_id}")
            assert route_response.status_code == 200

            plan_response = await router_client.post(f"/plan/{incident_id}")
            assert plan_response.status_code == 200
            graph = plan_response.json()
            action = graph["actions"][0]

        async with AsyncClient(transport=approval_transport, base_url="http://test") as approval_client:
            approval_response = await approval_client.post(
                f"/incidents/{incident_id}/approvals",
                json={
                    "approver": "oncall@example.local",
                    "action_id": action["action_id"],
                    "approved": True,
                    "reason": "validated runbook",
                },
            )
        assert approval_response.status_code == 200
        approval_id = approval_response.json()["approval"]["approval_id"]

        async with AsyncClient(transport=router_transport, base_url="http://test") as router_client:
            execute_response = await router_client.post(
                f"/execute/{incident_id}",
                json={
                    "action": action,
                    "autonomous": False,
                    "approval_id": approval_id,
                },
            )
        assert execute_response.status_code == 200
        body = execute_response.json()
        assert body["result"]["success"] is True

    asyncio.run(run_flow())
