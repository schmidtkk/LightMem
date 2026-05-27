from __future__ import annotations

import logging
import os

_log = logging.getLogger(__name__)

_MINIMAL_EXEMPT: frozenset[str] = frozenset({"sessionstart"})


# DISABLED_HOOKS is checked before profile: a per-event mute is a surgical
# override that should win even when profile=standard. profile is the volume knob.
# hook_event must be the canonical camelCase event name (SessionStart, Stop, ...);
# matching is case-insensitive but underscore variants are NOT normalised.
def disabled(hook_event: str) -> bool:
    event_lower = hook_event.lower()

    raw_disabled = os.environ.get("LIGHTMEM_DISABLED_HOOKS", "")
    if raw_disabled.strip():
        disabled_set = {name.strip().lower() for name in raw_disabled.split(",")}
        if event_lower in disabled_set:
            return True

    profile = os.environ.get("LIGHTMEM_HOOK_PROFILE", "standard").strip().lower()
    if profile == "off":
        return True
    if profile == "minimal":
        return event_lower not in _MINIMAL_EXEMPT
    if profile != "standard":
        _log.warning(
            "LIGHTMEM_HOOK_PROFILE=%r is not recognised; treating as 'standard'.",
            profile,
        )
    return False
