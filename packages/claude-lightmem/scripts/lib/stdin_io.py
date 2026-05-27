from __future__ import annotations

# Adapted from ECC (MIT) — vendor/ecc-reference/scripts/hooks/session-end.js:114
# Upstream commit: 1e8c7e7994223e0ff337d1626cd08e04a1ae67ed
# Upstream license: MIT, Copyright (c) 2026 Affaan Mustafa

import json
import logging
import sys
from typing import Any

_log = logging.getLogger(__name__)

MAX_STDIN_BYTES: int = 1024 * 1024


# Never raises — hooks must not crash on malformed input; callers rely on the
# {}-on-error contract to avoid wrapping every read site in try/except.
def read_json_stdin() -> dict[str, Any]:
    raw = sys.stdin.read(MAX_STDIN_BYTES)
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        _log.warning("stdin_io: JSON parse failed: %s", exc)
        return {}
    if not isinstance(parsed, dict):
        return {}
    return parsed
