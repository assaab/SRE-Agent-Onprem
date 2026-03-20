from __future__ import annotations

import json


class StubTelemetryCollectors:
    """Deterministic stub metrics and logs for tests and offline dev."""

    async def query_metrics(self, service: str, resource: str) -> str:
        payload = {
            "service": service,
            "resource": resource,
            "cpu_percent": 92,
            "error_rate_percent": 8,
            "window_minutes": 5,
        }
        return json.dumps(payload, sort_keys=True)

    async def query_logs(self, service: str, resource: str) -> str:
        payload = {
            "service": service,
            "resource": resource,
            "log_pattern": "error_spike",
            "count": 124,
            "window_minutes": 5,
        }
        return json.dumps(payload, sort_keys=True)

    async def query_topology(self, service: str, resource: str) -> str:
        payload = {
            "service": service,
            "resource": resource,
            "edges": 3,
            "stub": True,
        }
        return json.dumps(payload, sort_keys=True)
