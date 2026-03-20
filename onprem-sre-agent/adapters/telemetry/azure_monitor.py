from __future__ import annotations


class AzureMonitorClient:
    async def query_metrics(self, resource_id: str, metric_name: str) -> dict[str, str]:
        return {"resource_id": resource_id, "metric": metric_name, "status": "ok"}
