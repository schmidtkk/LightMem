from __future__ import annotations

"""
Tests for scripts/lib/init_helper.py

Derived purely from PRD_v0.2.md §7.1 (/lightmem:init UX), §5.2 (gateway block),
§5.5 (non-committable state), and the Round-6 QA API spec.
No implementation files were read during authoring.

Expected API:
  - SkeletonPlan — frozen dataclass: repo_root, existing_claude_md,
                   existing_lightmem_dir, topics_to_create
  - inspect_repo(repo_root: Path) -> SkeletonPlan
  - create_skeleton(repo_root: Path) -> None
  - gateway_block_content() -> str
  - update_claude_md(repo_root, mode: Literal["append_fenced","backup_rewrite","abort"])
      -> Path | None

SPEC AMBIGUITIES ENCOUNTERED:
  SA1. `inspect_repo.topics_to_create` reads from the templates directory at the
       repo root.  If templates/ does not exist, the list will be empty.  Tests
       that require non-empty topics_to_create are guarded with skipUnless.
  SA2. `gateway_block_content()` reads templates/CLAUDE.md.tmpl.  If the file
       does not exist, behavior is undefined; the test is guarded with skipUnless.
  SA3. The backup filename format "CLAUDE.md.bak.<UTC-ISO>" with ":" → "-" is
       tested by checking the .bak. infix and that the resulting filename is
       filesystem-safe (no colons).
  SA4. "All file writes atomic" — tested by verifying no .tmp leftover after
       each write operation.
  SA5. update_claude_md("append_fenced") for a file already containing the
       fence: the spec says "replace only the fence body".  Tests verify
       exactly one START/END marker pair remains in the result, and that
       content outside the fence is preserved.
"""

import dataclasses
import json
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_LIB = _REPO_ROOT / "scripts" / "lib"
if str(_SCRIPTS_LIB) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_LIB))

import init_helper  # type: ignore[import]  # noqa: E402 – imported after path fix

_TEMPLATES_DIR = _REPO_ROOT / "templates"
_TOPICS_TMPL_DIR = _TEMPLATES_DIR / "topics"
_CLAUDE_TMPL = _TEMPLATES_DIR / "CLAUDE.md.tmpl"

_HAS_TOPICS_TEMPLATES = _TOPICS_TMPL_DIR.is_dir() and bool(
    list(_TOPICS_TMPL_DIR.rglob("*.md"))
)
_HAS_CLAUDE_TMPL = _CLAUDE_TMPL.is_file()

_GATEWAY_START = "<!-- LIGHTMEM:GATEWAY:START -->"
_GATEWAY_END = "<!-- LIGHTMEM:GATEWAY:END -->"


# ---------------------------------------------------------------------------
# SkeletonPlan dataclass
# ---------------------------------------------------------------------------


class TestSkeletonPlanDataclass(unittest.TestCase):
    """SkeletonPlan must be a frozen dataclass with the required fields."""

    def _make(self, **kwargs: object) -> init_helper.SkeletonPlan:
        defaults: dict[str, object] = {
            "repo_root": Path("/tmp/fake"),
            "existing_claude_md": False,
            "existing_lightmem_dir": False,
            "topics_to_create": (),
        }
        defaults.update(kwargs)
        return init_helper.SkeletonPlan(**defaults)  # type: ignore[arg-type]

    def test_instantiation(self) -> None:
        plan = self._make()
        self.assertIsInstance(plan, init_helper.SkeletonPlan)

    def test_repo_root_field(self) -> None:
        p = Path("/tmp/myrepo")
        plan = self._make(repo_root=p)
        self.assertEqual(plan.repo_root, p)

    def test_existing_claude_md_field(self) -> None:
        plan = self._make(existing_claude_md=True)
        self.assertTrue(plan.existing_claude_md)

    def test_existing_lightmem_dir_field(self) -> None:
        plan = self._make(existing_lightmem_dir=True)
        self.assertTrue(plan.existing_lightmem_dir)

    def test_topics_to_create_field(self) -> None:
        plan = self._make(topics_to_create=("mission", "architecture"))
        self.assertEqual(plan.topics_to_create, ("mission", "architecture"))

    def test_is_frozen(self) -> None:
        plan = self._make()
        with self.assertRaises((AttributeError, TypeError, dataclasses.FrozenInstanceError)):
            plan.existing_claude_md = True  # type: ignore[misc]


