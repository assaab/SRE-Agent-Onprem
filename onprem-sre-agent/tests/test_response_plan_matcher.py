from libs.contracts.models import ActionType
from services.router.response_plans import match_response_plan


def test_matches_compute_performance_route() -> None:
    plan = match_response_plan("sev1", "CPU spike and error spike")
    assert plan.plan_id == "compute-performance-v1"
    assert ActionType.RUN_SHELL in plan.denied_actions


def test_matches_generic_route() -> None:
    plan = match_response_plan("sev4", "minor latency blip")
    assert plan.plan_id == "generic-observability-v1"
