from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from libs.observability.logging import get_logger


class AuditStore:
    def __init__(self) -> None:
        self._logger = get_logger("audit-store")
        self._dsn = os.getenv(
            "POSTGRES_DSN",
            "postgresql+asyncpg://postgres:postgres@localhost:5432/sre_agent",
        )
        self._engine: Optional[AsyncEngine] = None
        self._schema_ready = False
        self._fallback_mode = False
        self._fallback_events: list[dict[str, Any]] = []

    async def _ensure_schema(self) -> None:
        if self._schema_ready:
            return
        if self._engine is None:
            try:
                self._engine = create_async_engine(self._dsn, pool_pre_ping=True)
            except Exception:
                self._fallback_mode = True
                self._schema_ready = True
                self._logger.warning("audit_store_fallback_mode_enabled")
                return
        try:
            assert self._engine is not None
            async with self._engine.begin() as connection:
                await connection.execute(
                    text(
                        """
                        CREATE TABLE IF NOT EXISTS audit_events (
                            event_id BIGSERIAL PRIMARY KEY,
                            event_type TEXT NOT NULL,
                            payload JSONB NOT NULL,
                            created_at TIMESTAMP NOT NULL
                        );
                        """
                    )
                )
                await connection.execute(
                    text(
                        """
                        CREATE INDEX IF NOT EXISTS idx_audit_events_created_at
                        ON audit_events (created_at DESC);
                        """
                    )
                )
            self._schema_ready = True
        except Exception:
            self._fallback_mode = True
            self._schema_ready = True
            self._logger.warning("audit_store_fallback_mode_enabled")

    async def append(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        await self._ensure_schema()
        event = {
            "event_type": event_type,
            "payload": payload,
            "created_at": datetime.utcnow().isoformat(),
        }
        if self._fallback_mode:
            self._fallback_events.append(event)
            return event
        assert self._engine is not None
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO audit_events (event_type, payload, created_at)
                    VALUES (:event_type, CAST(:payload AS JSONB), :created_at);
                    """
                ),
                {
                    "event_type": event_type,
                    "payload": json.dumps(payload, default=str),
                    "created_at": datetime.utcnow(),
                },
            )
        self._logger.info("audit_event_appended", event_type=event_type)
        return event

    async def list_events(self, limit: int = 200) -> list[dict[str, Any]]:
        await self._ensure_schema()
        if self._fallback_mode:
            return list(reversed(self._fallback_events[-limit:]))
        assert self._engine is not None
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        """
                        SELECT event_type, payload, created_at
                        FROM audit_events
                        ORDER BY created_at DESC
                        LIMIT :limit;
                        """
                    ),
                    {"limit": limit},
                )
            ).mappings().all()
        return [
            {
                "event_type": row["event_type"],
                "payload": row["payload"],
                "created_at": row["created_at"].isoformat(),
            }
            for row in rows
        ]


audit_store = AuditStore()
