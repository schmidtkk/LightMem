from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

# Make the project lib importable when this script is invoked directly by
# Claude Code (which sets cwd to the target repo, not the plugin root).
_HERE = Path(__file__).resolve().parent
_PROJECT_ROOT = _HERE.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.lib import budget, injection, profile, stdin_io  # noqa: E402
from scripts.lib import topics  # noqa: E402
from scripts.lib.topics import parse_frontmatter  # noqa: E402

_log = logging.getLogger(__name__)

_UNINITIALIZED_SUGGESTION = (
    "<important>LightMem detected this repo has no memory."
    " Tell the user this and suggest running `/lightmem:init` to set up.</important>"
)

_MISSION_MAX_CHARS = 500
_MAX_CONSTRAINTS = 10
_MAX_DECISIONS = 3


def main() -> None:
    try:
        if profile.disabled("SessionStart"):
            return
        payload = stdin_io.read_json_stdin()
        _do_work(payload)
    except Exception as exc:
        _log.warning("session_start failed: %s", exc)
    finally:
        sys.exit(0)


def _repo_root(payload: dict[str, Any]) -> Path:
    cwd = payload.get("cwd")
    if cwd and Path(cwd).is_dir():
        return Path(cwd)
    _log.warning("session_start: missing or invalid cwd in payload; falling back to os.getcwd()")
    return Path(os.getcwd())


def _do_work(payload: dict[str, Any]) -> None:
    repo_root = _repo_root(payload)
    lightmem_dir = repo_root / ".claude" / "lightmem"

    # state.json is written only by /lightmem:init (create_skeleton). The directory
    # itself may exist from Stop/SessionEnd hooks running before init — so checking
    # the directory alone would give a false "initialized" signal.
    if not (lightmem_dir / "state.json").exists():
        text = budget.apply_budget(_UNINITIALIZED_SUGGESTION)
        sys.stdout.write(injection.build_session_start_output(text))
        return

    # Context disabled means emit an empty envelope so Claude sees nothing injected.
    if budget.is_context_disabled():
        sys.stdout.write(injection.build_session_start_output(""))
        return

    text = _build_hot_summary(repo_root, lightmem_dir, payload)
    text = budget.apply_budget(text)
    sys.stdout.write(injection.build_session_start_output(text))


def _build_hot_summary(
    repo_root: Path,
    lightmem_dir: Path,
    payload: dict[str, Any],
) -> str:
    topics_dir = lightmem_dir / "topics"
    sections: list[str] = []

    mission = _mission_head(topics_dir)
    if mission:
        sections.append(mission)

    constraints = _active_constraints(topics_dir)
    if constraints:
        sections.append(constraints)

    counts = _topic_counts(topics_dir)
    if counts:
        sections.append(counts)

    decisions = _recent_decisions(topics_dir)
    if decisions:
        sections.append(decisions)

    # Prior-session summary only makes sense on resume — replaying it on a fresh
    # startup would surface stale state when the user just opened a new session.
    source = payload.get("source", "")
    if source == "resume":
        prior = _prior_session_summary(lightmem_dir)
        if prior:
            sections.append(prior)

    return "\n\n".join(sections)


def _mission_head(topics_dir: Path) -> str:
    mission_file = topics_dir / "mission.md"
    if not mission_file.is_file():
        return ""
    try:
        text = mission_file.read_text(encoding="utf-8")
        _, body = parse_frontmatter(text)
        body = body.strip()
        if not body:
            return ""
        return body[:_MISSION_MAX_CHARS]
    except Exception as exc:
        _log.warning("session_start: could not read mission.md: %s", exc)
        return ""


def _active_constraints(topics_dir: Path) -> str:
    constraints_dir = topics_dir / "constraints"
    if not constraints_dir.is_dir():
        return ""

    lines: list[str] = []
    for md_file in sorted(constraints_dir.glob("*.md")):
        if len(lines) >= _MAX_CONSTRAINTS:
            break
        try:
            text = md_file.read_text(encoding="utf-8")
            fm, _ = parse_frontmatter(text)
            if fm.get("status") != "active":
                continue
            slug = md_file.stem
            summary = fm.get("summary", "")
            lines.append(f"- [{slug}] {summary}")
        except Exception as exc:
            _log.warning("session_start: skipping constraint %s: %s", md_file, exc)

    if not lines:
        return ""
    return "Active constraints:\n" + "\n".join(lines)


def _topic_counts(topics_dir: Path) -> str:
    if not topics_dir.is_dir():
        return ""

    all_topics = topics.walk_topics(topics_dir)
    counts: dict[str, int] = {
        "decision": 0,
        "constraint": 0,
        "gotcha": 0,
        "workflow": 0,
    }
    for t in all_topics:
        kind = t.kind.lower()
        if kind in counts:
            counts[kind] += 1

    return (
        f"Topics: {counts['decision']} decisions, "
        f"{counts['constraint']} constraints, "
        f"{counts['gotcha']} gotchas, "
        f"{counts['workflow']} workflows."
    )


def _recent_decisions(topics_dir: Path) -> str:
    if not topics_dir.is_dir():
        return ""

    all_topics = topics.walk_topics(topics_dir)
    decisions = [t for t in all_topics if t.kind.lower() == "decision"]

    # Sort descending by updated_at; treat missing or null as oldest possible date.
    decisions.sort(
        key=lambda t: t.frontmatter.get("updated_at") or "0000-00-00",
        reverse=True,
    )

    lines: list[str] = []
    for t in decisions[:_MAX_DECISIONS]:
        slug = t.id
        summary = t.frontmatter.get("summary", "")
        updated = t.frontmatter.get("updated_at", "")
        lines.append(f"- [{slug}] {summary} ({updated})")

    if not lines:
        return ""
    return "Recent decisions:\n" + "\n".join(lines)


def _prior_session_summary(lightmem_dir: Path) -> str:
    sessions_dir = lightmem_dir / "sessions"
    if not sessions_dir.is_dir():
        return ""

    session_files = sorted(sessions_dir.glob("*.md"), reverse=True)
    if not session_files:
        return ""

    # Most-recent file is the first after reverse-sort on filename, which is
    # date-prefixed so lexicographic order matches chronological order.
    most_recent = session_files[0]
    try:
        content = most_recent.read_text(encoding="utf-8")
    except Exception as exc:
        _log.warning("session_start: could not read session file %s: %s", most_recent, exc)
        return ""

    return injection.wrap_with_stale_replay_guard(content)


if __name__ == "__main__":
    main()
