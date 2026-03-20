from __future__ import annotations

from pydantic import BaseModel, Field


class ChangeCorrelationLLMOutput(BaseModel):
    summary: str
    confidence: float = Field(ge=0.0, le=1.0)
    kind: str = "deployment-history"
