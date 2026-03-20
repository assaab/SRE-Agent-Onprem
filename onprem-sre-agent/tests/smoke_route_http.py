"""HTTP smoke: ingest + route (requires services on 8001/8003)."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def main() -> None:
    payload = {
        "source": "smoke",
        "severity": "warning",
        "service": "test-svc",
        "resource": f"pod/smoke-{Path(__file__).stem}",
        "symptom": "cpu high for automated test",
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post("http://127.0.0.1:8001/ingest", json=payload)
        r.raise_for_status()
        inc = r.json()
        iid = inc["incident_id"]
        print("Ingested:", iid)
        r2 = await client.post(f"http://127.0.0.1:8003/route/{iid}")
        r2.raise_for_status()
        out = r2.json()
        print("Routed state:", out.get("state"), "plan:", out.get("response_plan", {}).get("plan_id"))


if __name__ == "__main__":
    asyncio.run(main())
