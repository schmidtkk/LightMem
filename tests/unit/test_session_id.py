from __future__ import annotations

"""
Tests for scripts/lib/session_id.py

Derived purely from PRD_v0.2.md §11 (ECC attribution) and ROADMAP §3 ECC ports,
plus the derive_short_id API description.  No implementation files were read
during authoring.

Expected behaviour (spec-derived):
  - derive_short_id(transcript_path: str | None) -> str | None
  - Extracts a standard UUID (8-4-4-4-12 hex, case-insensitive) from the
    BASENAME of transcript_path (not from parent directory components).
  - Returns the last 8 characters of the UUID, lowercased.
  - Returns None when:
      * input is None
      * input is empty string
      * basename contains no valid UUID
      * filename does not end with .jsonl (case of extension: see spec-gap note)

UUID format reminder:  xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
                       ^8 hex^  ^4^  ^4^  ^4^  ^---12 hex---^
Last 8 chars of UUID  = last 8 chars of the final 12-hex group.

ECC docs example (PRD §6.2.1 journal schema):
  00893aaf-19fa-41d2-8238-13269b9b3ca0  →  9b9b3ca0
"""

import sys
import unittest

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_LIB = _REPO_ROOT / "scripts" / "lib"
if str(_SCRIPTS_LIB) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_LIB))

import session_id  # type: ignore[import]  # noqa: E402 – imported after path fix


class TestDeriveShortIdNoneAndEmpty(unittest.TestCase):
    """derive_short_id must return None for sentinel / degenerate inputs."""

    def test_none_input(self) -> None:
        self.assertIsNone(session_id.derive_short_id(None))

    def test_empty_string_input(self) -> None:
        self.assertIsNone(session_id.derive_short_id(""))


class TestDeriveShortIdNoUUID(unittest.TestCase):
    """Paths whose basename contains no valid UUID must return None."""

    def test_no_uuid_in_filename(self) -> None:
        self.assertIsNone(session_id.derive_short_id("/foo/no-uuid-here.jsonl"))

    def test_partial_uuid_only(self) -> None:
        # Only 8 hex chars — not a full UUID
        self.assertIsNone(session_id.derive_short_id("/foo/abc12345.jsonl"))

    def test_random_hex_no_dashes(self) -> None:
        # 32 hex chars without dashes is NOT the canonical UUID format
        self.assertIsNone(
            session_id.derive_short_id("/foo/abc123451111222233334444555566.jsonl")
        )

    def test_plain_name_no_uuid(self) -> None:
        self.assertIsNone(session_id.derive_short_id("/foo/session.jsonl"))


class TestDeriveShortIdWrongExtension(unittest.TestCase):
    """Only .jsonl files are valid; other extensions must return None."""

    def test_json_extension_rejected(self) -> None:
        # .json is NOT .jsonl
        result = session_id.derive_short_id(
            "/abc12345-1111-2222-3333-444455556666.json"
        )
        self.assertIsNone(result)

    def test_txt_extension_rejected(self) -> None:
        result = session_id.derive_short_id(
            "/foo/abc12345-1111-2222-3333-444455556666.txt"
        )
        self.assertIsNone(result)

    def test_no_extension_rejected(self) -> None:
        result = session_id.derive_short_id(
            "/foo/abc12345-1111-2222-3333-444455556666"
        )
        self.assertIsNone(result)


class TestDeriveShortIdExtensionCaseGap(unittest.TestCase):
    """
    SPEC GAP: PRD §11 specifies the UUID matching is case-insensitive, but is
    silent on whether the .jsonl extension match is also case-insensitive.

    The most natural interpretation of "filename doesn't end .jsonl" is a
    case-insensitive check (consistent with how UUIDs are handled).  This test
    asserts that interpretation, but the result is documented as provisional
    until the spec is clarified.

    If the implementor makes a different choice (case-sensitive extension), this
    test should be updated to reflect the actual behaviour with a comment
    explaining the divergence.
    """

    def test_jsonl_uppercase_extension(self) -> None:
        # Spec gap: .JSONL extension case — we assert case-insensitive (accept)
        # as the most consistent interpretation with the UUID case handling.
        result = session_id.derive_short_id(
            "/abc12345-1111-2222-3333-444455556666.JSONL"
        )
        # Expected: treats .JSONL same as .jsonl → returns "55556666"
        # If the impl treats extension as case-sensitive, this will return None.
        # Update this assertion and the comment above to match confirmed behaviour.
        self.assertEqual(result, "55556666")


