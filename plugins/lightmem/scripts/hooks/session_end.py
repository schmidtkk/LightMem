from __future__ import annotations

import json
import logging
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

# Make the project lib importable when this script is invoked directly by
# Claude Code (which sets cwd to the target repo, not the plugin root).
_HERE = Path(__file__).resolve().parent
_PROJECT_ROOT = _HERE.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.lib import git_utils, markers, profile, scrub, stdin_io  # noqa: E402
from scripts.lib import session_id as session_id_lib  # noqa: E402

_log = logging.getLogger(__name__)

_MAX_USER_MESSAGES = 10
_MAX_USER_MSG_CHARS = 200
_MAX_TOOLS = 20
_MAX_FILES = 30

# Tool names that Claude uses to write files (per the hook spec).
_FILE_WRITE_TOOLS = frozenset({"Edit", "Write", "MultiEdit"})

_LAST_UPDATED_RE = re.compile(r"\*\*Last Updated:\*\*\s+\S+")
_STARTED_RE = re.compile(r"\*\*Started:\*\*\s+(\S+)")


def main() -> None:
    try:
        if profile.disabled("SessionEnd"):
            return
        payload = stdin_io.read_json_stdin()
        _do_work(payload)
    except Exception as exc:
        _log.warning("session_end failed: %s", exc)
    finally:
        sys.exit(0)


def _repo_root(payload: dict[str, Any]) -> Path:
    cwd = payload.get("cwd")
    if cwd and Path(cwd).is_dir():
        return Path(cwd)
    _log.warning("session_end: missing or invalid cwd in payload; falling back to os.getcwd()")
    return Path(os.getcwd())


# git_branch resolution lives in scripts.lib.git_utils; see W3 in the Round 5 review.


def _extract_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") in {
                "text",
                "input_text",
                "output_text",
            }:
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return ""


def _json_object(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, dict):
            return parsed
    return {}


def _extract_file_paths(raw: Any) -> list[str]:
    found: list[str] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key in ("file_path", "path", "filename"):
                path = value.get(key)
                if isinstance(path, str) and path:
                    found.append(path)
            for nested in value.values():
                visit(nested)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    parsed = _json_object(raw)
    visit(parsed if parsed else raw)
    return found


def _walk_transcript(
    transcript_path: str | None,
) -> tuple[list[str], list[str], list[str], int]:
    # Returns (user_msgs_capped, tools_unique, files_unique, total_user_count).
    if not transcript_path:
        return [], [], [], 0

    try:
        lines_raw = Path(transcript_path).read_text(encoding="utf-8").splitlines()
    except Exception as exc:
        _log.warning("session_end: could not read transcript %s: %s", transcript_path, exc)
        return [], [], [], 0

    all_user_msgs: list[str] = []
    tools_seen: dict[str, None] = {}
    files_seen: dict[str, None] = {}

    for raw_line in lines_raw:
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            entry = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict):
            continue

        message = entry.get("message")
        if not isinstance(message, dict):
            message = {}
        payload = entry.get("payload")
        if not isinstance(payload, dict):
            payload = {}
        payload_type = payload.get("type", "")

        if payload_type == "function_call":
            tool_name = str(payload.get("name") or "")
            if tool_name and len(tools_seen) < _MAX_TOOLS:
                tools_seen[tool_name] = None
            for file_path in _extract_file_paths(payload.get("arguments")):
                if len(files_seen) >= _MAX_FILES:
                    break
                files_seen[file_path] = None
            continue

        # Determine role from Claude Code and Codex rollout formats.
        role = (
            entry.get("role")
            or message.get("role", "")
            or payload.get("role", "")
            or entry.get("type")
        )

        # Extract content regardless of nesting depth.
        content_raw = (
            entry.get("content")
            or message.get("content")
            or payload.get("content")
        )

        if role == "user":
            # Scrub before persisting: user prompts can contain pasted credentials,
            # and session files are later read by SessionStart for resume injection
            # (Codex H2 — sessions are a second write path that doctor.secret_scan
            # now also covers).
            text = scrub.scrub(_extract_text(content_raw).replace("\n", " ").strip())
            if text:
                all_user_msgs.append(text)

        elif role == "assistant":
            # Content blocks for assistant turns may contain tool_use entries.
            if isinstance(content_raw, list):
                for block in content_raw:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") != "tool_use":
                        continue
                    tool_name = block.get("name", "")
                    if tool_name and len(tools_seen) < _MAX_TOOLS:
                        tools_seen[tool_name] = None
                    if tool_name in _FILE_WRITE_TOOLS:
                        # input key differs between transcript versions.
                        tool_input = block.get("input") or block.get("tool_input") or {}
                        for file_path in _extract_file_paths(tool_input):
                            if len(files_seen) >= _MAX_FILES:
                                break
                            files_seen[file_path] = None

    total = len(all_user_msgs)
    capped_msgs = [m[:_MAX_USER_MSG_CHARS] for m in all_user_msgs[-_MAX_USER_MESSAGES:]]
    return capped_msgs, list(tools_seen.keys()), list(files_seen.keys()), total


