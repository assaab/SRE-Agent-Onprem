from __future__ import annotations

import json


class AzureMonitorAdapter:
    async def query(self, resource: str, metric: str) -> str:
        return json.dumps({"provider": "azure-monitor", "resource": resource, "metric": metric}, sort_keys=True)


class PrometheusAdapter:
    async def query(self, promql: str) -> str:
        return json.dumps({"provider": "prometheus", "query": promql}, sort_keys=True)


class GrafanaAdapter:
    async def query_dashboard(self, dashboard_uid: str) -> str:
        return json.dumps({"provider": "grafana", "dashboard_uid": dashboard_uid}, sort_keys=True)


class ELKAdapter:
    async def search(self, index: str, expression: str) -> str:
        return json.dumps({"provider": "elk", "index": index, "expression": expression}, sort_keys=True)


class SplunkAdapter:
    async def search(self, query: str) -> str:
        return json.dumps({"provider": "splunk", "query": query}, sort_keys=True)
