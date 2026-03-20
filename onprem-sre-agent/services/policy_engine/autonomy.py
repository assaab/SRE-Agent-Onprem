from __future__ import annotations

from libs.contracts.models import ActionGraph, ActionType


def qualifies_for_autonomy(confidence: float, blast_radius: str, action_graph: ActionGraph) -> bool:
    if confidence < 0.90:
        return False
    if blast_radius.lower() != "single service":
        return False
    high_risk = {ActionType.DRAIN_NODE, ActionType.RUN_ANSIBLE_JOB, ActionType.ROLLBACK_DEPLOYMENT}
    action_types = {action.action_type for action in action_graph.actions}
    return action_types.isdisjoint(high_risk)
