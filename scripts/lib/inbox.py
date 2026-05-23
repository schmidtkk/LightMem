from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path

from scripts.lib import scrub as scrub_lib

_INBOX_HEADER = (
    "# LightMem inbox\n\n"
    "> Items pending promotion to topics."
    " Run `/lightmem:update` to review and promote.\n\n"
)

_MEM_TAG_RE: re.Pattern[str] = re.compile(r"\[mem\]", re.IGNORECASE)

# Matches a bounded source tag at the START of a string: "`abc12345` "
# The tag must be fully enclosed in backticks and followed by whitespace.
# This avoids mistaking code-like text (e.g. "`func()`") for a source tag.
_SOURCE_TAG_RE: re.Pattern[str] = re.compile(r"^`[^`]+`\s+")


def inbox_path(repo_root: Path) -> Path:
    return repo_root / ".claude" / "lightmem" / "inbox" / "pending.md"


def append_pending(
    repo_root: Path,
    text: str,
    *,
    source: str = "",
    ts: str | None = None,
) -> Path:
    """Append one pending item to inbox/pending.md (creates file if absent)."""
    text = scrub_lib.scrub(text.strip())
    if not text:
        return inbox_path(repo_root)

    if ts is None:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    path = inbox_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)

    if not path.exists():
        path.write_text(_INBOX_HEADER, encoding="utf-8")

    source_tag = f" `{source}`" if source else ""
    line = f"- [{ts}]{source_tag} {text}\n"

    with path.open("a", encoding="utf-8") as fh:
        fh.write(line)

    return path


def read_pending(repo_root: Path) -> list[str]:
    """Return the text of each pending item (bullets only, timestamp stripped)."""
    path = inbox_path(repo_root)
    if not path.exists():
        return []

    items: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if not stripped.startswith("- ["):
            continue
        # Strip leading "- [ts]" and optional "`source`" tag.
        after_close = stripped.find("]", 3)
        if after_close == -1:
            continue
        rest = stripped[after_close + 1 :].strip()
        # Strip a bounded source tag (`<id>` ) if present at the start.
        rest = _SOURCE_TAG_RE.sub("", rest)
        if rest:
            items.append(rest)
    return items


def clear_pending(repo_root: Path) -> None:
    """Reset inbox to the header, removing all pending items."""
    path = inbox_path(repo_root)
    if path.exists():
        tmp = path.with_suffix(".md.tmp")
        tmp.write_text(_INBOX_HEADER, encoding="utf-8")
        os.replace(tmp, path)


def extract_mem_tags(text: str) -> list[str]:
    """Return de-tagged content for every line that contains a [mem] marker."""
    results: list[str] = []
    for line in text.splitlines():
        if not _MEM_TAG_RE.search(line):
            continue
        content = _MEM_TAG_RE.sub("", line).strip()
        if content:
            results.append(content)
    return results
