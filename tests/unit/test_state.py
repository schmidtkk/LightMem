from __future__ import annotations

"""
Tests for scripts/lib/state.py

Derived purely from PRD_v0.2.md §5.5 (non-committable state), §6 (state schema),
and the API spec in the Round-4 QA brief.  No implementation files were read.

Expected API:
  - STATE_SCHEMA_VERSION: int == 1
  - state_path(repo_root: Path) -> Path
  - read_state(repo_root: Path) -> dict[str, Any]
  - write_state(repo_root: Path, state: dict[str, Any]) -> None
  - default_state() -> dict[str, Any]
"""

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_LIB = _REPO_ROOT / "scripts" / "lib"
if str(_SCRIPTS_LIB) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_LIB))

import state  # type: ignore[import]  # noqa: E402 – imported after path fix


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------


class TestStateSchemaVersion(unittest.TestCase):
    """PRD: STATE_SCHEMA_VERSION must be an int equal to 1."""

    def test_schema_version_exists(self) -> None:
        self.assertTrue(hasattr(state, "STATE_SCHEMA_VERSION"))

    def test_schema_version_is_int(self) -> None:
        self.assertIsInstance(state.STATE_SCHEMA_VERSION, int)

    def test_schema_version_value(self) -> None:
        self.assertEqual(state.STATE_SCHEMA_VERSION, 1)


# ---------------------------------------------------------------------------
# state_path()
# ---------------------------------------------------------------------------


