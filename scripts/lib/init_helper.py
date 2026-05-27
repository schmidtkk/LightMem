from __future__ import annotations

import dataclasses
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from scripts.lib import markers, state

# Plugin root is three levels up from this file (scripts/lib/init_helper.py).
_PLUGIN_ROOT: Path = Path(__file__).parent.parent.parent
_TEMPLATES_DIR: Path = _PLUGIN_ROOT / "templates"
_TOPICS_TEMPLATES_DIR: Path = _TEMPLATES_DIR / "topics"


@dataclasses.dataclass(frozen=True)
class SkeletonPlan:
    repo_root: Path
    existing_claude_md: bool
    existing_lightmem_dir: bool
    # tuple, not list — preserves the frozen-dataclass deep-immutability contract.
    topics_to_create: tuple[str, ...]
    existing_agents_md: bool = False


def _today_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _collect_template_names() -> list[str]:
    names: list[str] = []
    for tmpl in sorted(_TOPICS_TEMPLATES_DIR.rglob("*.md")):
        names.append(str(tmpl.relative_to(_TOPICS_TEMPLATES_DIR)))
    return names


def inspect_repo(repo_root: Path) -> SkeletonPlan:
    lightmem_dir = repo_root / ".claude/lightmem"
    topics_dir = lightmem_dir / "topics"
    existing_slugs: set[str] = set()
    if topics_dir.is_dir():
        for f in topics_dir.rglob("*.md"):
            existing_slugs.add(str(f.relative_to(topics_dir)))

    to_create: list[str] = []
    for name in _collect_template_names():
        if name not in existing_slugs:
            to_create.append(name)

    return SkeletonPlan(
        repo_root=repo_root,
        existing_claude_md=(repo_root / "CLAUDE.md").exists(),
        existing_lightmem_dir=lightmem_dir.is_dir(),
        topics_to_create=tuple(to_create),
        existing_agents_md=(repo_root / "AGENTS.md").exists(),
    )


def create_skeleton(repo_root: Path) -> None:
    lightmem_dir = repo_root / ".claude/lightmem"
    # Create the standard subdirectory layout.
    for subdir in ("topics", "sessions", "archive", "topics/decisions",
                   "topics/constraints", "topics/workflows", "topics/gotchas"):
        (lightmem_dir / subdir).mkdir(parents=True, exist_ok=True)

    # Write .gitignore from template (atomic).
    gi_src = _TEMPLATES_DIR / "gitignore.tmpl"
    gi_dst = lightmem_dir / ".gitignore"
    gi_content = gi_src.read_text(encoding="utf-8")
    _atomic_write(gi_dst, gi_content)

    # Copy topic templates, substituting TEMPLATE_DATE, only if target absent.
    today = _today_iso()
    topics_dir = lightmem_dir / "topics"
    for name in _collect_template_names():
        src = _TOPICS_TEMPLATES_DIR / name
        dst = topics_dir / name
        if dst.exists():
            # Never overwrite user-edited topic files.
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        content = src.read_text(encoding="utf-8").replace("TEMPLATE_DATE", today)
        _atomic_write(dst, content)

    # Initialize state.json only when absent (preserve existing counters).
    sp = state.state_path(repo_root)
    if not sp.exists():
        state.write_state(repo_root, state.default_state())


def gateway_block_content(gateway_file: str = "CLAUDE.md") -> str:
    if gateway_file not in {"CLAUDE.md", "AGENTS.md"}:
        raise ValueError(f"unsupported gateway file: {gateway_file}")
    tmpl = _TEMPLATES_DIR / f"{gateway_file}.tmpl"
    return tmpl.read_text(encoding="utf-8")


def _update_gateway_md(
    repo_root: Path,
    gateway_file: str,
    mode: Literal["append_fenced", "backup_rewrite", "abort"],
) -> Path | None:
    gateway_md = repo_root / gateway_file
    fence_block = markers.fence("GATEWAY", gateway_block_content(gateway_file))

    if mode == "abort":
        sys.stdout.write(fence_block + "\n")
        return None

    if mode == "backup_rewrite":
        if gateway_md.exists():
            ts = datetime.now(timezone.utc).isoformat().replace(":", "-")
            backup = gateway_md.with_name(f"{gateway_file}.bak.{ts}")
            os.replace(gateway_md, backup)
        _atomic_write(gateway_md, fence_block + "\n")
        return gateway_md

    # append_fenced (default): prepend or replace gateway fence idempotently.
    if not gateway_md.exists():
        _atomic_write(gateway_md, fence_block + "\n")
        return gateway_md

    existing = gateway_md.read_text(encoding="utf-8")
    pattern = markers.marker_pair_regex("GATEWAY")
    if pattern.search(existing):
        # Replace the existing fence body idempotently.
        new_content = pattern.sub(fence_block, existing)
    else:
        # Prepend the fence followed by a blank line separator.
        new_content = fence_block + "\n\n" + existing

    _atomic_write(gateway_md, new_content)
    return gateway_md


def update_claude_md(
    repo_root: Path,
    mode: Literal["append_fenced", "backup_rewrite", "abort"],
) -> Path | None:
    return _update_gateway_md(repo_root, "CLAUDE.md", mode)


def update_agents_md(
    repo_root: Path,
    mode: Literal["append_fenced", "backup_rewrite", "abort"],
) -> Path | None:
    return _update_gateway_md(repo_root, "AGENTS.md", mode)


def update_gateway_files(
    repo_root: Path,
    mode: Literal["append_fenced", "backup_rewrite", "abort"],
) -> tuple[Path, ...]:
    updated: list[Path] = []
    for gateway_file in ("CLAUDE.md", "AGENTS.md"):
        result = _update_gateway_md(repo_root, gateway_file, mode)
        if result is not None:
            updated.append(result)
    return tuple(updated)


def _atomic_write(path: Path, content: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)
