from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from libs.contracts.models import ActionRequest, ActionType
from libs.security.context import SecurityContext


@dataclass
class AdapterResult:
    success: bool
    message: str
    details: dict[str, Any]


class RestartServiceParams(BaseModel):
    service: str = Field(min_length=1)


class ScaleWorkloadParams(BaseModel):
    service: str = Field(min_length=1)
    maxReplicas: int = Field(ge=1, le=20)


class RollbackDeploymentParams(BaseModel):
    deployment: str = Field(min_length=1)
    to_revision: str = Field(min_length=1)


class TypedActionAdapterRegistry:
    def __init__(self) -> None:
        self.supported_actions = {
            ActionType.QUERY_METRICS,
            ActionType.QUERY_LOGS,
            ActionType.GET_RECENT_DEPLOYMENTS,
            ActionType.GET_TOPOLOGY,
            ActionType.RESTART_SERVICE,
            ActionType.SCALE_WORKLOAD,
            ActionType.ROLLBACK_DEPLOYMENT,
            ActionType.DRAIN_NODE,
            ActionType.OPEN_TICKET,
            ActionType.PAGE_HUMAN,
            ActionType.RUN_ANSIBLE_JOB,
        }

    def _validate_parameters(self, action: ActionRequest) -> None:
        if action.action_type == ActionType.RESTART_SERVICE:
            RestartServiceParams.model_validate(action.parameters)
        elif action.action_type == ActionType.SCALE_WORKLOAD:
            ScaleWorkloadParams.model_validate(action.parameters)
        elif action.action_type == ActionType.ROLLBACK_DEPLOYMENT:
            RollbackDeploymentParams.model_validate(action.parameters)

    async def run(self, action: ActionRequest, context: SecurityContext) -> AdapterResult:
        if action.action_type not in self.supported_actions:
            return AdapterResult(False, f"Unsupported action type {action.action_type}", {})
        if not context.can_access_target(action.target):
            return AdapterResult(False, f"Target {action.target} is not allowlisted", {})
        try:
            self._validate_parameters(action)
        except ValidationError as exc:
            return AdapterResult(False, "Action parameters failed validation", {"errors": exc.errors()})
        if action.dry_run:
            return AdapterResult(True, f"Dry-run completed for {action.action_type.value}", {"dry_run": True})
        return AdapterResult(True, f"Execution completed for {action.action_type.value}", {"dry_run": False})
