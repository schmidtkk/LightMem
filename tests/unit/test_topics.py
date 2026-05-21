from __future__ import annotations

"""
Tests for scripts/lib/topics.py

Derived purely from PRD_v0.2.md §5.3-5.5 (topic taxonomy + frontmatter) and the
Round-4 QA API spec.  No implementation files were read during authoring.

Expected API:
  - SLUG_REGEX: re.Pattern[str]  — matches ^[a-z][a-z0-9-]*$
  - VALID_KINDS: frozenset[str]  — {"mission","architecture","decision",
                                    "constraint","workflow","gotcha","roadmap"}
  - VALID_STATUSES: frozenset[str] — {"active","superseded","archived"}
  - is_valid_slug(slug: str) -> bool
  - parse_frontmatter(text: str) -> tuple[dict, str]
  - Topic — frozen dataclass with fields: id, kind, path, frontmatter, body
  - walk_topics(topics_dir: Path) -> list[Topic]
"""

import re
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_LIB = _REPO_ROOT / "scripts" / "lib"
if str(_SCRIPTS_LIB) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_LIB))

import topics  # type: ignore[import]  # noqa: E402 – imported after path fix


# ---------------------------------------------------------------------------
# SLUG_REGEX
# ---------------------------------------------------------------------------


class TestSlugRegexExists(unittest.TestCase):
    """SLUG_REGEX must be a compiled re.Pattern."""

    def test_slug_regex_is_pattern(self) -> None:
        self.assertIsInstance(topics.SLUG_REGEX, re.Pattern)


class TestSlugRegexMatches(unittest.TestCase):
    """SLUG_REGEX must match valid kebab-case slugs."""

    def _assertMatch(self, slug: str) -> None:
        self.assertIsNotNone(
            topics.SLUG_REGEX.match(slug),
            f"Expected SLUG_REGEX to match {slug!r}",
        )

    def test_simple_lowercase(self) -> None:
        self._assertMatch("hello")

    def test_kebab_case(self) -> None:
        self._assertMatch("my-slug")

    def test_kebab_with_digits(self) -> None:
        self._assertMatch("my-slug-123")

    def test_starts_with_letter_has_digit(self) -> None:
        self._assertMatch("a1b2c3")

    def test_single_letter(self) -> None:
        self._assertMatch("a")

    def test_multiple_hyphens(self) -> None:
        self._assertMatch("one-two-three")

    def test_long_slug(self) -> None:
        self._assertMatch("claude-md-as-gateway")


class TestSlugRegexRejects(unittest.TestCase):
    """SLUG_REGEX must NOT match invalid slugs."""

    def _assertNoMatch(self, slug: str) -> None:
        # Use fullmatch-like check: the match must cover the whole string
        m = topics.SLUG_REGEX.match(slug)
        matched_fully = m is not None and m.group() == slug
        self.assertFalse(
            matched_fully,
            f"Expected SLUG_REGEX to NOT fully match {slug!r}",
        )

    def test_starts_with_digit(self) -> None:
        self._assertNoMatch("1bad")

    def test_uppercase(self) -> None:
        self._assertNoMatch("MySlug")

    def test_all_uppercase(self) -> None:
        self._assertNoMatch("SLUG")

    def test_camel_case(self) -> None:
        self._assertNoMatch("camelCase")

    def test_contains_underscore(self) -> None:
        self._assertNoMatch("bad_slug")

    def test_contains_space(self) -> None:
        self._assertNoMatch("bad slug")

    def test_empty_string(self) -> None:
        self._assertNoMatch("")

    def test_starts_with_hyphen(self) -> None:
        self._assertNoMatch("-bad")


# ---------------------------------------------------------------------------
# is_valid_slug()
# ---------------------------------------------------------------------------


