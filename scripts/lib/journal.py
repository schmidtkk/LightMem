from __future__ import annotations

# Adapted from ECC (MIT) — vendor/ecc-reference/skills/continuous-learning-v2/hooks/observe.sh:286-293
# Upstream commit: 1e8c7e7994223e0ff337d1626cd08e04a1ae67ed
# Upstream license: MIT, Copyright (c) 2026 Affaan Mustafa

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

DEFAULT_JOURNAL_MAX_MB: int = 5


def journal_path(repo_root: Path) -> Path:
    return repo_root / ".claude/lightmem/journal.jsonl"


def archive_dir(repo_root: Path) -> Path:
    return repo_root / ".claude/lightmem/archive"


def read_max_mb() -> int:
    raw = os.environ.get("LIGHTMEM_JOURNAL_MAX_MB")
    if raw is None:
        return DEFAULT_JOURNAL_MAX_MB
    try:
        value = int(raw.strip())
    except ValueError:
        _log.warning(
            "LIGHTMEM_JOURNAL_MAX_MB=%r is not a valid integer; using default %d.",
            raw,
            DEFAULT_JOURNAL_MAX_MB,
        )
        print(
            f"[LightMem] WARNING: LIGHTMEM_JOURNAL_MAX_MB={raw!r} is not a valid "
            f"integer; using default {DEFAULT_JOURNAL_MAX_MB}.",
            file=sys.stderr,
        )
        return DEFAULT_JOURNAL_MAX_MB
    # Negative is meaningless for a size cap; zero is the special "rotate on
    # every append" sentinel used by tests and operators who want eager rotation.
    if value < 0:
        _log.warning(
            "LIGHTMEM_JOURNAL_MAX_MB=%r is negative; using default %d.",
            raw,
            DEFAULT_JOURNAL_MAX_MB,
        )
        print(
            f"[LightMem] WARNING: LIGHTMEM_JOURNAL_MAX_MB={raw!r} is "
            f"negative; using default {DEFAULT_JOURNAL_MAX_MB}.",
            file=sys.stderr,
        )
        return DEFAULT_JOURNAL_MAX_MB
    return value


def append(repo_root: Path, entry: dict[str, Any]) -> None:
    jp = journal_path(repo_root)
    jp.parent.mkdir(parents=True, exist_ok=True)

    # Compact JSONL — no extra whitespace, keep unicode literal (ensure_ascii=False).
    line = json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n"

    # POSIX guarantees a single write() up to PIPE_BUF (≥512 B, typically 4 KB)
    # is atomic for regular files opened in append mode; hook payloads stay well
    # within that limit, so no lock file is needed here.
    with open(jp, "a", encoding="utf-8") as fh:
        fh.write(line)

    if jp.stat().st_size > read_max_mb() * 1024 * 1024:
        rotate(repo_root)


def rotate(repo_root: Path) -> Path | None:
    jp = journal_path(repo_root)
    if not jp.exists():
        return None

    ad = archive_dir(repo_root)
    ad.mkdir(parents=True, exist_ok=True)

    # Replace `:` so the filename is safe on Windows paths (mirrors ECC observe.sh:291).
    ts = datetime.now(timezone.utc).isoformat().replace(":", "-")
    pid = os.getpid()
    archive_path = ad / f"journal-{ts}-{pid}.jsonl"

    # Atomic rename: no reader sees a partial file; the old path disappears atomically.
    os.replace(jp, archive_path)
    return archive_path
