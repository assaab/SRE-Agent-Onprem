from __future__ import annotations

from pydantic import BaseModel, Field


class RCAHypothesisItem(BaseModel):
    hypothesis: str
    confidence: float = Field(ge=0.0, le=1.0)
    supporting_evidence_ids: list[str] = Field(default_factory=list)


class RCALLMOutput(BaseModel):
    hypotheses: list[RCAHypothesisItem] = Field(default_factory=list)
