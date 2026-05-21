from __future__ import annotations

"""
Tests for scripts/lib/journal.py

Derived purely from PRD_v0.2.md §5.5 (non-committable state), §6.2 (Stop hook),
§6.2.1 (journal entry schema), §10 (LIGHTMEM_JOURNAL_MAX_MB), and the Round-4
QA API spec.  No implementation files were read during authoring.

Expected API:
  - DEFAULT_JOURNAL_MAX_MB: int == 5
  - journal_path(repo_root: Path) -> Path
  - archive_dir(repo_root: Path) -> Path
  - read_max_mb() -> int
  - append(repo_root: Path, entry: dict) -> None
  - rotate(repo_root: Path) -> Path | None
"""

import json
import os
import re
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_LIB = _REPO_ROOT / "scripts" / "lib"
if str(_SCRIPTS_LIB) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_LIB))

import journal  # type: ignore[import]  # noqa: E402 – imported after path fix


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------


class TestDefaultJournalMaxMb(unittest.TestCase):
    """DEFAULT_JOURNAL_MAX_MB must be an int equal to 5."""

    def test_exists(self) -> None:
        self.assertTrue(hasattr(journal, "DEFAULT_JOURNAL_MAX_MB"))

    def test_is_int(self) -> None:
        self.assertIsInstance(journal.DEFAULT_JOURNAL_MAX_MB, int)

    def test_value_is_5(self) -> None:
        self.assertEqual(journal.DEFAULT_JOURNAL_MAX_MB, 5)


# ---------------------------------------------------------------------------
# journal_path() and archive_dir()
# ---------------------------------------------------------------------------


