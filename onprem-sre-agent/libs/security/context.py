from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field


@dataclass
class SecurityContext:
    agent_identity: str
    tool_identity: str
    allowed_targets: list[str]
    secret_refs: dict[str, str] = field(default_factory=dict)

    def can_access_target(self, target: str) -> bool:
        if target in self.allowed_targets:
            return True
        return any(fnmatch.fnmatch(target, pattern) for pattern in self.allowed_targets)
