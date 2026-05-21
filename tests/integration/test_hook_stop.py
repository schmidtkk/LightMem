from __future__ import annotations

"""
Integration tests for scripts/hooks/stop.py

Derived purely from PRD_v0.2.md §6.2, §6.2.1, §10, §12 P1/P4/P5.
No hook implementation files were read during authoring.

The Stop hook fires after every assistant turn (async, PRD D4).

Key behaviours under test:
  - Re-entry guard: stop_hook_active=true → exit 0, no journal write.
  - LIGHTMEM_HOOK_PROFILE=off → exit 0, no journal write.
  - LIGHTMEM_DISABLED_HOOKS=Stop → exit 0, no journal write.
  - Normal path → appends exactly ONE JSONL line to journal.jsonl.
  - Journal line has all required fields from §6.2.1.
  - last_assistant_message is scrubbed before excerpting (secrets → [REDACTED]).
  - Excerpt is truncated to 200 chars.
  - transcript_uuid_tail is last 8 hex chars of UUID in transcript_path, or null.
  - Exit code is ALWAYS 0.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "hooks" / "stop.py"

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
    *,
    stop_hook_active: bool = False,
    last_assistant_message: str = "Hello from the assistant.",
    transcript_path: str = "/tmp/00893aaf-19fa-41d2-8238-13269b9b3ca0.jsonl",
) -> dict:
    return {
        "hook_event_name": "Stop",
        "stop_hook_active": stop_hook_active,
        "cwd": cwd,
        "session_id": "test-session-stop",
        "last_assistant_message": last_assistant_message,
        "transcript_path": transcript_path,
        "model": "claude-sonnet-4-6",
    }


def _init_lightmem(tmpdir: str) -> Path:
    """Create the .claude/lightmem/ structure inside *tmpdir*."""
    root = Path(tmpdir)
    lightmem = root / ".claude" / "lightmem"
    lightmem.mkdir(parents=True)
    (lightmem / "sessions").mkdir()
    (lightmem / "archive").mkdir()
    return root


def _journal_path(tmpdir: str) -> Path:
    return Path(tmpdir) / ".claude" / "lightmem" / "journal.jsonl"


def _read_journal_lines(tmpdir: str) -> list[dict]:
    """Return all parsed JSONL lines from journal.jsonl, empty list if absent."""
    jp = _journal_path(tmpdir)
    if not jp.exists():
        return []
    lines = []
    for raw in jp.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if raw:
            lines.append(json.loads(raw))
    return lines


# ──────────────────────────────────────────────────────────────────────────────
# Test: exit code is always 0
# ──────────────────────────────────────────────────────────────────────────────

class TestStopAlwaysExitsZero(unittest.TestCase):
    """PRD §6.2 step 6, §12 P4 item 14."""

    def test_exit_zero_normal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            result = _run_hook(_minimal_payload(tmpdir), repo_path=tmpdir)
            self.assertEqual(result.returncode, 0)

    def test_exit_zero_stop_hook_active(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            result = _run_hook(
                _minimal_payload(tmpdir, stop_hook_active=True), repo_path=tmpdir
            )
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

    def test_exit_zero_disabled_hooks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            result = _run_hook(
                _minimal_payload(tmpdir),
                env_overrides={"LIGHTMEM_DISABLED_HOOKS": "Stop"},
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


# ──────────────────────────────────────────────────────────────────────────────
# Test: re-entry guard (stop_hook_active=true)
# ──────────────────────────────────────────────────────────────────────────────

class TestStopReentryGuard(unittest.TestCase):
    """PRD §6.2 step 1: stop_hook_active=true → exit 0, no journal write."""

    def test_no_journal_write_when_active(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            result = _run_hook(
                _minimal_payload(tmpdir, stop_hook_active=True), repo_path=tmpdir
            )
            self.assertEqual(result.returncode, 0)
            lines = _read_journal_lines(tmpdir)
            self.assertEqual(len(lines), 0, "Expected no journal write when stop_hook_active=true")

    def test_journal_unchanged_when_active_and_journal_exists(self) -> None:
        """If journal already has a line, stop_hook_active=true must not add another."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            # Pre-populate with one entry
            jp = _journal_path(tmpdir)
            existing_entry = json.dumps({"ts": "2026-05-20T00:00:00+00:00", "note": "prior"})
            jp.write_text(existing_entry + "\n", encoding="utf-8")

            _run_hook(_minimal_payload(tmpdir, stop_hook_active=True), repo_path=tmpdir)

            lines = _read_journal_lines(tmpdir)
            self.assertEqual(len(lines), 1, "stop_hook_active=true must not append to existing journal")


