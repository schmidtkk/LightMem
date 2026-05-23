from __future__ import annotations

"""
Tests for index_builder.patch_index_entry

Expected API:
  patch_index_entry(repo_root: Path, topic_id: str) -> Path
  - Returns the path to index.md.
  - If index.md does not exist, falls back to write_index_md (full rebuild).
  - If topic_id not found on disk, falls back to write_index_md (full rebuild).
  - Updates the existing row for topic_id in-place when the row already exists.
  - Appends a new row when topic_id is not yet in the index.
  - Leaves no .tmp files after completing.
  - Atomic: uses write-then-replace pattern.
"""

import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_LIB = _REPO_ROOT / "scripts" / "lib"
if str(_SCRIPTS_LIB) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_LIB))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import index_builder  # type: ignore[import]  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TOPIC_A = """\
---
id: alpha
kind: decision
summary: The alpha decision
status: active
---

Body of alpha.
"""

_TOPIC_B = """\
---
id: beta
kind: constraint
summary: The beta constraint
status: active
---

Body of beta.
"""

_TOPIC_A_UPDATED = """\
---
id: alpha
kind: decision
summary: Updated alpha summary
status: superseded
---

Updated body.
"""


def _make_lightmem_dir(root: Path) -> Path:
    lm = root / ".claude" / "lightmem"
    lm.mkdir(parents=True, exist_ok=True)
    return lm


def _write_topic(topics_dir: Path, filename: str, content: str) -> None:
    topics_dir.mkdir(parents=True, exist_ok=True)
    (topics_dir / filename).write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Return value
# ---------------------------------------------------------------------------


class TestPatchIndexEntryReturnsPath(unittest.TestCase):
    def test_returns_path_object(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            lm = _make_lightmem_dir(root)
            _write_topic(lm / "topics", "alpha.md", _TOPIC_A)
            index_builder.write_index_md(root)
            result = index_builder.patch_index_entry(root, "alpha")
            self.assertIsInstance(result, Path)

    def test_returns_index_md_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            lm = _make_lightmem_dir(root)
            _write_topic(lm / "topics", "alpha.md", _TOPIC_A)
            index_builder.write_index_md(root)
            result = index_builder.patch_index_entry(root, "alpha")
            self.assertEqual(result, root / ".claude" / "lightmem" / "index.md")


# ---------------------------------------------------------------------------
# Fallback to full rebuild
# ---------------------------------------------------------------------------


class TestPatchIndexEntryFallback(unittest.TestCase):
    def test_fallback_when_no_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            lm = _make_lightmem_dir(root)
            _write_topic(lm / "topics", "alpha.md", _TOPIC_A)
            # Do NOT call write_index_md first
            result = index_builder.patch_index_entry(root, "alpha")
            self.assertTrue(result.exists())
            content = result.read_text(encoding="utf-8")
            self.assertIn("# LightMem topic index", content)

    def test_fallback_when_topic_deleted(self) -> None:
        """If the topic file no longer exists, full rebuild removes the stale row."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            lm = _make_lightmem_dir(root)
            _write_topic(lm / "topics", "alpha.md", _TOPIC_A)
            _write_topic(lm / "topics", "beta.md", _TOPIC_B)
            index_builder.write_index_md(root)
            # Delete alpha topic
            (lm / "topics" / "alpha.md").unlink()
            index_builder.patch_index_entry(root, "alpha")
            content = (root / ".claude" / "lightmem" / "index.md").read_text(encoding="utf-8")
            self.assertNotIn("| alpha |", content)
            self.assertIn("beta", content)


# ---------------------------------------------------------------------------
# In-place row update
# ---------------------------------------------------------------------------


