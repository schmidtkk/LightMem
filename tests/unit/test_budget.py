from __future__ import annotations

"""
Tests for scripts/lib/budget.py

Derived purely from PRD_v0.2.md §6.1.1 (truncation marker), §10 (env vars),
and the Expected API spec.  No implementation files were read during authoring.

Expected API (spec-derived):
  - DEFAULT_SESSION_START_MAX_CHARS: int == 8000
  - TRUNCATION_MARKER: str
      Begins with "\n\n[", contains "LightMem truncated context",
      "LIGHTMEM_SESSION_START_MAX_CHARS", "LIGHTMEM_SESSION_START_CONTEXT=off".
      Ends with "]".
  - read_max_chars() -> int
      No env → 8000.  Valid int str → that int.  Invalid/negative/empty → 8000 + warn.
  - is_context_disabled() -> bool
      Reads LIGHTMEM_SESSION_START_CONTEXT; case-insensitive strip;
      {"0","false","off","none","disabled"} → True; all else → False.
  - apply_budget(content: str, max_chars: int | None = None) -> str
      max_chars=None → read_max_chars().
      max_chars <= 0 → "".
      len(content) <= max_chars → unchanged.
      len(content) > max_chars → truncate to (max_chars - len(MARKER)) chars
          (rstripped), append MARKER.  Final length == max_chars (or close to it).
      Defensive: if len(MARKER) >= max_chars → max_chars chars ending with "]".

Environment isolation: unittest.mock.patch.dict(os.environ, {...}, clear=True).

SPEC AMBIGUITIES ENCOUNTERED:
  SA1. The spec says "truncate to max_chars - len(TRUNCATION_MARKER) chars
       (rstripped)".  The rstrip is applied to the cut prefix BEFORE appending
       the marker, so the final length may be <= max_chars, not exactly.  Tests
       verify "exactly max_chars" only for content without trailing whitespace
       at the cut point; for the whitespace case the test only checks the final
       length is <= max_chars and that the marker is appended.
  SA2. "warn to stderr" for invalid env var — tests redirect stderr but only
       assert on the return value (not the warning text) to stay portable.
  SA3. The defensive path ("extremely small budget") is defined as
       len(TRUNCATION_MARKER) >= max_chars.  Tests verify the result ends with
       "]" and is exactly max_chars chars long.
"""

import io
import os
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

import budget  # type: ignore[import]  # noqa: E402 – imported after path fix

# ENV var name constants (prevents magic-string drift in tests)
_ENV_MAX_CHARS = "LIGHTMEM_SESSION_START_MAX_CHARS"
_ENV_CONTEXT = "LIGHTMEM_SESSION_START_CONTEXT"


# ===========================================================================
# 1. Module-level constants
# ===========================================================================

class TestDefaultSessionStartMaxChars(unittest.TestCase):
    """DEFAULT_SESSION_START_MAX_CHARS must be exactly 8000."""

    def test_default_value_is_8000(self) -> None:
        self.assertEqual(budget.DEFAULT_SESSION_START_MAX_CHARS, 8000)

    def test_default_value_is_int(self) -> None:
        self.assertIsInstance(budget.DEFAULT_SESSION_START_MAX_CHARS, int)


class TestTruncationMarkerConstant(unittest.TestCase):
    """
    TRUNCATION_MARKER is the literal string appended when content is truncated.
    PRD §6.1.1 specifies the text; tests verify required substrings.
    """

    def test_truncation_marker_is_str(self) -> None:
        self.assertIsInstance(budget.TRUNCATION_MARKER, str)

    def test_truncation_marker_begins_with_newline_newline_bracket(self) -> None:
        self.assertTrue(
            budget.TRUNCATION_MARKER.startswith("\n\n["),
            msg=f"TRUNCATION_MARKER must start with '\\n\\n[', got: {budget.TRUNCATION_MARKER[:20]!r}",
        )

    def test_truncation_marker_contains_lightmem_truncated_context(self) -> None:
        self.assertIn("LightMem truncated context", budget.TRUNCATION_MARKER)

    def test_truncation_marker_contains_max_chars_env_var(self) -> None:
        self.assertIn("LIGHTMEM_SESSION_START_MAX_CHARS", budget.TRUNCATION_MARKER)

    def test_truncation_marker_contains_context_off_env_var(self) -> None:
        self.assertIn("LIGHTMEM_SESSION_START_CONTEXT=off", budget.TRUNCATION_MARKER)

    def test_truncation_marker_ends_with_close_bracket(self) -> None:
        self.assertTrue(
            budget.TRUNCATION_MARKER.endswith("]"),
            msg=f"TRUNCATION_MARKER must end with ']', got: {budget.TRUNCATION_MARKER[-5:]!r}",
        )

    def test_truncation_marker_is_non_empty(self) -> None:
        self.assertGreater(len(budget.TRUNCATION_MARKER), 0)


