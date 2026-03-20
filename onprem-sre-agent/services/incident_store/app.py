from __future__ import annotations

import os
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from libs.contracts.models import IncidentRecord
from libs.observability import instrument_fastapi, set_request_id
from services.incident_store.repository import repository

app = FastAPI(title="incident-store")
allowed_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:5173,http://localhost:5175").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
instrument_fastapi(app)


def _apply_cors_response_headers(request: Request, response: Response) -> None:
    origin = request.headers.get("origin")
    if origin and origin in allowed_origins:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/incidents", response_model=IncidentRecord)
async def upsert_incident(payload: IncidentRecord, request: Request) -> IncidentRecord:
    set_request_id(request.headers.get("x-request-id", str(uuid4())))
    return await repository.upsert(payload)


@app.get("/incidents/{incident_id}", response_model=IncidentRecord)
async def get_incident(incident_id: str, request: Request) -> IncidentRecord:
    set_request_id(request.headers.get("x-request-id", str(uuid4())))
    incident = await repository.get(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="incident not found")
    return incident


@app.get("/incidents", response_model=list[IncidentRecord])
async def list_incidents(request: Request, response: Response, limit: int = 50) -> list[IncidentRecord]:
    _apply_cors_response_headers(request, response)
    set_request_id(request.headers.get("x-request-id", str(uuid4())))
    return await repository.list_recent(limit=limit)
