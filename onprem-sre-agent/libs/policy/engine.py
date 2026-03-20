from __future__ import annotations

import fnmatch
import os
from pathlib import Path
from typing import Optional, cast

import yaml  # type: ignore[import-untyped]

from libs.contracts.models import (
    ActionRequest,
    ActionType,
    PolicyClass,
    PolicyDecision,
    ResponsePlan,
)


class PolicyEngine:
    def __init__(self) -> None:
        workspace_root = Path(__file__).resolve().parents[2]
        execution_file = workspace_root / "policies" / "execution" / "default-policy.yaml"
        approval_file = workspace_root / "policies" / "approval" / "rules.yaml"
        self._execution_policy = self._load_yaml(execution_file)
        self._approval_policy = self._load_yaml(approval_file)

    @staticmethod
    def _load_yaml(path: Path) -> dict[str, object]:
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}

    @staticmethod
    def _action_in_rule(action: ActionRequest, values: list[str]) -> bool:
        names = {action_name.strip() for action_name in values}
        return action.action_type.value in names

    @staticmethod
    def _target_allowed(target: str, target_patterns: list[str] | None) -> bool:
        if not target_patterns:
            return True
        return any(fnmatch.fnmatch(target, pattern) for pattern in target_patterns)

    @staticmethod
    def _when_matches(
        when: dict[str, object],
        action: ActionRequest,
        planner_confidence: float | None,
        blast_radius: str | None,
        severity: str | None,
    ) -> bool:
        action_types = when.get("actionTypeIn", [])
        if isinstance(action_types, list) and action_types:
            if not PolicyEngine._action_in_rule(action, [str(x) for x in action_types]):
                return False
        conf_min = when.get("confidenceMin")
        if conf_min is not None and planner_confidence is not None:
            try:
                if planner_confidence < float(conf_min):
                    return False
            except (TypeError, ValueError):
                return False
        elif conf_min is not None and planner_confidence is None:
            return False
        br = when.get("blastRadius")
        if br is not None and blast_radius is not None:
            if str(br).strip().lower() != blast_radius.strip().lower():
                return False
        elif br is not None and blast_radius is None:
            return False
        sev = when.get("severityIn")
        if isinstance(sev, list) and sev and severity is not None:
            if severity not in {str(x) for x in sev}:
                return False
        return True

    def evaluate(
        self,
        plan: ResponsePlan,
        action: ActionRequest,
        autonomous: bool,
        *,
        planner_confidence: float | None = None,
        blast_radius: str | None = None,
        severity: str | None = None,
        evidence_coverage: float | None = None,
    ) -> PolicyDecision:
        policy_ver = str(self._execution_policy.get("policyVersion", "v1"))
        kill_switch = os.getenv("AUTONOMY_KILL_SWITCH", "true").lower() == "true"
        if autonomous and kill_switch:
            return PolicyDecision(
                allowed=False,
                policy_class=plan.policy_class,
                reason="Autonomous mode blocked by kill switch",
                requires_approval=False,
                policy_version=policy_ver,
                deny_reason_code="kill_switch",
            )

        if action.action_type in plan.denied_actions:
            return PolicyDecision(
                allowed=False,
                policy_class=plan.policy_class,
                reason="Action is denied by response plan",
                requires_approval=False,
                policy_version=policy_ver,
                deny_reason_code="plan_denied_action",
            )

        if plan.allowed_actions and action.action_type not in plan.allowed_actions:
            return PolicyDecision(
                allowed=False,
                policy_class=plan.policy_class,
                reason="Action is outside plan allowlist",
                requires_approval=False,
                policy_version=policy_ver,
                deny_reason_code="outside_plan_allowlist",
            )

        raw_allowed_actions = self._execution_policy.get("allowedActions", [])
        execution_allowed_actions = set(raw_allowed_actions) if isinstance(raw_allowed_actions, list) else set()
        if execution_allowed_actions and action.action_type.value not in execution_allowed_actions:
            return PolicyDecision(
                allowed=False,
                policy_class=plan.policy_class,
                reason="Action blocked by execution policy allowlist",
                requires_approval=False,
                policy_version=policy_ver,
                deny_reason_code="execution_allowlist",
            )

        raw_denied_actions = self._execution_policy.get("deniedActions", [])
        execution_denied_actions = set(raw_denied_actions) if isinstance(raw_denied_actions, list) else set()
        if action.action_type.value in execution_denied_actions:
            return PolicyDecision(
                allowed=False,
                policy_class=plan.policy_class,
                reason="Action blocked by execution policy denylist",
                requires_approval=False,
                policy_version=policy_ver,
                deny_reason_code="execution_denylist",
            )

        target_allow_patterns = self._execution_policy.get("allowedTargetPatterns", [])
        target_patterns = cast(
            Optional[list[str]],
            target_allow_patterns if isinstance(target_allow_patterns, list) else None,
        )
        if not self._target_allowed(action.target, target_patterns):
            return PolicyDecision(
                allowed=False,
                policy_class=plan.policy_class,
                reason="Target blocked by execution policy allowlist",
                requires_approval=False,
                policy_version=policy_ver,
                deny_reason_code="target_blocked",
            )

        if plan.policy_class == PolicyClass.READ_ONLY and action.action_type in {
            ActionType.RESTART_SERVICE,
            ActionType.SCALE_WORKLOAD,
            ActionType.ROLLBACK_DEPLOYMENT,
            ActionType.DRAIN_NODE,
            ActionType.RUN_ANSIBLE_JOB,
            ActionType.RUN_SHELL,
        }:
            return PolicyDecision(
                allowed=False,
                policy_class=plan.policy_class,
                reason="Read-only workflow cannot invoke write actions",
                requires_approval=False,
                policy_version=policy_ver,
                deny_reason_code="read_only_write",
            )

        cov_min = self._approval_policy.get("minEvidenceCoverage")
        if cov_min is not None and evidence_coverage is not None:
            try:
                if evidence_coverage < float(cov_min):
                    return PolicyDecision(
                        allowed=False,
                        policy_class=plan.policy_class,
                        reason="Evidence coverage below policy threshold",
                        requires_approval=False,
                        policy_version=policy_ver,
                        deny_reason_code="low_evidence_coverage",
                    )
            except (TypeError, ValueError):
                pass

        requires_approval = plan.policy_class != PolicyClass.READ_ONLY
        matched_rule_id: str | None = None
        rules = self._approval_policy.get("rules", [])
        if isinstance(rules, list):
            for rule in rules:
                if not isinstance(rule, dict):
                    continue
                when = rule.get("when", {})
                if not isinstance(when, dict):
                    continue
                if not self._when_matches(
                    when,
                    action,
                    planner_confidence,
                    blast_radius,
                    severity,
                ):
                    continue
                requires_approval = bool(rule.get("requireApproval", requires_approval))
                matched_rule_id = str(rule.get("name", "")) or None
                break

        if autonomous and plan.policy_class in {PolicyClass.PRIVILEGED, PolicyClass.REVIEW_REQUIRED}:
            requires_approval = False

        scope = "action" if requires_approval else "none"
        return PolicyDecision(
            allowed=True,
            policy_class=plan.policy_class,
            reason="Allowed by plan and policy class",
            requires_approval=requires_approval,
            policy_version=policy_ver,
            rule_id=matched_rule_id,
            requires_approval_scope=scope,
        )