# ===========================================================================
# 2. read_max_chars()
# ===========================================================================

class TestReadMaxCharsDefault(unittest.TestCase):
    """No env var set → 8000."""

    def test_no_env_returns_8000(self) -> None:
        with unittest.mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(budget.read_max_chars(), 8000)

    def test_returns_int(self) -> None:
        with unittest.mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsInstance(budget.read_max_chars(), int)


class TestReadMaxCharsValidInt(unittest.TestCase):
    """Valid positive int strings → that int."""

    def test_env_4000_returns_4000(self) -> None:
        with unittest.mock.patch.dict(os.environ, {_ENV_MAX_CHARS: "4000"}, clear=True):
            self.assertEqual(budget.read_max_chars(), 4000)

    def test_env_0_returns_0(self) -> None:
        # Zero is explicitly a valid value per spec.
        with unittest.mock.patch.dict(os.environ, {_ENV_MAX_CHARS: "0"}, clear=True):
            self.assertEqual(budget.read_max_chars(), 0)

    def test_env_whitespace_padded_4000_returns_4000(self) -> None:
        # Whitespace-padded valid int must be accepted after strip.
        with unittest.mock.patch.dict(os.environ, {_ENV_MAX_CHARS: "  4000  "}, clear=True):
            self.assertEqual(budget.read_max_chars(), 4000)


class TestReadMaxCharsInvalidFallback(unittest.TestCase):
    """Invalid / negative / empty env var → 8000, warn to stderr."""

    def _read_with_env(self, value: str) -> int:
        with unittest.mock.patch.dict(os.environ, {_ENV_MAX_CHARS: value}, clear=True):
            with unittest.mock.patch("sys.stderr", new_callable=io.StringIO):
                return budget.read_max_chars()

    def test_garbage_string_returns_8000(self) -> None:
        self.assertEqual(self._read_with_env("garbage"), 8000)

    def test_negative_value_returns_8000(self) -> None:
        self.assertEqual(self._read_with_env("-100"), 8000)

    def test_whitespace_only_returns_8000(self) -> None:
        self.assertEqual(self._read_with_env("  "), 8000)

    def test_float_string_returns_8000(self) -> None:
        # "3.14" is not a valid int
        self.assertEqual(self._read_with_env("3.14"), 8000)


# ===========================================================================
# 3. is_context_disabled()
# ===========================================================================

class TestIsContextDisabledDefault(unittest.TestCase):
    """No env var → False."""

    def test_no_env_returns_false(self) -> None:
        with unittest.mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(budget.is_context_disabled())

    def test_returns_bool(self) -> None:
        with unittest.mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsInstance(budget.is_context_disabled(), bool)


class TestIsContextDisabledTrueValues(unittest.TestCase):
    """
    {"0","false","off","none","disabled"} (case-insensitive, stripped) → True.
    """

    def _disabled(self, value: str) -> bool:
        with unittest.mock.patch.dict(os.environ, {_ENV_CONTEXT: value}, clear=True):
            return budget.is_context_disabled()

    def test_off_lowercase(self) -> None:
        self.assertTrue(self._disabled("off"))

    def test_off_uppercase(self) -> None:
        self.assertTrue(self._disabled("OFF"))

    def test_off_mixed_case(self) -> None:
        self.assertTrue(self._disabled("Off"))

    def test_zero_string(self) -> None:
        self.assertTrue(self._disabled("0"))

    def test_false_lowercase(self) -> None:
        self.assertTrue(self._disabled("false"))

    def test_false_title_case(self) -> None:
        self.assertTrue(self._disabled("False"))

    def test_none_lowercase(self) -> None:
        self.assertTrue(self._disabled("none"))

    def test_none_title_case(self) -> None:
        self.assertTrue(self._disabled("None"))

    def test_disabled_lowercase(self) -> None:
        self.assertTrue(self._disabled("disabled"))

    def test_off_with_whitespace(self) -> None:
        # Whitespace must be stripped before comparison.
        self.assertTrue(self._disabled(" off "))


