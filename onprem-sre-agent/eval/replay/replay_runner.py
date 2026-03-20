from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path

from agents.change_correlation.agent import ChangeCorrelationAgent
from agents.evidence.agent import EvidenceAgent
from agents.planner.agent import RemediationPlannerAgent
from agents.rca.agent import RCAAgent
from agents.triage.agent import TriageAgent
from eval.scoring.scorecard import compute_score
from libs.contracts.models import ActionType, IncidentEnvelope, IncidentRecord
from libs.policy.engine import PolicyEngine
from services.router.response_plans import match_response_plan


def run_replay(dataset_path: Path) -> dict[str, float | int]:
    fixtures = json.loads(dataset_path.read_text(encoding="utf-8"))
    triage = TriageAgent()
    evidence_agent = EvidenceAgent()
    change_agent = ChangeCorrelationAgent()
    rca_agent = RCAAgent()
    planner = RemediationPlannerAgent()
    policy_engine = PolicyEngine()

    matches = 0
    evidence_items = 0
    duplicates = 0
    violations = 0
    rollback_count = 0
    actions_executed = 0
    seen = set()

    for incident in fixtures:
        plan = match_response_plan(incident["severity"], incident["symptom"])
        if plan.plan_id == incident["expected_route"]:
            matches += 1
        envelope = IncidentEnvelope(
            source=incident["source"],
            severity=incident["severity"].replace("critical", "sev1").replace("warning", "sev3"),
            service=incident["service"],
            resource=incident["resource"],
            symptom=incident["symptom"],
            occurred_at=datetime.utcnow(),
            dedupe_key=f"{incident['service']}:{incident['resource']}",
        )
        incident_record = IncidentRecord(incident_id=incident["incident_id"], metadata=envelope, response_plan=plan)
        asyncio.run(triage.run(incident_record))
        incident_record.evidence.extend(asyncio.run(evidence_agent.run(incident_record)))
        incident_record.evidence.append(asyncio.run(change_agent.run(incident_record)))
        incident_record.hypotheses.extend(asyncio.run(rca_agent.run(incident_record)))
        graph = asyncio.run(planner.run(incident_record))
        evidence_items += len(incident_record.evidence)
        key = f"{incident['service']}:{incident['resource']}"
        if key in seen:
            duplicates += 1
        seen.add(key)
        if ActionType.RUN_SHELL in plan.allowed_actions:
            violations += 1
        for action in graph.actions:
            actions_executed += 1
            decision = policy_engine.evaluate(plan, action, autonomous=False)
            if not decision.allowed:
                violations += 1
            if action.action_type == ActionType.ROLLBACK_DEPLOYMENT:
                rollback_count += 1

    score = compute_score(
        matches,
        len(fixtures),
        evidence_items,
        duplicates,
        violations,
        rollback_count=rollback_count,
        actions_executed=actions_executed,
    )
    return {
        "routing_precision": score.routing_precision,
        "evidence_completeness": score.evidence_completeness,
        "duplicate_call_rate": score.duplicate_call_rate,
        "policy_violations": score.policy_violations,
        "action_correctness": score.action_correctness,
        "rollback_frequency": score.rollback_frequency,
    }


if __name__ == "__main__":
    result = run_replay(Path("eval/datasets/compute_performance_incidents.json"))
    print(json.dumps(result, indent=2))
