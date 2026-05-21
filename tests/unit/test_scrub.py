from __future__ import annotations

"""
Tests for scripts/lib/scrub.py

Derived purely from PRD_v0.2.md §10.3 (secret-scrub regex).  No implementation
files were read during authoring.

PRD §10.3 specifies the following compiled regex (ported verbatim from ECC):

    SECRET_REGEX = re.compile(
        r"(?i)(api[_-]?key|token|secret|password|authorization|credentials?|auth)"
        r"([:=\\s\"']+)"
        r"([A-Za-z]+\\s+)?"
        r"([A-Za-z0-9_\\-/.+=]{8,})"
    )
    REDACT_REPLACEMENT = r"\\1\\2\\3[REDACTED]"

Group 1: keyword
Group 2: separator (one or more of :=\\s"')
Group 3: optional auth-scheme word + whitespace (e.g. "Bearer ")
Group 4: secret value, ≥8 chars from [A-Za-z0-9_\\-/.+=]

Replacement preserves groups 1-3 and replaces group 4 with [REDACTED].
"""

import re
import sys
import unittest

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_LIB = _REPO_ROOT / "scripts" / "lib"
if str(_SCRIPTS_LIB) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_LIB))

import scrub  # type: ignore[import]  # noqa: E402 – imported after path fix


class TestScrubModuleAttributes(unittest.TestCase):
    """scrub module must export the expected attributes."""

    def test_secret_regex_is_compiled_pattern(self) -> None:
        self.assertIsInstance(scrub.SECRET_REGEX, re.Pattern)

    def test_redact_replacement_is_str(self) -> None:
        self.assertIsInstance(scrub.REDACT_REPLACEMENT, str)

    def test_redact_replacement_references_redacted(self) -> None:
        # The replacement template must produce [REDACTED] for the secret value
        self.assertIn("[REDACTED]", scrub.REDACT_REPLACEMENT)

    def test_scrub_is_callable(self) -> None:
        self.assertTrue(callable(scrub.scrub))


class TestScrubPassThrough(unittest.TestCase):
    """Strings without secrets must pass through unchanged."""

    def test_empty_string(self) -> None:
        self.assertEqual(scrub.scrub(""), "")

    def test_plain_text_no_secrets(self) -> None:
        text = "The quick brown fox jumps over the lazy dog."
        self.assertEqual(scrub.scrub(text), text)

    def test_code_snippet_no_secrets(self) -> None:
        text = "def hello():\n    return 'world'\n"
        self.assertEqual(scrub.scrub(text), text)

    def test_json_no_secrets(self) -> None:
        text = '{"name": "John", "age": 30}'
        self.assertEqual(scrub.scrub(text), text)


