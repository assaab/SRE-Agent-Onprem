from __future__ import annotations

import logging
import os
from contextvars import ContextVar
from typing import Any

_structlog: Any
try:
    import structlog as _structlog
except ModuleNotFoundError:  # pragma: no cover - fallback for minimal test envs
    _structlog = None

structlog: Any = _structlog

_request_id: ContextVar[str] = ContextVar("request_id", default="-")


def set_request_id(request_id: str) -> None:
    _request_id.set(request_id)


class _FallbackLogger:
    def __init__(self, name: str) -> None:
        self._logger = logging.getLogger(name)

    def bind(self, **_: Any) -> _FallbackLogger:
        return self

    def info(self, event: str, **kwargs: Any) -> None:
        self._logger.info("%s %s", event, kwargs)

    def warning(self, event: str, **kwargs: Any) -> None:
        self._logger.warning("%s %s", event, kwargs)


def get_logger(name: str) -> Any:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    if structlog is None:
        return _FallbackLogger(name)
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.contextvars.merge_contextvars,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
    )
    logger = structlog.get_logger(name)
    return logger.bind(request_id=_request_id.get())
