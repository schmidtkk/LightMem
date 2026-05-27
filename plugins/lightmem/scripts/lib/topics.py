from __future__ import annotations

import dataclasses
import logging
import re
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

SLUG_REGEX: re.Pattern[str] = re.compile(r"^[a-z][a-z0-9-]*$")

VALID_KINDS: frozenset[str] = frozenset(
    {"mission", "architecture", "decision", "constraint", "workflow", "gotcha", "roadmap"}
)

VALID_STATUSES: frozenset[str] = frozenset({"active", "superseded", "archived"})


def is_valid_slug(slug: str) -> bool:
    return bool(SLUG_REGEX.match(slug))


_INLINE_COMMENT_RE: re.Pattern[str] = re.compile(r"(?<!\\)\s+#.*$")


def _strip_inline_comment(raw: str) -> str:
    # Strip unquoted, whitespace-prefixed inline comments (` # …`). Don't touch
    # values inside quotes or comments without a preceding space (e.g. URLs).
    # Codex H3.
    if not raw or raw[0] in ('"', "'"):
        return raw
    return _INLINE_COMMENT_RE.sub("", raw).rstrip()


def _parse_fm_value(raw: str) -> Any:
    raw = _strip_inline_comment(raw)
    # Inline list: [item, item, ...] — only flat string lists are supported.
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1]
        if not inner.strip():
            return []
        items: list[str] = []
        for item in inner.split(","):
            stripped = item.strip()
            # Strip optional surrounding quotes from each item.
            if (stripped.startswith('"') and stripped.endswith('"')) or (
                stripped.startswith("'") and stripped.endswith("'")
            ):
                stripped = stripped[1:-1]
            items.append(stripped)
        return items

    # Null literal or empty value → None.
    if raw == "null" or raw == "":
        return None

    # Quoted string — strip outer quotes only, no escape processing needed for
    # topic frontmatter (values are short slugs / summaries, not JSON strings).
    if (raw.startswith('"') and raw.endswith('"')) or (
        raw.startswith("'") and raw.endswith("'")
    ):
        return raw[1:-1]

    # Bare string — no auto-coercion of numbers or booleans (KISS per PRD §5.4).
    return raw


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    # Normalize real-world editor output before parsing (Codex H3):
    #   - Strip UTF-8 BOM if present (editors on Windows often add it).
    #   - Convert CRLF / lone CR to LF so the `\n---\n` delimiter matches.
    original = text
    if text.startswith("﻿"):
        text = text[1:]
    if "\r" in text:
        text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Frontmatter must open at the (post-normalization) start with `---\n`.
    if not text.startswith("---\n"):
        return {}, original

    rest = text[4:]
    close_idx = rest.find("\n---\n")
    if close_idx == -1:
        # Also accept a closing `---` at EOF with no trailing newline — common
        # when an editor strips the final newline on save. Codex H3.
        if rest.endswith("\n---"):
            close_idx = len(rest) - 4
            fm_block = rest[:close_idx]
            return _parse_fm_block(fm_block), ""
        # Unclosed frontmatter block — treat whole text as plain body to avoid
        # silently dropping content when the author forgot the closing delimiter.
        _log.warning("parse_frontmatter: unclosed frontmatter block")
        return {}, original

    fm_block = rest[:close_idx]
    # Body starts after the five chars \n---\n.
    body = rest[close_idx + 5:]

    return _parse_fm_block(fm_block), body


def _parse_fm_block(fm_block: str) -> dict[str, Any]:
    fm: dict[str, Any] = {}
    for line in fm_block.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        colon_pos = line.find(":")
        if colon_pos == -1:
            _log.warning("parse_frontmatter: skipping unparseable line: %r", line)
            continue
        key = line[:colon_pos].strip()
        raw_value = line[colon_pos + 1:].strip()
        if not key:
            continue
        fm[key] = _parse_fm_value(raw_value)
    return fm


@dataclasses.dataclass(frozen=True)
class Topic:
    id: str
    kind: str
    path: Path
    frontmatter: dict[str, Any]
    body: str


def walk_topics(topics_dir: Path) -> list[Topic]:
    topics: list[Topic] = []
    for md_file in topics_dir.rglob("*.md"):
        try:
            text = md_file.read_text(encoding="utf-8")
            fm, body = parse_frontmatter(text)
            topic_id = fm.get("id", md_file.stem)
            kind = fm.get("kind", "")
            # Cast to str in case frontmatter produced a non-string value for id/kind.
            topics.append(
                Topic(
                    id=str(topic_id),
                    kind=str(kind),
                    path=md_file,
                    frontmatter=fm,
                    body=body,
                )
            )
        except Exception as exc:
            _log.warning("walk_topics: skipping %s — %s", md_file, exc)

    # Sort by (kind, id) so output is deterministic across filesystems.
    topics.sort(key=lambda t: (t.kind, t.id))
    return topics