class TestScrubKeywordVariants(unittest.TestCase):
    """
    PRD §10.3: keywords are api_key|api-key|apikey|token|secret|password|
    authorization|credentials|credential|auth.

    Each variant below must trigger redaction when followed by an appropriate
    separator and a value of ≥8 characters.
    """

    def _assert_redacted(self, text: str) -> None:
        result = scrub.scrub(text)
        self.assertIn("[REDACTED]", result, msg=f"Expected redaction in: {result!r}")

    def _assert_secret_absent(self, text: str, secret: str) -> None:
        result = scrub.scrub(text)
        self.assertNotIn(secret, result, msg=f"Secret still visible in: {result!r}")

    # --- api_key variants ---

    def test_api_key_colon_quoted(self) -> None:
        text = 'api_key: "abcdefgh12345678"'
        self._assert_redacted(text)
        self._assert_secret_absent(text, "abcdefgh12345678")

    def test_api_key_equals_no_quotes(self) -> None:
        # Basic form: api_key=abc12345xyz
        text = "api_key=abc12345xyz"
        self._assert_redacted(text)
        self._assert_secret_absent(text, "abc12345xyz")

    def test_api_dash_key_uppercase(self) -> None:
        # API-KEY=... (hyphen variant, case-insensitive)
        text = "API-KEY=zzzzzzzzzz12345678"
        self._assert_redacted(text)
        self._assert_secret_absent(text, "zzzzzzzzzz12345678")

    def test_apikey_no_separator_char(self) -> None:
        # "apikey" (no underscore or hyphen) must also be recognised
        text = "apikey=ABCDEFGHIJKLMN"
        self._assert_redacted(text)
        self._assert_secret_absent(text, "ABCDEFGHIJKLMN")

    # --- token ---

    def test_token_with_bearer_scheme(self) -> None:
        # Group 3 (optional auth scheme) captures "Bearer "
        text = 'token = "Bearer abc12345xyz"'
        self._assert_redacted(text)
        self._assert_secret_absent(text, "abc12345xyz")

    def test_token_without_scheme(self) -> None:
        text = "token=mytoken1234567890"
        self._assert_redacted(text)
        self._assert_secret_absent(text, "mytoken1234567890")

    # --- secret ---

    def test_secret_colon(self) -> None:
        text = "secret: supersecretvalue123"
        self._assert_redacted(text)
        self._assert_secret_absent(text, "supersecretvalue123")

    # --- password ---

    def test_password_colon(self) -> None:
        text = "password: superSecret12345"
        self._assert_redacted(text)
        self._assert_secret_absent(text, "superSecret12345")

    # --- authorization ---

    def test_authorization_bearer(self) -> None:
        text = 'Authorization: "Bearer xyz1234567890"'
        self._assert_redacted(text)
        self._assert_secret_absent(text, "xyz1234567890")

    # --- credentials / credential ---

    def test_credentials_equals_quoted(self) -> None:
        text = 'credentials="mycredvalue123"'
        self._assert_redacted(text)
        self._assert_secret_absent(text, "mycredvalue123")

    def test_credential_singular(self) -> None:
        # credentials? covers both "credential" and "credentials"
        text = "credential=secretvalue99"
        self._assert_redacted(text)
        self._assert_secret_absent(text, "secretvalue99")

    # --- auth ---

    def test_auth_equals(self) -> None:
        text = "auth=verysecret1234"
        self._assert_redacted(text)
        self._assert_secret_absent(text, "verysecret1234")


class TestScrubMustNotTrigger(unittest.TestCase):
    """
    Strings that must NOT trigger redaction, per PRD §10.3 constraints:
    - Value < 8 characters → no match (group 4 requires ≥8 chars)
    - Keyword present but no valid separator immediately following
    - Unrelated keyword
    """

    def test_api_key_value_too_short(self) -> None:
        # "short" is 5 chars, less than the required 8
        text = "api_key=short"
        result = scrub.scrub(text)
        self.assertNotIn("[REDACTED]", result)

    def test_api_key_seven_chars_no_redact(self) -> None:
        # 7 chars — one under the threshold
        text = "api_key=abcdefg"
        result = scrub.scrub(text)
        self.assertNotIn("[REDACTED]", result)

    def test_apikey_no_separator_after_keyword(self) -> None:
        # "the apikey is fine" — the value after the separator is < 8 chars
        # "apikey" matches keyword; " " matches separator; "is fine" splits at space
        # so the contiguous value segment is too short.
        text = "the apikey is fine"
        result = scrub.scrub(text)
        self.assertNotIn("[REDACTED]", result)

    def test_unrelated_keyword_name(self) -> None:
        # "name" is not in the keyword list
        text = 'name = "John"'
        result = scrub.scrub(text)
        self.assertNotIn("[REDACTED]", result)

    def test_plain_sentence_no_match(self) -> None:
        text = "The authorization was granted by the committee."
        result = scrub.scrub(text)
        # "authorization" IS a keyword but has no separator or value after it
        self.assertNotIn("[REDACTED]", result)