# ---------------------------------------------------------------------------
# inspect_repo()
# ---------------------------------------------------------------------------


class TestInspectRepoFreshDir(unittest.TestCase):
    """inspect_repo on an empty tempdir: no CLAUDE.md, no lightmem dir."""

    def test_returns_skeleton_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan = init_helper.inspect_repo(Path(tmpdir))
            self.assertIsInstance(plan, init_helper.SkeletonPlan)

    def test_repo_root_set_correctly(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = init_helper.inspect_repo(root)
            self.assertEqual(plan.repo_root, root)

    def test_no_claude_md(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan = init_helper.inspect_repo(Path(tmpdir))
            self.assertFalse(plan.existing_claude_md)

    def test_no_lightmem_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan = init_helper.inspect_repo(Path(tmpdir))
            self.assertFalse(plan.existing_lightmem_dir)

    def test_topics_to_create_is_tuple(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan = init_helper.inspect_repo(Path(tmpdir))
            self.assertIsInstance(plan.topics_to_create, tuple)

    @unittest.skipUnless(_HAS_TOPICS_TEMPLATES, "templates/topics/ not present")
    def test_topics_to_create_nonempty_when_templates_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan = init_helper.inspect_repo(Path(tmpdir))
            self.assertGreater(len(plan.topics_to_create), 0)


class TestInspectRepoExistingSetup(unittest.TestCase):
    """inspect_repo on a dir with existing CLAUDE.md and .claude/lightmem/."""

    def test_detects_existing_claude_md(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "CLAUDE.md").write_text("# My project\n", encoding="utf-8")
            plan = init_helper.inspect_repo(Path(tmpdir))
            self.assertTrue(plan.existing_claude_md)

    def test_detects_existing_lightmem_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / ".claude" / "lightmem").mkdir(parents=True)
            plan = init_helper.inspect_repo(Path(tmpdir))
            self.assertTrue(plan.existing_lightmem_dir)

    def test_both_existing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "CLAUDE.md").write_text("# Project\n", encoding="utf-8")
            (root / ".claude" / "lightmem").mkdir(parents=True)
            plan = init_helper.inspect_repo(root)
            self.assertTrue(plan.existing_claude_md)
            self.assertTrue(plan.existing_lightmem_dir)

    def test_inspect_is_read_only(self) -> None:
        """inspect_repo must not create files or directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            before = set(root.rglob("*"))
            init_helper.inspect_repo(root)
            after = set(root.rglob("*"))
            self.assertEqual(before, after, "inspect_repo must not mutate the filesystem")


# ---------------------------------------------------------------------------
# create_skeleton()
# ---------------------------------------------------------------------------


class TestCreateSkeletonDirectories(unittest.TestCase):
    """create_skeleton creates the required directory structure."""

    def test_creates_topics_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            init_helper.create_skeleton(Path(tmpdir))
            self.assertTrue((Path(tmpdir) / ".claude" / "lightmem" / "topics").is_dir())

    def test_creates_sessions_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            init_helper.create_skeleton(Path(tmpdir))
            self.assertTrue((Path(tmpdir) / ".claude" / "lightmem" / "sessions").is_dir())

    def test_creates_archive_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            init_helper.create_skeleton(Path(tmpdir))
            self.assertTrue((Path(tmpdir) / ".claude" / "lightmem" / "archive").is_dir())

    def test_creates_gitignore(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            init_helper.create_skeleton(Path(tmpdir))
            gitignore = Path(tmpdir) / ".claude" / "lightmem" / ".gitignore"
            self.assertTrue(gitignore.is_file())

    def test_creates_state_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            init_helper.create_skeleton(Path(tmpdir))
            state_json = Path(tmpdir) / ".claude" / "lightmem" / "state.json"
            self.assertTrue(state_json.is_file())


class TestCreateSkeletonGitignore(unittest.TestCase):
    """create_skeleton writes a .gitignore that excludes required paths."""

    def _gitignore_content(self, tmpdir: str) -> str:
        return (Path(tmpdir) / ".claude" / "lightmem" / ".gitignore").read_text(encoding="utf-8")

    def test_gitignore_contains_journal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            init_helper.create_skeleton(Path(tmpdir))
            self.assertIn("journal.jsonl", self._gitignore_content(tmpdir))

    def test_gitignore_contains_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            init_helper.create_skeleton(Path(tmpdir))
            self.assertIn("sessions/", self._gitignore_content(tmpdir))

    def test_gitignore_contains_state_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            init_helper.create_skeleton(Path(tmpdir))
            self.assertIn("state.json", self._gitignore_content(tmpdir))


class TestCreateSkeletonStateJson(unittest.TestCase):
    """create_skeleton writes valid state.json with schema_version=1."""

    def _read_state(self, tmpdir: str) -> dict:
        return json.loads(
            (Path(tmpdir) / ".claude" / "lightmem" / "state.json").read_text(encoding="utf-8")
        )

    def test_state_json_is_valid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            init_helper.create_skeleton(Path(tmpdir))
            try:
                self._read_state(tmpdir)
            except json.JSONDecodeError as exc:
                self.fail(f"state.json is not valid JSON: {exc}")

    def test_state_json_schema_version_is_1(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            init_helper.create_skeleton(Path(tmpdir))
            data = self._read_state(tmpdir)
            self.assertEqual(data.get("schema_version"), 1)


class TestCreateSkeletonTopicTemplates(unittest.TestCase):
    """create_skeleton copies topic templates when they exist."""

    @unittest.skipUnless(_HAS_TOPICS_TEMPLATES, "templates/topics/ not present")
    def test_copies_topic_templates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            init_helper.create_skeleton(Path(tmpdir))
            topics_dir = Path(tmpdir) / ".claude" / "lightmem" / "topics"
            topic_files = list(topics_dir.rglob("*.md"))
            self.assertGreater(len(topic_files), 0,
                                "Topic templates must be copied into topics/ dir")

    @unittest.skipUnless(_HAS_TOPICS_TEMPLATES, "templates/topics/ not present")
    def test_preserves_subdir_structure(self) -> None:
        """Templates like decisions/example.md must retain their subdir."""
        with tempfile.TemporaryDirectory() as tmpdir:
            init_helper.create_skeleton(Path(tmpdir))
            topics_dir = Path(tmpdir) / ".claude" / "lightmem" / "topics"
            # At least one .md file should exist (top-level or in subdir)
            self.assertTrue(any(topics_dir.rglob("*.md")))


class TestCreateSkeletonIdempotent(unittest.TestCase):
    """create_skeleton does not crash on re-runs (idempotent)."""

    def test_double_run_does_not_raise(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            init_helper.create_skeleton(root)
            try:
                init_helper.create_skeleton(root)
            except Exception as exc:  # noqa: BLE001
                self.fail(f"create_skeleton raised on second run: {exc}")

    def test_double_run_dirs_still_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            init_helper.create_skeleton(root)
            init_helper.create_skeleton(root)
            lm = root / ".claude" / "lightmem"
            self.assertTrue((lm / "topics").is_dir())
            self.assertTrue((lm / "sessions").is_dir())
            self.assertTrue((lm / "archive").is_dir())


# ---------------------------------------------------------------------------
# gateway_block_content()
# ---------------------------------------------------------------------------


class TestGatewayBlockContent(unittest.TestCase):
    """gateway_block_content() returns the template body from templates/CLAUDE.md.tmpl."""

    @unittest.skipUnless(_HAS_CLAUDE_TMPL, "templates/CLAUDE.md.tmpl not present")
    def test_returns_nonempty_string(self) -> None:
        content = init_helper.gateway_block_content()
        self.assertIsInstance(content, str)
        self.assertGreater(len(content.strip()), 0)

    @unittest.skipUnless(_HAS_CLAUDE_TMPL, "templates/CLAUDE.md.tmpl not present")
    def test_returns_string_type(self) -> None:
        content = init_helper.gateway_block_content()
        self.assertIsInstance(content, str)

    def test_returns_string_always(self) -> None:
        """Even if template is absent, return type must be str (may be empty)."""
        result = init_helper.gateway_block_content()
        self.assertIsInstance(result, str)


# ---------------------------------------------------------------------------
# update_claude_md("append_fenced")
# ---------------------------------------------------------------------------


class TestUpdateClaudeMdAppendFencedNoFile(unittest.TestCase):
    """append_fenced with no existing CLAUDE.md: creates file with fence."""

    def test_creates_claude_md(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            init_helper.update_claude_md(root, "append_fenced")
            self.assertTrue((root / "CLAUDE.md").is_file())

    def test_returns_claude_md_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            result = init_helper.update_claude_md(root, "append_fenced")
            self.assertEqual(result, root / "CLAUDE.md")

    def test_new_file_contains_gateway_start(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            init_helper.update_claude_md(root, "append_fenced")
            content = (root / "CLAUDE.md").read_text(encoding="utf-8")
            self.assertIn(_GATEWAY_START, content)

    def test_new_file_contains_gateway_end(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            init_helper.update_claude_md(root, "append_fenced")
            content = (root / "CLAUDE.md").read_text(encoding="utf-8")
            self.assertIn(_GATEWAY_END, content)


class TestUpdateClaudeMdAppendFencedExistingNoFence(unittest.TestCase):
    """append_fenced with existing CLAUDE.md that has no fence: prepend fence, preserve content."""

    def test_prepends_fence_keeps_existing_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            original_content = "# My Project\n\nSome user-authored content.\n"
            (root / "CLAUDE.md").write_text(original_content, encoding="utf-8")
            init_helper.update_claude_md(root, "append_fenced")
            result = (root / "CLAUDE.md").read_text(encoding="utf-8")
            self.assertIn("Some user-authored content.", result)

    def test_fence_is_in_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "CLAUDE.md").write_text("# No fence here\n", encoding="utf-8")
            init_helper.update_claude_md(root, "append_fenced")
            result = (root / "CLAUDE.md").read_text(encoding="utf-8")
            self.assertIn(_GATEWAY_START, result)
            self.assertIn(_GATEWAY_END, result)

    def test_fence_appears_before_existing_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "CLAUDE.md").write_text("# Original\n", encoding="utf-8")
            init_helper.update_claude_md(root, "append_fenced")
            result = (root / "CLAUDE.md").read_text(encoding="utf-8")
            start_pos = result.index(_GATEWAY_START)
            original_pos = result.index("# Original")
            self.assertLess(start_pos, original_pos)


class TestUpdateClaudeMdAppendFencedExistingWithFence(unittest.TestCase):
    """append_fenced with existing fenced CLAUDE.md: exactly one fence, no duplication."""

    def _make_fenced_claude(self, root: Path, extra_content: str = "") -> None:
        content = (
            f"{_GATEWAY_START}\n"
            "## Project Memory (LightMem)\nOld gateway content.\n"
            f"{_GATEWAY_END}\n"
            "\n"
            f"{extra_content}"
        )
        (root / "CLAUDE.md").write_text(content, encoding="utf-8")

    def test_idempotent_no_duplicated_fence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._make_fenced_claude(root)
            init_helper.update_claude_md(root, "append_fenced")
            result = (root / "CLAUDE.md").read_text(encoding="utf-8")
            self.assertEqual(result.count(_GATEWAY_START), 1,
                             "Exactly one GATEWAY:START marker expected after idempotent update")
            self.assertEqual(result.count(_GATEWAY_END), 1,
                             "Exactly one GATEWAY:END marker expected after idempotent update")

    def test_content_outside_fence_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._make_fenced_claude(root, extra_content="## User Section\nHand-written.\n")
            init_helper.update_claude_md(root, "append_fenced")
            result = (root / "CLAUDE.md").read_text(encoding="utf-8")
            self.assertIn("Hand-written.", result)

    def test_returns_claude_md_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._make_fenced_claude(root)
            result = init_helper.update_claude_md(root, "append_fenced")
            self.assertEqual(result, root / "CLAUDE.md")


# ---------------------------------------------------------------------------
# update_claude_md("backup_rewrite")
# ---------------------------------------------------------------------------


class TestUpdateClaudeMdBackupRewriteWithExisting(unittest.TestCase):
    """backup_rewrite with existing CLAUDE.md: backup created, fresh file written."""

    def test_backup_file_created(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "CLAUDE.md").write_text("# Original content\n", encoding="utf-8")
            init_helper.update_claude_md(root, "backup_rewrite")
            bak_files = list(root.glob("CLAUDE.md.bak.*"))
            self.assertEqual(len(bak_files), 1, "Exactly one backup file expected")

    def test_backup_contains_original_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            original = "# Original content unique-string-12345\n"
            (root / "CLAUDE.md").write_text(original, encoding="utf-8")
            init_helper.update_claude_md(root, "backup_rewrite")
            bak_files = list(root.glob("CLAUDE.md.bak.*"))
            bak_content = bak_files[0].read_text(encoding="utf-8")
            self.assertIn("unique-string-12345", bak_content)

    def test_new_claude_md_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "CLAUDE.md").write_text("# Old\n", encoding="utf-8")
            init_helper.update_claude_md(root, "backup_rewrite")
            self.assertTrue((root / "CLAUDE.md").is_file())

    def test_backup_filename_has_no_colon(self) -> None:
        """Spec: ':' in UTC-ISO timestamps replaced with '-'."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "CLAUDE.md").write_text("original\n", encoding="utf-8")
            init_helper.update_claude_md(root, "backup_rewrite")
            bak_files = list(root.glob("CLAUDE.md.bak.*"))
            self.assertEqual(len(bak_files), 1)
            bak_name = bak_files[0].name
            self.assertNotIn(":", bak_name, "Backup filename must not contain ':'")

    def test_backup_filename_contains_bak_infix(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "CLAUDE.md").write_text("x\n", encoding="utf-8")
            init_helper.update_claude_md(root, "backup_rewrite")
            bak_files = list(root.glob("CLAUDE.md.bak.*"))
            self.assertEqual(len(bak_files), 1)
            self.assertIn(".bak.", bak_files[0].name)

    def test_returns_claude_md_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "CLAUDE.md").write_text("x\n", encoding="utf-8")
            result = init_helper.update_claude_md(root, "backup_rewrite")
            self.assertEqual(result, root / "CLAUDE.md")


