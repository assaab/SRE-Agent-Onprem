from __future__ import annotations

from typing import Any, List, Optional


def normalize_evidence_intents(raw: Optional[List[str]]) -> List[str]:
    """Map triage/router strings to canonical collector keys."""
    if not raw:
        return ["metrics", "logs", "recent_changes"]
    out: List[str] = []
    for item in raw:
        key = item.strip().lower()
        if key in {"metric", "metrics", "timeseries"}:
            if "metrics" not in out:
                out.append("metrics")
        elif key in {"log", "logs", "logging"}:
            if "logs" not in out:
                out.append("logs")
        elif key in {"recent_changes", "deployments", "deployment", "change", "changes"}:
            if "recent_changes" not in out:
                out.append("recent_changes")
        elif key in {"topology", "topo", "dependencies"}:
            if "topology" not in out:
                out.append("topology")
        else:
            if key not in out:
                out.append(key)
    return out if out else ["metrics", "logs"]


def extract_triage_dict(hypotheses: List[dict]) -> Optional[dict]:
    for block in hypotheses:
        if "triage" in block and isinstance(block["triage"], dict):
            return block["triage"]
    return None