class TestIsValidSlug(unittest.TestCase):
    """is_valid_slug must return True for valid slugs, False otherwise."""

    def test_valid_simple(self) -> None:
        self.assertTrue(topics.is_valid_slug("hello"))

    def test_valid_kebab(self) -> None:
        self.assertTrue(topics.is_valid_slug("my-topic"))

    def test_valid_with_digits(self) -> None:
        self.assertTrue(topics.is_valid_slug("decision-v2"))

    def test_valid_single_letter(self) -> None:
        self.assertTrue(topics.is_valid_slug("a"))

    def test_invalid_empty(self) -> None:
        self.assertFalse(topics.is_valid_slug(""))

    def test_invalid_uppercase(self) -> None:
        self.assertFalse(topics.is_valid_slug("MyTopic"))

    def test_invalid_starts_with_digit(self) -> None:
        self.assertFalse(topics.is_valid_slug("123topic"))

    def test_invalid_underscore(self) -> None:
        self.assertFalse(topics.is_valid_slug("bad_slug"))

    def test_invalid_space(self) -> None:
        self.assertFalse(topics.is_valid_slug("bad slug"))

    def test_invalid_starts_with_hyphen(self) -> None:
        self.assertFalse(topics.is_valid_slug("-bad"))

    def test_returns_bool_true(self) -> None:
        result = topics.is_valid_slug("valid")
        self.assertIsInstance(result, bool)

    def test_returns_bool_false(self) -> None:
        result = topics.is_valid_slug("INVALID")
        self.assertIsInstance(result, bool)


# ---------------------------------------------------------------------------
# VALID_KINDS and VALID_STATUSES
# ---------------------------------------------------------------------------


class TestValidKinds(unittest.TestCase):
    """VALID_KINDS must be a frozenset with exactly the specified values."""

    def test_is_frozenset(self) -> None:
        self.assertIsInstance(topics.VALID_KINDS, frozenset)

    def test_exact_members(self) -> None:
        expected = frozenset(
            {"mission", "architecture", "decision", "constraint", "workflow", "gotcha", "roadmap"}
        )
        self.assertEqual(topics.VALID_KINDS, expected)

    def test_contains_mission(self) -> None:
        self.assertIn("mission", topics.VALID_KINDS)

    def test_contains_architecture(self) -> None:
        self.assertIn("architecture", topics.VALID_KINDS)

    def test_contains_decision(self) -> None:
        self.assertIn("decision", topics.VALID_KINDS)

    def test_contains_constraint(self) -> None:
        self.assertIn("constraint", topics.VALID_KINDS)

    def test_contains_workflow(self) -> None:
        self.assertIn("workflow", topics.VALID_KINDS)

    def test_contains_gotcha(self) -> None:
        self.assertIn("gotcha", topics.VALID_KINDS)

    def test_contains_roadmap(self) -> None:
        self.assertIn("roadmap", topics.VALID_KINDS)

    def test_no_extra_members(self) -> None:
        self.assertEqual(len(topics.VALID_KINDS), 7)


class TestValidStatuses(unittest.TestCase):
    """VALID_STATUSES must be a frozenset with exactly the specified values."""

    def test_is_frozenset(self) -> None:
        self.assertIsInstance(topics.VALID_STATUSES, frozenset)

    def test_exact_members(self) -> None:
        expected = frozenset({"active", "superseded", "archived"})
        self.assertEqual(topics.VALID_STATUSES, expected)

    def test_contains_active(self) -> None:
        self.assertIn("active", topics.VALID_STATUSES)

    def test_contains_superseded(self) -> None:
        self.assertIn("superseded", topics.VALID_STATUSES)

    def test_contains_archived(self) -> None:
        self.assertIn("archived", topics.VALID_STATUSES)

    def test_no_extra_members(self) -> None:
        self.assertEqual(len(topics.VALID_STATUSES), 3)


# ---------------------------------------------------------------------------
# parse_frontmatter()
# ---------------------------------------------------------------------------


