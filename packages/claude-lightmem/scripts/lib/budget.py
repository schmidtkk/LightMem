from __future__ import annotations

# Adapted from ECC (MIT) — vendor/ecc-reference/scripts/hooks/session-start.js:92-145
# Upstream commit: 1e8c7e7994223e0ff337d1626cd08e04a1ae67ed
# Upstream license: MIT, Copyright (c) 2026 Affaan Mustafa

import logging
import os
import sys

_log = logging.getLogger(__name__)

DEFAULT_SESSION_START_MAX_CHARS: int = 8000

# Leading \n\n is the separator from the preceding content — it is intentionally
# part of the marker so callers can concatenate without an extra join step.
TRUNCATION_MARKER: str = (
    "\n\n[LightMem truncated context. Set LIGHTMEM_SESSION_START_MAX_CHARS to raise"
    " the cap or LIGHTMEM_SESSION_START_CONTEXT=off to disable injected context.]"
)


def read_max_chars() -> int:
    raw = os.environ.get("LIGHTMEM_SESSION_START_MAX_CHARS")
    # Mirror ECC `if (!raw) return DEFAULT` at session-start.js:99 — treat unset
    # AND explicit empty string as the no-op default without warning. Negative
    # and garbage values still warn so operators see real misconfiguration.
    if not raw or not raw.strip():
        return DEFAULT_SESSION_START_MAX_CHARS
    stripped = raw.strip()
    try:
        parsed = int(stripped)
    except ValueError:
        _log.warning(
            "LIGHTMEM_SESSION_START_MAX_CHARS=%r is not a valid integer; "
            "using default %d.",
            raw,
            DEFAULT_SESSION_START_MAX_CHARS,
        )
        print(
            f"[LightMem] WARNING: LIGHTMEM_SESSION_START_MAX_CHARS={raw!r} is not a "
            f"valid integer; using default {DEFAULT_SESSION_START_MAX_CHARS}.",
            file=sys.stderr,
        )
        return DEFAULT_SESSION_START_MAX_CHARS
    if parsed < 0:
        _log.warning(
            "LIGHTMEM_SESSION_START_MAX_CHARS=%r is negative; using default %d.",
            raw,
            DEFAULT_SESSION_START_MAX_CHARS,
        )
        print(
            f"[LightMem] WARNING: LIGHTMEM_SESSION_START_MAX_CHARS={raw!r} is "
            f"negative; using default {DEFAULT_SESSION_START_MAX_CHARS}.",
            file=sys.stderr,
        )
        return DEFAULT_SESSION_START_MAX_CHARS
    return parsed


def is_context_disabled() -> bool:
    # Mirrors ECC isSessionStartContextDisabled (session-start.js:93-96).
    raw = os.environ.get("LIGHTMEM_SESSION_START_CONTEXT", "")
    return raw.strip().lower() in {"0", "false", "off", "none", "disabled"}


def apply_budget(content: str, max_chars: int | None = None) -> str:
    if max_chars is None:
        max_chars = read_max_chars()

    # Zero budget means the caller explicitly requested no injection.
    if max_chars <= 0:
        return ""

    if len(content) <= max_chars:
        return content

    # Mirror ECC limitSessionStartContext (session-start.js:133-145):
    # trim trailing whitespace from the prefix to avoid mid-word or
    # mid-whitespace cut-offs, then append the self-documenting marker.
    prefix_len = max(0, max_chars - len(TRUNCATION_MARKER))
    prefix = content[:prefix_len].rstrip()

    _log.warning(
        "SessionStart context truncated from %d to %d chars.",
        len(content),
        max_chars,
    )
    print(
        f"[LightMem] WARNING: SessionStart context truncated from {len(content)} "
        f"to {max_chars} chars.",
        file=sys.stderr,
    )

    if prefix_len == 0:
        # Defensive degradation: the marker alone exceeds the budget.
        # Return a bracket-closed slice of the marker so the result is still a
        # syntactically terminated message within the hard cap.
        return (TRUNCATION_MARKER[: max_chars - 1] + "]")[:max_chars]

    return (prefix + TRUNCATION_MARKER)[:max_chars]
