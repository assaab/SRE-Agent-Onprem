from __future__ import annotations

import os
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from libs.observability import instrument_fastapi, set_request_id
from services.audit.store import audit_store

app = FastAPI(title="audit")
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


class AuditEventPayload(BaseModel):
    event_type: str
    payload: dict[str, object]


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/events")
async def append_event(event: AuditEventPayload, request: Request) -> dict[str, object]:
    set_request_id(request.headers.get("x-request-id", str(uuid4())))
    return await audit_store.append(event.event_type, event.payload)


@app.get("/events")
async def list_events(request: Request, response: Response, limit: int = 200) -> list[dict[str, object]]:
    _apply_cors_response_headers(request, response)
    set_request_id(request.headers.get("x-request-id", str(uuid4())))
    return await audit_store.list_events(limit)
