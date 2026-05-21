from __future__ import annotations

"""
Tests for scripts/lib/index_builder.py

Derived purely from PRD_v0.2.md §5.3-5.4 (topic taxonomy, topic file format),
§7 (skills table: /lightmem:index regenerates index.md), and the Round-6 QA
API spec.  No implementation files were read during authoring.

Expected API:
  - build_index_md(repo_root: Path) -> str
      Walks .claude/lightmem/topics/, builds markdown table sorted by (kind, id).
      Header: "# LightMem topic index"
      Generated timestamp line
      Table columns: | id | kind | status | summary | path |
  - write_index_md(repo_root: Path) -> Path
      Atomically writes to <repo>/.claude/lightmem/index.md.
      Returns the path.

SPEC AMBIGUITIES ENCOUNTERED:
  SA1. "empty table or 'no topics'" — the spec leaves the exact wording for
       zero-topic output ambiguous.  Tests check for the header and a reasonable
       "no topics" indicator OR an empty table body; both forms are accepted.
  SA2. The `path` column format (absolute vs relative) is unspecified.  Tests
       only verify that the path column contains the filename stem or some
       non-empty path string, not its exact form.
  SA3. "Generated timestamp" format is unspecified beyond containing "Generated".
       Tests check for the substring "Generated" in the output.
  SA4. Topics with missing frontmatter: the spec says id=stem, kind="",
       status=""/"unknown".  Tests verify the output does not crash and contains
       the file stem.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_LIB = _REPO_ROOT / "scripts" / "lib"
if str(_SCRIPTS_LIB) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_LIB))

import index_builder  # type: ignore[import]  # noqa: E402 – imported after path fix


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_TOPIC_A = """\
---
id: alpha-topic
kind: decision
summary: The alpha decision
status: active
---

# Alpha

Body.
"""

_VALID_TOPIC_B = """\
---
id: beta-topic
kind: constraint
summary: The beta constraint
status: active
---

# Beta

Body.
"""

_VALID_TOPIC_C = """\
---
id: gamma-topic
kind: decision
summary: The gamma decision
status: archived
---

# Gamma

Body.
"""


def _make_lightmem_dir(root: Path) -> Path:
    lm = root / ".claude" / "lightmem"
    lm.mkdir(parents=True, exist_ok=True)
    return lm


def _write_topic(topics_dir: Path, filename: str, content: str) -> None:
    topics_dir.mkdir(parents=True, exist_ok=True)
    (topics_dir / filename).write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# build_index_md — header and structure
# ---------------------------------------------------------------------------


class TestBuildIndexMdHeader(unittest.TestCase):
    """build_index_md must return a string with the required header."""

    def test_returns_string(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_lightmem_dir(Path(tmpdir))
            result = index_builder.build_index_md(Path(tmpdir))
            self.assertIsInstance(result, str)

    def test_contains_lightmem_topic_index_header(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_lightmem_dir(Path(tmpdir))
            result = index_builder.build_index_md(Path(tmpdir))
            self.assertIn("# LightMem topic index", result)

    def test_contains_generated_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_lightmem_dir(Path(tmpdir))
            result = index_builder.build_index_md(Path(tmpdir))
            self.assertIn("Generated", result)

    def test_contains_table_header_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            # Write one topic so table header is guaranteed to appear
            _write_topic(lm / "topics", "t.md",
                         "---\nid: t\nkind: decision\nsummary: s\nstatus: active\n---\n")
            result = index_builder.build_index_md(Path(tmpdir))
            # Table header must contain all five required column names
            self.assertIn("id", result)
            self.assertIn("kind", result)
            self.assertIn("status", result)
            self.assertIn("summary", result)
            self.assertIn("path", result)

    def test_table_header_row_format(self) -> None:
        """The table header row must contain pipe-separated column names."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            _write_topic(lm / "topics", "t.md",
                         "---\nid: t\nkind: decision\nsummary: s\nstatus: active\n---\n")
            result = index_builder.build_index_md(Path(tmpdir))
            # Must contain a markdown table header row with the five columns
            self.assertIn("| id |", result)
            self.assertIn("| kind |", result)
            self.assertIn("| status |", result)
            self.assertIn("| summary |", result)
            self.assertIn("| path |", result)


# ---------------------------------------------------------------------------
# build_index_md — empty topics directory
# ---------------------------------------------------------------------------


