from __future__ import annotations

"""
Tests for scripts/lib/stdin_io.py

Derived purely from PRD_v0.2.md §6.1 (hook skeleton), §8 (scripts inventory),
and §10 (environment variables).  No implementation files were read during
authoring.

Expected API (spec-derived):
  - MAX_STDIN_BYTES: int = 1024 * 1024   (exactly 1 MB)
  - read_json_stdin() -> dict[str, Any]
      * Reads at most MAX_STDIN_BYTES from sys.stdin.
      * Returns {} on empty input.
      * Returns {} on invalid JSON (does NOT raise).
      * Returns {} when the parsed value is not a dict (list, str, int, bool, null).
      * Truncates oversized input to MAX_STDIN_BYTES; returns {} if truncation
        produces invalid JSON.
      * On success, returns the parsed dict verbatim.
      * MUST NOT write anything to stdout; may log to stderr via stdlib logging.
      * MUST NOT raise on any input.

PRD §8 script skeleton:
    payload = stdin_io.read_json()   # 1 MB cap, returns {} on parse fail
"""

import contextlib
import io
import json
import sys
import unittest
import unittest.mock

from pathlib import Path

# ---------------------------------------------------------------------------
# Resolve the scripts/lib package so tests run from the repo root via
#   python3 -W error -m unittest discover tests
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_LIB = _REPO_ROOT / "scripts" / "lib"
if str(_SCRIPTS_LIB) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_LIB))

import stdin_io  # type: ignore[import]  # noqa: E402 – imported after path fix


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _call_with_stdin(text: str) -> dict:
    """Invoke read_json_stdin() with sys.stdin replaced by a StringIO."""
    with unittest.mock.patch("sys.stdin", io.StringIO(text)):
        return stdin_io.read_json_stdin()


def _call_with_stdin_capture_stdout(text: str) -> tuple[dict, str]:
    """Invoke read_json_stdin(), capture stdout as well, return (result, stdout)."""
    stdout_buf = io.StringIO()
    with contextlib.redirect_stdout(stdout_buf):
        with unittest.mock.patch("sys.stdin", io.StringIO(text)):
            result = stdin_io.read_json_stdin()
    return result, stdout_buf.getvalue()


# ===========================================================================
# 1. Module-level constant
# ===========================================================================

class TestMaxStdinBytes(unittest.TestCase):
    """PRD §8: MAX_STDIN_BYTES must be exactly 1 048 576 bytes (1 MiB)."""

    def test_constant_exists(self) -> None:
        self.assertTrue(hasattr(stdin_io, "MAX_STDIN_BYTES"))

    def test_constant_is_int(self) -> None:
        self.assertIsInstance(stdin_io.MAX_STDIN_BYTES, int)

    def test_constant_value_exact(self) -> None:
        self.assertEqual(stdin_io.MAX_STDIN_BYTES, 1024 * 1024)

    def test_constant_value_numeric(self) -> None:
        # Belt-and-suspenders: confirm the numeric value
        self.assertEqual(stdin_io.MAX_STDIN_BYTES, 1_048_576)


# ===========================================================================
# 2. Return type — always dict
# ===========================================================================

class TestReturnTypeIsDict(unittest.TestCase):
    """read_json_stdin() must always return a dict, never None or other types."""

    def test_empty_input_returns_dict(self) -> None:
        result = _call_with_stdin("")
        self.assertIsInstance(result, dict)

    def test_valid_json_returns_dict(self) -> None:
        result = _call_with_stdin('{"a": 1}')
        self.assertIsInstance(result, dict)

    def test_invalid_json_returns_dict(self) -> None:
        result = _call_with_stdin("not json")
        self.assertIsInstance(result, dict)

    def test_json_list_returns_dict(self) -> None:
        result = _call_with_stdin("[1, 2, 3]")
        self.assertIsInstance(result, dict)

    def test_json_null_returns_dict(self) -> None:
        result = _call_with_stdin("null")
        self.assertIsInstance(result, dict)

    def test_json_string_returns_dict(self) -> None:
        result = _call_with_stdin('"hello"')
        self.assertIsInstance(result, dict)

    def test_json_number_returns_dict(self) -> None:
        result = _call_with_stdin("42")
        self.assertIsInstance(result, dict)

    def test_json_bool_true_returns_dict(self) -> None:
        result = _call_with_stdin("true")
        self.assertIsInstance(result, dict)

    def test_json_bool_false_returns_dict(self) -> None:
        result = _call_with_stdin("false")
        self.assertIsInstance(result, dict)


