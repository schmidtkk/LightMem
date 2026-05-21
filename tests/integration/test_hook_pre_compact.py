from __future__ import annotations

"""
Integration tests for scripts/hooks/pre_compact.py

Derived purely from PRD_v0.2.md §6.4, §10, §12 P4/P5.
No hook implementation files were read during authoring.

PRD §6.4 (verbatim pattern from ECC pre-compact.js) specifies two actions:

  1. Append ``[<ts>] Context compaction triggered (trigger=<manual|auto>)\\n``
     to ``<cwd>/.claude/lightmem/compaction-log.txt``.
  2. If an active session file exists for today, append
     ``\\n---\\n**[Compaction occurred at <time>]**\\n`` to it.

Additional constraints:
  - Creates parent dirs if missing.
  - LIGHTMEM_HOOK_PROFILE=off → nothing is written.
  - Exit code is ALWAYS 0.
"""

import datetime
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "hooks" / "pre_compact.py"

_COMPACTION_LOG_RELPATH = ".claude/lightmem/compaction-log.txt"

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _build_env(overrides: dict[str, str] | None = None) -> dict[str, str]:
    env: dict[str, str] = os.environ.copy()
    env["PYTHONPATH"] = str(_REPO_ROOT)
    if overrides:
        env.update(overrides)
    return env


