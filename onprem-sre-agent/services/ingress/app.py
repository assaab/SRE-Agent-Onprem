from __future__ import annotations

from typing import Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from libs.contracts.models import IncidentRecord
from libs.memory import RedisHotStateProvider
from libs.observability import get_logger, instrument_fastapi, set_request_id
from services.incident_store.repository import repository
from services.ingress.normalizer import normalize

app = FastAPI(title="ingress")
instrument_fastapi(app)
logger = get_logger("ingress-service")
hot_state = RedisHotStateProvider()


class IngestPayload(BaseModel):
    source: str = "webhook"
    severity: str = "warning"
    service: str = Field(min_length=1)
    resource: str = Field(min_length=1)
    symptom: str = Field(min_length=1)
    raw_payload_ref: Optional[str] = None


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/ingest", response_model=IncidentRecord)
async def ingest(payload: IngestPayload, request: Request) -> IncidentRecord:
    request_id = request.headers.get("x-request-id", str(uuid4()))
    set_request_id(request_id)
    incident = normalize(payload.model_dump(exclude_none=True))
    dedupe_lock_key = f"dedupe:{incident.metadata.dedupe_key}"
    first_seen = await hot_state.set_if_absent(dedupe_lock_key, incident.incident_id, expire_seconds=300)
    if not first_seen:
        existing = await repository.get_by_dedupe_key(incident.metadata.dedupe_key)
        if existing is None:
            raise HTTPException(status_code=409, detail="duplicate incident")
        logger.info("incident_deduplicated", incident_id=existing.incident_id, dedupe_key=incident.metadata.dedupe_key)
        return existing
    logger.info("incident_ingested", incident_id=incident.incident_id, dedupe_key=incident.metadata.dedupe_key)
    return await repository.upsert(incident)