class TestParseFrontmatterNoHeader(unittest.TestCase):
    """Text without a frontmatter header must return ({}, original_text)."""

    def test_plain_text_no_header(self) -> None:
        text = "# Hello\n\nNo frontmatter here.\n"
        fm, body = topics.parse_frontmatter(text)
        self.assertEqual(fm, {})
        self.assertEqual(body, text)

    def test_empty_string(self) -> None:
        fm, body = topics.parse_frontmatter("")
        self.assertEqual(fm, {})
        self.assertEqual(body, "")

    def test_text_starting_with_dashes_but_not_frontmatter(self) -> None:
        # A line that is --- but not followed by a newline immediately starting
        # a valid frontmatter block. If only the opening marker is absent, treat
        # as no header.
        text = "Just some text.\n---\nNot frontmatter.\n"
        fm, body = topics.parse_frontmatter(text)
        # No opening ---\n → ({}, text)
        self.assertEqual(fm, {})
        self.assertEqual(body, text)

    def test_returns_tuple(self) -> None:
        result = topics.parse_frontmatter("plain text")
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)


class TestParseFrontmatterSimpleKeyValue(unittest.TestCase):
    """parse_frontmatter with simple key: value pairs."""

    def _make_doc(self, fm_lines: str, body: str = "body text\n") -> str:
        return f"---\n{fm_lines}---\n{body}"

    def test_single_key_value(self) -> None:
        text = self._make_doc("kind: decision\n")
        fm, body = topics.parse_frontmatter(text)
        self.assertEqual(fm.get("kind"), "decision")

    def test_multiple_key_value(self) -> None:
        text = self._make_doc("id: my-topic\nkind: gotcha\nstatus: active\n")
        fm, body = topics.parse_frontmatter(text)
        self.assertEqual(fm.get("id"), "my-topic")
        self.assertEqual(fm.get("kind"), "gotcha")
        self.assertEqual(fm.get("status"), "active")

    def test_body_extracted_correctly(self) -> None:
        body_text = "# My Topic\n\nSome content.\n"
        text = self._make_doc("id: slug\n", body_text)
        fm, body = topics.parse_frontmatter(text)
        self.assertEqual(body, body_text)

    def test_body_preserves_internal_dashes(self) -> None:
        """A --- line inside the body must not confuse the parser."""
        body_text = "line one\n---\nline after dashes\n"
        text = self._make_doc("id: slug\n", body_text)
        fm, body = topics.parse_frontmatter(text)
        self.assertIn("---", body)


class TestParseFrontmatterQuotedValues(unittest.TestCase):
    """Quoted string values must be unquoted (no surrounding quotes in result)."""

    def _make_doc(self, fm_lines: str, body: str = "") -> str:
        return f"---\n{fm_lines}---\n{body}"

    def test_double_quoted_value(self) -> None:
        text = self._make_doc('summary: "hello world"\n')
        fm, _ = topics.parse_frontmatter(text)
        self.assertEqual(fm.get("summary"), "hello world")

    def test_quoted_value_with_spaces(self) -> None:
        text = self._make_doc('summary: "CLAUDE.md is the gateway"\n')
        fm, _ = topics.parse_frontmatter(text)
        self.assertEqual(fm.get("summary"), "CLAUDE.md is the gateway")


class TestParseFrontmatterListValues(unittest.TestCase):
    """List values like key: [a, b] must be parsed into Python lists."""

    def _make_doc(self, fm_lines: str, body: str = "") -> str:
        return f"---\n{fm_lines}---\n{body}"

    def test_simple_list(self) -> None:
        text = self._make_doc("tags: [foo, bar]\n")
        fm, _ = topics.parse_frontmatter(text)
        self.assertEqual(fm.get("tags"), ["foo", "bar"])

    def test_list_with_whitespace_trimmed(self) -> None:
        text = self._make_doc("tags: [ foo , bar ]\n")
        fm, _ = topics.parse_frontmatter(text)
        result = fm.get("tags")
        self.assertIsInstance(result, list)
        self.assertEqual([v.strip() for v in result], ["foo", "bar"])

    def test_list_with_quoted_items(self) -> None:
        text = self._make_doc('tags: ["foo", "bar"]\n')
        fm, _ = topics.parse_frontmatter(text)
        result = fm.get("tags")
        self.assertIsInstance(result, list)
        # Quotes stripped from individual items
        self.assertEqual(len(result), 2)
        self.assertIn("foo", [v.strip('"').strip("'") for v in result])
        self.assertIn("bar", [v.strip('"').strip("'") for v in result])

    def test_empty_list(self) -> None:
        text = self._make_doc("supersedes: []\n")
        fm, _ = topics.parse_frontmatter(text)
        self.assertIsInstance(fm.get("supersedes"), list)
        self.assertEqual(len(fm.get("supersedes", [1])), 0)  # type: ignore[arg-type]


