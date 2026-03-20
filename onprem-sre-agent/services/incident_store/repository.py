from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from libs.contracts.models import IncidentRecord
from libs.observability.logging import get_logger


class IncidentRepository:
    def __init__(self) -> None:
        self._logger = get_logger("incident-repository")
        self._dsn = os.getenv(
            "POSTGRES_DSN",
            "postgresql+asyncpg://postgres:postgres@localhost:5432/sre_agent",
        )
        self._engine: Optional[AsyncEngine] = None
        self._schema_ready = False
        self._fallback_mode = False
        self._fallback_store: dict[str, IncidentRecord] = {}
        self._allowed_transitions: dict[str, set[str]] = {
            "open": {"investigating", "reopened"},
            "investigating": {"planned", "waiting_approval", "executing", "resolved", "reopened"},
            "planned": {"waiting_approval", "executing", "resolved", "investigating"},
            "waiting_approval": {"planned", "executing", "investigating"},
            "executing": {"resolved", "investigating", "reopened"},
            "resolved": {"reopened", "investigating"},
            "reopened": {"investigating", "planned"},
        }

    async def _ensure_schema(self) -> None:
        if self._schema_ready:
            return
        if self._engine is None:
            try:
                self._engine = create_async_engine(self._dsn, pool_pre_ping=True)
            except Exception:
                self._fallback_mode = True
                self._schema_ready = True
                self._logger.warning("incident_repository_fallback_mode_enabled")
                return
        try:
            assert self._engine is not None
            async with self._engine.begin() as connection:
                await connection.execute(
                    text(
                        """
                        CREATE TABLE IF NOT EXISTS incidents (
                            incident_id TEXT PRIMARY KEY,
                            dedupe_key TEXT NOT NULL,
                            state TEXT NOT NULL,
                            version INTEGER NOT NULL,
                            updated_at TIMESTAMP NOT NULL,
                            payload JSONB NOT NULL
                        );
                        """
                    )
                )
                await connection.execute(
                    text(
                        """
                        CREATE INDEX IF NOT EXISTS idx_incidents_updated_at
                        ON incidents (updated_at DESC);
                        """
                    )
                )
                await connection.execute(
                    text(
                        """
                        CREATE INDEX IF NOT EXISTS idx_incidents_dedupe_key
                        ON incidents (dedupe_key);
                        """
                    )
                )
            self._schema_ready = True
        except Exception:
            self._fallback_mode = True
            self._schema_ready = True
            self._logger.warning("incident_repository_fallback_mode_enabled")

    def _validate_state_transition(
        self,
        previous: IncidentRecord | None,
        next_record: IncidentRecord,
    ) -> None:
        if previous is None:
            return
        previous_state = previous.state.value
        next_state = next_record.state.value
        if previous_state == next_state:
            return
        allowed = self._allowed_transitions.get(previous_state, set())
        if next_state not in allowed:
            raise ValueError(
                f"Invalid state transition from {previous_state} to {next_state} for {next_record.incident_id}"
            )

    async def upsert(self, incident: IncidentRecord) -> IncidentRecord:
        await self._ensure_schema()
        previous = await self.get(incident.incident_id)
        self._validate_state_transition(previous, incident)

        incident.updated_at = datetime.utcnow()
        if previous is not None:
            incident.version = previous.version + 1

        if self._fallback_mode:
            self._fallback_store[incident.incident_id] = incident
            return incident

        engine = self._engine
        assert engine is not None
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO incidents (incident_id, dedupe_key, state, version, updated_at, payload)
                    VALUES (:incident_id, :dedupe_key, :state, :version, :updated_at, CAST(:payload AS JSONB))
                    ON CONFLICT (incident_id)
                    DO UPDATE SET
                        dedupe_key = EXCLUDED.dedupe_key,
                        state = EXCLUDED.state,
                        version = EXCLUDED.version,
                        updated_at = EXCLUDED.updated_at,
                        payload = EXCLUDED.payload;
                    """
                ),
                {
                    "incident_id": incident.incident_id,
                    "dedupe_key": incident.metadata.dedupe_key,
                    "state": incident.state.value,
                    "version": incident.version,
                    "updated_at": incident.updated_at,
                    "payload": incident.model_dump_json(),
                },
            )
        self._logger.info(
            "incident_upserted",
            incident_id=incident.incident_id,
            state=incident.state.value,
            version=incident.version,
        )
        return incident

    async def get(self, incident_id: str) -> IncidentRecord | None:
        await self._ensure_schema()
        if self._fallback_mode:
            return self._fallback_store.get(incident_id)
        engine = self._engine
        assert engine is not None
        async with engine.connect() as connection:
            row = (
                await connection.execute(
                    text("SELECT payload FROM incidents WHERE incident_id = :incident_id"),
                    {"incident_id": incident_id},
                )
            ).mappings().first()
        if row is None:
            return None
        return IncidentRecord.model_validate(row["payload"])

    async def list_recent(self, limit: int = 50) -> list[IncidentRecord]:
        await self._ensure_schema()
        if self._fallback_mode:
            fallback_rows = sorted(self._fallback_store.values(), key=lambda item: item.updated_at, reverse=True)
            return fallback_rows[:limit]
        engine = self._engine
        assert engine is not None
        async with engine.connect() as connection:
            db_rows = (
                await connection.execute(
                    text(
                        """
                        SELECT payload
                        FROM incidents
                        ORDER BY updated_at DESC
                        LIMIT :limit;
                        """
                    ),
                    {"limit": limit},
                )
            ).mappings().all()
        return [IncidentRecord.model_validate(row["payload"]) for row in db_rows]

    async def get_by_dedupe_key(self, dedupe_key: str) -> IncidentRecord | None:
        await self._ensure_schema()
        if self._fallback_mode:
            matched = [row for row in self._fallback_store.values() if row.metadata.dedupe_key == dedupe_key]
            if not matched:
                return None
            return sorted(matched, key=lambda item: item.updated_at, reverse=True)[0]
        engine = self._engine
        assert engine is not None
        async with engine.connect() as connection:
            row = (
                await connection.execute(
                    text(
                        """
                        SELECT payload
                        FROM incidents
                        WHERE dedupe_key = :dedupe_key
                        ORDER BY updated_at DESC
                        LIMIT 1;
                        """
                    ),
                    {"dedupe_key": dedupe_key},
                )
            ).mappings().first()
        if row is None:
            return None
        return IncidentRecord.model_validate(row["payload"])


repository = IncidentRepository()
