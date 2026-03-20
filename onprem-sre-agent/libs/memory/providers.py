from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, cast

import redis.asyncio as redis


class MemoryProvider:
    async def index(self, namespace: str, key: str, text: str) -> None:
        raise NotImplementedError

    async def search(self, namespace: str, query: str, limit: int = 5) -> list[str]:
        raise NotImplementedError


@dataclass
class InMemoryKnowledgeProvider(MemoryProvider):
    store: dict[str, dict[str, str]] = field(default_factory=dict)

    async def index(self, namespace: str, key: str, text: str) -> None:
        if namespace not in self.store:
            self.store[namespace] = {}
        self.store[namespace][key] = text

    async def search(self, namespace: str, query: str, limit: int = 5) -> list[str]:
        values = self.store.get(namespace, {})
        query_text = query.lower()
        ranked = [
            content
            for _, content in sorted(
                values.items(),
                key=lambda item: query_text in item[1].lower(),
                reverse=True,
            )
        ]
        return ranked[:limit]


class RedisHotStateProvider:
    def __init__(self) -> None:
        self._url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self._client: Any = redis.from_url(self._url, decode_responses=True)  # type: ignore[no-untyped-call]
        self._fallback: dict[str, str] = {}

    async def set_if_absent(self, key: str, value: str, expire_seconds: int) -> bool:
        try:
            return bool(await self._client.set(key, value, ex=expire_seconds, nx=True))
        except Exception:
            if key in self._fallback:
                return False
            self._fallback[key] = value
            return True

    async def get(self, key: str) -> str | None:
        try:
            return cast(str | None, await self._client.get(key))
        except Exception:
            return self._fallback.get(key)

    async def set_json(self, key: str, value: dict[str, object], expire_seconds: int | None = None) -> None:
        payload = json.dumps(value, default=str)
        try:
            await self._client.set(key, payload, ex=expire_seconds)
        except Exception:
            self._fallback[key] = payload

    async def get_json(self, key: str) -> dict[str, object] | None:
        payload = await self.get(key)
        if payload is None:
            return None
        decoded = json.loads(payload)
        if isinstance(decoded, dict):
            return cast(dict[str, object], decoded)
        return None

    async def acquire_lock(self, key: str, token: str, expire_seconds: int = 30) -> bool:
        return await self.set_if_absent(key, token, expire_seconds)

    async def release_lock(self, key: str, token: str) -> bool:
        try:
            current = await self._client.get(key)
            if current == token:
                await self._client.delete(key)
                return True
            return False
        except Exception:
            current = self._fallback.get(key)
            if current == token:
                del self._fallback[key]
                return True
            return False
