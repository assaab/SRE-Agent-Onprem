from __future__ import annotations

from libs.contracts.models import ActionType, PolicyClass, ResponsePlan


def match_response_plan(severity: str, symptom: str) -> ResponsePlan:
    symptom_lower = symptom.lower()
    if severity in {"sev1", "sev2"} and ("cpu" in symptom_lower or "error" in symptom_lower):
        return ResponsePlan(
            plan_id="compute-performance-v1",
            workflow_family="compute-performance",
            policy_class=PolicyClass.REVIEW_REQUIRED,
            allowed_actions=[
                ActionType.QUERY_METRICS,
                ActionType.QUERY_LOGS,
                ActionType.GET_RECENT_DEPLOYMENTS,
                ActionType.RESTART_SERVICE,
                ActionType.SCALE_WORKLOAD,
                ActionType.ROLLBACK_DEPLOYMENT,
            ],
            denied_actions=[ActionType.RUN_SHELL],
            max_retries=2,
        )
    return ResponsePlan(
        plan_id="generic-observability-v1",
        workflow_family="generic-observability",
        policy_class=PolicyClass.READ_ONLY,
        allowed_actions=[
            ActionType.QUERY_METRICS,
            ActionType.QUERY_LOGS,
            ActionType.GET_RECENT_DEPLOYMENTS,
            ActionType.OPEN_TICKET,
            ActionType.PAGE_HUMAN,
        ],
        denied_actions=[ActionType.RUN_SHELL, ActionType.ROLLBACK_DEPLOYMENT],
        max_retries=1,
    )