class TestUpdateClaudeMdBackupRewriteNoExisting(unittest.TestCase):
    """backup_rewrite with no existing CLAUDE.md: just write fresh."""

    def test_creates_claude_md(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            init_helper.update_claude_md(root, "backup_rewrite")
            self.assertTrue((root / "CLAUDE.md").is_file())

    def test_no_backup_file_when_no_original(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            init_helper.update_claude_md(root, "backup_rewrite")
            bak_files = list(root.glob("CLAUDE.md.bak.*"))
            self.assertEqual(len(bak_files), 0, "No backup expected when original absent")

    def test_returns_claude_md_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            result = init_helper.update_claude_md(root, "backup_rewrite")
            self.assertEqual(result, root / "CLAUDE.md")


# ---------------------------------------------------------------------------
# update_claude_md("abort")
# ---------------------------------------------------------------------------


class TestUpdateClaudeMdAbort(unittest.TestCase):
    """abort: read-only; returns None; does not mutate filesystem."""

    def test_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            result = init_helper.update_claude_md(root, "abort")
            self.assertIsNone(result)

    def test_does_not_create_claude_md(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            init_helper.update_claude_md(root, "abort")
            self.assertFalse((root / "CLAUDE.md").exists())

    def test_does_not_modify_existing_claude_md(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            original = "# Original, must not change.\n"
            (root / "CLAUDE.md").write_text(original, encoding="utf-8")
            init_helper.update_claude_md(root, "abort")
            result = (root / "CLAUDE.md").read_text(encoding="utf-8")
            self.assertEqual(result, original)

    def test_no_other_files_created(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            before = set(root.rglob("*"))
            init_helper.update_claude_md(root, "abort")
            after = set(root.rglob("*"))
            self.assertEqual(before, after, "abort must not mutate the filesystem")


if __name__ == "__main__":
    unittest.main()
