from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Optional

from libs.agent_runtime.settings import get_agent_runtime_settings


@dataclass
class LLMBudget:
    max_calls: int
    max_tokens: int
    calls: int = field(default=0)
    tokens_used: int = field(default=0)

    def record_call(self, tokens: int) -> None:
        self.calls += 1
        self.tokens_used += tokens
        if self.calls > self.max_calls:
            raise RuntimeError("LLM call budget exceeded for this route")
        if self.tokens_used > self.max_tokens:
            raise RuntimeError("LLM token budget exceeded for this route")


_llm_budget_var: ContextVar[Optional[LLMBudget]] = ContextVar("llm_budget", default=None)


def get_llm_budget() -> Optional[LLMBudget]:
    return _llm_budget_var.get()


@contextmanager
def llm_budget_context() -> Iterator[LLMBudget]:
    s = get_agent_runtime_settings()
    budget = LLMBudget(max_calls=s.llm_max_calls_per_route, max_tokens=s.llm_max_tokens_per_route)
    token = _llm_budget_var.set(budget)
    try:
        yield budget
    finally:
        _llm_budget_var.reset(token)