class TestIsContextDisabledFalseValues(unittest.TestCase):
    """
    "on" / "yes" / "true" / "" / "1" → False.
    """

    def _disabled(self, value: str) -> bool:
        with unittest.mock.patch.dict(os.environ, {_ENV_CONTEXT: value}, clear=True):
            return budget.is_context_disabled()

    def test_on(self) -> None:
        self.assertFalse(self._disabled("on"))

    def test_yes(self) -> None:
        self.assertFalse(self._disabled("yes"))

    def test_true(self) -> None:
        self.assertFalse(self._disabled("true"))

    def test_empty_string(self) -> None:
        self.assertFalse(self._disabled(""))

    def test_one(self) -> None:
        self.assertFalse(self._disabled("1"))


# ===========================================================================
# 4. apply_budget()
# ===========================================================================

class TestApplyBudgetUnchanged(unittest.TestCase):
    """Content at or below max_chars must be returned unchanged."""

    def test_well_below_cap(self) -> None:
        self.assertEqual(budget.apply_budget("hello", max_chars=100), "hello")

    def test_exactly_at_cap(self) -> None:
        content = "x" * 100
        self.assertEqual(budget.apply_budget(content, max_chars=100), content)

    def test_empty_content_well_below_cap(self) -> None:
        self.assertEqual(budget.apply_budget("", max_chars=100), "")


class TestApplyBudgetZeroAndNegative(unittest.TestCase):
    """max_chars <= 0 → empty string regardless of content."""

    def test_max_chars_zero_returns_empty(self) -> None:
        self.assertEqual(budget.apply_budget("hello", max_chars=0), "")

    def test_max_chars_negative_returns_empty(self) -> None:
        self.assertEqual(budget.apply_budget("hello", max_chars=-1), "")

    def test_max_chars_zero_large_content(self) -> None:
        self.assertEqual(budget.apply_budget("x" * 9000, max_chars=0), "")


class TestApplyBudgetTruncation(unittest.TestCase):
    """Content exceeding max_chars must be truncated and marker appended.

    Note: max_chars must exceed len(TRUNCATION_MARKER) (152 chars) to exercise
    the normal (non-defensive) truncation path.  Tests use max_chars=500 as a
    safe value that is well above the marker length.
    """

    # Use a cap safely above len(TRUNCATION_MARKER) for normal-path tests.
    _NORMAL_CAP = 500

    def test_truncated_length_is_exactly_max_chars(self) -> None:
        # Content is far larger than the cap; result must be exactly _NORMAL_CAP chars.
        with unittest.mock.patch("sys.stderr", new_callable=io.StringIO):
            result = budget.apply_budget("x" * 9000, max_chars=self._NORMAL_CAP)
        self.assertEqual(len(result), self._NORMAL_CAP)

    def test_truncated_result_ends_with_close_bracket(self) -> None:
        # TRUNCATION_MARKER ends with "]"; so must the truncated result.
        with unittest.mock.patch("sys.stderr", new_callable=io.StringIO):
            result = budget.apply_budget("x" * 9000, max_chars=self._NORMAL_CAP)
        self.assertTrue(result.endswith("]"), msg=f"Expected ']' at end, got: {result[-5:]!r}")

    def test_truncated_result_contains_truncation_marker(self) -> None:
        # With _NORMAL_CAP > len(TRUNCATION_MARKER), the full marker must appear.
        with unittest.mock.patch("sys.stderr", new_callable=io.StringIO):
            result = budget.apply_budget("x" * 9000, max_chars=self._NORMAL_CAP)
        self.assertIn(budget.TRUNCATION_MARKER, result)

    def test_truncated_result_no_trailing_whitespace_before_marker(self) -> None:
        # Cut point must be rstripped — no trailing space before the marker.
        # Use a content with a trailing space exactly at the cut position.
        marker_len = len(budget.TRUNCATION_MARKER)
        max_chars = 500
        prefix_len = max_chars - marker_len
        # Put trailing spaces at the cut point
        content = "a" * (prefix_len - 5) + "     " + "b" * 5000
        with unittest.mock.patch("sys.stderr", new_callable=io.StringIO):
            result = budget.apply_budget(content, max_chars=max_chars)
        # The part before TRUNCATION_MARKER must not end with whitespace
        marker_start = result.index(budget.TRUNCATION_MARKER)
        prefix = result[:marker_start]
        self.assertEqual(prefix, prefix.rstrip())

    def test_truncation_warns_to_stderr(self) -> None:
        # apply_budget must write a warning to stderr on truncation.
        with unittest.mock.patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            budget.apply_budget("x" * 9000, max_chars=self._NORMAL_CAP)
            output = mock_err.getvalue()
        # Any non-empty warning is acceptable; we just verify something was written.
        self.assertGreater(len(output), 0)


