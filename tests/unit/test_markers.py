from __future__ import annotations

"""
Tests for scripts/lib/markers.py

Derived purely from PRD_v0.2.md §5.2 (gateway block format) and §6.3 (session
summary marker block).  No implementation files were read during authoring.

Marker format (PRD §5.2):  <!-- LIGHTMEM:<EVENT>:<START|END> -->
Known events: GATEWAY (CLAUDE.md gateway block), SUMMARY (session summaries).

The fence() helper is the core idempotent-update primitive used by
/lightmem:init (PRD §5.2) and SessionEnd (PRD §6.3).
"""

import re
import sys
import unittest

# ---------------------------------------------------------------------------
# Resolve the scripts/lib package so tests run from the repo root via
#   python3 -m unittest discover tests
# ---------------------------------------------------------------------------
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_LIB = _REPO_ROOT / "scripts" / "lib"
if str(_SCRIPTS_LIB) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_LIB))

import markers  # type: ignore[import]  # noqa: E402 – imported after path fix


class TestMarkerPrefix(unittest.TestCase):
    """PRD §5.2: all markers share the LIGHTMEM prefix."""

    def test_marker_prefix_value(self) -> None:
        self.assertEqual(markers.MARKER_PREFIX, "LIGHTMEM")

    def test_marker_prefix_is_str(self) -> None:
        self.assertIsInstance(markers.MARKER_PREFIX, str)


class TestGatewayConstants(unittest.TestCase):
    """PRD §5.2: exact literal strings for GATEWAY markers."""

    def test_gateway_start_exact(self) -> None:
        self.assertEqual(markers.GATEWAY_START, "<!-- LIGHTMEM:GATEWAY:START -->")

    def test_gateway_end_exact(self) -> None:
        self.assertEqual(markers.GATEWAY_END, "<!-- LIGHTMEM:GATEWAY:END -->")

    def test_gateway_markers_are_strings(self) -> None:
        self.assertIsInstance(markers.GATEWAY_START, str)
        self.assertIsInstance(markers.GATEWAY_END, str)


class TestSummaryConstants(unittest.TestCase):
    """PRD §6.3: SUMMARY markers for session summary files."""

    def test_summary_start_exact(self) -> None:
        self.assertEqual(markers.SUMMARY_START, "<!-- LIGHTMEM:SUMMARY:START -->")

    def test_summary_end_exact(self) -> None:
        self.assertEqual(markers.SUMMARY_END, "<!-- LIGHTMEM:SUMMARY:END -->")

    def test_summary_markers_are_strings(self) -> None:
        self.assertIsInstance(markers.SUMMARY_START, str)
        self.assertIsInstance(markers.SUMMARY_END, str)

    def test_summary_and_gateway_are_distinct(self) -> None:
        self.assertNotEqual(markers.SUMMARY_START, markers.GATEWAY_START)
        self.assertNotEqual(markers.SUMMARY_END, markers.GATEWAY_END)


class TestFenceBasic(unittest.TestCase):
    """PRD §5.2: fence() wraps body between matching START/END with newlines."""

    def test_fence_gateway_simple(self) -> None:
        result = markers.fence("GATEWAY", "hello world")
        expected = (
            "<!-- LIGHTMEM:GATEWAY:START -->\n"
            "hello world\n"
            "<!-- LIGHTMEM:GATEWAY:END -->"
        )
        self.assertEqual(result, expected)

    def test_fence_contains_start_marker(self) -> None:
        result = markers.fence("GATEWAY", "body")
        self.assertIn("<!-- LIGHTMEM:GATEWAY:START -->", result)

    def test_fence_contains_end_marker(self) -> None:
        result = markers.fence("GATEWAY", "body")
        self.assertIn("<!-- LIGHTMEM:GATEWAY:END -->", result)

    def test_fence_start_precedes_end(self) -> None:
        result = markers.fence("GATEWAY", "body")
        start_pos = result.index("<!-- LIGHTMEM:GATEWAY:START -->")
        end_pos = result.index("<!-- LIGHTMEM:GATEWAY:END -->")
        self.assertLess(start_pos, end_pos)


class TestFenceEmptyBody(unittest.TestCase):
    """fence() with empty body must still produce both markers with a newline between them."""

    def test_fence_empty_body_contains_both_markers(self) -> None:
        result = markers.fence("GATEWAY", "")
        self.assertIn("<!-- LIGHTMEM:GATEWAY:START -->", result)
        self.assertIn("<!-- LIGHTMEM:GATEWAY:END -->", result)

    def test_fence_empty_body_newline_structure(self) -> None:
        # Expected: START\n\nEND (body is empty, so two consecutive newlines)
        result = markers.fence("GATEWAY", "")
        expected = (
            "<!-- LIGHTMEM:GATEWAY:START -->\n"
            "\n"
            "<!-- LIGHTMEM:GATEWAY:END -->"
        )
        self.assertEqual(result, expected)