# ===========================================================================
# 3. Empty input
# ===========================================================================

class TestEmptyInput(unittest.TestCase):
    """Empty stdin must produce an empty dict, not raise."""

    def test_empty_string_returns_empty_dict(self) -> None:
        result = _call_with_stdin("")
        self.assertEqual(result, {})

    def test_whitespace_only_returns_empty_dict(self) -> None:
        # A whitespace-only string is not valid JSON → returns {}
        result = _call_with_stdin("   \n\t  ")
        self.assertIsInstance(result, dict)
        # Either {} (parsed as invalid JSON) or {} from whitespace → both fine.
        # Spec just says empty input → {}.  Whitespace is treated as invalid.
        self.assertEqual(result, {})


# ===========================================================================
# 4. Valid JSON object inputs — parsed verbatim
# ===========================================================================

class TestValidJsonObjects(unittest.TestCase):
    """Successful parse must return the exact dict represented by the JSON."""

    def test_simple_flat_object(self) -> None:
        payload = {"key": "value", "number": 42}
        result = _call_with_stdin(json.dumps(payload))
        self.assertEqual(result, payload)

    def test_nested_object(self) -> None:
        payload = {"outer": {"inner": "data", "count": 7}}
        result = _call_with_stdin(json.dumps(payload))
        self.assertEqual(result, payload)

    def test_object_with_list_value(self) -> None:
        payload = {"items": [1, 2, 3], "flag": True}
        result = _call_with_stdin(json.dumps(payload))
        self.assertEqual(result, payload)

    def test_object_with_boolean_values(self) -> None:
        payload = {"active": True, "disabled": False}
        result = _call_with_stdin(json.dumps(payload))
        self.assertEqual(result, payload)

    def test_object_with_null_value(self) -> None:
        payload = {"key": None, "other": "present"}
        result = _call_with_stdin(json.dumps(payload))
        self.assertEqual(result, payload)

    def test_object_with_numeric_values(self) -> None:
        payload = {"integer": 99, "float": 3.14}
        result = _call_with_stdin(json.dumps(payload))
        self.assertEqual(result, payload)

    def test_object_with_unicode_values(self) -> None:
        payload = {"msg": "hello éà"}
        result = _call_with_stdin(json.dumps(payload))
        self.assertEqual(result, payload)

    def test_deeply_nested_object(self) -> None:
        payload = {"a": {"b": {"c": {"d": "deep"}}}}
        result = _call_with_stdin(json.dumps(payload))
        self.assertEqual(result, payload)

    def test_object_with_list_of_objects(self) -> None:
        payload = {"events": [{"type": "SessionStart"}, {"type": "Stop"}]}
        result = _call_with_stdin(json.dumps(payload))
        self.assertEqual(result, payload)

    def test_empty_json_object(self) -> None:
        # '{}' is valid JSON that parses to an empty dict — must return {}
        result = _call_with_stdin("{}")
        self.assertEqual(result, {})

    def test_realistic_hook_payload(self) -> None:
        # Mimics a realistic Claude Code hook stdin payload
        payload = {
            "session_id": "abc123",
            "hook_event_name": "SessionStart",
            "source": "startup",
            "stop_hook_active": False,
        }
        result = _call_with_stdin(json.dumps(payload))
        self.assertEqual(result, payload)


# ===========================================================================
# 5. Invalid JSON → {}
# ===========================================================================