class TestDeriveShortIdHappyPath(unittest.TestCase):
    """Core extraction: returns last 8 chars of the UUID, lowercased."""

    def test_standard_lowercase_uuid(self) -> None:
        # UUID: abc12345-1111-2222-3333-444455556666
        # Last group: 444455556666 (12 chars)
        # Last 8 chars: 55556666
        result = session_id.derive_short_id(
            "/foo/abc12345-1111-2222-3333-444455556666.jsonl"
        )
        self.assertEqual(result, "55556666")

    def test_uppercase_uuid_lowercased_output(self) -> None:
        # Case-insensitive UUID match; output must always be lowercase
        result = session_id.derive_short_id(
            "ABC12345-1111-2222-3333-444455556666.jsonl"
        )
        self.assertEqual(result, "55556666")

    def test_ecc_docs_example(self) -> None:
        # Example taken from PRD §6.2.1 journal schema
        # UUID: 00893aaf-19fa-41d2-8238-13269b9b3ca0
        # Last group: 13269b9b3ca0 (12 chars)
        # Last 8 chars: 9b9b3ca0
        result = session_id.derive_short_id(
            "/path/with/dir/00893aaf-19fa-41d2-8238-13269b9b3ca0.jsonl"
        )
        self.assertEqual(result, "9b9b3ca0")

    def test_no_leading_slash(self) -> None:
        # Relative-style path with no leading slash must still work
        result = session_id.derive_short_id(
            "abc12345-1111-2222-3333-444455556666.jsonl"
        )
        self.assertEqual(result, "55556666")

    def test_deep_path(self) -> None:
        result = session_id.derive_short_id(
            "/very/deep/nested/path/abc12345-1111-2222-3333-444455556666.jsonl"
        )
        self.assertEqual(result, "55556666")

    def test_codex_rollout_filename_prefix(self) -> None:
        result = session_id.derive_short_id(
            "/home/user/.codex/sessions/2026/03/13/"
            "rollout-2026-03-13T12-15-19-019ce567-ecc8-7613-a0f8-f8b0db87d1f6.jsonl"
        )
        self.assertEqual(result, "db87d1f6")


class TestDeriveShortIdOnlyBasenameCounts(unittest.TestCase):
    """
    UUIDs in parent directory components must be ignored; only the filename
    basename is examined (PRD §11 / session_id API description).
    """

    def test_uuid_in_parent_dir_ignored(self) -> None:
        # Parent dir has one UUID, filename has a different UUID
        result = session_id.derive_short_id(
            "/aaaaaaaa-1111-2222-3333-444444444444"
            "/bbbbbbbb-1111-2222-3333-555555555555.jsonl"
        )
        # Must return tail of the FILENAME UUID, not the parent dir UUID
        self.assertEqual(result, "55555555")

    def test_uuid_only_in_parent_dir(self) -> None:
        # Parent has UUID but filename does not → None
        result = session_id.derive_short_id(
            "/aaaaaaaa-1111-2222-3333-444444444444/session.jsonl"
        )
        self.assertIsNone(result)


class TestDeriveShortIdOutputShape(unittest.TestCase):
    """Output must always be exactly 8 lowercase hex characters when not None."""

    _VALID_PATHS = [
        "/foo/00893aaf-19fa-41d2-8238-13269b9b3ca0.jsonl",
        "/foo/abc12345-1111-2222-3333-444455556666.jsonl",
        "/foo/FFFFFFFF-FFFF-FFFF-FFFF-FFFFFFFFFFFF.jsonl",
        "/foo/00000000-0000-0000-0000-000000000000.jsonl",
    ]

    def test_output_is_exactly_8_chars(self) -> None:
        for path in self._VALID_PATHS:
            with self.subTest(path=path):
                result = session_id.derive_short_id(path)
                self.assertIsNotNone(result)
                self.assertEqual(len(result), 8, msg=f"Got {result!r} for {path}")  # type: ignore[arg-type]

    def test_output_is_lowercase_hex(self) -> None:
        import re

        hex_pattern = re.compile(r"^[0-9a-f]{8}$")
        for path in self._VALID_PATHS:
            with self.subTest(path=path):
                result = session_id.derive_short_id(path)
                self.assertIsNotNone(result)
                self.assertRegex(result, hex_pattern, msg=f"Got {result!r} for {path}")  # type: ignore[arg-type]

    def test_all_zeros_uuid(self) -> None:
        result = session_id.derive_short_id(
            "/foo/00000000-0000-0000-0000-000000000000.jsonl"
        )
        self.assertEqual(result, "00000000")

    def test_all_fs_uuid(self) -> None:
        result = session_id.derive_short_id(
            "/foo/ffffffff-ffff-ffff-ffff-ffffffffffff.jsonl"
        )
        self.assertEqual(result, "ffffffff")

    def test_uppercase_all_fs_uuid_lowercased(self) -> None:
        result = session_id.derive_short_id(
            "/foo/FFFFFFFF-FFFF-FFFF-FFFF-FFFFFFFFFFFF.jsonl"
        )
        self.assertEqual(result, "ffffffff")


if __name__ == "__main__":
    unittest.main()
