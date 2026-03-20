from __future__ import annotations

from datetime import datetime

from adapters.actions.executor import ActionExecutor
from libs.contracts.models import ActionRequest, ActionResult


class ExecutionAgent:
    def __init__(self) -> None:
        self.executor = ActionExecutor()

    async def run(self, request: ActionRequest) -> ActionResult:
        started_at = datetime.utcnow()
        success, message = await self.executor.execute(request)
        return ActionResult(
            action_id=request.action_id,
            success=success,
            status_message=message,
            started_at=started_at,
            finished_at=datetime.utcnow(),
        )