class TestParseFrontmatterNullAndEmpty(unittest.TestCase):
    """Null and empty values must be parsed as None."""

    def _make_doc(self, fm_lines: str, body: str = "") -> str:
        return f"---\n{fm_lines}---\n{body}"

    def test_explicit_null(self) -> None:
        text = self._make_doc("superseded_by: null\n")
        fm, _ = topics.parse_frontmatter(text)
        self.assertIsNone(fm.get("superseded_by"))

    def test_empty_value(self) -> None:
        text = self._make_doc("superseded_by:\n")
        fm, _ = topics.parse_frontmatter(text)
        self.assertIsNone(fm.get("superseded_by"))


class TestParseFrontmatterMalformed(unittest.TestCase):
    """Malformed frontmatter must return ({}, original_text) without raising."""

    def test_no_closing_marker(self) -> None:
        text = "---\nbroken\n"
        try:
            fm, body = topics.parse_frontmatter(text)
        except Exception as exc:  # noqa: BLE001
            self.fail(f"parse_frontmatter raised on malformed input: {exc}")
        self.assertEqual(fm, {})
        self.assertEqual(body, text)

    def test_malformed_does_not_raise(self) -> None:
        text = "---\nthis: is: bad: yaml\n---\n"
        try:
            topics.parse_frontmatter(text)
        except Exception as exc:  # noqa: BLE001
            self.fail(f"parse_frontmatter raised unexpectedly: {exc}")

    def test_malformed_returns_tuple(self) -> None:
        text = "---\nbroken\n"
        result = topics.parse_frontmatter(text)
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)


# ---------------------------------------------------------------------------
# Codex H3 — real-world editor input robustness
# ---------------------------------------------------------------------------


class TestParseFrontmatterRealWorldInput(unittest.TestCase):
    # Regressions for the cases Codex flagged in H3: real-world editors emit
    # UTF-8 BOMs, CRLF line endings, files without trailing newline, and
    # frontmatter with inline comments. None of these should silently degrade.

    def test_utf8_bom_at_start_is_stripped(self) -> None:
        text = "﻿---\nid: test\nkind: decision\n---\n# body"
        fm, body = topics.parse_frontmatter(text)
        self.assertEqual(fm.get("id"), "test")
        self.assertEqual(fm.get("kind"), "decision")
        self.assertIn("# body", body)

    def test_crlf_line_endings_parse(self) -> None:
        text = "---\r\nid: test\r\nkind: decision\r\n---\r\n# body\r\n"
        fm, body = topics.parse_frontmatter(text)
        self.assertEqual(fm.get("id"), "test")
        self.assertEqual(fm.get("kind"), "decision")
        self.assertIn("# body", body)

    def test_closing_dashes_at_eof_without_trailing_newline(self) -> None:
        text = "---\nid: test\nkind: decision\n---"
        fm, body = topics.parse_frontmatter(text)
        self.assertEqual(fm.get("id"), "test")
        self.assertEqual(fm.get("kind"), "decision")
        self.assertEqual(body, "")

    def test_inline_comment_after_value_is_stripped(self) -> None:
        # PRD §5.4 example: status: active # the LightMem default
        text = "---\nid: test\nstatus: active # the LightMem default\n---\n"
        fm, _ = topics.parse_frontmatter(text)
        self.assertEqual(fm.get("status"), "active")

    def test_inline_comment_with_quoted_value_left_alone(self) -> None:
        text = '---\nsummary: "Use # in markdown"\n---\n'
        fm, _ = topics.parse_frontmatter(text)
        self.assertEqual(fm.get("summary"), "Use # in markdown")

    def test_combined_bom_and_crlf_and_inline_comment(self) -> None:
        text = "﻿---\r\nid: test\r\nstatus: active # comment\r\n---\r\n# body\r\n"
        fm, body = topics.parse_frontmatter(text)
        self.assertEqual(fm.get("id"), "test")
        self.assertEqual(fm.get("status"), "active")
        self.assertIn("# body", body)


