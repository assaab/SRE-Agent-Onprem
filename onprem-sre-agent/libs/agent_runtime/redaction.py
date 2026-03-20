from __future__ import annotations

import re
from typing import Final

_BEARER: Final[re.Pattern[str]] = re.compile(r"(?i)(bearer\s+)([a-z0-9._\-]{8,})", re.IGNORECASE)
_API_KEY_INLINE: Final[re.Pattern[str]] = re.compile(
    r"(?i)(api[_-]?key|authorization|token)([\"'\s:=]+)([a-z0-9._\-]{12,})"
)


def redact_for_logging(text: str) -> str:
    """Best-effort redaction for logs and traces (ASCII only patterns)."""
    if not text:
        return text
    out = _BEARER.sub(r"\1[REDACTED]", text)
    out = _API_KEY_INLINE.sub(r"\1\2[REDACTED]", out)
    return out