class TestFenceMultilineBody(unittest.TestCase):
    """fence() must preserve internal newlines in the body exactly."""

    def test_fence_multiline_body_preserved(self) -> None:
        body = "multi\nline\nbody"
        result = markers.fence("GATEWAY", body)
        expected = (
            "<!-- LIGHTMEM:GATEWAY:START -->\n"
            "multi\nline\nbody\n"
            "<!-- LIGHTMEM:GATEWAY:END -->"
        )
        self.assertEqual(result, expected)

    def test_fence_multiline_internal_newlines_intact(self) -> None:
        body = "line1\nline2\nline3"
        result = markers.fence("GATEWAY", body)
        # Each internal line must appear literally in the output
        self.assertIn("line1\nline2\nline3", result)


class TestFenceSummaryEvent(unittest.TestCase):
    """fence() must also work for SUMMARY event (PRD §6.3)."""

    def test_fence_summary_exact(self) -> None:
        result = markers.fence("SUMMARY", "session content")
        expected = (
            "<!-- LIGHTMEM:SUMMARY:START -->\n"
            "session content\n"
            "<!-- LIGHTMEM:SUMMARY:END -->"
        )
        self.assertEqual(result, expected)


class TestFenceValidation(unittest.TestCase):
    """fence() must raise ValueError for event names that do not match ^[A-Z][A-Z0-9_]*$."""

    def test_fence_raises_on_lowercase(self) -> None:
        with self.assertRaises(ValueError):
            markers.fence("invalid-name", "body")

    def test_fence_raises_on_hyphen(self) -> None:
        with self.assertRaises(ValueError):
            markers.fence("INVALID-NAME", "body")

    def test_fence_raises_on_leading_digit(self) -> None:
        with self.assertRaises(ValueError):
            markers.fence("123", "body")

    def test_fence_raises_on_empty_event(self) -> None:
        with self.assertRaises(ValueError):
            markers.fence("", "body")

    def test_fence_raises_on_mixed_case(self) -> None:
        # Lowercase letters are not in [A-Z0-9_], so "Gateway" is invalid
        with self.assertRaises(ValueError):
            markers.fence("Gateway", "body")

    def test_fence_valid_underscore_after_first_char(self) -> None:
        # Underscore is allowed after the first character (^[A-Z][A-Z0-9_]*$)
        result = markers.fence("VALID_EVENT", "x")
        self.assertIn("<!-- LIGHTMEM:VALID_EVENT:START -->", result)
        self.assertIn("<!-- LIGHTMEM:VALID_EVENT:END -->", result)

    def test_fence_valid_single_char(self) -> None:
        # Single uppercase letter is valid
        result = markers.fence("A", "body")
        self.assertIn("<!-- LIGHTMEM:A:START -->", result)
        self.assertIn("<!-- LIGHTMEM:A:END -->", result)

    def test_fence_valid_with_digits_after_first(self) -> None:
        # Digits are allowed after the first character
        result = markers.fence("EVENT2", "body")
        self.assertIn("<!-- LIGHTMEM:EVENT2:START -->", result)
        self.assertIn("<!-- LIGHTMEM:EVENT2:END -->", result)