class TestStatePath(unittest.TestCase):
    """state_path(repo_root) must return repo_root / '.claude/lightmem/state.json'."""

    def test_state_path_returns_path_object(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            result = state.state_path(root)
            self.assertIsInstance(result, Path)

    def test_state_path_correct_location(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            expected = root / ".claude" / "lightmem" / "state.json"
            self.assertEqual(state.state_path(root), expected)

    def test_state_path_filename(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            result = state.state_path(root)
            self.assertEqual(result.name, "state.json")


# ---------------------------------------------------------------------------
# read_state()
# ---------------------------------------------------------------------------


class TestReadStateMissingFile(unittest.TestCase):
    """read_state on a non-existent file must return {}."""

    def test_missing_file_returns_empty_dict(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            # No state.json created
            result = state.read_state(root)
            self.assertEqual(result, {})

    def test_missing_file_returns_dict_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            result = state.read_state(root)
            self.assertIsInstance(result, dict)


class TestReadStateMalformedJSON(unittest.TestCase):
    """read_state on malformed JSON must return {} without raising."""

    def _write_raw(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_malformed_json_returns_empty_dict(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_raw(state.state_path(root), "this is not json {{{")
            result = state.read_state(root)
            self.assertEqual(result, {})

    def test_malformed_json_does_not_raise(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_raw(state.state_path(root), "}{bad json")
            try:
                state.read_state(root)
            except Exception as exc:  # noqa: BLE001
                self.fail(f"read_state raised unexpectedly: {exc}")

    def test_empty_file_returns_empty_dict(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_raw(state.state_path(root), "")
            result = state.read_state(root)
            self.assertEqual(result, {})

    def test_partial_json_returns_empty_dict(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_raw(state.state_path(root), '{"key": ')
            result = state.read_state(root)
            self.assertEqual(result, {})


class TestReadStateValidJSON(unittest.TestCase):
    """read_state on valid JSON dict must return the parsed dict."""

    def _write_json(self, path: Path, data: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")

    def test_valid_dict_returns_dict(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            data = {"schema_version": 1, "bootstrap_completed": False}
            self._write_json(state.state_path(root), data)
            result = state.read_state(root)
            self.assertIsInstance(result, dict)

    def test_valid_dict_preserves_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            data = {"schema_version": 1, "turn_count": 42, "bootstrap_completed": True}
            self._write_json(state.state_path(root), data)
            result = state.read_state(root)
            self.assertEqual(result["turn_count"], 42)
            self.assertEqual(result["bootstrap_completed"], True)

    def test_valid_dict_with_null_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            data = {"last_session_id": None}
            self._write_json(state.state_path(root), data)
            result = state.read_state(root)
            self.assertIsNone(result["last_session_id"])


class TestReadStateNonDictJSON(unittest.TestCase):
    """read_state on valid JSON that is not a dict must return {}."""

    def _write_json(self, path: Path, data: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")

    def test_json_list_returns_empty_dict(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_json(state.state_path(root), [1, 2, 3])
            result = state.read_state(root)
            self.assertEqual(result, {})

    def test_json_string_returns_empty_dict(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_json(state.state_path(root), "hello")
            result = state.read_state(root)
            self.assertEqual(result, {})

    def test_json_integer_returns_empty_dict(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_json(state.state_path(root), 42)
            result = state.read_state(root)
            self.assertEqual(result, {})

    def test_json_null_returns_empty_dict(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_json(state.state_path(root), None)
            result = state.read_state(root)
            self.assertEqual(result, {})

    def test_json_bool_returns_empty_dict(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_json(state.state_path(root), True)
            result = state.read_state(root)
            self.assertEqual(result, {})


# ---------------------------------------------------------------------------
# write_state()
# ---------------------------------------------------------------------------


class TestWriteStateCreatesFile(unittest.TestCase):
    """write_state must create parent dirs and write the state file."""

    def test_creates_parent_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            # Parent dirs do not exist yet
            target = state.state_path(root)
            self.assertFalse(target.parent.exists())
            state.write_state(root, {"turn_count": 0})
            self.assertTrue(target.parent.exists())

    def test_file_exists_after_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            state.write_state(root, {"turn_count": 0})
            self.assertTrue(state.state_path(root).exists())

    def test_file_contains_valid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            state.write_state(root, {"turn_count": 7})
            raw = state.state_path(root).read_text(encoding="utf-8")
            parsed = json.loads(raw)
            self.assertIsInstance(parsed, dict)


class TestWriteStateAtomicWrite(unittest.TestCase):
    """After write_state returns, the .tmp file must not exist."""

    def test_tmp_file_not_present_after_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            state.write_state(root, {"key": "value"})
            tmp_path = state.state_path(root).parent / "state.json.tmp"
            self.assertFalse(
                tmp_path.exists(),
                "Temporary file state.json.tmp must be renamed away after write_state",
            )


class TestWriteStateSchemaVersionInjection(unittest.TestCase):
    """write_state must inject schema_version: 1 always."""

    def test_injects_schema_version_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            state.write_state(root, {"turn_count": 0})
            raw = state.state_path(root).read_text(encoding="utf-8")
            data = json.loads(raw)
            self.assertIn("schema_version", data)
            self.assertEqual(data["schema_version"], 1)

    def test_overrides_wrong_schema_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            state.write_state(root, {"schema_version": 99, "turn_count": 5})
            raw = state.state_path(root).read_text(encoding="utf-8")
            data = json.loads(raw)
            self.assertEqual(data["schema_version"], 1)

    def test_schema_version_zero_overridden(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            state.write_state(root, {"schema_version": 0})
            raw = state.state_path(root).read_text(encoding="utf-8")
            data = json.loads(raw)
            self.assertEqual(data["schema_version"], 1)

    def test_correct_schema_version_preserved(self) -> None:
        """If schema_version is already 1, it must remain 1."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            state.write_state(root, {"schema_version": 1, "bootstrap_completed": False})
            raw = state.state_path(root).read_text(encoding="utf-8")
            data = json.loads(raw)
            self.assertEqual(data["schema_version"], 1)


class TestWriteStatePrettyPrinted(unittest.TestCase):
    """write_state must produce pretty-printed (multi-line) JSON."""

    def test_file_has_multiple_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            state.write_state(root, {"key": "value", "count": 0})
            raw = state.state_path(root).read_text(encoding="utf-8")
            lines = raw.splitlines()
            self.assertGreater(
                len(lines),
                1,
                "write_state output must be multi-line (pretty-printed), not compact JSON",
            )


class TestWriteStateRoundTrip(unittest.TestCase):
    """write_state followed by read_state must preserve the content."""

    def test_round_trip_dict_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            original = {
                "bootstrap_completed": True,
                "turn_count": 17,
                "last_session_id": "abc123",
            }
            state.write_state(root, original)
            result = state.read_state(root)
            self.assertEqual(result["bootstrap_completed"], True)
            self.assertEqual(result["turn_count"], 17)
            self.assertEqual(result["last_session_id"], "abc123")

    def test_round_trip_null_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            state.write_state(root, {"last_session_id": None})
            result = state.read_state(root)
            self.assertIsNone(result["last_session_id"])

    def test_round_trip_overwrites_previous(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            state.write_state(root, {"turn_count": 1})
            state.write_state(root, {"turn_count": 2})
            result = state.read_state(root)
            self.assertEqual(result["turn_count"], 2)


# ---------------------------------------------------------------------------
# default_state()
# ---------------------------------------------------------------------------


class TestDefaultStateShape(unittest.TestCase):
    """default_state() must return a dict with exactly the required keys."""

    def setUp(self) -> None:
        self.ds = state.default_state()

    def test_returns_dict(self) -> None:
        self.assertIsInstance(self.ds, dict)

    def test_has_schema_version(self) -> None:
        self.assertIn("schema_version", self.ds)

    def test_has_installed_at(self) -> None:
        self.assertIn("installed_at", self.ds)

    def test_has_bootstrap_completed(self) -> None:
        self.assertIn("bootstrap_completed", self.ds)

    def test_has_last_session_id(self) -> None:
        self.assertIn("last_session_id", self.ds)

    def test_has_turn_count(self) -> None:
        self.assertIn("turn_count", self.ds)


class TestDefaultStateValues(unittest.TestCase):
    """default_state() must return correct types and initial values."""

    def setUp(self) -> None:
        self.ds = state.default_state()

    def test_schema_version_is_1(self) -> None:
        self.assertEqual(self.ds["schema_version"], 1)

    def test_bootstrap_completed_is_false(self) -> None:
        self.assertIs(self.ds["bootstrap_completed"], False)

    def test_last_session_id_is_none(self) -> None:
        self.assertIsNone(self.ds["last_session_id"])

    def test_turn_count_is_zero(self) -> None:
        self.assertEqual(self.ds["turn_count"], 0)

    def test_turn_count_is_int(self) -> None:
        self.assertIsInstance(self.ds["turn_count"], int)

    def test_installed_at_is_string(self) -> None:
        self.assertIsInstance(self.ds["installed_at"], str)

    def test_installed_at_is_iso8601(self) -> None:
        """installed_at must be parseable by datetime.fromisoformat."""
        ts = self.ds["installed_at"]
        try:
            datetime.fromisoformat(ts)
        except ValueError as exc:
            self.fail(f"installed_at {ts!r} is not valid ISO 8601: {exc}")

    def test_installed_at_is_not_empty(self) -> None:
        self.assertNotEqual(self.ds["installed_at"].strip(), "")

    def test_schema_version_is_int(self) -> None:
        self.assertIsInstance(self.ds["schema_version"], int)


if __name__ == "__main__":
    unittest.main()