def _run_hook(
    payload: dict,
    env_overrides: dict[str, str] | None = None,
    repo_path: str | None = None,
) -> subprocess.CompletedProcess:
    env = _build_env(env_overrides)
    return subprocess.run(
        [sys.executable, str(_SCRIPT)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
        env=env,
        cwd=repo_path,
    )


def _minimal_payload(cwd: str, trigger: str = "manual") -> dict:
    return {
        "hook_event_name": "PreCompact",
        "cwd": cwd,
        "trigger": trigger,
    }


def _compaction_log(tmpdir: str) -> Path:
    return Path(tmpdir) / _COMPACTION_LOG_RELPATH


def _init_lightmem(tmpdir: str) -> Path:
    """Create .claude/lightmem/ and its sub-dirs inside *tmpdir*."""
    root = Path(tmpdir)
    lightmem = root / ".claude" / "lightmem"
    lightmem.mkdir(parents=True)
    (lightmem / "sessions").mkdir()
    (lightmem / "archive").mkdir()
    return root


def _today_str() -> str:
    """Return today's date as YYYY-MM-DD (matches session file naming)."""
    return datetime.date.today().strftime("%Y-%m-%d")


def _create_todays_session_file(tmpdir: str, short_id: str = "aabbccdd") -> Path:
    """Create a session file for today's date and return its path."""
    sessions_dir = Path(tmpdir) / ".claude" / "lightmem" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    session_file = sessions_dir / f"{_today_str()}-{short_id}.md"
    session_file.write_text(
        f"# Session: {_today_str()}\n\n"
        "**Date:** 2026-05-21\n"
        "**Project:** LightMem\n"
        "**Branch:** main\n"
        "**Worktree:** /tmp/example-repo\n\n"
        "---\n\n"
        "<!-- LIGHTMEM:SUMMARY:START -->\n"
        "Working on pre_compact hook.\n"
        "<!-- LIGHTMEM:SUMMARY:END -->\n",
        encoding="utf-8",
    )
    return session_file


# ──────────────────────────────────────────────────────────────────────────────
# Test: exit code is always 0
# ──────────────────────────────────────────────────────────────────────────────

class TestPreCompactAlwaysExitsZero(unittest.TestCase):
    """PRD §6.4 (implicit) + §12 P4 item 14: exit 0 in all cases."""

    def test_exit_zero_normal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            result = _run_hook(_minimal_payload(tmpdir), repo_path=tmpdir)
            self.assertEqual(result.returncode, 0)

    def test_exit_zero_no_lightmem_dir(self) -> None:
        """Hook must create missing dirs and still exit 0."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Do NOT call _init_lightmem — no .claude/lightmem/
            result = _run_hook(_minimal_payload(tmpdir), repo_path=tmpdir)
            self.assertEqual(result.returncode, 0)

    def test_exit_zero_profile_off(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            result = _run_hook(
                _minimal_payload(tmpdir),
                env_overrides={"LIGHTMEM_HOOK_PROFILE": "off"},
                repo_path=tmpdir,
            )
            self.assertEqual(result.returncode, 0)

    def test_exit_zero_malformed_stdin(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env = _build_env()
            result = subprocess.run(
                [sys.executable, str(_SCRIPT)],
                input="not json",
                capture_output=True,
                text=True,
                timeout=10,
                env=env,
                cwd=tmpdir,
            )
            self.assertEqual(result.returncode, 0)

    def test_exit_zero_no_session_file(self) -> None:
        """Even if no today's session file exists, the hook must exit 0."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            # sessions/ dir is empty — no session file today
            result = _run_hook(_minimal_payload(tmpdir), repo_path=tmpdir)
            self.assertEqual(result.returncode, 0)


# ──────────────────────────────────────────────────────────────────────────────
# Test: compaction-log.txt creation and content
# ──────────────────────────────────────────────────────────────────────────────

class TestPreCompactLogFile(unittest.TestCase):
    """PRD §6.4 action 1: append one timestamped line to compaction-log.txt."""

    def test_compaction_log_created(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            _run_hook(_minimal_payload(tmpdir), repo_path=tmpdir)
            log = _compaction_log(tmpdir)
            self.assertTrue(log.exists(), f"Expected {log} to exist")

    def test_compaction_log_has_one_line_after_first_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            _run_hook(_minimal_payload(tmpdir), repo_path=tmpdir)
            log = _compaction_log(tmpdir)
            lines = [l for l in log.read_text(encoding="utf-8").splitlines() if l.strip()]
            self.assertEqual(len(lines), 1)

    def test_log_line_starts_with_bracket(self) -> None:
        """PRD §6.4: line format starts with '[<ts>]'."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            _run_hook(_minimal_payload(tmpdir), repo_path=tmpdir)
            log = _compaction_log(tmpdir)
            first_line = log.read_text(encoding="utf-8").strip().splitlines()[0]
            self.assertTrue(
                first_line.startswith("["),
                msg=f"Expected line to start with '[', got: {first_line!r}",
            )

    def test_log_line_contains_context_compaction_triggered(self) -> None:
        """PRD §6.4: line must contain 'Context compaction triggered'."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            _run_hook(_minimal_payload(tmpdir), repo_path=tmpdir)
            content = _compaction_log(tmpdir).read_text(encoding="utf-8")
            self.assertIn("Context compaction triggered", content)

    def test_log_line_contains_trigger_equals_manual(self) -> None:
        """PRD §6.4: line must contain 'trigger=manual'."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            _run_hook(_minimal_payload(tmpdir, trigger="manual"), repo_path=tmpdir)
            content = _compaction_log(tmpdir).read_text(encoding="utf-8")
            self.assertIn("trigger=manual", content)

    def test_log_line_contains_trigger_equals_auto(self) -> None:
        """PRD §6.4: line must contain 'trigger=auto' for trigger=auto payload."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            _run_hook(_minimal_payload(tmpdir, trigger="auto"), repo_path=tmpdir)
            content = _compaction_log(tmpdir).read_text(encoding="utf-8")
            self.assertIn("trigger=auto", content)


# ──────────────────────────────────────────────────────────────────────────────
# Test: appending (not overwriting) on re-runs
# ──────────────────────────────────────────────────────────────────────────────

class TestPreCompactLogAppend(unittest.TestCase):
    """PRD §6.4: each hook invocation appends; does not overwrite."""

    def test_two_runs_produce_two_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            _run_hook(_minimal_payload(tmpdir), repo_path=tmpdir)
            _run_hook(_minimal_payload(tmpdir), repo_path=tmpdir)
            log = _compaction_log(tmpdir)
            lines = [l for l in log.read_text(encoding="utf-8").splitlines() if l.strip()]
            self.assertEqual(len(lines), 2)

    def test_three_runs_produce_three_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            for _ in range(3):
                _run_hook(_minimal_payload(tmpdir), repo_path=tmpdir)
            log = _compaction_log(tmpdir)
            lines = [l for l in log.read_text(encoding="utf-8").splitlines() if l.strip()]
            self.assertEqual(len(lines), 3)

    def test_existing_log_content_preserved(self) -> None:
        """Pre-existing log content must be retained after a new run."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            log = _compaction_log(tmpdir)
            log.parent.mkdir(parents=True, exist_ok=True)
            log.write_text("[2026-05-20T00:00:00+00:00] Prior compaction entry\n", encoding="utf-8")

            _run_hook(_minimal_payload(tmpdir), repo_path=tmpdir)

            content = log.read_text(encoding="utf-8")
            self.assertIn("Prior compaction entry", content)
            self.assertIn("Context compaction triggered", content)


# ──────────────────────────────────────────────────────────────────────────────
# Test: creates parent dirs if missing
# ──────────────────────────────────────────────────────────────────────────────

class TestPreCompactCreatesDirs(unittest.TestCase):
    """PRD §6.4: parent dirs created if missing."""

    def test_log_created_when_lightmem_dir_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            # No .claude/lightmem/ exists
            result = _run_hook(_minimal_payload(tmpdir), repo_path=tmpdir)
            self.assertEqual(result.returncode, 0)
            log = _compaction_log(tmpdir)
            self.assertTrue(log.exists(), "compaction-log.txt must be created even without pre-existing .claude/lightmem/")

    def test_log_content_correct_when_dirs_auto_created(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _run_hook(_minimal_payload(tmpdir), repo_path=tmpdir)
            content = _compaction_log(tmpdir).read_text(encoding="utf-8")
            self.assertIn("Context compaction triggered", content)


# ──────────────────────────────────────────────────────────────────────────────
# Test: today's session file gets compaction marker appended
# ──────────────────────────────────────────────────────────────────────────────

class TestPreCompactSessionFileMarker(unittest.TestCase):
    """PRD §6.4 action 2: today's session file gets '**[Compaction occurred at HH:MM:SS]**'."""

    def test_compaction_marker_appended_to_session_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            session_file = _create_todays_session_file(tmpdir)
            original_content = session_file.read_text(encoding="utf-8")

            _run_hook(_minimal_payload(tmpdir), repo_path=tmpdir)

            new_content = session_file.read_text(encoding="utf-8")
            # PRD §6.4: appends '**[Compaction occurred at <time>]**'
            self.assertIn("**[Compaction occurred at", new_content)

    def test_session_file_original_content_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            session_file = _create_todays_session_file(tmpdir)

            _run_hook(_minimal_payload(tmpdir), repo_path=tmpdir)

            content = session_file.read_text(encoding="utf-8")
            self.assertIn("Working on pre_compact hook.", content)
            self.assertIn("# Session:", content)

    def test_compaction_marker_contains_time(self) -> None:
        """The appended marker must include a time component (HH:MM:SS format)."""
        import re
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            session_file = _create_todays_session_file(tmpdir)

            _run_hook(_minimal_payload(tmpdir), repo_path=tmpdir)

            content = session_file.read_text(encoding="utf-8")
            # Match **[Compaction occurred at HH:MM:SS]**
            self.assertRegex(content, r"\*\*\[Compaction occurred at \d{2}:\d{2}:\d{2}\]")

    def test_compaction_separator_appended(self) -> None:
        """PRD §6.4: appends \\n---\\n before the marker."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            session_file = _create_todays_session_file(tmpdir)
            original_content = session_file.read_text(encoding="utf-8")

            _run_hook(_minimal_payload(tmpdir), repo_path=tmpdir)

            new_content = session_file.read_text(encoding="utf-8")
            appended = new_content[len(original_content):]
            self.assertIn("---", appended)

    def test_no_session_file_created_when_none_exists_today(self) -> None:
        """PRD §6.4: if no today's session file, only compaction-log.txt is touched."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            # sessions/ dir is empty — no session file for today
            _run_hook(_minimal_payload(tmpdir), repo_path=tmpdir)

            # No session file should have been created
            sd = Path(tmpdir) / ".claude" / "lightmem" / "sessions"
            today_files = list(sd.glob(f"{_today_str()}-*.md"))
            self.assertEqual(
                len(today_files),
                0,
                f"Expected no session file created by pre_compact when none existed: {today_files}",
            )

    def test_only_compaction_log_touched_when_no_session_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            _run_hook(_minimal_payload(tmpdir), repo_path=tmpdir)
            # compaction-log.txt must exist
            self.assertTrue(_compaction_log(tmpdir).exists())


# ──────────────────────────────────────────────────────────────────────────────
# Test: LIGHTMEM_HOOK_PROFILE=off
# ──────────────────────────────────────────────────────────────────────────────

class TestPreCompactProfileOff(unittest.TestCase):
    """PRD §10.1 / §12 P5 item 15: profile=off → nothing written."""

    def test_no_log_created_when_profile_off(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            _run_hook(
                _minimal_payload(tmpdir),
                env_overrides={"LIGHTMEM_HOOK_PROFILE": "off"},
                repo_path=tmpdir,
            )
            log = _compaction_log(tmpdir)
            self.assertFalse(
                log.exists(),
                "compaction-log.txt must NOT be created when LIGHTMEM_HOOK_PROFILE=off",
            )

    def test_session_file_unchanged_when_profile_off(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            session_file = _create_todays_session_file(tmpdir)
            original_content = session_file.read_text(encoding="utf-8")

            _run_hook(
                _minimal_payload(tmpdir),
                env_overrides={"LIGHTMEM_HOOK_PROFILE": "off"},
                repo_path=tmpdir,
            )

            new_content = session_file.read_text(encoding="utf-8")
            self.assertEqual(
                original_content,
                new_content,
                "Session file must not be modified when LIGHTMEM_HOOK_PROFILE=off",
            )

    def test_no_error_on_stderr_when_profile_off(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            result = _run_hook(
                _minimal_payload(tmpdir),
                env_overrides={"LIGHTMEM_HOOK_PROFILE": "off"},
                repo_path=tmpdir,
            )
            self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