# ──────────────────────────────────────────────────────────────────────────────
# Test: LIGHTMEM_HOOK_PROFILE=off
# ──────────────────────────────────────────────────────────────────────────────

class TestStopProfileOff(unittest.TestCase):
    """PRD §10.1: profile=off → exit 0, no journal write; §12 P5 item 15."""

    def test_no_journal_write_profile_off(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            _run_hook(
                _minimal_payload(tmpdir),
                env_overrides={"LIGHTMEM_HOOK_PROFILE": "off"},
                repo_path=tmpdir,
            )
            lines = _read_journal_lines(tmpdir)
            self.assertEqual(len(lines), 0)

    def test_no_journal_file_created_profile_off(self) -> None:
        """profile=off must not even create journal.jsonl."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            _run_hook(
                _minimal_payload(tmpdir),
                env_overrides={"LIGHTMEM_HOOK_PROFILE": "off"},
                repo_path=tmpdir,
            )
            self.assertFalse(_journal_path(tmpdir).exists())


# ──────────────────────────────────────────────────────────────────────────────
# Test: LIGHTMEM_DISABLED_HOOKS=Stop
# ──────────────────────────────────────────────────────────────────────────────

class TestStopDisabledHooks(unittest.TestCase):
    """PRD §10: LIGHTMEM_DISABLED_HOOKS=Stop → exit 0, no journal write."""

    def test_no_journal_write_when_stop_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            _run_hook(
                _minimal_payload(tmpdir),
                env_overrides={"LIGHTMEM_DISABLED_HOOKS": "Stop"},
                repo_path=tmpdir,
            )
            lines = _read_journal_lines(tmpdir)
            self.assertEqual(len(lines), 0)

    def test_no_journal_write_stop_in_comma_list(self) -> None:
        """Stop must be skipped even when listed alongside other hooks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            _run_hook(
                _minimal_payload(tmpdir),
                env_overrides={"LIGHTMEM_DISABLED_HOOKS": "SessionEnd,Stop"},
                repo_path=tmpdir,
            )
            lines = _read_journal_lines(tmpdir)
            self.assertEqual(len(lines), 0)


# ──────────────────────────────────────────────────────────────────────────────
# Test: normal journal write
# ──────────────────────────────────────────────────────────────────────────────

class TestStopNormalJournalWrite(unittest.TestCase):
    """PRD §6.2 steps 3-5; §6.2.1 journal entry schema; §12 P1 item 4."""

    def _run_normal(self, tmpdir: str, **kwargs) -> list[dict]:
        _init_lightmem(tmpdir)
        _run_hook(_minimal_payload(tmpdir, **kwargs), repo_path=tmpdir)
        return _read_journal_lines(tmpdir)

    def test_appends_one_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lines = self._run_normal(tmpdir)
            self.assertEqual(len(lines), 1, "Expected exactly one JSONL line in journal")

    def test_line_is_valid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lines = self._run_normal(tmpdir)
            self.assertIsInstance(lines[0], dict)

    def test_field_ts_present_and_iso(self) -> None:
        """PRD §6.2.1: ts field must be present and look like an ISO-8601 timestamp."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lines = self._run_normal(tmpdir)
            entry = lines[0]
            self.assertIn("ts", entry)
            ts = entry["ts"]
            self.assertIsInstance(ts, str)
            # Minimal ISO-8601 check: contains 'T' and at least 10 date chars
            self.assertIn("T", ts)
            self.assertGreater(len(ts), 10)

    def test_field_session_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lines = self._run_normal(tmpdir)
            entry = lines[0]
            self.assertIn("session_id", entry)
            self.assertEqual(entry["session_id"], "test-session-stop")

    def test_field_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lines = self._run_normal(tmpdir)
            entry = lines[0]
            self.assertIn("cwd", entry)
            self.assertIsInstance(entry["cwd"], str)

    def test_field_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lines = self._run_normal(tmpdir)
            entry = lines[0]
            self.assertIn("model", entry)
            self.assertEqual(entry["model"], "claude-sonnet-4-6")

    def test_field_last_assistant_hash_format(self) -> None:
        """PRD §6.2.1: last_assistant_hash must be 'sha256:<hex>'."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lines = self._run_normal(tmpdir)
            entry = lines[0]
            self.assertIn("last_assistant_hash", entry)
            h = entry["last_assistant_hash"]
            self.assertTrue(
                isinstance(h, str) and h.startswith("sha256:"),
                msg=f"Expected 'sha256:<hex>', got {h!r}",
            )
            hex_part = h[len("sha256:"):]
            self.assertGreater(len(hex_part), 0)
            # Must be valid hex
            int(hex_part, 16)

    def test_field_last_assistant_excerpt_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lines = self._run_normal(tmpdir)
            entry = lines[0]
            self.assertIn("last_assistant_excerpt", entry)

    def test_field_touched_files_present(self) -> None:
        """PRD §6.2.1: touched_files is optional but must be a list when present."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lines = self._run_normal(tmpdir)
            entry = lines[0]
            # Field may be absent or a list
            if "touched_files" in entry:
                self.assertIsInstance(entry["touched_files"], list)

    def test_second_run_appends_not_overwrites(self) -> None:
        """Running stop twice must produce exactly 2 lines in the journal."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            _run_hook(_minimal_payload(tmpdir), repo_path=tmpdir)
            _run_hook(_minimal_payload(tmpdir), repo_path=tmpdir)
            lines = _read_journal_lines(tmpdir)
            self.assertEqual(len(lines), 2)


# ──────────────────────────────────────────────────────────────────────────────
# Test: transcript_uuid_tail derivation
# ──────────────────────────────────────────────────────────────────────────────

class TestStopTranscriptUuidTail(unittest.TestCase):
    """PRD §6.2.1: transcript_uuid_tail = last 8 hex chars of UUID in transcript_path."""

    def test_uuid_tail_extracted_correctly(self) -> None:
        """UUID 00893aaf-19fa-41d2-8238-13269b9b3ca0 → tail = '9b9b3ca0'."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            payload = _minimal_payload(
                tmpdir,
                transcript_path="/tmp/00893aaf-19fa-41d2-8238-13269b9b3ca0.jsonl",
            )
            _run_hook(payload, repo_path=tmpdir)
            lines = _read_journal_lines(tmpdir)
            entry = lines[0]
            self.assertIn("transcript_uuid_tail", entry)
            self.assertEqual(entry["transcript_uuid_tail"], "9b9b3ca0")

    def test_uuid_tail_null_when_no_transcript_path(self) -> None:
        """PRD §6.2.1: transcript_uuid_tail is null if transcript_path absent/no UUID."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            payload = _minimal_payload(tmpdir, transcript_path="")
            _run_hook(payload, repo_path=tmpdir)
            lines = _read_journal_lines(tmpdir)
            entry = lines[0]
            self.assertIn("transcript_uuid_tail", entry)
            self.assertIsNone(
                entry["transcript_uuid_tail"],
                msg=f"Expected null, got {entry['transcript_uuid_tail']!r}",
            )

    def test_uuid_tail_null_when_path_has_no_uuid(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            payload = _minimal_payload(tmpdir, transcript_path="/tmp/no-uuid-here.jsonl")
            _run_hook(payload, repo_path=tmpdir)
            lines = _read_journal_lines(tmpdir)
            entry = lines[0]
            self.assertIsNone(entry.get("transcript_uuid_tail"))

    def test_uuid_tail_different_uuid(self) -> None:
        """Verify extraction with a different UUID."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            # UUID: abc12345-1111-2222-3333-444455556666
            # Last 8 chars of last group (444455556666): 55556666
            payload = _minimal_payload(
                tmpdir,
                transcript_path="/path/abc12345-1111-2222-3333-444455556666.jsonl",
            )
            _run_hook(payload, repo_path=tmpdir)
            lines = _read_journal_lines(tmpdir)
            entry = lines[0]
            self.assertEqual(entry["transcript_uuid_tail"], "55556666")


# ──────────────────────────────────────────────────────────────────────────────
# Test: secret scrubbing of last_assistant_message
# ──────────────────────────────────────────────────────────────────────────────

class TestStopSecretScrubbing(unittest.TestCase):
    """PRD §6.2 step 4 + §10.3 + §12 P1 item 5: excerpt must be scrubbed."""

    def test_api_key_redacted_in_excerpt(self) -> None:
        """PRD §10.3: 'api_key=ssssssssecret123' → excerpt contains '[REDACTED]'."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            msg = "Here is my api_key=ssssssssecret123 for the service."
            payload = _minimal_payload(tmpdir, last_assistant_message=msg)
            _run_hook(payload, repo_path=tmpdir)
            lines = _read_journal_lines(tmpdir)
            entry = lines[0]
            self.assertIn("[REDACTED]", entry["last_assistant_excerpt"])
            self.assertNotIn("ssssssssecret123", entry["last_assistant_excerpt"])

    def test_password_redacted_in_excerpt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            msg = "Use password=mysuperpassword123 to login."
            payload = _minimal_payload(tmpdir, last_assistant_message=msg)
            _run_hook(payload, repo_path=tmpdir)
            lines = _read_journal_lines(tmpdir)
            entry = lines[0]
            self.assertIn("[REDACTED]", entry["last_assistant_excerpt"])
            self.assertNotIn("mysuperpassword123", entry["last_assistant_excerpt"])

    def test_clean_message_not_redacted(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            msg = "The code review looks good to me."
            payload = _minimal_payload(tmpdir, last_assistant_message=msg)
            _run_hook(payload, repo_path=tmpdir)
            lines = _read_journal_lines(tmpdir)
            entry = lines[0]
            self.assertNotIn("[REDACTED]", entry["last_assistant_excerpt"])

    def test_secret_straddling_200_char_boundary_is_redacted(self) -> None:
        # Codex H1 regression: a secret whose keyword starts before char 200 but
        # whose value bytes extend past 200 must be scrubbed in full before the
        # excerpt cut. The pre-fix code did message[:200] then scrub() and would
        # leak a sub-8-char prefix of the secret value that the regex cannot
        # match. Position the keyword at char 180 so the value crosses the cut.
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            prefix = "A" * 180
            secret = "api_key=ssssecretvalue12345xyz"
            msg = prefix + secret + " trailing"
            self.assertGreater(len(prefix) + len("api_key="), 0)
            self.assertLess(len(prefix), 200)
            self.assertGreater(len(prefix + secret), 200)
            payload = _minimal_payload(tmpdir, last_assistant_message=msg)
            _run_hook(payload, repo_path=tmpdir)
            entry = _read_journal_lines(tmpdir)[0]
            excerpt = entry["last_assistant_excerpt"]
            self.assertNotIn(
                "ssssecretvalue", excerpt,
                f"secret value leaked into excerpt: {excerpt!r}",
            )
            self.assertIn("[REDACTED]", excerpt)

    def test_hash_is_based_on_full_message_not_truncated(self) -> None:
        """PRD §6.2.1: last_assistant_hash is SHA-256 of the FULL message.

        Verify that a 1000-char message produces a hash of the full text,
        not just the first 200 chars.  We do this by computing both hashes
        ourselves and asserting that only the full-message hash matches.
        """
        import hashlib

        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            msg = "A" * 1000
            payload = _minimal_payload(tmpdir, last_assistant_message=msg)
            _run_hook(payload, repo_path=tmpdir)
            lines = _read_journal_lines(tmpdir)
            entry = lines[0]
            reported_hash = entry["last_assistant_hash"]

            full_hash = "sha256:" + hashlib.sha256(msg.encode()).hexdigest()
            truncated_hash = "sha256:" + hashlib.sha256(msg[:200].encode()).hexdigest()

            self.assertEqual(
                reported_hash,
                full_hash,
                msg=(
                    f"Hash must be of the full message.\n"
                    f"Got:      {reported_hash}\n"
                    f"Expected: {full_hash}\n"
                    f"Trunc:    {truncated_hash}"
                ),
            )


# ──────────────────────────────────────────────────────────────────────────────
# Test: excerpt truncation to 200 chars
# ──────────────────────────────────────────────────────────────────────────────

class TestStopExcerptTruncation(unittest.TestCase):
    """PRD §6.2.1: last_assistant_excerpt = first 200 chars of message, post-scrub."""

    def test_excerpt_max_200_chars_for_long_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            msg = "X" * 1000  # 1000 char message
            payload = _minimal_payload(tmpdir, last_assistant_message=msg)
            _run_hook(payload, repo_path=tmpdir)
            lines = _read_journal_lines(tmpdir)
            entry = lines[0]
            excerpt = entry["last_assistant_excerpt"]
            self.assertLessEqual(
                len(excerpt),
                200,
                msg=f"Excerpt is {len(excerpt)} chars, expected ≤ 200",
            )

    def test_excerpt_exactly_200_chars_for_1000_char_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            # Use a repeating pattern with no secrets to avoid scrub expanding length
            msg = "Hello world. " * 80  # ~1040 chars, no secrets
            payload = _minimal_payload(tmpdir, last_assistant_message=msg)
            _run_hook(payload, repo_path=tmpdir)
            lines = _read_journal_lines(tmpdir)
            entry = lines[0]
            excerpt = entry["last_assistant_excerpt"]
            self.assertEqual(
                len(excerpt),
                200,
                msg=f"Excerpt is {len(excerpt)} chars, expected exactly 200",
            )

    def test_short_message_not_padded(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_lightmem(tmpdir)
            msg = "Short."
            payload = _minimal_payload(tmpdir, last_assistant_message=msg)
            _run_hook(payload, repo_path=tmpdir)
            lines = _read_journal_lines(tmpdir)
            entry = lines[0]
            self.assertEqual(entry["last_assistant_excerpt"], "Short.")


if __name__ == "__main__":
    unittest.main()
