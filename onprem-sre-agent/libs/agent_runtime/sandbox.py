from __future__ import annotations

from libs.contracts.models import ActionRequest, ActionType
from libs.observability.logging import get_logger

_logger = get_logger("sandbox-coordinator")

_PRIVILEGED: frozenset[ActionType] = frozenset(
    {
        ActionType.RUN_SHELL,
        ActionType.RUN_ANSIBLE_JOB,
        ActionType.DRAIN_NODE,
    }
)


def is_privileged_action(action: ActionRequest) -> bool:
    return action.action_type in _PRIVILEGED


def log_nemoclaw_style_sandbox(action: ActionRequest) -> None:
    """Placeholder for NemoClaw-style sandbox integration: log envelope before adapter runs."""
    _logger.info(
        "sandbox_envelope",
        action_id=action.action_id,
        action_type=action.action_type.value,
        target=action.target,
        dry_run=action.dry_run,
        note="Route execution through sandbox SDK here when SANDBOX_ENABLED=true",
    )
