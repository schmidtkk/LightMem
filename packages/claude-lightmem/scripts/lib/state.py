from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

STATE_SCHEMA_VERSION: int = 1


def state_path(repo_root: Path) -> Path:
    return repo_root / ".claude/lightmem/state.json"


def read_state(repo_root: Path) -> dict[str, Any]:
    p = state_path(repo_root)
    if not p.exists():
        # Caller decides what "no file" means — could be uninitialized or first run.
        return {}
    try:
        text = p.read_text(encoding="utf-8")
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        _log.warning("state.json is malformed, returning empty state: %s", exc)
        return {}
    if not isinstance(parsed, dict):
        _log.warning("state.json root is not a dict, returning empty state")
        return {}
    return parsed


def write_state(repo_root: Path, state: dict[str, Any]) -> None:
    p = state_path(repo_root)
    p.parent.mkdir(parents=True, exist_ok=True)

    # Inject schema_version last so it always wins regardless of what the caller passed.
    out = dict(state)
    out["schema_version"] = STATE_SCHEMA_VERSION

    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(out, indent=2, sort_keys=True), encoding="utf-8")
    # os.replace is atomic on POSIX — avoids partial-write corruption on crash.
    os.replace(tmp, p)


def default_state() -> dict[str, Any]:
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "bootstrap_completed": False,
        "last_session_id": None,
        "turn_count": 0,
    }
