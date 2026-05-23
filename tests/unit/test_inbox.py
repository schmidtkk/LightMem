from __future__ import annotations

"""
Tests for scripts/lib/inbox.py

Expected API:
  - inbox_path(repo_root: Path) -> Path
  - append_pending(repo_root, text, *, source="", ts=None) -> Path
  - read_pending(repo_root) -> list[str]
  - clear_pending(repo_root) -> None
  - extract_mem_tags(text: str) -> list[str]
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

import inbox  # type: ignore[import]  # noqa: E402


# ---------------------------------------------------------------------------
# inbox_path
# ---------------------------------------------------------------------------


class TestInboxPath(unittest.TestCase):
    def test_returns_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = inbox.inbox_path(Path(tmpdir))
            self.assertIsInstance(result, Path)

    def test_path_ends_with_pending_md(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = inbox.inbox_path(Path(tmpdir))
            self.assertEqual(result.name, "pending.md")

    def test_path_is_under_lightmem(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = inbox.inbox_path(Path(tmpdir))
            self.assertIn(".claude", str(result))
            self.assertIn("lightmem", str(result))
            self.assertIn("inbox", str(result))


# ---------------------------------------------------------------------------
# append_pending
# ---------------------------------------------------------------------------


class TestAppendPending(unittest.TestCase):
    def test_creates_file_if_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            inbox.append_pending(root, "test item")
            self.assertTrue(inbox.inbox_path(root).exists())

    def test_returns_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = inbox.append_pending(Path(tmpdir), "test item")
            self.assertIsInstance(result, Path)

    def test_item_readable_back(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            inbox.append_pending(root, "remember this fact")
            items = inbox.read_pending(root)
            self.assertEqual(len(items), 1)
            self.assertIn("remember this fact", items[0])

    def test_multiple_items_append(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            inbox.append_pending(root, "first item")
            inbox.append_pending(root, "second item")
            items = inbox.read_pending(root)
            self.assertEqual(len(items), 2)

    def test_empty_text_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            inbox.append_pending(root, "   ")
            items = inbox.read_pending(root)
            self.assertEqual(items, [])

    def test_source_tag_included_in_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            inbox.append_pending(root, "some fact", source="abc12345")
            content = inbox.inbox_path(root).read_text(encoding="utf-8")
            self.assertIn("abc12345", content)

    def test_custom_ts_used(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            inbox.append_pending(root, "fact", ts="2026-01-01T00:00:00Z")
            content = inbox.inbox_path(root).read_text(encoding="utf-8")
            self.assertIn("2026-01-01T00:00:00Z", content)

    def test_secret_scrubbed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            inbox.append_pending(root, "api_key=supersecret123456")
            content = inbox.inbox_path(root).read_text(encoding="utf-8")
            self.assertNotIn("supersecret123456", content)
            self.assertIn("[REDACTED]", content)

    def test_header_written_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            inbox.append_pending(root, "first")
            inbox.append_pending(root, "second")
            content = inbox.inbox_path(root).read_text(encoding="utf-8")
            self.assertEqual(content.count("# LightMem inbox"), 1)


# ---------------------------------------------------------------------------
# read_pending
# ---------------------------------------------------------------------------


class TestReadPending(unittest.TestCase):
    def test_empty_list_when_no_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = inbox.read_pending(Path(tmpdir))
            self.assertEqual(result, [])

    def test_returns_list_of_strings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            inbox.append_pending(root, "an item")
            result = inbox.read_pending(root)
            self.assertIsInstance(result, list)
            self.assertTrue(all(isinstance(s, str) for s in result))

    def test_text_without_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            inbox.append_pending(root, "clean fact")
            items = inbox.read_pending(root)
            self.assertEqual(len(items), 1)
            self.assertNotIn("[", items[0])

    def test_text_without_source_tag(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            inbox.append_pending(root, "fact here", source="src123")
            items = inbox.read_pending(root)
            self.assertEqual(len(items), 1)
            self.assertNotIn("`src123`", items[0])
            self.assertIn("fact here", items[0])

    def test_order_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            inbox.append_pending(root, "alpha")
            inbox.append_pending(root, "beta")
            inbox.append_pending(root, "gamma")
            items = inbox.read_pending(root)
            self.assertEqual(len(items), 3)
            self.assertIn("alpha", items[0])
            self.assertIn("beta", items[1])
            self.assertIn("gamma", items[2])


# ---------------------------------------------------------------------------
# clear_pending
# ---------------------------------------------------------------------------


class TestClearPending(unittest.TestCase):
    def test_no_op_when_file_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                inbox.clear_pending(Path(tmpdir))
            except Exception as exc:  # noqa: BLE001
                self.fail(f"clear_pending raised on absent file: {exc}")

    def test_items_gone_after_clear(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            inbox.append_pending(root, "item one")
            inbox.append_pending(root, "item two")
            inbox.clear_pending(root)
            items = inbox.read_pending(root)
            self.assertEqual(items, [])

    def test_file_still_exists_after_clear(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            inbox.append_pending(root, "something")
            inbox.clear_pending(root)
            self.assertTrue(inbox.inbox_path(root).exists())

    def test_can_append_after_clear(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            inbox.append_pending(root, "first round")
            inbox.clear_pending(root)
            inbox.append_pending(root, "second round")
            items = inbox.read_pending(root)
            self.assertEqual(len(items), 1)
            self.assertIn("second round", items[0])

    def test_clear_is_atomic_no_tmp_leftover(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            inbox.append_pending(root, "item")
            inbox.clear_pending(root)
            inbox_dir = inbox.inbox_path(root).parent
            tmp_files = list(inbox_dir.glob("*.tmp"))
            self.assertEqual(tmp_files, [])


# ---------------------------------------------------------------------------
# extract_mem_tags
# ---------------------------------------------------------------------------


class TestExtractMemTags(unittest.TestCase):
    def test_empty_string_returns_empty(self) -> None:
        self.assertEqual(inbox.extract_mem_tags(""), [])

    def test_no_tag_returns_empty(self) -> None:
        self.assertEqual(inbox.extract_mem_tags("no tag here"), [])

    def test_tag_at_end_of_line(self) -> None:
        result = inbox.extract_mem_tags("we decided X [mem]")
        self.assertEqual(len(result), 1)
        self.assertIn("we decided X", result[0])
        self.assertNotIn("[mem]", result[0])

    def test_tag_at_start_of_line(self) -> None:
        result = inbox.extract_mem_tags("[mem] important fact")
        self.assertEqual(len(result), 1)
        self.assertIn("important fact", result[0])

    def test_tag_in_middle_of_line(self) -> None:
        result = inbox.extract_mem_tags("before [mem] after")
        self.assertEqual(len(result), 1)
        self.assertNotIn("[mem]", result[0])

    def test_case_insensitive(self) -> None:
        result = inbox.extract_mem_tags("fact [MEM]")
        self.assertEqual(len(result), 1)

    def test_multiple_tagged_lines(self) -> None:
        text = "line one [mem]\nno tag\nline three [mem]"
        result = inbox.extract_mem_tags(text)
        self.assertEqual(len(result), 2)

    def test_untagged_lines_excluded(self) -> None:
        text = "tagged [mem]\nuntagged line\nalso untagged"
        result = inbox.extract_mem_tags(text)
        self.assertEqual(len(result), 1)


if __name__ == "__main__":
    unittest.main()