class TestInvalidJson(unittest.TestCase):
    """Invalid JSON input must return {} and never raise."""

    def test_literal_not_json(self) -> None:
        self.assertEqual(_call_with_stdin("not json"), {})

    def test_broken_open_brace(self) -> None:
        self.assertEqual(_call_with_stdin("{broken"), {})

    def test_unclosed_string(self) -> None:
        self.assertEqual(_call_with_stdin('{"key": "unclosed'), {})

    def test_trailing_comma(self) -> None:
        self.assertEqual(_call_with_stdin('{"a": 1,}'), {})

    def test_single_quote_json(self) -> None:
        # Python-style single-quoted dict is NOT valid JSON
        self.assertEqual(_call_with_stdin("{'key': 'value'}"), {})

    def test_bare_word_true_uppercase(self) -> None:
        # "True" (Python) is not valid JSON (must be lowercase "true")
        self.assertEqual(_call_with_stdin("True"), {})

    def test_just_a_colon(self) -> None:
        self.assertEqual(_call_with_stdin(":"), {})

    def test_xml_tag(self) -> None:
        self.assertEqual(_call_with_stdin("<tag>value</tag>"), {})


# ===========================================================================
# 6. Non-dict JSON top-level → {}
# ===========================================================================

class TestNonDictJson(unittest.TestCase):
    """
    JSON that parses successfully but is not a dict must return {}.
    PRD §8: read_json() returns {} on parse fail — non-dict is treated as fail.
    """

    def test_json_list_returns_empty_dict(self) -> None:
        self.assertEqual(_call_with_stdin("[1, 2, 3]"), {})

    def test_json_empty_list_returns_empty_dict(self) -> None:
        self.assertEqual(_call_with_stdin("[]"), {})

    def test_json_list_of_objects_returns_empty_dict(self) -> None:
        self.assertEqual(_call_with_stdin('[{"a": 1}]'), {})

    def test_json_string_scalar_returns_empty_dict(self) -> None:
        self.assertEqual(_call_with_stdin('"hello"'), {})

    def test_json_integer_scalar_returns_empty_dict(self) -> None:
        self.assertEqual(_call_with_stdin("42"), {})

    def test_json_float_scalar_returns_empty_dict(self) -> None:
        self.assertEqual(_call_with_stdin("3.14"), {})

    def test_json_true_returns_empty_dict(self) -> None:
        self.assertEqual(_call_with_stdin("true"), {})

    def test_json_false_returns_empty_dict(self) -> None:
        self.assertEqual(_call_with_stdin("false"), {})

    def test_json_null_returns_empty_dict(self) -> None:
        # null parses to Python None, which is not a dict → {}
        self.assertEqual(_call_with_stdin("null"), {})


# ===========================================================================
# 7. Oversized input (> MAX_STDIN_BYTES)
# ===========================================================================

