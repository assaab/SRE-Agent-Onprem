from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ReplayScore:
    routing_precision: float
    evidence_completeness: float
    duplicate_call_rate: float
    policy_violations: int
    action_correctness: float
    rollback_frequency: float = 0.0


def compute_score(
    matches: int,
    total: int,
    evidence_items: int,
    duplicates: int,
    violations: int,
    rollback_count: int = 0,
    actions_executed: int = 0,
) -> ReplayScore:
    routing_precision = matches / total if total else 0.0
    evidence_completeness = min(1.0, evidence_items / max(total, 1))
    duplicate_call_rate = duplicates / max(evidence_items, 1)
    action_correctness = 1.0 if violations == 0 else 0.0
    rollback_frequency = rollback_count / max(actions_executed, 1)
    return ReplayScore(
        routing_precision=routing_precision,
        evidence_completeness=evidence_completeness,
        duplicate_call_rate=duplicate_call_rate,
        policy_violations=violations,
        action_correctness=action_correctness,
        rollback_frequency=rollback_frequency,
    )
