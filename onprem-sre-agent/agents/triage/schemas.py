from __future__ import annotations

from pydantic import BaseModel, Field


class TriageLLMOutput(BaseModel):
    incident_type: str = Field(description="Short category, e.g. performance, availability")
    priority: str = Field(description="p1 or p2 style priority")
    probable_domains: list[str] = Field(default_factory=list)
    next_required_evidence: list[str] = Field(default_factory=list)
