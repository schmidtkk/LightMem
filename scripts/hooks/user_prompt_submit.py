from __future__ import annotations

"""UserPromptSubmit hook — extracts [mem]-tagged lines from the user's message
and appends them to inbox/pending.md for later promotion via /lightmem:update.

No LLM calls. Exits 0 on any internal exception (design invariant).
"""

import logging
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PROJECT_ROOT = _HERE.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.lib import inbox, profile, session_id as session_id_lib, stdin_io  # noqa: E402

_log = logging.getLogger(__name__)


def main() -> None:
    try:
        if profile.disabled("UserPromptSubmit"):
            return
        payload = stdin_io.read_json_stdin()
        _do_work(payload)
    except Exception as exc:
        _log.warning("user_prompt_submit failed: %s", exc)
    finally:
        sys.exit(0)


def _do_work(payload: dict) -> None:
    prompt: str = payload.get("prompt", "")
    if not prompt or "[mem]" not in prompt.lower():
        return

    cwd = payload.get("cwd", "")
    if not cwd:
        return
    repo_root = Path(cwd)

    transcript_path = payload.get("transcript_path", "")
    short_id = session_id_lib.derive_short_id(transcript_path) if transcript_path else ""

    candidates = inbox.extract_mem_tags(prompt)
    for text in candidates:
        inbox.append_pending(repo_root, text, source=short_id)


if __name__ == "__main__":
    main()
