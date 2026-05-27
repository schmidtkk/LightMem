from __future__ import annotations

import hashlib
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

from scripts.lib import git_utils, journal, profile, scrub, stdin_io  # noqa: E402
from scripts.lib import session_id as session_id_lib  # noqa: E402

_log = logging.getLogger(__name__)


def main() -> None:
    try:
        if profile.disabled("Stop"):
            return
        payload = stdin_io.read_json_stdin()
        _do_work(payload)
    except Exception as exc:
        _log.warning("stop failed: %s", exc)
    finally:
        sys.exit(0)


def _repo_root(payload: dict[str, Any]) -> Path:
    cwd = payload.get("cwd")
    if cwd and Path(cwd).is_dir():
        return Path(cwd)
    _log.warning("stop: missing or invalid cwd in payload; falling back to os.getcwd()")
    return Path(os.getcwd())


def _do_work(payload: dict[str, Any]) -> None:
    # Re-entry guard: Claude Code sets this flag when a Stop hook itself triggers
    # another Stop event, which would cause infinite recursion.
    if payload.get("stop_hook_active"):
        return

    repo_root = _repo_root(payload)
    cwd_str = str(repo_root)

    session_id = payload.get("session_id", "")
    transcript_path = payload.get("transcript_path")
    model = payload.get("model", "")
    last_assistant_message = payload.get("last_assistant_message", "")

    ts = datetime.now(timezone.utc).isoformat()
    git_branch = git_utils.current_branch(cwd_str)
    transcript_uuid_tail = session_id_lib.derive_short_id(transcript_path)

    if last_assistant_message:
        last_assistant_hash = (
            "sha256:" + hashlib.sha256(last_assistant_message.encode()).hexdigest()
        )
        # Scrub the FULL message before excerpting — otherwise a secret straddling
        # the 200-char boundary would leak a short prefix that the regex cannot
        # detect (Codex H1).
        last_assistant_excerpt = scrub.scrub(last_assistant_message)[:200]
    else:
        last_assistant_hash = None
        last_assistant_excerpt = ""

    entry: dict[str, Any] = {
        "ts": ts,
        "session_id": session_id,
        "transcript_uuid_tail": transcript_uuid_tail,
        "git_branch": git_branch,
        "cwd": cwd_str,
        "model": model,
        "last_assistant_hash": last_assistant_hash,
        "last_assistant_excerpt": last_assistant_excerpt,
        # v0.2 will populate this from the PostToolUse aggregator.
        "touched_files": [],
    }

    journal.append(repo_root, entry)


if __name__ == "__main__":
    main()