class TestMarkerPairRegex(unittest.TestCase):
    """
    marker_pair_regex(event) returns a DOTALL re.Pattern that matches the entire
    fenced region including both markers.
    """

    def test_returns_compiled_pattern(self) -> None:
        pat = markers.marker_pair_regex("GATEWAY")
        self.assertIsInstance(pat, re.Pattern)

    def test_pattern_is_dotall(self) -> None:
        # The pattern must match across newlines (DOTALL/re.S)
        pat = markers.marker_pair_regex("GATEWAY")
        block = markers.fence("GATEWAY", "line1\nline2")
        self.assertIsNotNone(pat.search(block))

    def test_search_returns_full_fenced_region(self) -> None:
        pat = markers.marker_pair_regex("GATEWAY")
        body = "hello world"
        fenced = markers.fence("GATEWAY", body)
        match = pat.search(fenced)
        self.assertIsNotNone(match)
        # The match must span the full fenced region
        self.assertEqual(match.group(), fenced)  # type: ignore[union-attr]

    def test_search_within_surrounding_content(self) -> None:
        pat = markers.marker_pair_regex("GATEWAY")
        body = "inner content"
        fenced = markers.fence("GATEWAY", body)
        # Embed the fenced block between other content
        document = "text before\n\n" + fenced + "\n\ntext after"
        match = pat.search(document)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(), fenced)  # type: ignore[union-attr]

    def test_does_not_match_wrong_event(self) -> None:
        # A GATEWAY regex must not match a SUMMARY block
        pat = markers.marker_pair_regex("GATEWAY")
        summary_block = markers.fence("SUMMARY", "summary body")
        match = pat.search(summary_block)
        self.assertIsNone(match)

    def test_summary_pattern_matches_summary_block(self) -> None:
        pat = markers.marker_pair_regex("SUMMARY")
        summary_block = markers.fence("SUMMARY", "session summary text")
        match = pat.search(summary_block)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(), summary_block)  # type: ignore[union-attr]

    def test_gateway_pattern_does_not_match_summary_document(self) -> None:
        pat = markers.marker_pair_regex("GATEWAY")
        document = (
            "# Some heading\n\n"
            + markers.fence("SUMMARY", "session content")
            + "\n\nsome footer"
        )
        self.assertIsNone(pat.search(document))

    def test_multiline_body_matched(self) -> None:
        pat = markers.marker_pair_regex("GATEWAY")
        body = "## Heading\n\nParagraph one.\n\nParagraph two."
        fenced = markers.fence("GATEWAY", body)
        match = pat.search(fenced)
        self.assertIsNotNone(match)
        self.assertIn("Paragraph two.", match.group())  # type: ignore[union-attr]

    def test_two_blocks_produce_two_independent_matches(self) -> None:
        # Pins the non-greedy (.*?) invariant: a greedy pattern would collapse
        # two adjacent GATEWAY blocks into a single super-match. This is the
        # primary correctness property of marker_pair_regex.
        pat = markers.marker_pair_regex("GATEWAY")
        document = (
            markers.fence("GATEWAY", "first")
            + "\n\nintervening text\n\n"
            + markers.fence("GATEWAY", "second")
        )
        matches = pat.findall(document)
        self.assertEqual(len(matches), 2)
        self.assertIn("first", matches[0])
        self.assertNotIn("second", matches[0])
        self.assertIn("second", matches[1])
        self.assertNotIn("first", matches[1])


class TestIdempotentReplacement(unittest.TestCase):
    """
    Core idempotent-update primitive used by /lightmem:init (PRD §5.2) and
    SessionEnd (PRD §6.3).

    Given a document with one fenced GATEWAY block, use marker_pair_regex +
    re.sub to replace the inner body.  The result must have exactly one GATEWAY
    block containing the new body, and no leftover markers from the old block.
    """

    def _count_occurrences(self, haystack: str, needle: str) -> int:
        return haystack.count(needle)

    def test_replace_gateway_body_produces_single_block(self) -> None:
        original_body = "original content"
        new_body = "new body"

        document = (
            "# My Project\n\n"
            + markers.fence("GATEWAY", original_body)
            + "\n\n## Other section\n\nUser-authored content."
        )

        pat = markers.marker_pair_regex("GATEWAY")
        new_fenced = markers.fence("GATEWAY", new_body)
        result = pat.sub(new_fenced, document)

        # Exactly one START and one END marker must appear
        self.assertEqual(
            self._count_occurrences(result, "<!-- LIGHTMEM:GATEWAY:START -->"), 1
        )
        self.assertEqual(
            self._count_occurrences(result, "<!-- LIGHTMEM:GATEWAY:END -->"), 1
        )

    def test_replace_gateway_body_contains_new_body(self) -> None:
        document = markers.fence("GATEWAY", "old content")
        pat = markers.marker_pair_regex("GATEWAY")
        new_fenced = markers.fence("GATEWAY", "new body")
        result = pat.sub(new_fenced, document)
        self.assertIn("new body", result)

    def test_replace_gateway_body_removes_old_body(self) -> None:
        old_body = "old content that must vanish"
        document = markers.fence("GATEWAY", old_body)
        pat = markers.marker_pair_regex("GATEWAY")
        new_fenced = markers.fence("GATEWAY", "replacement")
        result = pat.sub(new_fenced, document)
        self.assertNotIn(old_body, result)

    def test_replace_preserves_content_outside_fence(self) -> None:
        pre_text = "# Title\n\n"
        post_text = "\n\n## User Section\n\nHand-written content."
        document = pre_text + markers.fence("GATEWAY", "old") + post_text

        pat = markers.marker_pair_regex("GATEWAY")
        new_fenced = markers.fence("GATEWAY", "new")
        result = pat.sub(new_fenced, document)

        self.assertTrue(result.startswith(pre_text))
        self.assertIn("Hand-written content.", result)

    def test_idempotent_double_replace(self) -> None:
        # Replacing twice with the same content must yield the same result
        document = markers.fence("GATEWAY", "body")
        pat = markers.marker_pair_regex("GATEWAY")
        replacement = markers.fence("GATEWAY", "final body")

        result1 = pat.sub(replacement, document)
        result2 = pat.sub(replacement, result1)
        self.assertEqual(result1, result2)


if __name__ == "__main__":
    unittest.main()
