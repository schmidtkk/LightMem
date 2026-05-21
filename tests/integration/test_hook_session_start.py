from __future__ import annotations

"""
Integration tests for scripts/hooks/session_start.py

Derived purely from PRD_v0.2.md §6.1, §6.1.1, §6.1.2, §6.1.3, §10, §12 P0/P3/P5.
No hook implementation files were read during authoring.

Each test launches the hook as a real subprocess via subprocess.run, mirroring
how Claude Code invokes it.  A fresh TemporaryDirectory serves as the synthetic
repo root, so no real repo state is ever touched.

Output contract (PRD §6.1.3):
    {"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"..."}}

Exit code is ALWAYS 0 (PRD §6.1 rule 4, §12 P4 item 14).
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "hooks" / "session_start.py"

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _build_env(overrides: dict[str, str] | None = None) -> dict[str, str]:
    """Return a copy of the current environment with PYTHONPATH set to the repo
    root so the hook can import scripts/lib, plus any caller-supplied overrides.
    """
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
    """Invoke session_start.py with *payload* as JSON on stdin.

    *repo_path* is passed as the subprocess's working directory AND as the
    ``cwd`` field inside the payload (if not already set by the caller).
    """
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


def _minimal_payload(cwd: str, source: str = "startup") -> dict:
    """Return a minimal SessionStart payload pointing at *cwd*."""
    return {
        "hook_event_name": "SessionStart",
        "source": source,
        "cwd": cwd,
        "session_id": "test-session-abc",
        "transcript_path": "/tmp/00893aaf-19fa-41d2-8238-13269b9b3ca0.jsonl",
        "model": "claude-sonnet-4-6",
    }


def _parse_output(stdout: str) -> dict:
    """Parse the hook's JSON stdout, raising AssertionError on failure."""
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"Hook stdout is not valid JSON: {exc!r}\nstdout={stdout!r}"
        ) from exc


# ──────────────────────────────────────────────────────────────────────────────
# Test: exit code is always 0
# ──────────────────────────────────────────────────────────────────────────────

