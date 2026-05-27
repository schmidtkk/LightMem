from __future__ import annotations

import subprocess


# git rev-parse is the cheapest branch-name query and works in detached HEAD
# (returns "HEAD"). Timeout is short — a hung git process must not block the
# user's turn for more than a couple of seconds.
def current_branch(cwd: str) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=cwd,
            capture_output=True,
            timeout=2,
            text=True,
        )
        if result.returncode == 0:
            return result.stdout.strip() or "unknown"
    except Exception:
        pass
    return "unknown"
