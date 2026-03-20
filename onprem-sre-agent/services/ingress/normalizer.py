from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Optional
from uuid import uuid4

from libs.contracts.models import IncidentEnvelope, IncidentRecord

SEVERITY_MAP = {
    "critical": "sev1",
    "high": "sev2",
    "warning": "sev3",
    "info": "sev4",
}


KNOWN_SOURCES = {
    "webhook",
    "azure-monitor",
    "azure-arc",
    "prometheus",
    "grafana",
    "elk",
    "splunk",
    "servicenow",
    "pagerduty",
}


def _canonical_source(raw_source: Optional[str]) -> str:
    source = (raw_source or "webhook").strip().lower()
    if source not in KNOWN_SOURCES:
        return "webhook"
    return source


def _dedupe_key(source: str, service: str, resource: str, symptom: str) -> str:
    canonical = f"{source}:{service}:{resource}:{symptom.strip().lower()}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def normalize(payload: dict[str, str]) -> IncidentRecord:
    source = payload.get("source", "webhook")
    canonical_source = _canonical_source(source)
    service = payload.get("service", "unknown-service").strip().lower()
    resource = payload.get("resource", "unknown-resource").strip().lower()
    symptom = payload.get("symptom", "unspecified symptom").strip()
    severity_raw = payload.get("severity", "warning").lower()
    severity = SEVERITY_MAP.get(severity_raw, "sev3")
    dedupe_key = _dedupe_key(canonical_source, service, resource, symptom)

    envelope = IncidentEnvelope(
        source=canonical_source,
        severity=severity,
        service=service,
        resource=resource,
        symptom=symptom,
        occurred_at=datetime.utcnow(),
        dedupe_key=dedupe_key,
        raw_payload_ref=payload.get("raw_payload_ref"),
    )
    incident_id = f"inc_{uuid4().hex[:12]}"
    return IncidentRecord(incident_id=incident_id, metadata=envelope)