class TestSessionStartAlwaysExitsZero(unittest.TestCase):
    """PRD §6.1 rule 4: always exit 0, even on errors."""

    def test_exit_zero_uninitialized_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_hook(_minimal_payload(tmpdir), repo_path=tmpdir)
            self.assertEqual(result.returncode, 0)

    def test_exit_zero_initialized_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lightmem = Path(tmpdir) / ".claude" / "lightmem"
            lightmem.mkdir(parents=True)
            result = _run_hook(_minimal_payload(tmpdir), repo_path=tmpdir)
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

    def test_exit_zero_empty_stdin(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env = _build_env()
            result = subprocess.run(
                [sys.executable, str(_SCRIPT)],
                input="",
                capture_output=True,
                text=True,
                timeout=10,
                env=env,
                cwd=tmpdir,
            )
            self.assertEqual(result.returncode, 0)

    def test_exit_zero_profile_off(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_hook(
                _minimal_payload(tmpdir),
                env_overrides={"LIGHTMEM_HOOK_PROFILE": "off"},
                repo_path=tmpdir,
            )
            self.assertEqual(result.returncode, 0)

    def test_exit_zero_context_off(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lightmem = Path(tmpdir) / ".claude" / "lightmem"
            lightmem.mkdir(parents=True)
            result = _run_hook(
                _minimal_payload(tmpdir),
                env_overrides={"LIGHTMEM_SESSION_START_CONTEXT": "off"},
                repo_path=tmpdir,
            )
            self.assertEqual(result.returncode, 0)


# ──────────────────────────────────────────────────────────────────────────────
# Test: uninitialized repo → suggestion mentioning /lightmem:init
# ──────────────────────────────────────────────────────────────────────────────

class TestSessionStartUninitializedRepo(unittest.TestCase):
    """PRD §6.1 step 3 uninitialized branch; §12 P0 item 1."""

    def test_stdout_is_valid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_hook(_minimal_payload(tmpdir), repo_path=tmpdir)
            # stdout must be parseable JSON
            _parse_output(result.stdout)

    def test_output_has_hook_specific_output_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_hook(_minimal_payload(tmpdir), repo_path=tmpdir)
            data = _parse_output(result.stdout)
            self.assertIn("hookSpecificOutput", data)

    def test_output_event_name_is_session_start(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_hook(_minimal_payload(tmpdir), repo_path=tmpdir)
            data = _parse_output(result.stdout)
            hook_out = data.get("hookSpecificOutput", {})
            self.assertEqual(hook_out.get("hookEventName"), "SessionStart")

    def test_additional_context_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_hook(_minimal_payload(tmpdir), repo_path=tmpdir)
            data = _parse_output(result.stdout)
            hook_out = data.get("hookSpecificOutput", {})
            self.assertIn("additionalContext", hook_out)

    def test_suggestion_mentions_lightmem_init(self) -> None:
        """PRD §6.1: uninitialized repo → single-line suggestion mentioning /lightmem:init."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_hook(_minimal_payload(tmpdir), repo_path=tmpdir)
            data = _parse_output(result.stdout)
            additional_context = data["hookSpecificOutput"]["additionalContext"]
            self.assertIn("/lightmem:init", additional_context)

    def test_no_lightmem_dir_triggers_suggestion(self) -> None:
        """Confirm no .claude/lightmem/ dir exists in the temp repo."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lightmem_dir = Path(tmpdir) / ".claude" / "lightmem"
            self.assertFalse(lightmem_dir.exists())
            result = _run_hook(_minimal_payload(tmpdir), repo_path=tmpdir)
            data = _parse_output(result.stdout)
            ctx = data["hookSpecificOutput"]["additionalContext"]
            self.assertIn("/lightmem:init", ctx)


# ──────────────────────────────────────────────────────────────────────────────
# Test: initialized repo → hot summary injected
# ──────────────────────────────────────────────────────────────────────────────

_MISSION_FRONTMATTER = """\
---
id: mission
kind: mission
summary: LightMem is a structured memory plugin
status: active
tags: []
supersedes: []
superseded_by: null
created_at: 2026-05-21
updated_at: 2026-05-21
---

# Project Mission

LightMem turns a repo into a structured, team-shareable, gateway-routed project
memory database.  Hooks maintain it; skills curate it.
"""

_CONSTRAINT_FRONTMATTER = """\
---
id: no-llm-in-hook
kind: constraint
summary: No LLM calls inside any hook script
status: active
tags: [architecture]
supersedes: []
superseded_by: null
created_at: 2026-05-21
updated_at: 2026-05-21
---

# No LLM calls inside any hook script

Hooks must be pure-stdlib Python.  Any LLM call would add latency and create
circular dependencies.
"""

_DECISION_FRONTMATTER = """\
---
id: claude-md-as-gateway
kind: decision
summary: CLAUDE.md is the gateway, not the database
status: active
tags: [architecture, memory]
supersedes: []
superseded_by: null
created_at: 2026-05-21
updated_at: 2026-05-21
---

# CLAUDE.md is the gateway, not the database

Use CLAUDE.md as an L0 router.  The full memory database lives under topics/.
"""


def _create_initialized_repo(
    tmpdir: str,
    *,
    with_mission: bool = True,
    with_constraint: bool = False,
    with_decision: bool = False,
) -> Path:
    """Scaffold a minimal initialized lightmem repo inside *tmpdir*."""
    root = Path(tmpdir)
    lightmem = root / ".claude" / "lightmem"
    topics = lightmem / "topics"
    topics.mkdir(parents=True)
    (lightmem / "sessions").mkdir()
    (lightmem / "archive").mkdir()

    if with_mission:
        (topics / "mission.md").write_text(_MISSION_FRONTMATTER, encoding="utf-8")

    if with_constraint:
        constraints_dir = topics / "constraints"
        constraints_dir.mkdir()
        (constraints_dir / "no-llm-in-hook.md").write_text(
            _CONSTRAINT_FRONTMATTER, encoding="utf-8"
        )

    if with_decision:
        decisions_dir = topics / "decisions"
        decisions_dir.mkdir()
        (decisions_dir / "claude-md-as-gateway.md").write_text(
            _DECISION_FRONTMATTER, encoding="utf-8"
        )

    return root


class TestSessionStartInitializedRepo(unittest.TestCase):
    """PRD §6.1.1: hot summary composition for an initialized repo."""

    def test_stdout_is_valid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _create_initialized_repo(tmpdir, with_mission=True)
            result = _run_hook(_minimal_payload(tmpdir), repo_path=tmpdir)
            _parse_output(result.stdout)

    def test_output_shape_has_hook_specific_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _create_initialized_repo(tmpdir, with_mission=True)
            result = _run_hook(_minimal_payload(tmpdir), repo_path=tmpdir)
            data = _parse_output(result.stdout)
            self.assertIn("hookSpecificOutput", data)
            self.assertIn("additionalContext", data["hookSpecificOutput"])
            self.assertEqual(
                data["hookSpecificOutput"].get("hookEventName"), "SessionStart"
            )

    def test_mission_body_text_in_context(self) -> None:
        """PRD §6.1.1 step 1: first 500 chars of mission.md body included."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _create_initialized_repo(tmpdir, with_mission=True)
            result = _run_hook(_minimal_payload(tmpdir), repo_path=tmpdir)
            data = _parse_output(result.stdout)
            ctx = data["hookSpecificOutput"]["additionalContext"]
            # The mission body contains this phrase
            self.assertIn("LightMem", ctx)

    def test_additional_context_is_string(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _create_initialized_repo(tmpdir, with_mission=True)
            result = _run_hook(_minimal_payload(tmpdir), repo_path=tmpdir)
            data = _parse_output(result.stdout)
            self.assertIsInstance(
                data["hookSpecificOutput"]["additionalContext"], str
            )

    def test_no_lightmem_init_suggestion_when_initialized(self) -> None:
        """Initialized repo must NOT emit the /lightmem:init nudge."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _create_initialized_repo(tmpdir, with_mission=True)
            result = _run_hook(_minimal_payload(tmpdir), repo_path=tmpdir)
            data = _parse_output(result.stdout)
            ctx = data["hookSpecificOutput"]["additionalContext"]
            # The "run init" nudge should not appear for an initialized repo
            self.assertNotIn("/lightmem:init", ctx)


class TestSessionStartConstraintInjection(unittest.TestCase):
    """PRD §6.1.1 step 2: active constraints formatted as - [<slug>] <summary>."""

    def test_constraint_slug_and_summary_in_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _create_initialized_repo(
                tmpdir, with_mission=True, with_constraint=True
            )
            result = _run_hook(_minimal_payload(tmpdir), repo_path=tmpdir)
            data = _parse_output(result.stdout)
            ctx = data["hookSpecificOutput"]["additionalContext"]
            # PRD format: - [<slug>] <summary>
            self.assertIn("[no-llm-in-hook]", ctx)
            self.assertIn("No LLM calls inside any hook script", ctx)

    def test_constraint_line_format(self) -> None:
        """Each constraint line must match '- [<slug>] <summary>' format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _create_initialized_repo(
                tmpdir, with_mission=True, with_constraint=True
            )
            result = _run_hook(_minimal_payload(tmpdir), repo_path=tmpdir)
            data = _parse_output(result.stdout)
            ctx = data["hookSpecificOutput"]["additionalContext"]
            self.assertIn("- [no-llm-in-hook]", ctx)


# ──────────────────────────────────────────────────────────────────────────────
# Test: LIGHTMEM_HOOK_PROFILE=off → short-circuit
# ──────────────────────────────────────────────────────────────────────────────

class TestSessionStartProfileOff(unittest.TestCase):
    """PRD §10.1: LIGHTMEM_HOOK_PROFILE=off → exit 0 before any work; §12 P5 item 15."""

    def test_profile_off_uninitialized_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_hook(
                _minimal_payload(tmpdir),
                env_overrides={"LIGHTMEM_HOOK_PROFILE": "off"},
                repo_path=tmpdir,
            )
            self.assertEqual(result.returncode, 0)
            # stdout is empty OR minimal (no meaningful JSON context); no error output
            self.assertEqual(result.stderr, "")

    def test_profile_off_initialized_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _create_initialized_repo(tmpdir, with_mission=True)
            result = _run_hook(
                _minimal_payload(tmpdir),
                env_overrides={"LIGHTMEM_HOOK_PROFILE": "off"},
                repo_path=tmpdir,
            )
            self.assertEqual(result.returncode, 0)

    def test_profile_off_no_error_on_stderr(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_hook(
                _minimal_payload(tmpdir),
                env_overrides={"LIGHTMEM_HOOK_PROFILE": "off"},
                repo_path=tmpdir,
            )
            # No uncaught exception tracebacks
            self.assertNotIn("Traceback", result.stderr)

    def test_profile_off_stdout_empty_or_minimal(self) -> None:
        """PRD §10.1/§12 P5: profile=off → no meaningful output.

        The spec allows stdout to be empty string or minimal ``{}``; either
        satisfies the short-circuit contract.  We do NOT require a full
        additionalContext payload when the hook is disabled.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_hook(
                _minimal_payload(tmpdir),
                env_overrides={"LIGHTMEM_HOOK_PROFILE": "off"},
                repo_path=tmpdir,
            )
            stdout = result.stdout.strip()
            # Accept empty or minimal JSON (no additionalContext with real content)
            if stdout:
                # If JSON is emitted, it must parse and must NOT contain rich context
                try:
                    data = json.loads(stdout)
                    # If it has hookSpecificOutput, additionalContext must be empty/absent
                    hook_out = data.get("hookSpecificOutput", {})
                    ctx = hook_out.get("additionalContext", "")
                    self.assertEqual(ctx, "")
                except json.JSONDecodeError:
                    # Non-JSON non-empty stdout is a failure
                    self.fail(
                        f"profile=off emitted non-empty, non-JSON stdout: {stdout!r}"
                    )


# ──────────────────────────────────────────────────────────────────────────────
# Test: LIGHTMEM_SESSION_START_CONTEXT=off → empty additionalContext
# ──────────────────────────────────────────────────────────────────────────────

class TestSessionStartContextOff(unittest.TestCase):
    """PRD §10 / §12 P3 item 10: LIGHTMEM_SESSION_START_CONTEXT=off → empty additionalContext."""

    def test_context_off_stdout_is_valid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _create_initialized_repo(tmpdir, with_mission=True)
            result = _run_hook(
                _minimal_payload(tmpdir),
                env_overrides={"LIGHTMEM_SESSION_START_CONTEXT": "off"},
                repo_path=tmpdir,
            )
            _parse_output(result.stdout)

    def test_context_off_additional_context_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _create_initialized_repo(tmpdir, with_mission=True)
            result = _run_hook(
                _minimal_payload(tmpdir),
                env_overrides={"LIGHTMEM_SESSION_START_CONTEXT": "off"},
                repo_path=tmpdir,
            )
            data = _parse_output(result.stdout)
            ctx = data["hookSpecificOutput"]["additionalContext"]
            self.assertEqual(ctx, "")

    def test_context_off_exit_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _create_initialized_repo(tmpdir, with_mission=True)
            result = _run_hook(
                _minimal_payload(tmpdir),
                env_overrides={"LIGHTMEM_SESSION_START_CONTEXT": "off"},
                repo_path=tmpdir,
            )
            self.assertEqual(result.returncode, 0)


# ──────────────────────────────────────────────────────────────────────────────
# Test: malformed / missing stdin
# ──────────────────────────────────────────────────────────────────────────────

class TestSessionStartRobustness(unittest.TestCase):
    """PRD §6.1 rule 1 + rule 4: malformed stdin must not crash the hook."""

    def test_malformed_stdin_exits_zero(self) -> None:
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

    def test_malformed_stdin_no_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env = _build_env()
            result = subprocess.run(
                [sys.executable, str(_SCRIPT)],
                input="{bad",
                capture_output=True,
                text=True,
                timeout=10,
                env=env,
                cwd=tmpdir,
            )
            self.assertNotIn("Traceback", result.stderr)

    def test_empty_stdin_exits_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env = _build_env()
            result = subprocess.run(
                [sys.executable, str(_SCRIPT)],
                input="",
                capture_output=True,
                text=True,
                timeout=10,
                env=env,
                cwd=tmpdir,
            )
            self.assertEqual(result.returncode, 0)

    def test_null_json_exits_zero(self) -> None:
        """Sending JSON null (not an object) must not crash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env = _build_env()
            result = subprocess.run(
                [sys.executable, str(_SCRIPT)],
                input="null",
                capture_output=True,
                text=True,
                timeout=10,
                env=env,
                cwd=tmpdir,
            )
            self.assertEqual(result.returncode, 0)


# ──────────────────────────────────────────────────────────────────────────────
# Test: source=resume → stale-replay guard in additionalContext
# ──────────────────────────────────────────────────────────────────────────────

class TestSessionStartResumeStaleGuard(unittest.TestCase):
    """PRD §6.1.2: on source=resume, prior-session summary wrapped with stale-replay guard.

    The guard text 'HISTORICAL REFERENCE ONLY' must appear in additionalContext
    when a prior-session file is found and injected (PRD §12 P3 item 11).

    This test pre-creates a session file so the hook has something to inject.
    """

    def _create_repo_with_session_file(self, tmpdir: str) -> Path:
        root = _create_initialized_repo(tmpdir, with_mission=True)
        sessions_dir = root / ".claude" / "lightmem" / "sessions"
        # Create a session file with today's date and a known shortId
        session_file = sessions_dir / "2026-05-21-9b9b3ca0.md"
        session_file.write_text(
            "# Session: 2026-05-21\n\n"
            "**Date:** 2026-05-21\n"
            "**Project:** LightMem\n"
            "**Branch:** main\n"
            "**Worktree:** /tmp/example-repo\n\n"
            "---\n\n"
            "<!-- LIGHTMEM:SUMMARY:START -->\n"
            "Worked on hook implementation.\n"
            "<!-- LIGHTMEM:SUMMARY:END -->\n",
            encoding="utf-8",
        )
        return root

    def test_resume_exits_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            self._create_repo_with_session_file(tmpdir)
            payload = _minimal_payload(tmpdir, source="resume")
            result = _run_hook(payload, repo_path=tmpdir)
            self.assertEqual(result.returncode, 0)

    def test_resume_stdout_is_valid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            self._create_repo_with_session_file(tmpdir)
            payload = _minimal_payload(tmpdir, source="resume")
            result = _run_hook(payload, repo_path=tmpdir)
            _parse_output(result.stdout)

    def test_resume_with_session_file_has_stale_guard(self) -> None:
        """PRD §6.1.2: HISTORICAL REFERENCE ONLY must appear when session injected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self._create_repo_with_session_file(tmpdir)
            payload = _minimal_payload(tmpdir, source="resume")
            result = _run_hook(payload, repo_path=tmpdir)
            data = _parse_output(result.stdout)
            ctx = data["hookSpecificOutput"]["additionalContext"]
            self.assertIn("HISTORICAL REFERENCE ONLY", ctx)


if __name__ == "__main__":
    unittest.main()