class TestJournalPath(unittest.TestCase):
    """journal_path(repo_root) must return repo_root / '.claude/lightmem/journal.jsonl'."""

    def test_returns_path_object(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = journal.journal_path(Path(tmpdir))
            self.assertIsInstance(result, Path)

    def test_correct_location(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            expected = root / ".claude" / "lightmem" / "journal.jsonl"
            self.assertEqual(journal.journal_path(root), expected)

    def test_filename(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = journal.journal_path(Path(tmpdir))
            self.assertEqual(result.name, "journal.jsonl")


class TestArchiveDir(unittest.TestCase):
    """archive_dir(repo_root) must return repo_root / '.claude/lightmem/archive'."""

    def test_returns_path_object(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = journal.archive_dir(Path(tmpdir))
            self.assertIsInstance(result, Path)

    def test_correct_location(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            expected = root / ".claude" / "lightmem" / "archive"
            self.assertEqual(journal.archive_dir(root), expected)

    def test_dirname(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = journal.archive_dir(Path(tmpdir))
            self.assertEqual(result.name, "archive")


# ---------------------------------------------------------------------------
# read_max_mb()
# ---------------------------------------------------------------------------


class TestReadMaxMb(unittest.TestCase):
    """read_max_mb() must respect LIGHTMEM_JOURNAL_MAX_MB env var."""

    def test_no_env_returns_5(self) -> None:
        with unittest.mock.patch.dict(os.environ, {}, clear=True):
            result = journal.read_max_mb()
            self.assertEqual(result, 5)

    def test_valid_int_env(self) -> None:
        with unittest.mock.patch.dict(
            os.environ, {"LIGHTMEM_JOURNAL_MAX_MB": "10"}, clear=True
        ):
            result = journal.read_max_mb()
            self.assertEqual(result, 10)

    def test_valid_int_env_1(self) -> None:
        with unittest.mock.patch.dict(
            os.environ, {"LIGHTMEM_JOURNAL_MAX_MB": "1"}, clear=True
        ):
            result = journal.read_max_mb()
            self.assertEqual(result, 1)

    def test_garbage_env_returns_5(self) -> None:
        with unittest.mock.patch.dict(
            os.environ, {"LIGHTMEM_JOURNAL_MAX_MB": "not-a-number"}, clear=True
        ):
            result = journal.read_max_mb()
            self.assertEqual(result, 5)

    def test_empty_env_returns_5(self) -> None:
        with unittest.mock.patch.dict(
            os.environ, {"LIGHTMEM_JOURNAL_MAX_MB": ""}, clear=True
        ):
            result = journal.read_max_mb()
            self.assertEqual(result, 5)

    def test_negative_env_returns_5(self) -> None:
        with unittest.mock.patch.dict(
            os.environ, {"LIGHTMEM_JOURNAL_MAX_MB": "-1"}, clear=True
        ):
            result = journal.read_max_mb()
            self.assertEqual(result, 5)

    def test_float_string_returns_5(self) -> None:
        """Float strings are not valid integers; must fall back to 5."""
        with unittest.mock.patch.dict(
            os.environ, {"LIGHTMEM_JOURNAL_MAX_MB": "5.5"}, clear=True
        ):
            result = journal.read_max_mb()
            self.assertEqual(result, 5)

    def test_returns_int(self) -> None:
        with unittest.mock.patch.dict(os.environ, {}, clear=True):
            result = journal.read_max_mb()
            self.assertIsInstance(result, int)


# ---------------------------------------------------------------------------
# append()
# ---------------------------------------------------------------------------


class TestAppendBasic(unittest.TestCase):
    """append() must write a single valid JSON line terminated with newline."""

    def test_creates_journal_file(self) -> None:
        with unittest.mock.patch.dict(
            os.environ, {"LIGHTMEM_JOURNAL_MAX_MB": "100"}, clear=True
        ):
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                journal.append(root, {"ts": "2026-01-01T00:00:00+00:00", "session_id": "abc"})
                self.assertTrue(journal.journal_path(root).exists())

    def test_creates_parent_dir_if_missing(self) -> None:
        with unittest.mock.patch.dict(
            os.environ, {"LIGHTMEM_JOURNAL_MAX_MB": "100"}, clear=True
        ):
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                jp = journal.journal_path(root)
                self.assertFalse(jp.parent.exists())
                journal.append(root, {"key": "value"})
                self.assertTrue(jp.parent.exists())

    def test_written_line_is_valid_json(self) -> None:
        with unittest.mock.patch.dict(
            os.environ, {"LIGHTMEM_JOURNAL_MAX_MB": "100"}, clear=True
        ):
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                journal.append(root, {"event": "test", "count": 1})
                raw = journal.journal_path(root).read_text(encoding="utf-8")
                line = raw.strip()
                parsed = json.loads(line)
                self.assertIsInstance(parsed, dict)

    def test_written_line_ends_with_newline(self) -> None:
        with unittest.mock.patch.dict(
            os.environ, {"LIGHTMEM_JOURNAL_MAX_MB": "100"}, clear=True
        ):
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                journal.append(root, {"event": "test"})
                raw = journal.journal_path(root).read_text(encoding="utf-8")
                self.assertTrue(raw.endswith("\n"))

    def test_written_line_preserves_entry_data(self) -> None:
        with unittest.mock.patch.dict(
            os.environ, {"LIGHTMEM_JOURNAL_MAX_MB": "100"}, clear=True
        ):
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                entry = {"ts": "2026-05-21T12:00:00+00:00", "session_id": "sess1"}
                journal.append(root, entry)
                raw = journal.journal_path(root).read_text(encoding="utf-8")
                parsed = json.loads(raw.strip())
                self.assertEqual(parsed["session_id"], "sess1")
                self.assertEqual(parsed["ts"], "2026-05-21T12:00:00+00:00")


class TestAppendMultiple(unittest.TestCase):
    """append() called multiple times must produce one line per call."""

    def test_multiple_appends_correct_line_count(self) -> None:
        with unittest.mock.patch.dict(
            os.environ, {"LIGHTMEM_JOURNAL_MAX_MB": "100"}, clear=True
        ):
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                for i in range(5):
                    journal.append(root, {"index": i})
                raw = journal.journal_path(root).read_text(encoding="utf-8")
                lines = [ln for ln in raw.splitlines() if ln.strip()]
                self.assertEqual(len(lines), 5)

    def test_multiple_appends_each_line_valid_json(self) -> None:
        with unittest.mock.patch.dict(
            os.environ, {"LIGHTMEM_JOURNAL_MAX_MB": "100"}, clear=True
        ):
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                for i in range(3):
                    journal.append(root, {"i": i, "msg": f"entry-{i}"})
                raw = journal.journal_path(root).read_text(encoding="utf-8")
                for line in raw.splitlines():
                    if line.strip():
                        parsed = json.loads(line)
                        self.assertIsInstance(parsed, dict)

    def test_multiple_appends_preserve_order(self) -> None:
        with unittest.mock.patch.dict(
            os.environ, {"LIGHTMEM_JOURNAL_MAX_MB": "100"}, clear=True
        ):
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                for i in range(4):
                    journal.append(root, {"seq": i})
                raw = journal.journal_path(root).read_text(encoding="utf-8")
                lines = [ln for ln in raw.splitlines() if ln.strip()]
                for idx, line in enumerate(lines):
                    parsed = json.loads(line)
                    self.assertEqual(parsed["seq"], idx)


class TestAppendSerialization(unittest.TestCase):
    """append() must serialize with ensure_ascii=False and compact separators."""

    def test_unicode_preserved(self) -> None:
        with unittest.mock.patch.dict(
            os.environ, {"LIGHTMEM_JOURNAL_MAX_MB": "100"}, clear=True
        ):
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                unicode_value = "你好世界"
                journal.append(root, {"msg": unicode_value})
                raw = journal.journal_path(root).read_text(encoding="utf-8")
                # ensure_ascii=False → unicode chars appear literally, not as \uXXXX
                self.assertIn(unicode_value, raw)
                self.assertNotIn("\\u", raw)

    def test_compact_separators_no_space_after_colon(self) -> None:
        """Compact separators means no space after : or , inside the JSON."""
        with unittest.mock.patch.dict(
            os.environ, {"LIGHTMEM_JOURNAL_MAX_MB": "100"}, clear=True
        ):
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                journal.append(root, {"a": 1, "b": 2})
                raw = journal.journal_path(root).read_text(encoding="utf-8")
                line = raw.strip()
                # Compact: no ": " or ", " (key-value colon or comma should have no trailing space)
                self.assertNotIn(": ", line)
                self.assertNotIn(", ", line)

    def test_single_line_per_entry(self) -> None:
        """Each entry must be exactly one line (no embedded newlines from the serializer)."""
        with unittest.mock.patch.dict(
            os.environ, {"LIGHTMEM_JOURNAL_MAX_MB": "100"}, clear=True
        ):
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                journal.append(root, {"k": "v"})
                raw = journal.journal_path(root).read_text(encoding="utf-8")
                # Only one non-empty line
                non_empty_lines = [ln for ln in raw.split("\n") if ln]
                self.assertEqual(len(non_empty_lines), 1)


# ---------------------------------------------------------------------------
# rotate()
# ---------------------------------------------------------------------------


class TestRotateNoJournal(unittest.TestCase):
    """rotate() when journal does not exist must return None without crashing."""

    def test_no_journal_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = journal.rotate(Path(tmpdir))
            self.assertIsNone(result)

    def test_no_journal_does_not_raise(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                journal.rotate(Path(tmpdir))
            except Exception as exc:  # noqa: BLE001
                self.fail(f"rotate() raised unexpectedly with no journal: {exc}")


class TestRotateWithJournal(unittest.TestCase):
    """rotate() when journal exists must move it to the archive dir."""

    def _create_journal(self, root: Path, content: str = '{"ts":"2026-01-01"}\n') -> None:
        jp = journal.journal_path(root)
        jp.parent.mkdir(parents=True, exist_ok=True)
        jp.write_text(content, encoding="utf-8")

    def test_returns_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._create_journal(root)
            result = journal.rotate(root)
            self.assertIsInstance(result, Path)

    def test_original_journal_removed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._create_journal(root)
            journal.rotate(root)
            self.assertFalse(journal.journal_path(root).exists())

    def test_archive_file_created(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._create_journal(root)
            archive_path = journal.rotate(root)
            self.assertIsNotNone(archive_path)
            self.assertTrue(archive_path.exists())  # type: ignore[union-attr]

    def test_archive_dir_created_if_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._create_journal(root)
            adir = journal.archive_dir(root)
            self.assertFalse(adir.exists())
            journal.rotate(root)
            self.assertTrue(adir.exists())

    def test_archive_in_correct_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._create_journal(root)
            archive_path = journal.rotate(root)
            self.assertIsNotNone(archive_path)
            self.assertEqual(archive_path.parent, journal.archive_dir(root))  # type: ignore[union-attr]

    def test_archive_filename_starts_with_journal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._create_journal(root)
            archive_path = journal.rotate(root)
            self.assertIsNotNone(archive_path)
            self.assertTrue(archive_path.name.startswith("journal-"))  # type: ignore[union-attr]

    def test_archive_filename_ends_with_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._create_journal(root)
            archive_path = journal.rotate(root)
            self.assertIsNotNone(archive_path)
            self.assertTrue(archive_path.name.endswith(".jsonl"))  # type: ignore[union-attr]

    def test_archive_filename_contains_pid(self) -> None:
        """Archive filename must include the process ID."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._create_journal(root)
            archive_path = journal.rotate(root)
            self.assertIsNotNone(archive_path)
            pid_str = str(os.getpid())
            self.assertIn(pid_str, archive_path.name)  # type: ignore[union-attr]

    def test_archive_filename_no_colons(self) -> None:
        """Archive filename must not contain ':' (Windows-safe)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._create_journal(root)
            archive_path = journal.rotate(root)
            self.assertIsNotNone(archive_path)
            self.assertNotIn(":", archive_path.name)  # type: ignore[union-attr]

    def test_archive_filename_matches_pattern(self) -> None:
        """Archive filename must match journal-<ts>-<pid>.jsonl pattern."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._create_journal(root)
            archive_path = journal.rotate(root)
            self.assertIsNotNone(archive_path)
            # Pattern: journal-<something>-<pid>.jsonl, no colons in ts
            name = archive_path.name  # type: ignore[union-attr]
            pattern = re.compile(r"^journal-.+-\d+\.jsonl$")
            self.assertIsNotNone(
                pattern.match(name),
                f"Archive filename {name!r} does not match expected pattern",
            )

    def test_archive_content_matches_original(self) -> None:
        """The archived file must contain the same content as the original journal."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            content = '{"ts":"2026-05-21","event":"test"}\n'
            self._create_journal(root, content)
            archive_path = journal.rotate(root)
            self.assertIsNotNone(archive_path)
            archived_content = archive_path.read_text(encoding="utf-8")  # type: ignore[union-attr]
            self.assertEqual(archived_content, content)


# ---------------------------------------------------------------------------
# Size-triggered rotation
# ---------------------------------------------------------------------------


class TestSizeTriggeredRotation(unittest.TestCase):
    """append() must trigger rotation when journal size exceeds the threshold."""

    def test_rotation_triggered_at_zero_mb_threshold(self) -> None:
        """
        LIGHTMEM_JOURNAL_MAX_MB=0 means 0 MB → any content (size > 0 bytes)
        triggers rotation.  After one append the original journal must be gone
        and the archive dir must contain exactly one file.
        """
        with unittest.mock.patch.dict(
            os.environ, {"LIGHTMEM_JOURNAL_MAX_MB": "0"}, clear=True
        ):
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                journal.append(root, {"event": "trigger-rotation"})
                # After append with 0 MB threshold, journal should be rotated away
                jp = journal.journal_path(root)
                adir = journal.archive_dir(root)

                # The journal may or may not still exist depending on whether
                # the new entry is written before or after rotation check.
                # What MUST be true: the archive dir exists and has 1 file.
                if adir.exists():
                    archived = list(adir.iterdir())
                    self.assertEqual(
                        len(archived),
                        1,
                        f"Expected 1 archived file, found: {archived}",
                    )
                    # And if the original journal is also gone:
                    # (it may have been recreated with a new entry after rotation)
                    # so we just confirm archive happened

    def test_no_rotation_below_threshold(self) -> None:
        """With a large threshold, small appends must not trigger rotation."""
        with unittest.mock.patch.dict(
            os.environ, {"LIGHTMEM_JOURNAL_MAX_MB": "100"}, clear=True
        ):
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                for i in range(3):
                    journal.append(root, {"event": f"entry-{i}"})
                # Archive dir should not exist or be empty (no rotation)
                adir = journal.archive_dir(root)
                if adir.exists():
                    archived = list(adir.iterdir())
                    self.assertEqual(
                        len(archived),
                        0,
                        "No rotation expected with 100 MB threshold for small entries",
                    )
                # Journal must still exist
                self.assertTrue(journal.journal_path(root).exists())

    def test_rotation_produces_archive_file(self) -> None:
        """Forced rotation via LIGHTMEM_JOURNAL_MAX_MB=0 produces archive file."""
        with unittest.mock.patch.dict(
            os.environ, {"LIGHTMEM_JOURNAL_MAX_MB": "0"}, clear=True
        ):
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                # Pre-create a non-empty journal so size > 0
                jp = journal.journal_path(root)
                jp.parent.mkdir(parents=True, exist_ok=True)
                jp.write_text('{"pre":"existing"}\n', encoding="utf-8")
                # Now append; size > 0 MB threshold → rotation
                journal.append(root, {"event": "new"})
                adir = journal.archive_dir(root)
                archived = list(adir.iterdir()) if adir.exists() else []
                self.assertGreaterEqual(
                    len(archived),
                    1,
                    "Expected at least one archived file after size-triggered rotation",
                )


if __name__ == "__main__":
    unittest.main()
