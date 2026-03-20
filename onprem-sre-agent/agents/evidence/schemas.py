from __future__ import annotations

from pydantic import BaseModel, Field


class EvidenceLLMItem(BaseModel):
    source: str
    kind: str
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str


class EvidenceLLMOutput(BaseModel):
    entries: list[EvidenceLLMItem] = Field(default_factory=list)
