from __future__ import annotations

"""
Integration tests for scripts/hooks/session_end.py

Derived purely from PRD_v0.2.md §6.3, §5.5, §10, §12 P2/P4/P5.
No hook implementation files were read during authoring.

Key behaviours under test:
  - Creates .claude/lightmem/sessions/<YYYY-MM-DD>-<shortId>.md on first run.
  - Session file has standard header fields: # Session, **Date:**, **Project:**,
    **Branch:**, **Worktree:**, then --- separator.
  - SUMMARY block is marker-fenced:
        <!-- LIGHTMEM:SUMMARY:START --> ... <!-- LIGHTMEM:SUMMARY:END -->
  - Re-running on same transcript_path (same shortId): only ONE SUMMARY fence,
    and user-authored content outside the fence is preserved.
  - Missing/unreadable transcript_path: file still created with header.
  - Auto-purge: old session files (mtime > LIGHTMEM_RETENTION_DAYS) are deleted
    when .last-purge does not exist (or is also old).
  - Auto-purge gate: fresh .last-purge → purge does NOT run.
  - LIGHTMEM_HOOK_PROFILE=off → no session file created.
  - Exit code is ALWAYS 0.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "hooks" / "session_end.py"

# Markers defined in PRD §6.3 (idempotent marker-block pattern)
_SUMMARY_START = "<!-- LIGHTMEM:SUMMARY:START -->"
_SUMMARY_END = "<!-- LIGHTMEM:SUMMARY:END -->"

# Known UUID whose last 8 chars of last group = "9b9b3ca0"
_TRANSCRIPT_UUID = "00893aaf-19fa-41d2-8238-13269b9b3ca0"
_TRANSCRIPT_PATH = f"/tmp/{_TRANSCRIPT_UUID}.jsonl"
_SHORT_ID = "9b9b3ca0"
_CODEX_ROLLOUT_UUID = "019ce567-ecc8-7613-a0f8-f8b0db87d1f6"
_CODEX_SHORT_ID = "db87d1f6"

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


def _minimal_payload(
    cwd: str,
    transcript_path: str = _TRANSCRIPT_PATH,
) -> dict:
    return {
        "hook_event_name": "SessionEnd",
        "cwd": cwd,
        "session_id": "test-session-end",
        "transcript_path": transcript_path,
    }


def _init_lightmem(tmpdir: str) -> Path:
    """Create the .claude/lightmem/ skeleton inside *tmpdir*."""
    root = Path(tmpdir)
    lightmem = root / ".claude" / "lightmem"
    lightmem.mkdir(parents=True)
    (lightmem / "sessions").mkdir()
    (lightmem / "archive").mkdir()
    return root


def _sessions_dir(tmpdir: str) -> Path:
    return Path(tmpdir) / ".claude" / "lightmem" / "sessions"


def _find_session_file(tmpdir: str, short_id: str = _SHORT_ID) -> Path | None:
    """Return the session file whose name ends with '-<short_id>.md', or None."""
    sd = _sessions_dir(tmpdir)
    if not sd.exists():
        return None
    for f in sd.glob(f"*-{short_id}.md"):
        return f
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Test: exit code is always 0
# ──────────────────────────────────────────────────────────────────────────────

class TestSessionEndAlwaysExitsZero(unittest.TestCase):
    """PRD §6.3 step 6, §12 P4 item 14."""

    def test_exit_zero_normal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            result = _run_hook(_minimal_payload(tmpdir), repo_path=tmpdir)
            self.assertEqual(result.returncode, 0)

    def test_exit_zero_no_transcript(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            payload = _minimal_payload(tmpdir, transcript_path="/does/not/exist.jsonl")
            result = _run_hook(payload, repo_path=tmpdir)
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
                input="bad json",
                capture_output=True,
                text=True,
                timeout=10,
                env=env,
                cwd=tmpdir,
            )
            self.assertEqual(result.returncode, 0)


# ──────────────────────────────────────────────────────────────────────────────
# Test: basic session file creation
# ──────────────────────────────────────────────────────────────────────────────

class TestSessionEndBasicFileCreation(unittest.TestCase):
    """PRD §6.3 step 4: write sessions/<date>-<shortId>.md; §12 P2 item 7."""

    def test_session_file_created(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            _run_hook(_minimal_payload(tmpdir), repo_path=tmpdir)
            session_file = _find_session_file(tmpdir)
            self.assertIsNotNone(
                session_file,
                f"Expected session file *-{_SHORT_ID}.md in sessions/",
            )

    def test_session_file_name_contains_date(self) -> None:
        """Filename must be <YYYY-MM-DD>-<shortId>.md."""
        import re
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            _run_hook(_minimal_payload(tmpdir), repo_path=tmpdir)
            session_file = _find_session_file(tmpdir)
            self.assertIsNotNone(session_file)
            # Filename: YYYY-MM-DD-<8hexchars>.md
            self.assertRegex(
                session_file.name,
                r"^\d{4}-\d{2}-\d{2}-[0-9a-f]{8}\.md$",
            )

    def test_session_file_name_contains_short_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            _run_hook(_minimal_payload(tmpdir), repo_path=tmpdir)
            session_file = _find_session_file(tmpdir)
            self.assertIsNotNone(session_file)
            self.assertIn(_SHORT_ID, session_file.name)

    def test_session_file_is_nonempty(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            _run_hook(_minimal_payload(tmpdir), repo_path=tmpdir)
            session_file = _find_session_file(tmpdir)
            self.assertIsNotNone(session_file)
            content = session_file.read_text(encoding="utf-8")
            self.assertGreater(len(content.strip()), 0)


# ──────────────────────────────────────────────────────────────────────────────
# Test: session file header structure
# ──────────────────────────────────────────────────────────────────────────────

class TestSessionEndFileHeader(unittest.TestCase):
    """PRD §6.3: session file has standard header fields."""

    def _get_content(self, tmpdir: str) -> str:
        _init_lightmem(tmpdir)
        _run_hook(_minimal_payload(tmpdir), repo_path=tmpdir)
        session_file = _find_session_file(tmpdir)
        self.assertIsNotNone(session_file, "Session file not created")
        return session_file.read_text(encoding="utf-8")

    def test_header_contains_session_title(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            content = self._get_content(tmpdir)
            self.assertIn("# Session:", content)

    def test_header_contains_date_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            content = self._get_content(tmpdir)
            self.assertIn("**Date:**", content)

    def test_header_contains_project_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            content = self._get_content(tmpdir)
            self.assertIn("**Project:**", content)

    def test_header_contains_worktree_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            content = self._get_content(tmpdir)
            self.assertIn("**Worktree:**", content)

    def test_header_contains_separator(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            content = self._get_content(tmpdir)
            self.assertIn("---", content)

    def test_header_contains_summary_start_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            content = self._get_content(tmpdir)
            self.assertIn(_SUMMARY_START, content)

    def test_header_contains_summary_end_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            content = self._get_content(tmpdir)
            self.assertIn(_SUMMARY_END, content)

    def test_summary_start_before_summary_end(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            content = self._get_content(tmpdir)
            start_pos = content.find(_SUMMARY_START)
            end_pos = content.find(_SUMMARY_END)
            self.assertGreater(start_pos, -1)
            self.assertGreater(end_pos, start_pos)


# ──────────────────────────────────────────────────────────────────────────────
# Test: idempotency — re-running does not duplicate SUMMARY fence
# ──────────────────────────────────────────────────────────────────────────────

class TestSessionEndIdempotency(unittest.TestCase):
    """PRD §6.3 step 4 + §12 P2 item 8: re-run updates only the SUMMARY fence."""

    def test_single_summary_start_marker_after_two_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            _run_hook(_minimal_payload(tmpdir), repo_path=tmpdir)
            _run_hook(_minimal_payload(tmpdir), repo_path=tmpdir)
            session_file = _find_session_file(tmpdir)
            self.assertIsNotNone(session_file)
            content = session_file.read_text(encoding="utf-8")
            count = content.count(_SUMMARY_START)
            self.assertEqual(
                count,
                1,
                msg=f"Expected exactly 1 SUMMARY:START marker, found {count}",
            )

    def test_single_summary_end_marker_after_two_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            _run_hook(_minimal_payload(tmpdir), repo_path=tmpdir)
            _run_hook(_minimal_payload(tmpdir), repo_path=tmpdir)
            session_file = _find_session_file(tmpdir)
            self.assertIsNotNone(session_file)
            content = session_file.read_text(encoding="utf-8")
            count = content.count(_SUMMARY_END)
            self.assertEqual(
                count,
                1,
                msg=f"Expected exactly 1 SUMMARY:END marker, found {count}",
            )

    def test_user_content_outside_summary_fence_preserved(self) -> None:
        """PRD §6.3: user-authored sections outside the SUMMARY fence survive re-runs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            # First run: creates the file
            _run_hook(_minimal_payload(tmpdir), repo_path=tmpdir)
            session_file = _find_session_file(tmpdir)
            self.assertIsNotNone(session_file)

            # Append user-authored content AFTER the SUMMARY:END marker
            user_note = "\n## My Notes\n\nThis is a user-authored section.\n"
            with session_file.open("a", encoding="utf-8") as fh:
                fh.write(user_note)

            # Second run: should update the SUMMARY fence, preserve the note
            _run_hook(_minimal_payload(tmpdir), repo_path=tmpdir)

            content = session_file.read_text(encoding="utf-8")
            self.assertIn("My Notes", content)
            self.assertIn("This is a user-authored section.", content)

    def test_only_one_session_file_after_two_runs(self) -> None:
        """A second run with the same shortId must not create a duplicate file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            _run_hook(_minimal_payload(tmpdir), repo_path=tmpdir)
            _run_hook(_minimal_payload(tmpdir), repo_path=tmpdir)
            files = list(_sessions_dir(tmpdir).glob(f"*-{_SHORT_ID}.md"))
            self.assertEqual(len(files), 1)


# ──────────────────────────────────────────────────────────────────────────────
# Test: missing transcript_path
# ──────────────────────────────────────────────────────────────────────────────

class TestSessionEndMissingTranscript(unittest.TestCase):
    """PRD §6.3: unreadable transcript → file still created with header."""

    def test_session_file_created_when_transcript_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            # Use a transcript_path with a UUID so shortId can be derived,
            # but the file itself does not exist
            payload = _minimal_payload(
                tmpdir,
                transcript_path=f"/does/not/exist/{_TRANSCRIPT_UUID}.jsonl",
            )
            _run_hook(payload, repo_path=tmpdir)
            session_file = _find_session_file(tmpdir)
            self.assertIsNotNone(
                session_file,
                "Session file must be created even when transcript is missing",
            )

    def test_session_file_has_header_when_transcript_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            payload = _minimal_payload(
                tmpdir,
                transcript_path=f"/does/not/exist/{_TRANSCRIPT_UUID}.jsonl",
            )
            _run_hook(payload, repo_path=tmpdir)
            session_file = _find_session_file(tmpdir)
            self.assertIsNotNone(session_file)
            content = session_file.read_text(encoding="utf-8")
            self.assertIn("**Date:**", content)
            self.assertIn("**Project:**", content)


# ──────────────────────────────────────────────────────────────────────────────
# Test: LIGHTMEM_HOOK_PROFILE=off
# ──────────────────────────────────────────────────────────────────────────────

class TestSessionEndProfileOff(unittest.TestCase):
    """PRD §10.1 / §12 P5 item 15: profile=off → no session file created."""

    def test_no_session_file_created_profile_off(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            _run_hook(
                _minimal_payload(tmpdir),
                env_overrides={"LIGHTMEM_HOOK_PROFILE": "off"},
                repo_path=tmpdir,
            )
            session_file = _find_session_file(tmpdir)
            self.assertIsNone(
                session_file,
                "No session file should be created when LIGHTMEM_HOOK_PROFILE=off",
            )

    def test_sessions_dir_empty_profile_off(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            _run_hook(
                _minimal_payload(tmpdir),
                env_overrides={"LIGHTMEM_HOOK_PROFILE": "off"},
                repo_path=tmpdir,
            )
            sd = _sessions_dir(tmpdir)
            if sd.exists():
                self.assertEqual(
                    list(sd.glob("*.md")),
                    [],
                    "No .md files should exist in sessions/ when profile=off",
                )


# ──────────────────────────────────────────────────────────────────────────────
# Test: Codex H2 — session-file secret scrubbing
# ──────────────────────────────────────────────────────────────────────────────

class TestSessionEndScrubsSecrets(unittest.TestCase):
    # Session files are read back by SessionStart on resume, so unscrubbed
    # user prompts would leak credentials across sessions. Codex H2.

    def _write_transcript_with_secret(self, tmpdir: str) -> str:
        secret_line = (
            '{"type":"user","content":"please commit this. api_key=sssssecret12345xyz"}\n'
        )
        path = Path(tmpdir) / "transcript-with-secret.jsonl"
        path.write_text(secret_line, encoding="utf-8")
        return str(path)

    def test_user_message_with_secret_redacted_in_session_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            tp = self._write_transcript_with_secret(tmpdir)
            payload = _minimal_payload(tmpdir, transcript_path=tp)
            _run_hook(payload, repo_path=tmpdir)
            sessions_dir = Path(tmpdir) / ".claude" / "lightmem" / "sessions"
            files = list(sessions_dir.glob("*.md"))
            self.assertEqual(len(files), 1)
            content = files[0].read_text(encoding="utf-8")
            self.assertNotIn(
                "sssssecret12345xyz", content,
                "secret leaked into session file",
            )
            self.assertIn("[REDACTED]", content)


# ──────────────────────────────────────────────────────────────────────────────
# Test: Codex rollout transcript parsing
# ──────────────────────────────────────────────────────────────────────────────

class TestSessionEndCodexTranscriptParsing(unittest.TestCase):
    """Codex stores messages and tool calls under response_item.payload."""

    def _write_codex_rollout(self, tmpdir: str) -> str:
        path = Path(tmpdir) / (
            "rollout-2026-03-13T12-15-19-"
            f"{_CODEX_ROLLOUT_UUID}.jsonl"
        )
        lines = [
            {
                "type": "session_meta",
                "payload": {
                    "id": _CODEX_ROLLOUT_UUID,
                    "cwd": tmpdir,
                    "originator": "codex_cli_rs",
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "Implement dual Codex and Claude support.",
                        }
                    ],
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "exec_command",
                    "arguments": "{\"cmd\":\"rg Codex README.md\"}",
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "apply_patch",
                    "arguments": "{\"file_path\":\"README.md\"}",
                },
            },
        ]
        path.write_text(
            "\n".join(json.dumps(line) for line in lines) + "\n",
            encoding="utf-8",
        )
        return str(path)

    def test_codex_payload_user_message_is_captured(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            tp = self._write_codex_rollout(tmpdir)
            _run_hook(_minimal_payload(tmpdir, transcript_path=tp), repo_path=tmpdir)
            session_file = _find_session_file(tmpdir, _CODEX_SHORT_ID)
            self.assertIsNotNone(session_file)
            content = session_file.read_text(encoding="utf-8")
            self.assertIn("Implement dual Codex and Claude support.", content)

    def test_codex_payload_tool_calls_are_captured(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            tp = self._write_codex_rollout(tmpdir)
            _run_hook(_minimal_payload(tmpdir, transcript_path=tp), repo_path=tmpdir)
            session_file = _find_session_file(tmpdir, _CODEX_SHORT_ID)
            self.assertIsNotNone(session_file)
            content = session_file.read_text(encoding="utf-8")
            self.assertIn("exec_command", content)
            self.assertIn("apply_patch", content)

    def test_codex_payload_file_path_is_captured(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            tp = self._write_codex_rollout(tmpdir)
            _run_hook(_minimal_payload(tmpdir, transcript_path=tp), repo_path=tmpdir)
            session_file = _find_session_file(tmpdir, _CODEX_SHORT_ID)
            self.assertIsNotNone(session_file)
            content = session_file.read_text(encoding="utf-8")
            self.assertIn("README.md", content)


# ──────────────────────────────────────────────────────────────────────────────
# Test: auto-purge
# ──────────────────────────────────────────────────────────────────────────────

class TestSessionEndAutoPurge(unittest.TestCase):
    """PRD §6.3 step 5: auto-purge deletes old session files once per day.

    The purge runs when .last-purge does NOT exist (or is older than retention).
    Files older than LIGHTMEM_RETENTION_DAYS are deleted.
    """

    def _backdate_mtime(self, path: Path, days: int) -> None:
        """Set the mtime of *path* to *days* ago."""
        old_ts = time.time() - days * 86400
        os.utime(str(path), (old_ts, old_ts))

    def test_old_session_file_deleted_when_no_last_purge(self) -> None:
        """Old session file (60 days old) is purged; no .last-purge present."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            sd = _sessions_dir(tmpdir)

            # Create an old session file (unrelated UUID, 60 days old)
            old_short_id = "deadbeef"
            old_session = sd / f"2026-03-22-{old_short_id}.md"
            old_session.write_text("# Old session\n", encoding="utf-8")
            self._backdate_mtime(old_session, 60)

            # Confirm .last-purge does not exist
            last_purge = Path(tmpdir) / ".claude" / "lightmem" / ".last-purge"
            self.assertFalse(last_purge.exists())

            # Run session_end for a NEW transcript (different short_id)
            _run_hook(
                _minimal_payload(tmpdir),
                env_overrides={"LIGHTMEM_RETENTION_DAYS": "30"},
                repo_path=tmpdir,
            )

            # The old file should have been purged
            self.assertFalse(
                old_session.exists(),
                f"Expected old session file to be purged, but it still exists: {old_session}",
            )

    def test_recent_session_file_not_deleted(self) -> None:
        """A 5-day-old session file is within retention and must NOT be deleted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            sd = _sessions_dir(tmpdir)

            recent_short_id = "cafebabe"
            recent_session = sd / f"2026-05-16-{recent_short_id}.md"
            recent_session.write_text("# Recent session\n", encoding="utf-8")
            self._backdate_mtime(recent_session, 5)

            # No .last-purge so purge runs
            _run_hook(
                _minimal_payload(tmpdir),
                env_overrides={"LIGHTMEM_RETENTION_DAYS": "30"},
                repo_path=tmpdir,
            )

            self.assertTrue(
                recent_session.exists(),
                "Recent session file (5 days old) must not be purged with 30-day retention",
            )

    def test_purge_gated_by_fresh_last_purge(self) -> None:
        """PRD §6.3 step 5: if .last-purge is fresh (just touched), purge does NOT run."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            sd = _sessions_dir(tmpdir)
            lightmem_dir = Path(tmpdir) / ".claude" / "lightmem"

            # Create an old session file
            old_short_id = "f00dcafe"
            old_session = sd / f"2026-03-22-{old_short_id}.md"
            old_session.write_text("# Old session\n", encoding="utf-8")
            self._backdate_mtime(old_session, 60)

            # Create a fresh .last-purge (just touched = now)
            last_purge = lightmem_dir / ".last-purge"
            last_purge.touch()

            # Run session_end with retention=30 days
            _run_hook(
                _minimal_payload(tmpdir),
                env_overrides={"LIGHTMEM_RETENTION_DAYS": "30"},
                repo_path=tmpdir,
            )

            # Old file must still exist because .last-purge was fresh
            self.assertTrue(
                old_session.exists(),
                "Old session file must NOT be purged when .last-purge is fresh",
            )


if __name__ == "__main__":
    unittest.main()
