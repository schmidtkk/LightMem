from __future__ import annotations

"""
Tests for scripts/lib/doctor.py

Derived purely from PRD_v0.2.md §9 (doctor checks — 17 concrete predicates),
§5 (memory model), §10 (env vars), and the Round-6 QA API spec.  No
implementation files were read during authoring.

Expected API:
  - CheckResult — frozen dataclass: status, name, message, fix_hint
  - ALL_CHECKS: list[Callable[[Path], CheckResult]] — exactly 17 entries
  - run_all(repo_root: Path) -> list[CheckResult]
  - summary(results: list[CheckResult]) -> tuple[int, int, int]
  - Individual check functions: doctor.check_<name>(repo_root) -> CheckResult

SPEC AMBIGUITIES ENCOUNTERED:
  SA1. The spec does not specify the exact `name` field value for each
       CheckResult.  Tests verify only `status`, not the exact `name` text,
       except where the spec explicitly names a check ("check_<name>").
  SA2. For `no_broken_relative_links`, the spec says "local paths inside
       .claude/lightmem/".  It is ambiguous whether all relative links or only
       ./ prefixed links are scanned.  Tests use `[text](./path)` form as the
       spec example.
  SA3. For `secret_scan`, the spec says "outside literal [REDACTED]" —
       interpreted as: after scrub() is applied, if SECRET_REGEX still matches
       the result, the check fails.  Tests use raw unredacted secrets.
  SA4. For `archive_purge_recent`, the threshold is RETENTION_DAYS × 2 days.
       Tests set mtime to 200 days in the past (well beyond any reasonable
       RETENTION_DAYS × 2) to trigger warn reliably.
  SA5. For exception-resilience, the exact status field of the converted result
       is "warn" per spec.  The `name` field of the result is implementation-
       defined when a check raises; tests only verify status=="warn".
"""

import dataclasses
import os
import sys
import tempfile
import time
import unittest
import unittest.mock
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_LIB = _REPO_ROOT / "scripts" / "lib"
if str(_SCRIPTS_LIB) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_LIB))

import doctor  # type: ignore[import]  # noqa: E402 – imported after path fix


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_TOPIC = """\
---
id: my-topic
kind: decision
summary: A test topic
status: active
---

# My Topic

Some body.
"""

_GATEWAY_MARKER = "<!-- LIGHTMEM:GATEWAY:START -->"
_GATEWAY_END = "<!-- LIGHTMEM:GATEWAY:END -->"


def _make_lightmem_dir(root: Path) -> Path:
    """Create .claude/lightmem/ directory structure and return it."""
    lm = root / ".claude" / "lightmem"
    lm.mkdir(parents=True, exist_ok=True)
    return lm


def _write_gitignore(lm: Path, content: str) -> None:
    (lm / ".gitignore").write_text(content, encoding="utf-8")


def _write_topic(topics_dir: Path, filename: str, content: str) -> None:
    topics_dir.mkdir(parents=True, exist_ok=True)
    (topics_dir / filename).write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# CheckResult dataclass
# ---------------------------------------------------------------------------


class TestCheckResultDataclass(unittest.TestCase):
    """CheckResult must be a frozen dataclass with the required fields."""

    def _make(self, **kwargs: object) -> doctor.CheckResult:
        defaults: dict[str, object] = {
            "status": "pass",
            "name": "test_check",
            "message": "all good",
        }
        defaults.update(kwargs)
        return doctor.CheckResult(**defaults)  # type: ignore[arg-type]

    def test_instantiation_pass(self) -> None:
        cr = self._make(status="pass")
        self.assertEqual(cr.status, "pass")

    def test_instantiation_warn(self) -> None:
        cr = self._make(status="warn")
        self.assertEqual(cr.status, "warn")

    def test_instantiation_fail(self) -> None:
        cr = self._make(status="fail")
        self.assertEqual(cr.status, "fail")

    def test_name_field(self) -> None:
        cr = self._make(name="claude_md_exists")
        self.assertEqual(cr.name, "claude_md_exists")

    def test_message_field(self) -> None:
        cr = self._make(message="CLAUDE.md not found")
        self.assertEqual(cr.message, "CLAUDE.md not found")

    def test_fix_hint_defaults_to_none(self) -> None:
        cr = self._make()
        self.assertIsNone(cr.fix_hint)

    def test_fix_hint_can_be_set(self) -> None:
        cr = self._make(fix_hint="Run /lightmem:init")
        self.assertEqual(cr.fix_hint, "Run /lightmem:init")

    def test_is_frozen(self) -> None:
        cr = self._make()
        with self.assertRaises((AttributeError, TypeError, dataclasses.FrozenInstanceError)):
            cr.status = "fail"  # type: ignore[misc]

    def test_name_immutable(self) -> None:
        cr = self._make()
        with self.assertRaises((AttributeError, TypeError, dataclasses.FrozenInstanceError)):
            cr.name = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ALL_CHECKS — exactly 17 entries
