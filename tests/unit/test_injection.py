from __future__ import annotations

"""
Tests for scripts/lib/injection.py

Derived purely from PRD_v0.2.md §6.1.2 (stale-replay guard), §6.1.3 (output
format), and the Expected API spec.  No implementation files were read during
authoring.

Expected API (spec-derived):
  - STALE_REPLAY_GUARD_PRELUDE: str — 7-line verbatim prelude from PRD §6.1.2.
      Contains: "HISTORICAL REFERENCE ONLY", "NOT LIVE INSTRUCTIONS",
                "STALE-BY-DEFAULT", and the em-dash character —.
  - STALE_REPLAY_BEGIN_MARKER: str == "--- BEGIN PRIOR-SESSION SUMMARY ---"
  - STALE_REPLAY_END_MARKER: str  == "--- END PRIOR-SESSION SUMMARY ---"
  - wrap_with_stale_replay_guard(content: str) -> str
      Returns: <PRELUDE>\n\n<BEGIN_MARKER>\n<content>\n<END_MARKER>
      Empty content: <PRELUDE>\n\n<BEGIN_MARKER>\n\n<END_MARKER>
  - build_session_start_output(additional_context: str) -> str
      JSON: {"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"..."}}
      Uses ensure_ascii=False.
  - build_hook_output(hook_event_name: str, additional_context: str = "") -> str
      Same envelope shape; parameterised event name; default "" for context.
"""

import json
import sys
import unittest

from pathlib import Path

# ---------------------------------------------------------------------------
# Resolve the scripts/lib package so tests run from the repo root via
#   python3 -W error -m unittest discover tests
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_LIB = _REPO_ROOT / "scripts" / "lib"
if str(_SCRIPTS_LIB) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_LIB))

import injection  # type: ignore[import]  # noqa: E402 – imported after path fix


# ===========================================================================
# 1. STALE_REPLAY_GUARD_PRELUDE constant
# ===========================================================================

class TestStaleReplayGuardPrelude(unittest.TestCase):
    """PRD §6.1.2: the prelude is a non-empty, multi-line verbatim string."""

    def test_prelude_is_str(self) -> None:
        self.assertIsInstance(injection.STALE_REPLAY_GUARD_PRELUDE, str)

    def test_prelude_is_non_empty(self) -> None:
        self.assertTrue(len(injection.STALE_REPLAY_GUARD_PRELUDE) > 0)

    def test_prelude_is_multiline(self) -> None:
        self.assertIn("\n", injection.STALE_REPLAY_GUARD_PRELUDE)

    def test_prelude_contains_historical_reference_only(self) -> None:
        self.assertIn("HISTORICAL REFERENCE ONLY", injection.STALE_REPLAY_GUARD_PRELUDE)

    def test_prelude_contains_not_live_instructions(self) -> None:
        self.assertIn("NOT LIVE INSTRUCTIONS", injection.STALE_REPLAY_GUARD_PRELUDE)

    def test_prelude_contains_stale_by_default(self) -> None:
        self.assertIn("STALE-BY-DEFAULT", injection.STALE_REPLAY_GUARD_PRELUDE)

    def test_prelude_contains_em_dash(self) -> None:
        self.assertIn("—", injection.STALE_REPLAY_GUARD_PRELUDE)


# ===========================================================================
# 2. STALE_REPLAY_BEGIN_MARKER and STALE_REPLAY_END_MARKER constants
# ===========================================================================

class TestStaleReplayMarkerConstants(unittest.TestCase):
    """PRD §6.1.2: exact literal values for the fence markers."""

    def test_begin_marker_exact(self) -> None:
        self.assertEqual(
            injection.STALE_REPLAY_BEGIN_MARKER,
            "--- BEGIN PRIOR-SESSION SUMMARY ---",
        )

    def test_end_marker_exact(self) -> None:
        self.assertEqual(
            injection.STALE_REPLAY_END_MARKER,
            "--- END PRIOR-SESSION SUMMARY ---",
        )

    def test_begin_marker_is_str(self) -> None:
        self.assertIsInstance(injection.STALE_REPLAY_BEGIN_MARKER, str)

    def test_end_marker_is_str(self) -> None:
        self.assertIsInstance(injection.STALE_REPLAY_END_MARKER, str)

    def test_begin_and_end_are_distinct(self) -> None:
        self.assertNotEqual(
            injection.STALE_REPLAY_BEGIN_MARKER,
            injection.STALE_REPLAY_END_MARKER,
        )


# ===========================================================================
# 3. wrap_with_stale_replay_guard — normal content
# ===========================================================================

