from __future__ import annotations

from typing import Protocol, runtime_checkable

from adapters.telemetry.stub import StubTelemetryCollectors
from libs.agent_runtime.settings import get_agent_runtime_settings


@runtime_checkable
class TelemetryCollectorsProtocol(Protocol):
    async def query_metrics(self, service: str, resource: str) -> str: ...

    async def query_logs(self, service: str, resource: str) -> str: ...

    async def query_topology(self, service: str, resource: str) -> str: ...


def get_telemetry_collectors() -> TelemetryCollectorsProtocol:
    s = get_agent_runtime_settings()
    if s.telemetry_adapter == "stub":
        return StubTelemetryCollectors()
    return StubTelemetryCollectors()
