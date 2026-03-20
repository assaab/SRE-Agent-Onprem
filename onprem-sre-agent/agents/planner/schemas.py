from __future__ import annotations

from pydantic import BaseModel, Field


class PlannerLLMOutput(BaseModel):
    objective: str = ""
    prerequisites: list[str] = Field(default_factory=list)
    safety_checks: list[str] = Field(default_factory=list)
    rollback_plan: list[str] = Field(default_factory=list)
    blast_radius: str = "single service"
    success_signal: str = ""
    action_type_names: list[str] = Field(default_factory=list)
    planner_confidence: float = Field(ge=0.0, le=1.0, default=0.85)