class TestScrubMultipleSecrets(unittest.TestCase):
    """All secrets in a single string must be redacted in one scrub() call.

    IMPORTANT REGEX QUIRK (spec-derived, PRD §10.3):
    The optional auth-scheme group is ([A-Za-z]+\\s+)? — it matches a word of
    purely alphabetic characters followed by whitespace.  If the FIRST secret
    value in a string is purely alphabetic and is immediately followed by a
    space and another keyword (e.g. "api_key=abcdefghijkl token=..."), the
    regex engine can consume the first value as the auth-scheme and the
    subsequent keyword-plus-value as the secret, producing only ONE match for
    the whole span.

    To guarantee two independent matches, secret values must contain at least
    one non-alphabetic character (digit, underscore, etc.) so the optional
    scheme group cannot consume them.  All multi-secret tests below use values
    that contain at least one digit.
    """

    def test_two_secrets_both_redacted(self) -> None:
        # Values contain digits → group 3 ([A-Za-z]+\s+) cannot consume them
        text = "api_key=abc123456789 token=xyz987654321"
        result = scrub.scrub(text)
        self.assertNotIn("abc123456789", result)
        self.assertNotIn("xyz987654321", result)
        # [REDACTED] must appear at least twice
        self.assertGreaterEqual(result.count("[REDACTED]"), 2)

    def test_secret_and_password_both_redacted(self) -> None:
        text = "secret=myfirstsecret1234 password=mysecondpass5678"
        result = scrub.scrub(text)
        self.assertNotIn("myfirstsecret1234", result)
        self.assertNotIn("mysecondpass5678", result)


class TestScrubIdempotency(unittest.TestCase):
    """
    Scrubbing already-scrubbed text must not further modify the output.

    The replacement string [REDACTED] begins with '[', which is not in the
    value character class [A-Za-z0-9_\\-/.+=], so the secret regex cannot
    match [REDACTED] as a secret value on a second pass — assuming the secret
    that was redacted is not left visible by the optional auth-scheme group.

    REGEX QUIRK NOTE (PRD §10.3):
    If a purely-alphabetic secret value is consumed by the optional auth-scheme
    group ([A-Za-z]+\\s+) on the first pass, it is left un-redacted in the
    output.  A second pass can then redact it, making the function non-idempotent
    for those inputs.  Tests here use values containing at least one digit to
    avoid this edge case (digits break the [A-Za-z]+ match in group 3).

    The count of [REDACTED] substrings must be the same after the second call.
    """

    def test_idempotent_single_secret(self) -> None:
        # Single secret with alphanumeric value (digit present → stable match)
        original = "api_key=abc123456789"
        first_pass = scrub.scrub(original)
        second_pass = scrub.scrub(first_pass)
        # The number of [REDACTED] occurrences must not increase on second pass
        self.assertEqual(first_pass.count("[REDACTED]"), second_pass.count("[REDACTED]"))
        self.assertEqual(first_pass, second_pass)

    def test_idempotent_multiple_secrets(self) -> None:
        # Both values contain digits → each is matched independently; no
        # bleed between matches via the auth-scheme group.
        original = "token=aaa1bbcccdddeee password=fff111222333"
        first_pass = scrub.scrub(original)
        second_pass = scrub.scrub(first_pass)
        self.assertEqual(first_pass.count("[REDACTED]"), second_pass.count("[REDACTED]"))
        self.assertEqual(first_pass, second_pass)

    def test_clean_string_idempotent(self) -> None:
        clean = "no secrets here"
        self.assertEqual(scrub.scrub(clean), scrub.scrub(scrub.scrub(clean)))


class TestScrubOutputStructure(unittest.TestCase):
    """The replacement must preserve keyword, separator, and optional scheme."""

    def test_keyword_preserved_in_output(self) -> None:
        text = "api_key=abcdefghijkl"
        result = scrub.scrub(text)
        # Keyword (group 1) must still appear
        self.assertIn("api_key", result)

    def test_separator_preserved_in_output(self) -> None:
        text = "api_key=abcdefghijkl"
        result = scrub.scrub(text)
        # Separator (group 2) must still appear
        self.assertIn("=", result)

    def test_bearer_scheme_preserved_in_output(self) -> None:
        text = 'token = "Bearer abc12345xyz"'
        result = scrub.scrub(text)
        # Group 3 (auth scheme) must be preserved in the replacement
        self.assertIn("Bearer", result)

    def test_redacted_marker_replaces_value(self) -> None:
        text = "password=supersecretpass"
        result = scrub.scrub(text)
        self.assertIn("[REDACTED]", result)
        self.assertNotIn("supersecretpass", result)


if __name__ == "__main__":
    unittest.main()