class TestPatchIndexEntryUpdateExistingRow(unittest.TestCase):
    def test_existing_row_updated_in_place(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            lm = _make_lightmem_dir(root)
            _write_topic(lm / "topics", "alpha.md", _TOPIC_A)
            index_builder.write_index_md(root)

            # Now update the topic file with new summary
            _write_topic(lm / "topics", "alpha.md", _TOPIC_A_UPDATED)
            index_builder.patch_index_entry(root, "alpha")

            content = (root / ".claude" / "lightmem" / "index.md").read_text(encoding="utf-8")
            self.assertIn("Updated alpha summary", content)

    def test_old_summary_gone_after_update(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            lm = _make_lightmem_dir(root)
            _write_topic(lm / "topics", "alpha.md", _TOPIC_A)
            index_builder.write_index_md(root)

            _write_topic(lm / "topics", "alpha.md", _TOPIC_A_UPDATED)
            index_builder.patch_index_entry(root, "alpha")

            content = (root / ".claude" / "lightmem" / "index.md").read_text(encoding="utf-8")
            self.assertNotIn("The alpha decision", content)
            self.assertIn("Updated alpha summary", content)

    def test_other_rows_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            lm = _make_lightmem_dir(root)
            _write_topic(lm / "topics", "alpha.md", _TOPIC_A)
            _write_topic(lm / "topics", "beta.md", _TOPIC_B)
            index_builder.write_index_md(root)

            _write_topic(lm / "topics", "alpha.md", _TOPIC_A_UPDATED)
            index_builder.patch_index_entry(root, "alpha")

            content = (root / ".claude" / "lightmem" / "index.md").read_text(encoding="utf-8")
            self.assertIn("The beta constraint", content)

    def test_only_one_row_for_topic_after_patch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            lm = _make_lightmem_dir(root)
            _write_topic(lm / "topics", "alpha.md", _TOPIC_A)
            index_builder.write_index_md(root)
            _write_topic(lm / "topics", "alpha.md", _TOPIC_A_UPDATED)
            index_builder.patch_index_entry(root, "alpha")

            content = (root / ".claude" / "lightmem" / "index.md").read_text(encoding="utf-8")
            self.assertEqual(content.count("| alpha |"), 1)


# ---------------------------------------------------------------------------
# Insert new row
# ---------------------------------------------------------------------------


class TestPatchIndexEntryInsertNewRow(unittest.TestCase):
    def test_new_topic_row_appears(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            lm = _make_lightmem_dir(root)
            _write_topic(lm / "topics", "alpha.md", _TOPIC_A)
            index_builder.write_index_md(root)

            # Add beta after initial index
            _write_topic(lm / "topics", "beta.md", _TOPIC_B)
            index_builder.patch_index_entry(root, "beta")

            content = (root / ".claude" / "lightmem" / "index.md").read_text(encoding="utf-8")
            self.assertIn("beta", content)
            self.assertIn("The beta constraint", content)

    def test_existing_rows_preserved_on_insert(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            lm = _make_lightmem_dir(root)
            _write_topic(lm / "topics", "alpha.md", _TOPIC_A)
            index_builder.write_index_md(root)
            _write_topic(lm / "topics", "beta.md", _TOPIC_B)
            index_builder.patch_index_entry(root, "beta")

            content = (root / ".claude" / "lightmem" / "index.md").read_text(encoding="utf-8")
            self.assertIn("alpha", content)
            self.assertIn("beta", content)


# ---------------------------------------------------------------------------
# Atomicity
# ---------------------------------------------------------------------------


class TestPatchIndexEntryAtomic(unittest.TestCase):
    def test_no_tmp_file_after_patch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            lm = _make_lightmem_dir(root)
            _write_topic(lm / "topics", "alpha.md", _TOPIC_A)
            index_builder.write_index_md(root)
            _write_topic(lm / "topics", "alpha.md", _TOPIC_A_UPDATED)
            index_builder.patch_index_entry(root, "alpha")

            tmp_files = list((lm).glob("*.tmp"))
            self.assertEqual(tmp_files, [])

    def test_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            lm = _make_lightmem_dir(root)
            _write_topic(lm / "topics", "alpha.md", _TOPIC_A)
            index_builder.write_index_md(root)
            index_builder.patch_index_entry(root, "alpha")
            try:
                index_builder.patch_index_entry(root, "alpha")
            except Exception as exc:  # noqa: BLE001
                self.fail(f"patch_index_entry raised on second call: {exc}")


if __name__ == "__main__":
    unittest.main()
