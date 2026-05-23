from __future__ import annotations

"""
Integration tests for scripts/hooks/user_prompt_submit.py

Key behaviours:
  - LIGHTMEM_HOOK_PROFILE=off → exit 0, no inbox write.
  - LIGHTMEM_DISABLED_HOOKS=UserPromptSubmit → exit 0, no inbox write.
  - Prompt without [mem] → exit 0, no inbox write.
  - Prompt with [mem] → exit 0, inbox/pending.md created with extracted text.
  - Multiple [mem] tags → multiple inbox items.
  - Missing cwd → exit 0, no crash.
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
_SCRIPT = _REPO_ROOT / "scripts" / "hooks" / "user_prompt_submit.py"


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


def _minimal_payload(cwd: str, *, prompt: str = "hello world") -> dict:
    return {
        "hook_event_name": "UserPromptSubmit",
        "cwd": cwd,
        "session_id": "test-session-ups",
        "transcript_path": "/tmp/00893aaf-19fa-41d2-8238-13269b9b3ca0.jsonl",
        "prompt": prompt,
    }


def _inbox_path(root: Path) -> Path:
    return root / ".claude" / "lightmem" / "inbox" / "pending.md"


# ---------------------------------------------------------------------------
# Exit code
# ---------------------------------------------------------------------------


class TestUserPromptSubmitExitCode(unittest.TestCase):
    def test_always_exits_zero_normal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_hook(_minimal_payload(tmpdir, prompt="no tag"))
            self.assertEqual(result.returncode, 0)

    def test_always_exits_zero_with_mem_tag(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_hook(_minimal_payload(tmpdir, prompt="important [mem]"))
            self.assertEqual(result.returncode, 0)

    def test_always_exits_zero_profile_off(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_hook(
                _minimal_payload(tmpdir, prompt="fact [mem]"),
                env_overrides={"LIGHTMEM_HOOK_PROFILE": "off"},
            )
            self.assertEqual(result.returncode, 0)

    def test_always_exits_zero_on_bad_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_hook({}, repo_path=tmpdir)
            self.assertEqual(result.returncode, 0)


# ---------------------------------------------------------------------------
# Profile / disabled guard
# ---------------------------------------------------------------------------


class TestUserPromptSubmitDisabled(unittest.TestCase):
    def test_profile_off_no_inbox_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _run_hook(
                _minimal_payload(tmpdir, prompt="should be saved [mem]"),
                env_overrides={"LIGHTMEM_HOOK_PROFILE": "off"},
            )
            self.assertFalse(_inbox_path(root).exists())

    def test_disabled_hook_no_inbox_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _run_hook(
                _minimal_payload(tmpdir, prompt="should be saved [mem]"),
                env_overrides={"LIGHTMEM_DISABLED_HOOKS": "UserPromptSubmit"},
            )
            self.assertFalse(_inbox_path(root).exists())


# ---------------------------------------------------------------------------
# No [mem] tag — no inbox write
# ---------------------------------------------------------------------------


class TestUserPromptSubmitNoTag(unittest.TestCase):
    def test_no_tag_no_inbox_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _run_hook(_minimal_payload(tmpdir, prompt="plain message no tag"))
            self.assertFalse(_inbox_path(root).exists())

    def test_empty_prompt_no_inbox_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _run_hook(_minimal_payload(tmpdir, prompt=""))
            self.assertFalse(_inbox_path(root).exists())


# ---------------------------------------------------------------------------
# [mem] tag — inbox written
# ---------------------------------------------------------------------------


class TestUserPromptSubmitWithTag(unittest.TestCase):
    def test_mem_tag_creates_inbox_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _run_hook(_minimal_payload(tmpdir, prompt="important fact [mem]"))
            self.assertTrue(_inbox_path(root).exists())

    def test_mem_tag_content_in_inbox(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _run_hook(_minimal_payload(tmpdir, prompt="important fact [mem]"))
            content = _inbox_path(root).read_text(encoding="utf-8")
            self.assertIn("important fact", content)

    def test_mem_tag_stripped_from_inbox_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _run_hook(_minimal_payload(tmpdir, prompt="important fact [mem]"))
            content = _inbox_path(root).read_text(encoding="utf-8")
            self.assertNotIn("[mem]", content)

    def test_case_insensitive_MEM(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _run_hook(_minimal_payload(tmpdir, prompt="upper case [MEM]"))
            self.assertTrue(_inbox_path(root).exists())

    def test_multiple_tagged_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            prompt = "first thing [mem]\nno tag here\nsecond thing [mem]"
            _run_hook(_minimal_payload(tmpdir, prompt=prompt))
            content = _inbox_path(root).read_text(encoding="utf-8")
            bullets = [l for l in content.splitlines() if l.startswith("- [")]
            self.assertEqual(len(bullets), 2)


# ---------------------------------------------------------------------------
# Missing / invalid cwd
# ---------------------------------------------------------------------------


class TestUserPromptSubmitMissingCwd(unittest.TestCase):
    def test_missing_cwd_exits_zero(self) -> None:
        payload = {"hook_event_name": "UserPromptSubmit", "prompt": "fact [mem]"}
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_hook(payload, repo_path=tmpdir)
            self.assertEqual(result.returncode, 0)

    def test_empty_cwd_exits_zero(self) -> None:
        payload = {
            "hook_event_name": "UserPromptSubmit",
            "cwd": "",
            "prompt": "fact [mem]",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_hook(payload, repo_path=tmpdir)
            self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
