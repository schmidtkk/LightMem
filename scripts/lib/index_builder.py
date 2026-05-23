from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from scripts.lib import topics as topics_lib


def _format_topic_row(topic: topics_lib.Topic, lightmem_dir: Path) -> str:
    summary = str(topic.frontmatter.get("summary", "")).replace("|", "\\|")
    status = str(topic.frontmatter.get("status", "")).replace("|", "\\|")
    kind = topic.kind.replace("|", "\\|")
    tid = topic.id.replace("|", "\\|")
    try:
        rel_path = str(topic.path.relative_to(lightmem_dir))
    except ValueError:
        rel_path = str(topic.path)
    return f"| {tid} | {kind} | {status} | {summary} | {rel_path} |"


def build_index_md(repo_root: Path) -> str:
    topics_dir = repo_root / ".claude/lightmem/topics"
    all_topics = topics_lib.walk_topics(topics_dir) if topics_dir.is_dir() else []
    # walk_topics already sorts by (kind, id); preserve that order.
    lightmem_dir = repo_root / ".claude/lightmem"

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines: list[str] = [
        "# LightMem topic index",
        "",
        f"Generated {ts}.",
        "",
        "| id | kind | status | summary | path |",
        "|---|---|---|---|---|",
    ]

    for t in all_topics:
        lines.append(_format_topic_row(t, lightmem_dir))

    return "\n".join(lines) + "\n"


def write_index_md(repo_root: Path) -> Path:
    content = build_index_md(repo_root)
    lightmem_dir = repo_root / ".claude/lightmem"
    lightmem_dir.mkdir(parents=True, exist_ok=True)
    index_path = lightmem_dir / "index.md"
    tmp = index_path.with_suffix(".md.tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, index_path)
    return index_path


def patch_index_entry(repo_root: Path, topic_id: str) -> Path:
    """Update or insert the index.md row for one topic without a full rebuild.

    Falls back to write_index_md when the index does not yet exist or the
    topic cannot be found on disk (e.g. it was just deleted).
    """
    index_path = repo_root / ".claude/lightmem/index.md"
    if not index_path.exists():
        return write_index_md(repo_root)

    topics_dir = repo_root / ".claude/lightmem/topics"
    all_topics = topics_lib.walk_topics(topics_dir) if topics_dir.is_dir() else []
    topic = next((t for t in all_topics if t.id == topic_id), None)
    if topic is None:
        # Topic deleted — fall back to full rebuild so the row is removed.
        return write_index_md(repo_root)

    lightmem_dir = repo_root / ".claude/lightmem"
    new_row = _format_topic_row(topic, lightmem_dir)

    content = index_path.read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)

    row_prefix = f"| {topic_id} |"
    replaced = False
    new_lines: list[str] = []
    for line in lines:
        if line.startswith(row_prefix):
            new_lines.append(new_row + "\n")
            replaced = True
        else:
            new_lines.append(line)

    if not replaced:
        # New topic — append after the last table row.
        new_lines.append(new_row + "\n")

    tmp = index_path.with_suffix(".md.tmp")
    tmp.write_text("".join(new_lines), encoding="utf-8")
    os.replace(tmp, index_path)
    return index_path