class TestWrapWithStaleReplayGuardNormal(unittest.TestCase):
    """
    PRD §6.1.2: structure is <PRELUDE>\n\n<BEGIN>\n<content>\n<END>.
    Exactly one blank line between prelude and BEGIN marker.
    No extra blank lines inside the fence.
    """

    def _wrap(self, content: str) -> str:
        return injection.wrap_with_stale_replay_guard(content)

    def test_result_is_str(self) -> None:
        self.assertIsInstance(self._wrap("test"), str)

    def test_contains_prelude(self) -> None:
        result = self._wrap("test content")
        self.assertIn(injection.STALE_REPLAY_GUARD_PRELUDE, result)

    def test_contains_begin_marker_on_own_line(self) -> None:
        result = self._wrap("test content")
        lines = result.splitlines()
        self.assertIn(injection.STALE_REPLAY_BEGIN_MARKER, lines)

    def test_contains_end_marker_on_own_line(self) -> None:
        result = self._wrap("test content")
        lines = result.splitlines()
        self.assertIn(injection.STALE_REPLAY_END_MARKER, lines)

    def test_content_between_markers(self) -> None:
        result = self._wrap("test content")
        begin_pos = result.index(injection.STALE_REPLAY_BEGIN_MARKER)
        end_pos = result.index(injection.STALE_REPLAY_END_MARKER)
        inner = result[begin_pos + len(injection.STALE_REPLAY_BEGIN_MARKER) : end_pos]
        self.assertIn("test content", inner)

    def test_begin_before_end(self) -> None:
        result = self._wrap("test content")
        begin_pos = result.index(injection.STALE_REPLAY_BEGIN_MARKER)
        end_pos = result.index(injection.STALE_REPLAY_END_MARKER)
        self.assertLess(begin_pos, end_pos)

    def test_exactly_one_blank_line_between_prelude_and_begin(self) -> None:
        result = self._wrap("test content")
        prelude = injection.STALE_REPLAY_GUARD_PRELUDE
        begin = injection.STALE_REPLAY_BEGIN_MARKER
        # After the prelude there must be exactly one blank line (two newlines)
        # then the BEGIN marker — no more, no fewer.
        expected_join = prelude + "\n\n" + begin
        self.assertIn(expected_join, result)

    def test_no_extra_blank_line_after_begin_before_content(self) -> None:
        result = self._wrap("test content")
        begin = injection.STALE_REPLAY_BEGIN_MARKER
        # Immediately after BEGIN marker and a single newline, content starts.
        # There must NOT be a blank line (double newline) between BEGIN and content.
        begin_then_blank = begin + "\n\n"
        self.assertNotIn(begin_then_blank, result)

    def test_no_extra_blank_line_after_content_before_end(self) -> None:
        result = self._wrap("test content")
        end = injection.STALE_REPLAY_END_MARKER
        # Just before END marker there must NOT be an extra blank line.
        blank_then_end = "\n\n" + end
        self.assertNotIn(blank_then_end, result)

    def test_structure_exact_shape(self) -> None:
        prelude = injection.STALE_REPLAY_GUARD_PRELUDE
        begin = injection.STALE_REPLAY_BEGIN_MARKER
        end = injection.STALE_REPLAY_END_MARKER
        content = "test content"
        expected = prelude + "\n\n" + begin + "\n" + content + "\n" + end
        self.assertEqual(self._wrap(content), expected)


# ===========================================================================
# 4. wrap_with_stale_replay_guard — empty content
# ===========================================================================

class TestWrapWithStaleReplayGuardEmpty(unittest.TestCase):
    """
    PRD spec: empty content produces BEGIN\n\nEND (empty line between markers).
    Must not crash; both markers must appear.
    """

    def test_empty_content_does_not_crash(self) -> None:
        result = injection.wrap_with_stale_replay_guard("")
        self.assertIsInstance(result, str)

    def test_empty_content_has_begin_marker(self) -> None:
        result = injection.wrap_with_stale_replay_guard("")
        self.assertIn(injection.STALE_REPLAY_BEGIN_MARKER, result)

    def test_empty_content_has_end_marker(self) -> None:
        result = injection.wrap_with_stale_replay_guard("")
        self.assertIn(injection.STALE_REPLAY_END_MARKER, result)

    def test_empty_content_has_empty_line_between_markers(self) -> None:
        result = injection.wrap_with_stale_replay_guard("")
        begin = injection.STALE_REPLAY_BEGIN_MARKER
        end = injection.STALE_REPLAY_END_MARKER
        # Between BEGIN and END must be an empty line (i.e. \n\n).
        between_markers = begin + "\n\n" + end
        self.assertIn(between_markers, result)

    def test_empty_content_exact_shape(self) -> None:
        prelude = injection.STALE_REPLAY_GUARD_PRELUDE
        begin = injection.STALE_REPLAY_BEGIN_MARKER
        end = injection.STALE_REPLAY_END_MARKER
        # With empty content, \n<content>\n collapses to \n\n
        expected = prelude + "\n\n" + begin + "\n\n" + end
        self.assertEqual(injection.wrap_with_stale_replay_guard(""), expected)


