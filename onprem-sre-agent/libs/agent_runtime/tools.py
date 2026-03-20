"""Read-only tool helpers for agentic flows (metrics, logs, deploy history)."""

from __future__ import annotations

from adapters.actions.change_feed import get_change_feed_client
from adapters.telemetry.factory import get_telemetry_collectors


async def tool_query_metrics(service: str, resource: str) -> str:
    return await get_telemetry_collectors().query_metrics(service, resource)


async def tool_query_logs(service: str, resource: str) -> str:
    return await get_telemetry_collectors().query_logs(service, resource)


async def tool_recent_deployments(service: str) -> str:
    return await get_change_feed_client().get_recent_deployments(service)


async def tool_query_topology(service: str, resource: str) -> str:
    """Stub topology snapshot for on-prem evidence collection."""
    return await get_telemetry_collectors().query_topology(service, resource)