# ---------------------------------------------------------------------------
# Topic dataclass
# ---------------------------------------------------------------------------


class TestTopicDataclass(unittest.TestCase):
    """Topic must be a frozen dataclass with the specified fields."""

    def _make_topic(self) -> topics.Topic:  # type: ignore[name-defined]
        return topics.Topic(
            id="my-topic",
            kind="decision",
            path=Path("/fake/path.md"),
            frontmatter={"id": "my-topic", "kind": "decision"},
            body="Some body text.",
        )

    def test_topic_has_id(self) -> None:
        t = self._make_topic()
        self.assertEqual(t.id, "my-topic")

    def test_topic_has_kind(self) -> None:
        t = self._make_topic()
        self.assertEqual(t.kind, "decision")

    def test_topic_has_path(self) -> None:
        t = self._make_topic()
        self.assertEqual(t.path, Path("/fake/path.md"))

    def test_topic_has_frontmatter(self) -> None:
        t = self._make_topic()
        self.assertIsInstance(t.frontmatter, dict)

    def test_topic_has_body(self) -> None:
        t = self._make_topic()
        self.assertEqual(t.body, "Some body text.")

    def test_topic_is_frozen(self) -> None:
        """Frozen dataclass must raise on attribute assignment."""
        t = self._make_topic()
        with self.assertRaises((AttributeError, TypeError)):
            t.id = "new-id"  # type: ignore[misc]

    def test_topic_kind_immutable(self) -> None:
        t = self._make_topic()
        with self.assertRaises((AttributeError, TypeError)):
            t.kind = "workflow"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# walk_topics()
# ---------------------------------------------------------------------------


class TestWalkTopicsEdgeCases(unittest.TestCase):
    """walk_topics on missing or empty dirs must return []."""

    def test_nonexistent_dir_returns_empty(self) -> None:
        result = topics.walk_topics(Path("/nonexistent/directory/that/does/not/exist"))
        self.assertEqual(result, [])

    def test_empty_dir_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = topics.walk_topics(Path(tmpdir))
            self.assertEqual(result, [])

    def test_dir_with_no_md_files_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "not-markdown.txt").write_text("hello", encoding="utf-8")
            result = topics.walk_topics(Path(tmpdir))
            self.assertEqual(result, [])