class TestBuildIndexMdEmptyTopics(unittest.TestCase):
    """build_index_md with no topics: header present; graceful empty output."""

    def test_does_not_raise_on_empty_topics(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_lightmem_dir(Path(tmpdir))
            try:
                index_builder.build_index_md(Path(tmpdir))
            except Exception as exc:  # noqa: BLE001
                self.fail(f"build_index_md raised on empty topics dir: {exc}")

    def test_header_present_on_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_lightmem_dir(Path(tmpdir))
            result = index_builder.build_index_md(Path(tmpdir))
            self.assertIn("# LightMem topic index", result)

    def test_empty_topics_no_crash_when_topics_dir_missing(self) -> None:
        """No .claude/lightmem/topics dir at all → graceful output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_lightmem_dir(Path(tmpdir))  # creates .claude/lightmem but not topics/
            try:
                result = index_builder.build_index_md(Path(tmpdir))
                self.assertIsInstance(result, str)
            except Exception as exc:  # noqa: BLE001
                self.fail(f"build_index_md raised when topics dir missing: {exc}")


# ---------------------------------------------------------------------------
# build_index_md — rows per topic
# ---------------------------------------------------------------------------


class TestBuildIndexMdTopicRows(unittest.TestCase):
    """build_index_md with topics: one row per topic in the table."""

    def test_single_topic_row_in_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            _write_topic(lm / "topics", "alpha-topic.md", _VALID_TOPIC_A)
            result = index_builder.build_index_md(Path(tmpdir))
            self.assertIn("alpha-topic", result)

    def test_topic_id_in_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            _write_topic(lm / "topics", "my-decision.md",
                         "---\nid: my-decision\nkind: decision\nsummary: My summary\nstatus: active\n---\n")
            result = index_builder.build_index_md(Path(tmpdir))
            self.assertIn("my-decision", result)

    def test_topic_kind_in_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            _write_topic(lm / "topics", "my-decision.md",
                         "---\nid: my-decision\nkind: decision\nsummary: s\nstatus: active\n---\n")
            result = index_builder.build_index_md(Path(tmpdir))
            self.assertIn("decision", result)

    def test_topic_status_in_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            _write_topic(lm / "topics", "my-topic.md",
                         "---\nid: my-topic\nkind: gotcha\nsummary: s\nstatus: archived\n---\n")
            result = index_builder.build_index_md(Path(tmpdir))
            self.assertIn("archived", result)

    def test_topic_summary_in_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            _write_topic(lm / "topics", "my-topic.md",
                         "---\nid: my-topic\nkind: decision\n"
                         "summary: Unique summary text here\nstatus: active\n---\n")
            result = index_builder.build_index_md(Path(tmpdir))
            self.assertIn("Unique summary text here", result)

    def test_multiple_topics_all_rows_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            _write_topic(lm / "topics", "alpha-topic.md", _VALID_TOPIC_A)
            _write_topic(lm / "topics", "beta-topic.md", _VALID_TOPIC_B)
            _write_topic(lm / "topics", "gamma-topic.md", _VALID_TOPIC_C)
            result = index_builder.build_index_md(Path(tmpdir))
            self.assertIn("alpha-topic", result)
            self.assertIn("beta-topic", result)
            self.assertIn("gamma-topic", result)


# ---------------------------------------------------------------------------
# build_index_md — sorting by (kind, id)
# ---------------------------------------------------------------------------


class TestBuildIndexMdSorting(unittest.TestCase):
    """build_index_md output must be sorted by (kind, id)."""

    def test_sorted_by_kind_then_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            # constraint < decision alphabetically
            _write_topic(lm / "topics", "beta-topic.md", _VALID_TOPIC_B)   # constraint
            _write_topic(lm / "topics", "alpha-topic.md", _VALID_TOPIC_A)  # decision
            _write_topic(lm / "topics", "gamma-topic.md", _VALID_TOPIC_C)  # decision
            result = index_builder.build_index_md(Path(tmpdir))
            # beta-topic (constraint) must appear before alpha-topic (decision)
            pos_beta = result.index("beta-topic")
            pos_alpha = result.index("alpha-topic")
            self.assertLess(pos_beta, pos_alpha,
                            "constraint rows must precede decision rows (sorted by kind)")

    def test_same_kind_sorted_by_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            # Both decisions: gamma and alpha — alpha must come first
            _write_topic(lm / "topics", "gamma-topic.md", _VALID_TOPIC_C)
            _write_topic(lm / "topics", "alpha-topic.md", _VALID_TOPIC_A)
            result = index_builder.build_index_md(Path(tmpdir))
            pos_alpha = result.index("alpha-topic")
            pos_gamma = result.index("gamma-topic")
            self.assertLess(pos_alpha, pos_gamma,
                            "alpha-topic must precede gamma-topic (same kind, sorted by id)")


# ---------------------------------------------------------------------------
# build_index_md — missing frontmatter fallback
# ---------------------------------------------------------------------------


class TestBuildIndexMdMissingFrontmatter(unittest.TestCase):
    """Topics without proper frontmatter must not crash; use fallback id=stem."""

    def test_no_frontmatter_does_not_crash(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            _write_topic(lm / "topics", "bare-topic.md",
                         "# Just a heading\n\nNo frontmatter.\n")
            try:
                result = index_builder.build_index_md(Path(tmpdir))
                self.assertIsInstance(result, str)
            except Exception as exc:  # noqa: BLE001
                self.fail(f"build_index_md raised on missing frontmatter: {exc}")

    def test_fallback_id_is_stem(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            _write_topic(lm / "topics", "bare-topic.md", "# No frontmatter\n")
            result = index_builder.build_index_md(Path(tmpdir))
            self.assertIn("bare-topic", result)

    def test_partial_frontmatter_does_not_crash(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            _write_topic(lm / "topics", "partial.md",
                         "---\nid: partial\n---\nNo kind or status.\n")
            try:
                result = index_builder.build_index_md(Path(tmpdir))
                self.assertIsInstance(result, str)
            except Exception as exc:  # noqa: BLE001
                self.fail(f"build_index_md raised on partial frontmatter: {exc}")

    def test_mixed_valid_and_invalid_topics(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lm = _make_lightmem_dir(Path(tmpdir))
            _write_topic(lm / "topics", "valid.md", _VALID_TOPIC_A)
            _write_topic(lm / "topics", "invalid.md", "# No frontmatter\n")
            try:
                result = index_builder.build_index_md(Path(tmpdir))
                # Both must appear
                self.assertIn("alpha-topic", result)
                self.assertIn("invalid", result)
            except Exception as exc:  # noqa: BLE001
                self.fail(f"build_index_md raised on mixed topics: {exc}")


# ---------------------------------------------------------------------------
# write_index_md — file creation and return value
# ---------------------------------------------------------------------------


class TestWriteIndexMdCreatesFile(unittest.TestCase):
    """write_index_md writes to .claude/lightmem/index.md and returns the path."""

    def test_returns_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_lightmem_dir(Path(tmpdir))
            result = index_builder.write_index_md(Path(tmpdir))
            self.assertIsInstance(result, Path)

    def test_returns_correct_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _make_lightmem_dir(root)
            result = index_builder.write_index_md(root)
            expected = root / ".claude" / "lightmem" / "index.md"
            self.assertEqual(result, expected)

    def test_file_exists_after_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _make_lightmem_dir(root)
            index_builder.write_index_md(root)
            index_path = root / ".claude" / "lightmem" / "index.md"
            self.assertTrue(index_path.is_file())

    def test_file_contains_header(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _make_lightmem_dir(root)
            index_builder.write_index_md(root)
            content = (root / ".claude" / "lightmem" / "index.md").read_text(encoding="utf-8")
            self.assertIn("# LightMem topic index", content)

    def test_file_content_matches_build_index_md(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            lm = _make_lightmem_dir(root)
            _write_topic(lm / "topics", "t.md",
                         "---\nid: t\nkind: decision\nsummary: s\nstatus: active\n---\n")
            built = index_builder.build_index_md(root)
            index_builder.write_index_md(root)
            written = (root / ".claude" / "lightmem" / "index.md").read_text(encoding="utf-8")
            self.assertEqual(built, written)


# ---------------------------------------------------------------------------
# write_index_md — atomic write (no .tmp leftover)
# ---------------------------------------------------------------------------


class TestWriteIndexMdAtomic(unittest.TestCase):
    """write_index_md must leave no .tmp file after completing."""

    def test_no_tmp_file_after_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _make_lightmem_dir(root)
            index_builder.write_index_md(root)
            lm = root / ".claude" / "lightmem"
            tmp_candidates = list(lm.glob("*.tmp")) + list(lm.glob("index.md.tmp"))
            self.assertEqual(tmp_candidates, [],
                             "No .tmp file should remain after write_index_md")

    def test_write_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _make_lightmem_dir(root)
            index_builder.write_index_md(root)
            try:
                index_builder.write_index_md(root)
            except Exception as exc:  # noqa: BLE001
                self.fail(f"write_index_md raised on second call: {exc}")
            index_path = root / ".claude" / "lightmem" / "index.md"
            self.assertTrue(index_path.is_file())


# ---------------------------------------------------------------------------
# write_index_md — does not create lightmem dir if absent
# (the dir must exist; write_index_md only creates the index.md file)
# ---------------------------------------------------------------------------


class TestWriteIndexMdParentDirHandling(unittest.TestCase):
    """write_index_md behaviour when parent dir already exists."""

    def test_overwrites_existing_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            lm = _make_lightmem_dir(root)
            old_content = "# Old index — should be overwritten\n"
            (lm / "index.md").write_text(old_content, encoding="utf-8")
            index_builder.write_index_md(root)
            new_content = (lm / "index.md").read_text(encoding="utf-8")
            self.assertNotEqual(new_content, old_content)
            self.assertIn("# LightMem topic index", new_content)


if __name__ == "__main__":
    unittest.main()
