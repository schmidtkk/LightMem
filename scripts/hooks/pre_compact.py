from __future__ import annotations

# Adapted from ECC (MIT) — vendor/ecc-reference/scripts/hooks/pre-compact.js:1-48
# Upstream commit: 1e8c7e7994223e0ff337d1626cd08e04a1ae67ed
# Upstream license: MIT, Copyright (c) 2026 Affaan Mustafa

import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Make the project lib importable when this script is invoked directly by
# Claude Code (which sets cwd to the target repo, not the plugin root).
_HERE = Path(__file__).resolve().parent
_PROJECT_ROOT = _HERE.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.lib import profile, stdin_io  # noqa: E402

_log = logging.getLogger(__name__)


def main() -> None:
    try:
        if profile.disabled("PreCompact"):
            return
        payload = stdin_io.read_json_stdin()
        _do_work(payload)
    except Exception as exc:
        _log.warning("pre_compact failed: %s", exc)
    finally:
        sys.exit(0)


def _repo_root(payload: dict[str, Any]) -> Path:
    cwd = payload.get("cwd")
    if cwd and Path(cwd).is_dir():
        return Path(cwd)
    _log.warning("pre_compact: missing or invalid cwd in payload; falling back to os.getcwd()")
    return Path(os.getcwd())


def _do_work(payload: dict[str, Any]) -> None:
    repo_root = _repo_root(payload)
    trigger = payload.get("trigger", "unknown")

    now_utc = datetime.now(timezone.utc)
    timestamp = now_utc.isoformat()
    time_str = now_utc.strftime("%H:%M:%S")
    today = now_utc.strftime("%Y-%m-%d")

    lightmem_dir = repo_root / ".claude" / "lightmem"
    log_file = lightmem_dir / "compaction-log.txt"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    with open(log_file, "a", encoding="utf-8") as fh:
        fh.write(f"[{timestamp}] Context compaction triggered (trigger={trigger})\n")

    # Annotate the active session file so reviewers know a compaction boundary occurred.
    sessions_dir = lightmem_dir / "sessions"
    if sessions_dir.is_dir():
        todays_files = sorted(sessions_dir.glob(f"{today}-*.md"), reverse=True)
        if todays_files:
            active_session = todays_files[0]
            try:
                with open(active_session, "a", encoding="utf-8") as fh:
                    fh.write(f"\n---\n**[Compaction occurred at {time_str}]**\n")
            except Exception as exc:
                _log.warning(
                    "pre_compact: could not annotate session file %s: %s",
                    active_session,
                    exc,
                )


if __name__ == "__main__":
    main()