class TestWalkTopicsSingleFile(unittest.TestCase):
    """walk_topics with one .md file must return a list of length 1."""

    def test_single_md_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            md = Path(tmpdir) / "my-topic.md"
            md.write_text("---\nid: my-topic\nkind: decision\n---\nBody.\n", encoding="utf-8")
            result = topics.walk_topics(Path(tmpdir))
            self.assertEqual(len(result), 1)

    def test_single_file_correct_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            md = Path(tmpdir) / "my-topic.md"
            md.write_text("---\nid: my-topic\nkind: decision\n---\nBody.\n", encoding="utf-8")
            result = topics.walk_topics(Path(tmpdir))
            self.assertEqual(result[0].id, "my-topic")

    def test_single_file_correct_kind(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            md = Path(tmpdir) / "my-topic.md"
            md.write_text("---\nid: my-topic\nkind: gotcha\n---\nBody.\n", encoding="utf-8")
            result = topics.walk_topics(Path(tmpdir))
            self.assertEqual(result[0].kind, "gotcha")

    def test_single_file_path_is_absolute_or_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            md = Path(tmpdir) / "my-topic.md"
            md.write_text("---\nid: my-topic\nkind: decision\n---\nBody.\n", encoding="utf-8")
            result = topics.walk_topics(Path(tmpdir))
            self.assertEqual(result[0].path, md)


class TestWalkTopicsIdFallback(unittest.TestCase):
    """If frontmatter has no 'id', Topic.id must fall back to the file stem."""

    def test_id_falls_back_to_stem(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            md = Path(tmpdir) / "my-stem.md"
            md.write_text("# No frontmatter\n", encoding="utf-8")
            result = topics.walk_topics(Path(tmpdir))
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0].id, "my-stem")

    def test_kind_falls_back_to_empty_string(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            md = Path(tmpdir) / "no-kind.md"
            md.write_text("# Just a heading\n", encoding="utf-8")
            result = topics.walk_topics(Path(tmpdir))
            self.assertEqual(result[0].kind, "")

    def test_id_from_frontmatter_overrides_stem(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            md = Path(tmpdir) / "filename-stem.md"
            md.write_text(
                "---\nid: frontmatter-id\nkind: decision\n---\nBody.\n",
                encoding="utf-8",
            )
            result = topics.walk_topics(Path(tmpdir))
            self.assertEqual(result[0].id, "frontmatter-id")


class TestWalkTopicsRecursive(unittest.TestCase):
    """walk_topics must discover .md files in subdirectories recursively."""

    def test_finds_files_in_subdir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            subdir = root / "decisions"
            subdir.mkdir()
            (subdir / "my-decision.md").write_text(
                "---\nid: my-decision\nkind: decision\n---\nBody.\n", encoding="utf-8"
            )
            result = topics.walk_topics(root)
            self.assertEqual(len(result), 1)

    def test_finds_files_across_multiple_subdirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "decisions").mkdir()
            (root / "gotchas").mkdir()
            (root / "decisions" / "dec-1.md").write_text(
                "---\nid: dec-1\nkind: decision\n---\n", encoding="utf-8"
            )
            (root / "gotchas" / "gotcha-1.md").write_text(
                "---\nid: gotcha-1\nkind: gotcha\n---\n", encoding="utf-8"
            )
            (root / "mission.md").write_text(
                "---\nid: mission\nkind: mission\n---\n", encoding="utf-8"
            )
            result = topics.walk_topics(root)
            self.assertEqual(len(result), 3)

    def test_finds_nested_deep_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            deep = root / "a" / "b" / "c"
            deep.mkdir(parents=True)
            (deep / "deep-topic.md").write_text(
                "---\nid: deep-topic\nkind: decision\n---\n", encoding="utf-8"
            )
            result = topics.walk_topics(root)
            self.assertEqual(len(result), 1)


class TestWalkTopicsSorted(unittest.TestCase):
    """walk_topics must return topics sorted by (kind, id)."""

    def test_sorted_by_kind_then_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "decisions").mkdir()
            (root / "gotchas").mkdir()

            # Create topics in mixed order
            (root / "decisions" / "b-decision.md").write_text(
                "---\nid: b-decision\nkind: decision\n---\n", encoding="utf-8"
            )
            (root / "gotchas" / "a-gotcha.md").write_text(
                "---\nid: a-gotcha\nkind: gotcha\n---\n", encoding="utf-8"
            )
            (root / "decisions" / "a-decision.md").write_text(
                "---\nid: a-decision\nkind: decision\n---\n", encoding="utf-8"
            )

            result = topics.walk_topics(root)
            self.assertEqual(len(result), 3)

            # Sort key is (kind, id)
            # decision < gotcha alphabetically
            self.assertEqual(result[0].kind, "decision")
            self.assertEqual(result[0].id, "a-decision")
            self.assertEqual(result[1].kind, "decision")
            self.assertEqual(result[1].id, "b-decision")
            self.assertEqual(result[2].kind, "gotcha")
            self.assertEqual(result[2].id, "a-gotcha")

    def test_same_kind_sorted_by_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            for name in ["c-topic", "a-topic", "b-topic"]:
                (root / f"{name}.md").write_text(
                    f"---\nid: {name}\nkind: workflow\n---\n", encoding="utf-8"
                )
            result = topics.walk_topics(root)
            ids = [t.id for t in result]
            self.assertEqual(ids, sorted(ids))

    def test_returns_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = topics.walk_topics(Path(tmpdir))
            self.assertIsInstance(result, list)


if __name__ == "__main__":
    unittest.main()