def _build_summary_body(
    user_msgs: list[str],
    tools: list[str],
    files: list[str],
    total_user_count: int,
) -> str:
    lines: list[str] = ["## Session Summary"]

    lines.append("### Tasks")
    if user_msgs:
        for msg in user_msgs:
            lines.append(f"- {msg.rstrip()}")
    else:
        lines.append("- (no user messages captured)")

    lines.append("### Files Modified")
    if files:
        for f in files:
            lines.append(f"- {f}")
    else:
        lines.append("- (none)")

    lines.append("### Tools Used")
    lines.append(", ".join(tools) if tools else "(none)")

    lines.append("### Stats")
    lines.append(f"- Total user messages: {total_user_count}")

    return "\n".join(lines)


def _build_header(
    today: str,
    started_time: str,
    updated_time: str,
    project_name: str,
    branch: str,
    cwd_str: str,
) -> str:
    return (
        f"# Session: {today}\n"
        f"**Date:** {today}\n"
        f"**Started:** {started_time}\n"
        f"**Last Updated:** {updated_time}\n"
        f"**Project:** {project_name}\n"
        f"**Branch:** {branch}\n"
        f"**Worktree:** {cwd_str}"
    )


def _do_work(payload: dict[str, Any]) -> None:
    repo_root = _repo_root(payload)
    cwd_str = str(repo_root)
    transcript_path = payload.get("transcript_path")

    # Derive short_id from transcript UUID; fall back to session_id tail.
    short_id = session_id_lib.derive_short_id(transcript_path)
    if short_id is None:
        raw_sid = payload.get("session_id", "unknown")
        raw_tail = raw_sid[-8:].lower() if raw_sid else "unknown"
        # Apply the same sanitizer derive_short_id uses so the fallback path
        # component cannot contain separators regardless of payload source.
        short_id = re.sub(r"[^a-z0-9]", "", raw_tail) or "unknown"

    now_utc = datetime.now(timezone.utc)
    today = now_utc.strftime("%Y-%m-%d")
    current_time = now_utc.strftime("%H:%M:%S")

    sessions_dir = repo_root / ".claude" / "lightmem" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    session_file = sessions_dir / f"{today}-{short_id}.md"

    branch = git_utils.current_branch(cwd_str)
    project_name = repo_root.name

    user_msgs, tools, files, total_user_count = _walk_transcript(transcript_path)
    summary_body = _build_summary_body(user_msgs, tools, files, total_user_count)
    new_fence = markers.fence("SUMMARY", summary_body)

    if session_file.exists():
        existing = session_file.read_text(encoding="utf-8")

        # Preserve the original start time so repeated SessionEnd calls don't
        # reset it to the current time.
        started_match = _STARTED_RE.search(existing)
        started_time = started_match.group(1) if started_match else current_time

        # Replace the SUMMARY fence if one exists; otherwise append it.
        summary_re = markers.marker_pair_regex("SUMMARY")
        if summary_re.search(existing):
            updated_content = summary_re.sub(new_fence, existing)
        else:
            updated_content = existing.rstrip() + "\n\n" + new_fence + "\n"

        # Refresh only the Last Updated field; leave everything else intact.
        updated_content = _LAST_UPDATED_RE.sub(
            f"**Last Updated:** {current_time}", updated_content
        )
    else:
        started_time = current_time
        header = _build_header(
            today, started_time, current_time, project_name, branch, cwd_str
        )
        updated_content = f"{header}\n\n---\n\n{new_fence}\n"

    session_file.write_text(updated_content, encoding="utf-8")

    _auto_purge(repo_root)


def _auto_purge(repo_root: Path) -> None:
    lightmem_dir = repo_root / ".claude" / "lightmem"
    purge_marker = lightmem_dir / ".last-purge"

    if purge_marker.exists():
        age_seconds = (
            datetime.now(timezone.utc).timestamp() - purge_marker.stat().st_mtime
        )
        # Skip if already purged within the last 24 hours.
        if age_seconds < 86400:
            return

    raw_days = os.environ.get("LIGHTMEM_RETENTION_DAYS", "30")
    try:
        retention_days = int(raw_days.strip())
    except ValueError:
        _log.warning(
            "LIGHTMEM_RETENTION_DAYS=%r is not a valid integer; using default 30.", raw_days
        )
        retention_days = 30

    cutoff_ts = datetime.now(timezone.utc).timestamp() - retention_days * 86400

    sessions_dir = lightmem_dir / "sessions"
    if sessions_dir.is_dir():
        for f in sessions_dir.glob("*.md"):
            try:
                if f.stat().st_mtime < cutoff_ts:
                    f.unlink()
            except Exception as exc:
                _log.warning("session_end: could not delete %s: %s", f, exc)

    archive_dir = lightmem_dir / "archive"
    if archive_dir.is_dir():
        for f in archive_dir.glob("journal-*.jsonl"):
            try:
                if f.stat().st_mtime < cutoff_ts:
                    f.unlink()
            except Exception as exc:
                _log.warning("session_end: could not delete %s: %s", f, exc)

    # Touch the marker to record when the last purge ran.
    lightmem_dir.mkdir(parents=True, exist_ok=True)
    purge_marker.touch()


if __name__ == "__main__":
    main()