class TestOversizedInput(unittest.TestCase):
    """
    Input larger than MAX_STDIN_BYTES must be silently truncated.
    The function must not crash; it must return a dict.
    If truncation produces invalid JSON, {} is returned.

    PRD §8: "read at most MAX_STDIN_BYTES from stdin … silently truncated."
    """

    def test_two_mb_input_returns_dict(self) -> None:
        # A 2 MB string of repeated {"key":"value"} — not valid JSON when
        # truncated at 1 MB because the brace count is not balanced.
        chunk = '{"key":"value"}'
        big_input = chunk * (2 * 1024 * 1024 // len(chunk) + 1)
        result = _call_with_stdin(big_input)
        # Must always return a dict (may be {} due to truncation → invalid JSON)
        self.assertIsInstance(result, dict)

    def test_two_mb_garbage_returns_empty_dict(self) -> None:
        # 2 MB of 'x' characters is not JSON → truncated → still not JSON → {}
        big_input = "x" * (2 * 1024 * 1024)
        result = _call_with_stdin(big_input)
        self.assertEqual(result, {})

    def test_just_over_limit_returns_dict(self) -> None:
        # Exactly MAX_STDIN_BYTES + 1 characters of 'a' — not valid JSON
        big_input = "a" * (stdin_io.MAX_STDIN_BYTES + 1)
        result = _call_with_stdin(big_input)
        self.assertIsInstance(result, dict)

    def test_oversized_input_does_not_raise(self) -> None:
        big_input = "z" * (3 * 1024 * 1024)
        try:
            result = _call_with_stdin(big_input)
        except Exception as exc:  # noqa: BLE001
            self.fail(f"read_json_stdin() raised on oversized input: {exc!r}")
        self.assertIsInstance(result, dict)

    def test_reads_at_most_max_stdin_bytes(self) -> None:
        """
        Verify the truncation boundary: feed exactly MAX_STDIN_BYTES of 'a'
        (not valid JSON) followed by valid JSON.  Since only the first
        MAX_STDIN_BYTES are read, the valid JSON suffix is never seen.
        """
        valid_suffix = '{"reachable": true}'
        # Build an input that has MAX_STDIN_BYTES of 'a', then a valid JSON suffix.
        big_input = "a" * stdin_io.MAX_STDIN_BYTES + valid_suffix
        result = _call_with_stdin(big_input)
        # The suffix should NOT have been parsed (it was beyond the read limit)
        self.assertNotIn("reachable", result)
        # And the truncated portion 'aaa…a' is not valid JSON → {}
        self.assertEqual(result, {})


# ===========================================================================
# 8. Stdout must be empty
# ===========================================================================

class TestNoStdoutOutput(unittest.TestCase):
    """
    PRD §8: read_json_stdin() MUST NOT write anything to stdout.
    (It may log to stderr via stdlib logging, but stdout must remain clean.)
    """

    def test_empty_input_no_stdout(self) -> None:
        _, stdout = _call_with_stdin_capture_stdout("")
        self.assertEqual(stdout, "")

    def test_valid_json_no_stdout(self) -> None:
        _, stdout = _call_with_stdin_capture_stdout('{"a": 1}')
        self.assertEqual(stdout, "")

    def test_invalid_json_no_stdout(self) -> None:
        _, stdout = _call_with_stdin_capture_stdout("not json")
        self.assertEqual(stdout, "")

    def test_json_list_no_stdout(self) -> None:
        _, stdout = _call_with_stdin_capture_stdout("[1, 2, 3]")
        self.assertEqual(stdout, "")

    def test_json_null_no_stdout(self) -> None:
        _, stdout = _call_with_stdin_capture_stdout("null")
        self.assertEqual(stdout, "")

    def test_oversized_input_no_stdout(self) -> None:
        big_input = "z" * (2 * 1024 * 1024)
        _, stdout = _call_with_stdin_capture_stdout(big_input)
        self.assertEqual(stdout, "")


# ===========================================================================
# 9. No exceptions raised — robustness guarantee
# ===========================================================================

class TestNoExceptionsRaised(unittest.TestCase):
    """
    PRD §8: hook skeleton wraps everything in try/except; the library function
    itself must also never propagate an exception on any input.
    """

    _PATHOLOGICAL_INPUTS = [
        "",
        "not json",
        "{broken",
        "null",
        "true",
        "false",
        "42",
        '"string"',
        "[1, 2, 3]",
        '{"valid": "object"}',
        "   ",
        "\x00\x01\x02",          # null bytes and control chars
        "{" * 1000,               # deeply unbalanced braces
        '{"key": ' + "}" * 500,  # malformed nesting
        "a" * (2 * 1024 * 1024), # 2 MB of non-JSON
    ]

    def _assert_no_raise(self, text: str) -> None:
        try:
            result = _call_with_stdin(text)
        except Exception as exc:  # noqa: BLE001
            self.fail(
                f"read_json_stdin() raised {type(exc).__name__!r} on input "
                f"{text[:40]!r}...: {exc!r}"
            )
        self.assertIsInstance(result, dict)

    def test_no_exception_on_all_pathological_inputs(self) -> None:
        for text in self._PATHOLOGICAL_INPUTS:
            with self.subTest(input_prefix=repr(text[:40])):
                self._assert_no_raise(text)


# ===========================================================================
# 10. Function is callable and accepts no arguments
# ===========================================================================

class TestFunctionSignature(unittest.TestCase):
    """read_json_stdin must be a callable taking no arguments."""

    def test_is_callable(self) -> None:
        self.assertTrue(callable(stdin_io.read_json_stdin))

    def test_returns_on_call_with_no_args(self) -> None:
        with unittest.mock.patch("sys.stdin", io.StringIO("")):
            result = stdin_io.read_json_stdin()
        self.assertIsNotNone(result)


if __name__ == "__main__":
    unittest.main()