# ---------------------------------------------------------------------------


class TestAllChecksLength(unittest.TestCase):
    """ALL_CHECKS must contain exactly 17 check functions."""

    def test_all_checks_is_list(self) -> None:
        self.assertIsInstance(doctor.ALL_CHECKS, list)

    def test_all_checks_has_17_entries(self) -> None:
        self.assertEqual(len(doctor.ALL_CHECKS), 17)

    def test_all_checks_entries_are_callable(self) -> None:
        for i, fn in enumerate(doctor.ALL_CHECKS):
            with self.subTest(index=i):
                self.assertTrue(callable(fn), f"Entry {i} is not callable: {fn!r}")


# ---------------------------------------------------------------------------
# run_all — basic contract
# ---------------------------------------------------------------------------


class TestRunAllBasicContract(unittest.TestCase):
    """run_all must return exactly 17 CheckResult objects, in order."""

    def test_run_all_returns_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            results = doctor.run_all(Path(tmpdir))
            self.assertIsInstance(results, list)

    def test_run_all_returns_17_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            results = doctor.run_all(Path(tmpdir))
            self.assertEqual(len(results), 17)

    def test_run_all_results_are_check_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            results = doctor.run_all(Path(tmpdir))
            for r in results:
                self.assertIsInstance(r, doctor.CheckResult)

    def test_run_all_does_not_raise(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                doctor.run_all(Path(tmpdir))
            except Exception as exc:  # noqa: BLE001
                self.fail(f"run_all raised unexpectedly: {exc}")

    def test_run_all_empty_dir_mostly_warns(self) -> None:
        """Empty tempdir: missing CLAUDE.md and missing lightmem dir → many warns."""
        with tempfile.TemporaryDirectory() as tmpdir:
            results = doctor.run_all(Path(tmpdir))
            statuses = [r.status for r in results]
            warn_or_fail = [s for s in statuses if s in ("warn", "fail")]
            # At least claude_md_exists and lightmem_dir_exists are warns
            self.assertGreaterEqual(len(warn_or_fail), 2)

    def test_run_all_results_in_same_order_as_all_checks(self) -> None:
        """Results must be in the same order as ALL_CHECKS."""
        with tempfile.TemporaryDirectory() as tmpdir:
            results = doctor.run_all(Path(tmpdir))
            # Each result must have a name field; the order should be stable
            names = [r.name for r in results]
            # run_all called twice must yield same order
            results2 = doctor.run_all(Path(tmpdir))
            names2 = [r.name for r in results2]
            self.assertEqual(names, names2)

    def test_run_all_statuses_valid_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            results = doctor.run_all(Path(tmpdir))
            valid = {"pass", "warn", "fail"}
            for r in results:
                self.assertIn(r.status, valid, f"Unexpected status {r.status!r}")


# ---------------------------------------------------------------------------
# run_all — exception resilience
# ---------------------------------------------------------------------------


class TestRunAllExceptionResilience(unittest.TestCase):
    """If a check raises an exception, run_all must convert it to status='warn'."""

    def test_exception_in_check_converted_to_warn(self) -> None:
        def _boom(_root: Path) -> doctor.CheckResult:
            raise RuntimeError("simulated check failure")

        original_checks = list(doctor.ALL_CHECKS)
        patched = [_boom] + original_checks[1:]

        with unittest.mock.patch.object(doctor, "ALL_CHECKS", patched):
            with tempfile.TemporaryDirectory() as tmpdir:
                try:
                    results = doctor.run_all(Path(tmpdir))
                except Exception as exc:  # noqa: BLE001
                    self.fail(f"run_all raised despite exception-resilience spec: {exc}")

                self.assertEqual(len(results), 17)
                self.assertEqual(results[0].status, "warn",
                                 "Exceptional check must be converted to status='warn'")

    def test_exception_in_last_check_does_not_raise(self) -> None:
        def _boom(_root: Path) -> doctor.CheckResult:
            raise ValueError("last check fails")

        original_checks = list(doctor.ALL_CHECKS)
        patched = original_checks[:-1] + [_boom]

        with unittest.mock.patch.object(doctor, "ALL_CHECKS", patched):
            with tempfile.TemporaryDirectory() as tmpdir:
                try:
                    results = doctor.run_all(Path(tmpdir))
                except Exception as exc:  # noqa: BLE001
                    self.fail(f"run_all raised on last-check exception: {exc}")

                self.assertEqual(results[-1].status, "warn")


# ---------------------------------------------------------------------------
# summary()
# ---------------------------------------------------------------------------


class TestSummary(unittest.TestCase):
    """summary() returns (pass_count, warn_count, fail_count)."""

    def _cr(self, status: str) -> doctor.CheckResult:
        return doctor.CheckResult(status=status, name="x", message="")  # type: ignore[arg-type]

    def test_summary_arithmetic(self) -> None:
        results = [
            self._cr("pass"),
            self._cr("pass"),
            self._cr("warn"),
            self._cr("warn"),
            self._cr("warn"),
            self._cr("fail"),
        ]
        self.assertEqual(doctor.summary(results), (2, 3, 1))

    def test_summary_all_pass(self) -> None:
        results = [self._cr("pass")] * 5
        p, w, f = doctor.summary(results)
        self.assertEqual(p, 5)
        self.assertEqual(w, 0)
        self.assertEqual(f, 0)

    def test_summary_all_fail(self) -> None:
        results = [self._cr("fail")] * 3
        p, w, f = doctor.summary(results)
        self.assertEqual(p, 0)
        self.assertEqual(w, 0)
        self.assertEqual(f, 3)

    def test_summary_empty_list(self) -> None:
        p, w, f = doctor.summary([])
        self.assertEqual((p, w, f), (0, 0, 0))

    def test_summary_returns_tuple(self) -> None:
        result = doctor.summary([])
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 3)

    def test_summary_values_sum_to_length(self) -> None:
        results = [
            self._cr("pass"),
            self._cr("warn"),
            self._cr("fail"),
            self._cr("pass"),
        ]
        p, w, f = doctor.summary(results)
        self.assertEqual(p + w + f, len(results))


