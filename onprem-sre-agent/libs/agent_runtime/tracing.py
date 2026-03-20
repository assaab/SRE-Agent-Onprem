from __future__ import annotations

from contextlib import nullcontext
from typing import Any

try:
    from opentelemetry import trace

    _tracer = trace.get_tracer("onprem_sre_agent.agents", "0.1.0")
except Exception:  # pragma: no cover
    _tracer = None


def agent_span(name: str) -> Any:
    if _tracer is not None:
        return _tracer.start_as_current_span(f"agent.{name}")
    return nullcontext()
