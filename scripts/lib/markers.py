from __future__ import annotations

import re

MARKER_PREFIX = "LIGHTMEM"

GATEWAY_START = "<!-- LIGHTMEM:GATEWAY:START -->"
GATEWAY_END = "<!-- LIGHTMEM:GATEWAY:END -->"

SUMMARY_START = "<!-- LIGHTMEM:SUMMARY:START -->"
SUMMARY_END = "<!-- LIGHTMEM:SUMMARY:END -->"

_EVENT_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


def _validate_event(event: str) -> None:
    if not _EVENT_RE.match(event):
        raise ValueError(f"Invalid event name {event!r}: must match ^[A-Z][A-Z0-9_]*$")


def fence(event: str, body: str) -> str:
    _validate_event(event)
    start = f"<!-- {MARKER_PREFIX}:{event}:START -->"
    end = f"<!-- {MARKER_PREFIX}:{event}:END -->"
    return f"{start}\n{body}\n{end}"


def marker_pair_regex(event: str) -> re.Pattern[str]:
    _validate_event(event)
    start = re.escape(f"<!-- {MARKER_PREFIX}:{event}:START -->")
    end = re.escape(f"<!-- {MARKER_PREFIX}:{event}:END -->")
    return re.compile(f"{start}.*?{end}", re.DOTALL)
