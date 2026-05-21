from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from scripts.lib import topics as topics_lib


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
        summary = str(t.frontmatter.get("summary", "")).replace("|", "\\|")
        status = str(t.frontmatter.get("status", "")).replace("|", "\\|")
        kind = t.kind.replace("|", "\\|")
        tid = t.id.replace("|", "\\|")
        try:
            rel_path = str(t.path.relative_to(lightmem_dir))
        except ValueError:
            rel_path = str(t.path)
        lines.append(f"| {tid} | {kind} | {status} | {summary} | {rel_path} |")

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