# ===========================================================================
# 5. wrap_with_stale_replay_guard — multiline content
# ===========================================================================

class TestWrapWithStaleReplayGuardMultiline(unittest.TestCase):
    """Internal newlines in content must be preserved exactly."""

    def test_multiline_content_preserved(self) -> None:
        content = "multi\nline\ncontent"
        result = injection.wrap_with_stale_replay_guard(content)
        self.assertIn("multi\nline\ncontent", result)

    def test_multiline_content_between_markers(self) -> None:
        content = "line one\nline two\nline three"
        result = injection.wrap_with_stale_replay_guard(content)
        begin_pos = result.index(injection.STALE_REPLAY_BEGIN_MARKER)
        end_pos = result.index(injection.STALE_REPLAY_END_MARKER)
        inner = result[begin_pos + len(injection.STALE_REPLAY_BEGIN_MARKER) : end_pos]
        for line in ["line one", "line two", "line three"]:
            self.assertIn(line, inner)

    def test_multiline_content_exact_shape(self) -> None:
        prelude = injection.STALE_REPLAY_GUARD_PRELUDE
        begin = injection.STALE_REPLAY_BEGIN_MARKER
        end = injection.STALE_REPLAY_END_MARKER
        content = "multi\nline\ncontent"
        expected = prelude + "\n\n" + begin + "\n" + content + "\n" + end
        self.assertEqual(injection.wrap_with_stale_replay_guard(content), expected)


# ===========================================================================
# 6. build_session_start_output
# ===========================================================================

class TestBuildSessionStartOutputStructure(unittest.TestCase):
    """
    PRD §6.1.3: JSON output with hookSpecificOutput envelope.
    Structure: {"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"..."}}
    """

    def test_returns_str(self) -> None:
        self.assertIsInstance(injection.build_session_start_output("hello"), str)

    def test_parses_as_json(self) -> None:
        result = injection.build_session_start_output("hello")
        parsed = json.loads(result)
        self.assertIsInstance(parsed, dict)

    def test_top_level_key_hook_specific_output(self) -> None:
        parsed = json.loads(injection.build_session_start_output("hello"))
        self.assertIn("hookSpecificOutput", parsed)

    def test_no_extra_top_level_keys(self) -> None:
        parsed = json.loads(injection.build_session_start_output("hello"))
        self.assertEqual(list(parsed.keys()), ["hookSpecificOutput"])

    def test_hook_event_name_is_session_start(self) -> None:
        parsed = json.loads(injection.build_session_start_output("hello"))
        inner = parsed["hookSpecificOutput"]
        self.assertEqual(inner["hookEventName"], "SessionStart")

    def test_additional_context_matches_input(self) -> None:
        parsed = json.loads(injection.build_session_start_output("hello"))
        inner = parsed["hookSpecificOutput"]
        self.assertEqual(inner["additionalContext"], "hello")

    def test_inner_has_exactly_two_keys(self) -> None:
        parsed = json.loads(injection.build_session_start_output("hello"))
        inner = parsed["hookSpecificOutput"]
        self.assertEqual(sorted(inner.keys()), ["additionalContext", "hookEventName"])


class TestBuildSessionStartOutputEmptyContext(unittest.TestCase):
    """Empty additional_context must produce field with empty string value, not missing."""

    def test_empty_context_parses_as_json(self) -> None:
        result = injection.build_session_start_output("")
        parsed = json.loads(result)
        self.assertIsInstance(parsed, dict)

    def test_empty_context_key_present(self) -> None:
        parsed = json.loads(injection.build_session_start_output(""))
        inner = parsed["hookSpecificOutput"]
        self.assertIn("additionalContext", inner)

    def test_empty_context_value_is_empty_string(self) -> None:
        parsed = json.loads(injection.build_session_start_output(""))
        inner = parsed["hookSpecificOutput"]
        self.assertEqual(inner["additionalContext"], "")

    def test_empty_context_hook_event_name_still_session_start(self) -> None:
        parsed = json.loads(injection.build_session_start_output(""))
        inner = parsed["hookSpecificOutput"]
        self.assertEqual(inner["hookEventName"], "SessionStart")