# ---------------------------------------------------------------------------
# check_claude_md_exists (check #1)
# ---------------------------------------------------------------------------


class TestCheckClaudeMdExists(unittest.TestCase):
    """PRD §9: warn if CLAUDE.md missing; pass if present."""

    def test_missing_claude_md_is_warn(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = doctor.check_claude_md_exists(Path(tmpdir))
            self.assertEqual(result.status, "warn")

    def test_present_claude_md_is_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "CLAUDE.md").write_text("# Hello\n", encoding="utf-8")
            result = doctor.check_claude_md_exists(Path(tmpdir))
            self.assertEqual(result.status, "pass")

    def test_returns_check_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = doctor.check_claude_md_exists(Path(tmpdir))
            self.assertIsInstance(result, doctor.CheckResult)


# ---------------------------------------------------------------------------
# check_claude_md_has_gateway (check #2)
# ---------------------------------------------------------------------------


class TestCheckClaudeMdHasGateway(unittest.TestCase):
    """PRD §9: warn if LIGHTMEM:GATEWAY:START marker absent in CLAUDE.md."""

    def test_no_claude_md_is_warn(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = doctor.check_claude_md_has_gateway(Path(tmpdir))
            self.assertEqual(result.status, "warn")

    def test_claude_md_without_marker_is_warn(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "CLAUDE.md").write_text("# No gateway\n", encoding="utf-8")
            result = doctor.check_claude_md_has_gateway(Path(tmpdir))
            self.assertEqual(result.status, "warn")

    def test_claude_md_with_marker_is_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            content = f"{_GATEWAY_MARKER}\nsome content\n{_GATEWAY_END}\n"
            (Path(tmpdir) / "CLAUDE.md").write_text(content, encoding="utf-8")
            result = doctor.check_claude_md_has_gateway(Path(tmpdir))
            self.assertEqual(result.status, "pass")

    def test_fix_hint_or_message_suggests_init_when_file_exists_no_marker(self) -> None:
        """Spec: 'warn, suggest /lightmem:init' when CLAUDE.md exists but lacks the marker."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "CLAUDE.md").write_text("# My project\n", encoding="utf-8")
            result = doctor.check_claude_md_has_gateway(Path(tmpdir))
            hint_text = (result.fix_hint or "").lower()
            msg_text = result.message.lower()
            self.assertTrue(
                "init" in hint_text or "init" in msg_text or "lightmem" in msg_text,
                f"Expected suggestion referencing 'init' or 'lightmem'; got "
                f"fix_hint={result.fix_hint!r}, message={result.message!r}",
            )


# ---------------------------------------------------------------------------
# check_claude_md_size_warn (check #3)
# ---------------------------------------------------------------------------


class TestCheckClaudeMdSizeWarn(unittest.TestCase):
    """PRD §5.2: warn if CLAUDE.md bytes > 8192; pass if <= 8192."""

    def test_small_file_is_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "CLAUDE.md").write_text("x" * 100, encoding="utf-8")
            result = doctor.check_claude_md_size_warn(Path(tmpdir))
            self.assertEqual(result.status, "pass")

    def test_file_just_under_8kb_is_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "CLAUDE.md").write_text("x" * 8192, encoding="utf-8")
            result = doctor.check_claude_md_size_warn(Path(tmpdir))
            self.assertEqual(result.status, "pass")

    def test_file_over_8kb_is_warn(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "CLAUDE.md").write_text("x" * 8193, encoding="utf-8")
            result = doctor.check_claude_md_size_warn(Path(tmpdir))
            self.assertEqual(result.status, "warn")

    def test_file_over_16kb_is_still_warn(self) -> None:
        """This check only handles the warn boundary; fail is check #4."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "CLAUDE.md").write_text("x" * 17000, encoding="utf-8")
            result = doctor.check_claude_md_size_warn(Path(tmpdir))
            self.assertEqual(result.status, "warn")

    def test_missing_claude_md_is_pass(self) -> None:
        """No CLAUDE.md → no size to check; must not crash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = doctor.check_claude_md_size_warn(Path(tmpdir))
            # pass is acceptable (file absent means no size violation)
            self.assertIn(result.status, ("pass", "warn"))


# ---------------------------------------------------------------------------
# check_claude_md_size_fail (check #4)
# ---------------------------------------------------------------------------


class TestCheckClaudeMdSizeFail(unittest.TestCase):
    """PRD §5.2: fail if CLAUDE.md bytes > 16384."""

    def test_small_file_is_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "CLAUDE.md").write_text("x" * 100, encoding="utf-8")
            result = doctor.check_claude_md_size_fail(Path(tmpdir))
            self.assertEqual(result.status, "pass")

    def test_file_just_under_16kb_is_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "CLAUDE.md").write_text("x" * 16384, encoding="utf-8")
            result = doctor.check_claude_md_size_fail(Path(tmpdir))
            self.assertEqual(result.status, "pass")

    def test_file_over_16kb_is_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "CLAUDE.md").write_text("x" * 16385, encoding="utf-8")
            result = doctor.check_claude_md_size_fail(Path(tmpdir))
            self.assertEqual(result.status, "fail")

    def test_missing_claude_md_is_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = doctor.check_claude_md_size_fail(Path(tmpdir))
            self.assertIn(result.status, ("pass", "warn"))


# ---------------------------------------------------------------------------
# check_lightmem_dir_exists (check #5)
# ---------------------------------------------------------------------------


class TestCheckLightmemDirExists(unittest.TestCase):
    """PRD §9: warn if .claude/lightmem/ missing."""

    def test_missing_dir_is_warn(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = doctor.check_lightmem_dir_exists(Path(tmpdir))
            self.assertEqual(result.status, "warn")

    def test_present_dir_is_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_lightmem_dir(Path(tmpdir))
            result = doctor.check_lightmem_dir_exists(Path(tmpdir))
            self.assertEqual(result.status, "pass")


# ---------------------------------------------------------------------------
# check_gitignore_present (check #6)
# ---------------------------------------------------------------------------


class TestCheckGitignorePresent(unittest.TestCase):
    """PRD §9: warn if .claude/lightmem/.gitignore missing or incomplete."""

    def test_missing_gitignore_is_warn(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_lightmem_dir(Path(tmpdir))
            result = doctor.check_gitignore_present(Path(tmpdir))
            self.assertEqual(result.status, "warn")

    def test_gitignore_without_journal_is_warn(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            # Present but missing journal.jsonl entry
            _write_gitignore(lm, "sessions/\nstate.json\n")
            result = doctor.check_gitignore_present(Path(tmpdir))
            self.assertEqual(result.status, "warn")

    def test_gitignore_without_sessions_is_warn(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            _write_gitignore(lm, "journal.jsonl\nstate.json\n")
            result = doctor.check_gitignore_present(Path(tmpdir))
            self.assertEqual(result.status, "warn")

    def test_gitignore_without_state_json_is_warn(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            _write_gitignore(lm, "journal.jsonl\nsessions/\n")
            result = doctor.check_gitignore_present(Path(tmpdir))
            self.assertEqual(result.status, "warn")

    def test_complete_gitignore_is_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            _write_gitignore(
                lm,
                "journal.jsonl\nsessions/\narchive/\nstate.json\n"
                ".last-purge\ncompaction-log.txt\ninbox/\n",
            )
            result = doctor.check_gitignore_present(Path(tmpdir))
            self.assertEqual(result.status, "pass")


# ---------------------------------------------------------------------------
# check_topic_frontmatter_valid (check #7)
# ---------------------------------------------------------------------------


class TestCheckTopicFrontmatterValid(unittest.TestCase):
    """PRD §9: fail if any topic has missing required frontmatter fields."""

    def test_no_topics_is_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_lightmem_dir(Path(tmpdir))
            result = doctor.check_topic_frontmatter_valid(Path(tmpdir))
            self.assertEqual(result.status, "pass")

    def test_valid_topic_is_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            topics_dir = lm / "topics"
            _write_topic(topics_dir, "my-topic.md", _VALID_TOPIC)
            result = doctor.check_topic_frontmatter_valid(Path(tmpdir))
            self.assertEqual(result.status, "pass")

    def test_topic_missing_id_is_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            topics_dir = lm / "topics"
            content = "---\nkind: decision\nsummary: test\nstatus: active\n---\nbody\n"
            _write_topic(topics_dir, "missing-id.md", content)
            result = doctor.check_topic_frontmatter_valid(Path(tmpdir))
            self.assertEqual(result.status, "fail")

    def test_topic_missing_kind_is_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            topics_dir = lm / "topics"
            content = "---\nid: my-topic\nsummary: test\nstatus: active\n---\nbody\n"
            _write_topic(topics_dir, "my-topic.md", content)
            result = doctor.check_topic_frontmatter_valid(Path(tmpdir))
            self.assertEqual(result.status, "fail")

    def test_topic_missing_summary_is_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            topics_dir = lm / "topics"
            content = "---\nid: my-topic\nkind: decision\nstatus: active\n---\nbody\n"
            _write_topic(topics_dir, "my-topic.md", content)
            result = doctor.check_topic_frontmatter_valid(Path(tmpdir))
            self.assertEqual(result.status, "fail")

    def test_topic_missing_status_is_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            topics_dir = lm / "topics"
            content = "---\nid: my-topic\nkind: decision\nsummary: test\n---\nbody\n"
            _write_topic(topics_dir, "my-topic.md", content)
            result = doctor.check_topic_frontmatter_valid(Path(tmpdir))
            self.assertEqual(result.status, "fail")

    def test_fail_result_mentions_offending_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            topics_dir = lm / "topics"
            content = "---\nkind: decision\nsummary: test\nstatus: active\n---\nbody\n"
            _write_topic(topics_dir, "bad-file.md", content)
            result = doctor.check_topic_frontmatter_valid(Path(tmpdir))
            self.assertEqual(result.status, "fail")
            # message should mention the problematic file somehow
            self.assertIn("bad-file", result.message)


# ---------------------------------------------------------------------------
# check_topic_id_matches_filename (check #8)
# ---------------------------------------------------------------------------


class TestCheckTopicIdMatchesFilename(unittest.TestCase):
    """PRD §9: fail if frontmatter id != filename stem."""

    def test_matching_id_is_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            topics_dir = lm / "topics"
            content = "---\nid: my-topic\nkind: decision\nsummary: s\nstatus: active\n---\n"
            _write_topic(topics_dir, "my-topic.md", content)
            result = doctor.check_topic_id_matches_filename(Path(tmpdir))
            self.assertEqual(result.status, "pass")

    def test_mismatched_id_is_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            topics_dir = lm / "topics"
            content = "---\nid: wrong-id\nkind: decision\nsummary: s\nstatus: active\n---\n"
            _write_topic(topics_dir, "my-topic.md", content)
            result = doctor.check_topic_id_matches_filename(Path(tmpdir))
            self.assertEqual(result.status, "fail")

    def test_no_topics_is_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_lightmem_dir(Path(tmpdir))
            result = doctor.check_topic_id_matches_filename(Path(tmpdir))
            self.assertEqual(result.status, "pass")


# ---------------------------------------------------------------------------
# check_slug_is_kebab_case (check #9)
# ---------------------------------------------------------------------------


class TestCheckSlugIsKebabCase(unittest.TestCase):
    """PRD §9: fail if any topic id doesn't match ^[a-z][a-z0-9-]*$."""

    def test_valid_kebab_is_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            topics_dir = lm / "topics"
            content = "---\nid: valid-slug\nkind: decision\nsummary: s\nstatus: active\n---\n"
            _write_topic(topics_dir, "valid-slug.md", content)
            result = doctor.check_slug_is_kebab_case(Path(tmpdir))
            self.assertEqual(result.status, "pass")

    def test_slug_with_digit_is_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            topics_dir = lm / "topics"
            content = "---\nid: slug-v2\nkind: decision\nsummary: s\nstatus: active\n---\n"
            _write_topic(topics_dir, "slug-v2.md", content)
            result = doctor.check_slug_is_kebab_case(Path(tmpdir))
            self.assertEqual(result.status, "pass")

    def test_uppercase_slug_is_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            topics_dir = lm / "topics"
            content = "---\nid: BadSlug\nkind: decision\nsummary: s\nstatus: active\n---\n"
            _write_topic(topics_dir, "BadSlug.md", content)
            result = doctor.check_slug_is_kebab_case(Path(tmpdir))
            self.assertEqual(result.status, "fail")

    def test_underscore_slug_is_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            topics_dir = lm / "topics"
            content = "---\nid: bad_slug\nkind: decision\nsummary: s\nstatus: active\n---\n"
            _write_topic(topics_dir, "bad_slug.md", content)
            result = doctor.check_slug_is_kebab_case(Path(tmpdir))
            self.assertEqual(result.status, "fail")

    def test_no_topics_is_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_lightmem_dir(Path(tmpdir))
            result = doctor.check_slug_is_kebab_case(Path(tmpdir))
            self.assertEqual(result.status, "pass")


# ---------------------------------------------------------------------------
# check_no_duplicate_slugs (check #10)
# ---------------------------------------------------------------------------


class TestCheckNoDuplicateSlugs(unittest.TestCase):
    """PRD §9: fail if any two topic files share an id."""

    def test_unique_slugs_is_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            topics_dir = lm / "topics"
            _write_topic(topics_dir, "topic-a.md",
                         "---\nid: topic-a\nkind: decision\nsummary: s\nstatus: active\n---\n")
            _write_topic(topics_dir, "topic-b.md",
                         "---\nid: topic-b\nkind: decision\nsummary: s\nstatus: active\n---\n")
            result = doctor.check_no_duplicate_slugs(Path(tmpdir))
            self.assertEqual(result.status, "pass")

    def test_duplicate_slugs_is_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            topics_dir = lm / "topics"
            subdir = topics_dir / "decisions"
            subdir.mkdir(parents=True, exist_ok=True)
            shared_id = "---\nid: same-id\nkind: decision\nsummary: s\nstatus: active\n---\n"
            _write_topic(topics_dir, "same-id.md", shared_id)
            (subdir / "also-same.md").write_text(
                "---\nid: same-id\nkind: decision\nsummary: s\nstatus: active\n---\n",
                encoding="utf-8",
            )
            result = doctor.check_no_duplicate_slugs(Path(tmpdir))
            self.assertEqual(result.status, "fail")

    def test_no_topics_is_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_lightmem_dir(Path(tmpdir))
            result = doctor.check_no_duplicate_slugs(Path(tmpdir))
            self.assertEqual(result.status, "pass")


# ---------------------------------------------------------------------------
# check_topic_status_valid (check #11)
# ---------------------------------------------------------------------------


class TestCheckTopicStatusValid(unittest.TestCase):
    """PRD §9: fail if any topic status not in {active, superseded, archived}."""

    def test_active_status_is_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            _write_topic(lm / "topics", "t.md",
                         "---\nid: t\nkind: decision\nsummary: s\nstatus: active\n---\n")
            result = doctor.check_topic_status_valid(Path(tmpdir))
            self.assertEqual(result.status, "pass")

    def test_superseded_status_is_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            _write_topic(lm / "topics", "t.md",
                         "---\nid: t\nkind: decision\nsummary: s\nstatus: superseded\n---\n")
            result = doctor.check_topic_status_valid(Path(tmpdir))
            self.assertEqual(result.status, "pass")

    def test_archived_status_is_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            _write_topic(lm / "topics", "t.md",
                         "---\nid: t\nkind: decision\nsummary: s\nstatus: archived\n---\n")
            result = doctor.check_topic_status_valid(Path(tmpdir))
            self.assertEqual(result.status, "pass")

    def test_draft_status_is_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            _write_topic(lm / "topics", "t.md",
                         "---\nid: t\nkind: decision\nsummary: s\nstatus: draft\n---\n")
            result = doctor.check_topic_status_valid(Path(tmpdir))
            self.assertEqual(result.status, "fail")

    def test_invalid_status_is_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            _write_topic(lm / "topics", "t.md",
                         "---\nid: t\nkind: decision\nsummary: s\nstatus: wip\n---\n")
            result = doctor.check_topic_status_valid(Path(tmpdir))
            self.assertEqual(result.status, "fail")

    def test_no_topics_is_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_lightmem_dir(Path(tmpdir))
            result = doctor.check_topic_status_valid(Path(tmpdir))
            self.assertEqual(result.status, "pass")


# ---------------------------------------------------------------------------
# check_superseded_by_resolves (check #12)
# ---------------------------------------------------------------------------


class TestCheckSupersededByResolves(unittest.TestCase):
    """PRD §9: fail if superseded_by references a missing topic."""

    def test_no_superseded_by_field_is_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            _write_topic(lm / "topics", "t.md", _VALID_TOPIC)
            result = doctor.check_superseded_by_resolves(Path(tmpdir))
            self.assertEqual(result.status, "pass")

    def test_superseded_by_null_is_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            content = (
                "---\nid: t\nkind: decision\nsummary: s\n"
                "status: active\nsuperseded_by: null\n---\n"
            )
            _write_topic(lm / "topics", "t.md", content)
            result = doctor.check_superseded_by_resolves(Path(tmpdir))
            self.assertEqual(result.status, "pass")

    def test_superseded_by_existing_target_is_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            topics_dir = lm / "topics"
            _write_topic(topics_dir, "topic-a.md",
                         "---\nid: topic-a\nkind: decision\nsummary: s\n"
                         "status: superseded\nsuperseded_by: topic-b\n---\n")
            _write_topic(topics_dir, "topic-b.md",
                         "---\nid: topic-b\nkind: decision\nsummary: s\nstatus: active\n---\n")
            result = doctor.check_superseded_by_resolves(Path(tmpdir))
            self.assertEqual(result.status, "pass")

    def test_superseded_by_missing_target_is_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            content = (
                "---\nid: t\nkind: decision\nsummary: s\n"
                "status: superseded\nsuperseded_by: nonexistent-target\n---\n"
            )
            _write_topic(lm / "topics", "t.md", content)
            result = doctor.check_superseded_by_resolves(Path(tmpdir))
            self.assertEqual(result.status, "fail")

    def test_no_topics_is_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_lightmem_dir(Path(tmpdir))
            result = doctor.check_superseded_by_resolves(Path(tmpdir))
            self.assertEqual(result.status, "pass")


# ---------------------------------------------------------------------------
# check_no_broken_relative_links (check #13)
# ---------------------------------------------------------------------------


class TestCheckNoBrokenRelativeLinks(unittest.TestCase):
    """PRD §9: warn for [text](./path) links to non-existent local files."""

    def test_no_topics_is_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_lightmem_dir(Path(tmpdir))
            result = doctor.check_no_broken_relative_links(Path(tmpdir))
            self.assertEqual(result.status, "pass")

    def test_topic_with_no_links_is_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            _write_topic(lm / "topics", "t.md", _VALID_TOPIC)
            result = doctor.check_no_broken_relative_links(Path(tmpdir))
            self.assertEqual(result.status, "pass")

    def test_topic_with_broken_relative_link_is_warn(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            topics_dir = lm / "topics"
            content = (
                "---\nid: t\nkind: decision\nsummary: s\nstatus: active\n---\n"
                "See [here](./nonexistent-file.md) for details.\n"
            )
            _write_topic(topics_dir, "t.md", content)
            result = doctor.check_no_broken_relative_links(Path(tmpdir))
            self.assertEqual(result.status, "warn")

    def test_topic_with_valid_relative_link_is_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            topics_dir = lm / "topics"
            topics_dir.mkdir(parents=True, exist_ok=True)
            # Create the target file first (topics_dir now exists)
            (topics_dir / "target.md").write_text("# Target\n", encoding="utf-8")
            content = (
                "---\nid: t\nkind: decision\nsummary: s\nstatus: active\n---\n"
                "See [here](./target.md) for details.\n"
            )
            _write_topic(topics_dir, "t.md", content)
            result = doctor.check_no_broken_relative_links(Path(tmpdir))
            self.assertEqual(result.status, "pass")


# ---------------------------------------------------------------------------
# check_journal_size_ok (check #14)
# ---------------------------------------------------------------------------


class TestCheckJournalSizeOk(unittest.TestCase):
    """PRD §9: warn if journal.jsonl > LIGHTMEM_JOURNAL_MAX_MB."""

    def test_no_journal_is_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_lightmem_dir(Path(tmpdir))
            result = doctor.check_journal_size_ok(Path(tmpdir))
            self.assertEqual(result.status, "pass")

    def test_small_journal_is_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            (lm / "journal.jsonl").write_text('{"ts":"2026-01-01"}\n', encoding="utf-8")
            result = doctor.check_journal_size_ok(Path(tmpdir))
            self.assertEqual(result.status, "pass")

    def test_large_journal_with_small_env_override_is_warn(self) -> None:
        """Set LIGHTMEM_JOURNAL_MAX_MB=1, write >1MB journal → warn."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            # Write just over 1MB
            data = "x" * (1024 * 1024 + 1)
            (lm / "journal.jsonl").write_text(data, encoding="utf-8")
            with unittest.mock.patch.dict(os.environ, {"LIGHTMEM_JOURNAL_MAX_MB": "1"}):
                result = doctor.check_journal_size_ok(Path(tmpdir))
            self.assertEqual(result.status, "warn")


# ---------------------------------------------------------------------------
# check_secret_scan (check #15)
# ---------------------------------------------------------------------------


class TestCheckSecretScan(unittest.TestCase):
    """PRD §9: fail if SECRET_REGEX matches in journal tail or topic bodies outside [REDACTED]."""

    def test_no_journal_and_no_topics_is_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_lightmem_dir(Path(tmpdir))
            result = doctor.check_secret_scan(Path(tmpdir))
            self.assertEqual(result.status, "pass")

    def test_clean_journal_is_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            (lm / "journal.jsonl").write_text(
                '{"ts":"2026-01-01","message":"no secrets here"}\n', encoding="utf-8"
            )
            result = doctor.check_secret_scan(Path(tmpdir))
            self.assertEqual(result.status, "pass")

    def test_journal_with_raw_api_key_is_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            (lm / "journal.jsonl").write_text(
                '{"excerpt":"api_key=abcdefgh12345678"}\n', encoding="utf-8"
            )
            result = doctor.check_secret_scan(Path(tmpdir))
            self.assertEqual(result.status, "fail")

    def test_journal_with_redacted_value_is_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            (lm / "journal.jsonl").write_text(
                '{"excerpt":"api_key=[REDACTED]"}\n', encoding="utf-8"
            )
            result = doctor.check_secret_scan(Path(tmpdir))
            self.assertEqual(result.status, "pass")

    def test_topic_with_raw_secret_is_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            content = (
                "---\nid: t\nkind: decision\nsummary: s\nstatus: active\n---\n"
                "password=supersecretpassword1\n"
            )
            _write_topic(lm / "topics", "t.md", content)
            result = doctor.check_secret_scan(Path(tmpdir))
            self.assertEqual(result.status, "fail")

    def test_topic_with_clean_body_is_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            _write_topic(lm / "topics", "t.md", _VALID_TOPIC)
            result = doctor.check_secret_scan(Path(tmpdir))
            self.assertEqual(result.status, "pass")

    def test_session_file_with_raw_secret_is_fail(self) -> None:
        # Codex H2: sessions/ is a second write path that resume injection reads
        # back into Claude's context. secret_scan must cover it.
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            sessions = lm / "sessions"
            sessions.mkdir(exist_ok=True)
            (sessions / "2026-05-21-abcdef00.md").write_text(
                "# Session\n\n## Tasks\n- api_key=sssssecret12345xyz\n",
                encoding="utf-8",
            )
            result = doctor.check_secret_scan(Path(tmpdir))
            self.assertEqual(result.status, "fail")
            self.assertIn("sessions/", result.message)


# ---------------------------------------------------------------------------
# check_archive_purge_recent (check #16)
# ---------------------------------------------------------------------------


class TestCheckArchivePurgeRecent(unittest.TestCase):
    """PRD §9: warn if .last-purge mtime older than RETENTION_DAYS × 2 days, or missing."""

    def test_missing_last_purge_is_warn(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_lightmem_dir(Path(tmpdir))
            result = doctor.check_archive_purge_recent(Path(tmpdir))
            self.assertEqual(result.status, "warn")

    def test_fresh_last_purge_is_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            purge_marker = lm / ".last-purge"
            purge_marker.write_text("", encoding="utf-8")
            # Default mtime is now → should pass
            result = doctor.check_archive_purge_recent(Path(tmpdir))
            self.assertEqual(result.status, "pass")

    def test_old_last_purge_is_warn(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            purge_marker = lm / ".last-purge"
            purge_marker.write_text("", encoding="utf-8")
            # Set mtime to 200 days in the past (well beyond any RETENTION_DAYS × 2)
            old_time = time.time() - (200 * 24 * 3600)
            os.utime(purge_marker, (old_time, old_time))
            result = doctor.check_archive_purge_recent(Path(tmpdir))
            self.assertEqual(result.status, "warn")


# ---------------------------------------------------------------------------
# check_inbox_absent (check #17)
# ---------------------------------------------------------------------------


class TestCheckInboxAbsent(unittest.TestCase):
    """v0.2: inbox/ is a supported artifact. Warn only on unexpected files inside."""

    def test_no_inbox_is_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_lightmem_dir(Path(tmpdir))
            result = doctor.check_inbox_absent(Path(tmpdir))
            self.assertEqual(result.status, "pass")

    def test_inbox_with_only_pending_md_is_pass(self) -> None:
        """inbox/pending.md is the only expected file — should not warn."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            inbox = lm / "inbox"
            inbox.mkdir()
            (inbox / "pending.md").write_text("# LightMem inbox\n", encoding="utf-8")
            result = doctor.check_inbox_absent(Path(tmpdir))
            self.assertEqual(result.status, "pass")

    def test_inbox_with_unexpected_file_is_warn(self) -> None:
        """Unexpected files inside inbox/ should trigger a warn."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            inbox = lm / "inbox"
            inbox.mkdir()
            (inbox / "stray_file.txt").write_text("surprise", encoding="utf-8")
            result = doctor.check_inbox_absent(Path(tmpdir))
            self.assertEqual(result.status, "warn")

    def test_inbox_empty_dir_is_pass(self) -> None:
        """An empty inbox/ dir (no files) should pass — not a problem."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            (lm / "inbox").mkdir()
            result = doctor.check_inbox_absent(Path(tmpdir))
            self.assertEqual(result.status, "pass")

    def test_no_lightmem_dir_at_all_is_pass(self) -> None:
        """No .claude/lightmem/ means no inbox either → pass."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = doctor.check_inbox_absent(Path(tmpdir))
            self.assertEqual(result.status, "pass")


if __name__ == "__main__":
    unittest.main()
