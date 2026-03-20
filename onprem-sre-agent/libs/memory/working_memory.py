from __future__ import annotations

import os
from uuid import uuid4

from libs.memory.providers import InMemoryKnowledgeProvider, RedisHotStateProvider

_wm_provider = InMemoryKnowledgeProvider()
_redis = RedisHotStateProvider()
_enabled = os.getenv("WORKING_MEMORY_ENABLED", "true").lower() == "true"


async def index_incident_snippet(incident_id: str, text: str) -> None:
    if not _enabled or not text.strip():
        return
    key = f"wm:{incident_id}"
    await _wm_provider.index("incidents", key, text)
    await _redis.set_json(
        f"{key}:evt:{uuid4().hex[:8]}",
        {"incident_id": incident_id, "text": text},
        expire_seconds=86400,
    )


async def search_incident_memory(incident_id: str, query: str, limit: int = 5) -> list[str]:
    if not _enabled:
        return []
    return await _wm_provider.search("incidents", f"{incident_id} {query}", limit=limit)
