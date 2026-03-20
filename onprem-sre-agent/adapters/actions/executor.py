from __future__ import annotations

import asyncio
import random
from typing import Final

from adapters.actions.typed_adapters import TypedActionAdapterRegistry
from libs.agent_runtime.sandbox import is_privileged_action, log_nemoclaw_style_sandbox
from libs.agent_runtime.settings import get_agent_runtime_settings
from libs.contracts.models import ActionRequest
from libs.observability.logging import get_logger
from libs.security.context import SecurityContext
from services.audit.store import audit_store


class ActionExecutor:
    def __init__(self) -> None:
        self._logger = get_logger("action-executor")
        self.registry = TypedActionAdapterRegistry()
        self.seen_idempotency_keys: set[str] = set()
        self._default_retry_limit: Final[int] = 3

    async def _run_with_retries(self, action: ActionRequest, context: SecurityContext) -> tuple[bool, str]:
        attempts = 0
        while attempts < self._default_retry_limit:
            attempts += 1
            try:
                result = await asyncio.wait_for(
                    self.registry.run(action, context),
                    timeout=action.timeout_seconds,
                )
                if result.success:
                    return True, result.message
                if attempts >= self._default_retry_limit:
                    return False, result.message
            except TimeoutError:
                if attempts >= self._default_retry_limit:
                    return False, f"Action timed out after {attempts} attempts"
            await asyncio.sleep(0.2 + random.uniform(0.0, 0.2))
        return False, "Action failed after retries"

    async def execute(self, action: ActionRequest) -> tuple[bool, str]:
        if action.idempotency_key in self.seen_idempotency_keys:
            return True, f"Skipped duplicate idempotency key {action.idempotency_key}"

        if get_agent_runtime_settings().sandbox_enabled and is_privileged_action(action):
            log_nemoclaw_style_sandbox(action)

        context = SecurityContext(
            agent_identity="execution-agent",
            tool_identity=f"adapter:{action.action_type.value}",
            allowed_targets=[action.target, "k8s-*", "arc-*"],
        )
        success, message = await self._run_with_retries(action, context)
        if success:
            self.seen_idempotency_keys.add(action.idempotency_key)
        await audit_store.append(
            "adapter_execution",
            {
                "action_id": action.action_id,
                "action_type": action.action_type.value,
                "target": action.target,
                "success": success,
                "message": message,
            },
        )
        self._logger.info("adapter_execution_complete", action_id=action.action_id, success=success)
        return success, message