class TestApplyBudgetNoneMaxChars(unittest.TestCase):
    """max_chars=None → reads read_max_chars() from env."""

    def test_none_max_chars_no_env_defaults_to_8000(self) -> None:
        # Content shorter than 8000 must pass through unchanged.
        with unittest.mock.patch.dict(os.environ, {}, clear=True):
            content = "short content"
            self.assertEqual(budget.apply_budget(content, max_chars=None), content)

    def test_none_max_chars_with_env_1000_truncates(self) -> None:
        # 1000 > len(TRUNCATION_MARKER)=152, so normal truncation path applies.
        with unittest.mock.patch.dict(
            os.environ, {_ENV_MAX_CHARS: "1000"}, clear=True
        ):
            with unittest.mock.patch("sys.stderr", new_callable=io.StringIO):
                result = budget.apply_budget("x" * 9000, max_chars=None)
        self.assertEqual(len(result), 1000)

    def test_none_max_chars_with_env_1000_ends_with_bracket(self) -> None:
        with unittest.mock.patch.dict(
            os.environ, {_ENV_MAX_CHARS: "1000"}, clear=True
        ):
            with unittest.mock.patch("sys.stderr", new_callable=io.StringIO):
                result = budget.apply_budget("x" * 9000, max_chars=None)
        self.assertTrue(result.endswith("]"))

    def test_positional_default_same_as_none(self) -> None:
        # Calling apply_budget(content) with no max_chars arg is same as None.
        with unittest.mock.patch.dict(os.environ, {}, clear=True):
            content = "short"
            self.assertEqual(budget.apply_budget(content), content)


class TestApplyBudgetDefensiveSmallBudget(unittest.TestCase):
    """
    Defensive path: len(TRUNCATION_MARKER) >= max_chars.
    Must return exactly max_chars chars ending with "]".
    """

    def _small_cap(self) -> int:
        # Pick a cap smaller than the marker, but positive.
        return min(50, len(budget.TRUNCATION_MARKER) - 1)

    def test_defensive_result_length_is_max_chars(self) -> None:
        cap = self._small_cap()
        with unittest.mock.patch("sys.stderr", new_callable=io.StringIO):
            result = budget.apply_budget("x" * 9000, max_chars=cap)
        self.assertEqual(len(result), cap)

    def test_defensive_result_ends_with_close_bracket(self) -> None:
        cap = self._small_cap()
        with unittest.mock.patch("sys.stderr", new_callable=io.StringIO):
            result = budget.apply_budget("x" * 9000, max_chars=cap)
        self.assertTrue(
            result.endswith("]"),
            msg=f"Expected result to end with ']', got: {result[-5:]!r}",
        )

    def test_defensive_result_exact_spec_case(self) -> None:
        # max_chars=50 is specified in the task as a concrete test case.
        with unittest.mock.patch("sys.stderr", new_callable=io.StringIO):
            result = budget.apply_budget("x" * 9000, max_chars=50)
        self.assertEqual(len(result), 50)
        self.assertTrue(result.endswith("]"))


if __name__ == "__main__":
    unittest.main()