class TestBuildSessionStartOutputUnicode(unittest.TestCase):
    """ensure_ascii=False: unicode must round-trip correctly through json.loads."""

    def test_unicode_chinese_round_trips(self) -> None:
        context = "unicode 中文 —"
        parsed = json.loads(injection.build_session_start_output(context))
        self.assertEqual(parsed["hookSpecificOutput"]["additionalContext"], context)

    def test_unicode_not_escaped_in_output(self) -> None:
        context = "中文"
        result = injection.build_session_start_output(context)
        # ensure_ascii=False means the Chinese characters appear literally,
        # not as \\uXXXX escape sequences.
        self.assertIn("中文", result)

    def test_em_dash_round_trips(self) -> None:
        context = "em—dash"
        parsed = json.loads(injection.build_session_start_output(context))
        self.assertEqual(parsed["hookSpecificOutput"]["additionalContext"], context)


# ===========================================================================
# 7. build_hook_output
# ===========================================================================

class TestBuildHookOutputStructure(unittest.TestCase):
    """
    build_hook_output(hook_event_name, additional_context="") must produce the
    same JSON envelope as build_session_start_output but with parameterised
    event name.
    """

    def test_returns_str(self) -> None:
        self.assertIsInstance(injection.build_hook_output("UserPromptSubmit", "ctx"), str)

    def test_parses_as_json(self) -> None:
        result = injection.build_hook_output("UserPromptSubmit", "ctx")
        parsed = json.loads(result)
        self.assertIsInstance(parsed, dict)

    def test_top_level_key_hook_specific_output(self) -> None:
        parsed = json.loads(injection.build_hook_output("UserPromptSubmit", "ctx"))
        self.assertIn("hookSpecificOutput", parsed)

    def test_no_extra_top_level_keys(self) -> None:
        parsed = json.loads(injection.build_hook_output("UserPromptSubmit", "ctx"))
        self.assertEqual(list(parsed.keys()), ["hookSpecificOutput"])

    def test_hook_event_name_matches_argument(self) -> None:
        parsed = json.loads(injection.build_hook_output("UserPromptSubmit", "ctx"))
        inner = parsed["hookSpecificOutput"]
        self.assertEqual(inner["hookEventName"], "UserPromptSubmit")

    def test_additional_context_matches_argument(self) -> None:
        parsed = json.loads(injection.build_hook_output("UserPromptSubmit", "ctx"))
        inner = parsed["hookSpecificOutput"]
        self.assertEqual(inner["additionalContext"], "ctx")


class TestBuildHookOutputDefaultContext(unittest.TestCase):
    """Default additional_context must produce empty string value, not missing key."""

    def test_default_context_parses_as_json(self) -> None:
        result = injection.build_hook_output("Stop")
        parsed = json.loads(result)
        self.assertIsInstance(parsed, dict)

    def test_default_context_key_present(self) -> None:
        parsed = json.loads(injection.build_hook_output("Stop"))
        inner = parsed["hookSpecificOutput"]
        self.assertIn("additionalContext", inner)

    def test_default_context_value_is_empty_string(self) -> None:
        parsed = json.loads(injection.build_hook_output("Stop"))
        inner = parsed["hookSpecificOutput"]
        self.assertEqual(inner["additionalContext"], "")

    def test_default_context_hook_event_name(self) -> None:
        parsed = json.loads(injection.build_hook_output("Stop"))
        inner = parsed["hookSpecificOutput"]
        self.assertEqual(inner["hookEventName"], "Stop")


class TestBuildHookOutputArbitraryEventName(unittest.TestCase):
    """
    build_hook_output does NOT validate event name — caller responsibility.
    Must not raise on arbitrary strings.
    """

    def test_arbitrary_event_name_does_not_raise(self) -> None:
        # Must not raise; event name validation is caller responsibility.
        result = injection.build_hook_output("Anything")
        parsed = json.loads(result)
        self.assertEqual(parsed["hookSpecificOutput"]["hookEventName"], "Anything")

    def test_lowercase_event_name_does_not_raise(self) -> None:
        result = injection.build_hook_output("sessionstart")
        parsed = json.loads(result)
        self.assertEqual(parsed["hookSpecificOutput"]["hookEventName"], "sessionstart")

    def test_event_name_with_spaces_does_not_raise(self) -> None:
        result = injection.build_hook_output("My Event")
        parsed = json.loads(result)
        self.assertEqual(parsed["hookSpecificOutput"]["hookEventName"], "My Event")

    def test_empty_event_name_does_not_raise(self) -> None:
        result = injection.build_hook_output("")
        parsed = json.loads(result)
        self.assertEqual(parsed["hookSpecificOutput"]["hookEventName"], "")


if __name__ == "__main__":
    unittest.main()
