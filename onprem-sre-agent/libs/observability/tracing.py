from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI

_FastAPIInstrumentor: Any
try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor as _FastAPIInstrumentor
except ModuleNotFoundError:  # pragma: no cover
    _FastAPIInstrumentor = None

FastAPIInstrumentor: Any = _FastAPIInstrumentor


def instrument_fastapi(app: FastAPI) -> None:
    if FastAPIInstrumentor is None:
        return
    if os.getenv("OTEL_ENABLED", "true").lower() != "true":
        return
    FastAPIInstrumentor.instrument_app(app)
