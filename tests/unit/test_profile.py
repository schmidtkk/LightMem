from __future__ import annotations

"""
Tests for scripts/lib/profile.py

Derived purely from PRD_v0.2.md §10 (environment variables) and §10.1
(LIGHTMEM_HOOK_PROFILE semantics).  No implementation files were read during
authoring.

Expected API (spec-derived):
  - disabled(hook_event: str) -> bool
      * Returns True iff the given hook should short-circuit and exit early.
      * Reads LIGHTMEM_HOOK_PROFILE (default "standard"); whitespace-trimmed
        and lowercased before comparison.
          "standard" → no profile-based disabling.
          "minimal"  → every event except SessionStart is disabled.
          "off"      → every event is disabled.
          <unknown>  → treated as "standard" (operator warning to stderr OK).
      * Reads LIGHTMEM_DISABLED_HOOKS (default ""); comma-separated event names,
        whitespace-trimmed, case-insensitive.  If hook_event matches any entry,
        return True regardless of profile.
      * hook_event matching is case-insensitive throughout.

PRD §10 canonical event names tested: SessionStart, Stop, SessionEnd,
PreCompact, PostCompact, UserPromptSubmit, PreToolUse, PostToolUse.

Environment isolation strategy: unittest.mock.patch.dict(os.environ, {}, clear=True)
is used per test to prevent env-var leakage between tests.

SPEC AMBIGUITIES FOUND (documented here for implementor/reviewer):
  SA1. PRD §10.1 says "minimal: SessionStart still injects suggestion; everything
       else exits 0 immediately." — "everything else" is taken to mean every
       event name other than SessionStart (case-insensitive).  The tests verify
       Stop, SessionEnd, PreCompact, PostCompact, UserPromptSubmit, PreToolUse,
       PostToolUse are all disabled under minimal.
  SA2. LIGHTMEM_DISABLED_HOOKS matching is specified as case-insensitive but the
       spec does not address underscore vs camelCase variants (e.g., "stop" vs
       "Stop" are the same; "session_start" vs "SessionStart" is not explicitly
       addressed).  Tests use canonical camelCase names.
  SA3. LIGHTMEM_DISABLED_HOOKS only ADDS to profile restrictions — it never
       overrides them in the permissive direction.  For example, setting
       LIGHTMEM_DISABLED_HOOKS=SessionStart under LIGHTMEM_HOOK_PROFILE=standard
       disables SessionStart; but setting LIGHTMEM_DISABLED_HOOKS=Stop under
       LIGHTMEM_HOOK_PROFILE=off does not un-disable any other event.
  SA4. PRD says disabled() reads env vars; it does not specify whether env vars
       are read once at import time (module-level) or on every call.  Tests
       use per-call patching, which works for both approaches.
"""

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

import profile as lightmem_profile  # type: ignore[import]  # noqa: E402 – after path fix


# ---------------------------------------------------------------------------
# Canonical event names from PRD §10 / §6
# ---------------------------------------------------------------------------

_ALL_CANONICAL_EVENTS = [
    "SessionStart",
    "Stop",
    "SessionEnd",
    "PreCompact",
    "PostCompact",
    "UserPromptSubmit",
    "PreToolUse",
    "PostToolUse",
]

_MINIMAL_ALLOWED = ["SessionStart"]           # only allowed event in minimal profile
_MINIMAL_DISABLED = [                         # all events disabled in minimal profile
    "Stop",
    "SessionEnd",
    "PreCompact",
    "PostCompact",
    "UserPromptSubmit",
    "PreToolUse",
    "PostToolUse",
]


# ===========================================================================
# 1. Function exists and is callable
# ===========================================================================

class TestDisabledFunctionExists(unittest.TestCase):
    """The module must export a callable named 'disabled'."""

    def test_disabled_is_callable(self) -> None:
        self.assertTrue(callable(lightmem_profile.disabled))

    def test_disabled_returns_bool(self) -> None:
        with unittest.mock.patch.dict(os.environ, {}, clear=True):
            result = lightmem_profile.disabled("SessionStart")
        self.assertIsInstance(result, bool)


# ===========================================================================
# 2. Default profile (no env vars set) — "standard" behaviour
# ===========================================================================

class TestDefaultProfile(unittest.TestCase):
    """
    PRD §10, D11: default LIGHTMEM_HOOK_PROFILE is "standard".
    With no env vars set, no events should be disabled.
    """

    def _disabled(self, event: str) -> bool:
        with unittest.mock.patch.dict(os.environ, {}, clear=True):
            return lightmem_profile.disabled(event)

    def test_session_start_not_disabled_by_default(self) -> None:
        self.assertFalse(self._disabled("SessionStart"))

    def test_stop_not_disabled_by_default(self) -> None:
        self.assertFalse(self._disabled("Stop"))

    def test_session_end_not_disabled_by_default(self) -> None:
        self.assertFalse(self._disabled("SessionEnd"))

    def test_pre_compact_not_disabled_by_default(self) -> None:
        self.assertFalse(self._disabled("PreCompact"))

    def test_post_compact_not_disabled_by_default(self) -> None:
        self.assertFalse(self._disabled("PostCompact"))

    def test_user_prompt_submit_not_disabled_by_default(self) -> None:
        self.assertFalse(self._disabled("UserPromptSubmit"))

    def test_pre_tool_use_not_disabled_by_default(self) -> None:
        self.assertFalse(self._disabled("PreToolUse"))

    def test_post_tool_use_not_disabled_by_default(self) -> None:
        self.assertFalse(self._disabled("PostToolUse"))

    def test_all_canonical_events_not_disabled_by_default(self) -> None:
        for event in _ALL_CANONICAL_EVENTS:
            with self.subTest(event=event):
                self.assertFalse(self._disabled(event))


# ===========================================================================
# 3. LIGHTMEM_HOOK_PROFILE=standard (explicit)
# ===========================================================================

class TestProfileStandard(unittest.TestCase):
    """
    PRD §10.1: "standard" — all hooks run their full path.
    No events should be disabled by profile alone.
    """

    def _disabled(self, event: str) -> bool:
        with unittest.mock.patch.dict(
            os.environ,
            {"LIGHTMEM_HOOK_PROFILE": "standard"},
            clear=True,
        ):
            return lightmem_profile.disabled(event)

    def test_all_canonical_events_not_disabled_under_standard(self) -> None:
        for event in _ALL_CANONICAL_EVENTS:
            with self.subTest(event=event):
                self.assertFalse(self._disabled(event))


# ===========================================================================
# 4. LIGHTMEM_HOOK_PROFILE=off — every event disabled
# ===========================================================================

class TestProfileOff(unittest.TestCase):
    """
    PRD §10.1: "off" — every hook exits 0 before any work.
    All canonical events must be disabled.
    """

    def _disabled(self, event: str) -> bool:
        with unittest.mock.patch.dict(
            os.environ,
            {"LIGHTMEM_HOOK_PROFILE": "off"},
            clear=True,
        ):
            return lightmem_profile.disabled(event)

    def test_session_start_disabled_under_off(self) -> None:
        self.assertTrue(self._disabled("SessionStart"))

    def test_stop_disabled_under_off(self) -> None:
        self.assertTrue(self._disabled("Stop"))

    def test_session_end_disabled_under_off(self) -> None:
        self.assertTrue(self._disabled("SessionEnd"))

    def test_pre_compact_disabled_under_off(self) -> None:
        self.assertTrue(self._disabled("PreCompact"))

    def test_post_compact_disabled_under_off(self) -> None:
        self.assertTrue(self._disabled("PostCompact"))

    def test_user_prompt_submit_disabled_under_off(self) -> None:
        self.assertTrue(self._disabled("UserPromptSubmit"))

    def test_pre_tool_use_disabled_under_off(self) -> None:
        self.assertTrue(self._disabled("PreToolUse"))

    def test_post_tool_use_disabled_under_off(self) -> None:
        self.assertTrue(self._disabled("PostToolUse"))

    def test_all_canonical_events_disabled_under_off(self) -> None:
        for event in _ALL_CANONICAL_EVENTS:
            with self.subTest(event=event):
                self.assertTrue(self._disabled(event))


# ===========================================================================
# 5. LIGHTMEM_HOOK_PROFILE=minimal
# ===========================================================================

class TestProfileMinimal(unittest.TestCase):
    """
    PRD §10.1: "minimal" — SessionStart still runs; everything else disabled.
    """

    def _disabled(self, event: str) -> bool:
        with unittest.mock.patch.dict(
            os.environ,
            {"LIGHTMEM_HOOK_PROFILE": "minimal"},
            clear=True,
        ):
            return lightmem_profile.disabled(event)

    def test_session_start_not_disabled_under_minimal(self) -> None:
        self.assertFalse(self._disabled("SessionStart"))

    def test_stop_disabled_under_minimal(self) -> None:
        self.assertTrue(self._disabled("Stop"))

    def test_session_end_disabled_under_minimal(self) -> None:
        self.assertTrue(self._disabled("SessionEnd"))

    def test_pre_compact_disabled_under_minimal(self) -> None:
        self.assertTrue(self._disabled("PreCompact"))

    def test_post_compact_disabled_under_minimal(self) -> None:
        self.assertTrue(self._disabled("PostCompact"))

    def test_user_prompt_submit_disabled_under_minimal(self) -> None:
        self.assertTrue(self._disabled("UserPromptSubmit"))

    def test_pre_tool_use_disabled_under_minimal(self) -> None:
        self.assertTrue(self._disabled("PreToolUse"))

    def test_post_tool_use_disabled_under_minimal(self) -> None:
        self.assertTrue(self._disabled("PostToolUse"))

    def test_all_minimal_disabled_events(self) -> None:
        for event in _MINIMAL_DISABLED:
            with self.subTest(event=event):
                self.assertTrue(self._disabled(event))


# ===========================================================================
# 6. Profile value — case and whitespace tolerance
# ===========================================================================

class TestProfileCaseWhitespaceTolerance(unittest.TestCase):
    """
    PRD §10: LIGHTMEM_HOOK_PROFILE is whitespace-trimmed and lowercased before
    comparison.  "STANDARD", "  standard  ", "Standard" must all behave as
    "standard".
    """

    def _disabled_with_profile(self, profile_value: str, event: str) -> bool:
        with unittest.mock.patch.dict(
            os.environ,
            {"LIGHTMEM_HOOK_PROFILE": profile_value},
            clear=True,
        ):
            return lightmem_profile.disabled(event)

    def test_uppercase_standard_treated_as_standard(self) -> None:
        for event in _ALL_CANONICAL_EVENTS:
            with self.subTest(event=event):
                self.assertFalse(self._disabled_with_profile("STANDARD", event))

    def test_mixed_case_standard_treated_as_standard(self) -> None:
        for event in _ALL_CANONICAL_EVENTS:
            with self.subTest(event=event):
                self.assertFalse(self._disabled_with_profile("Standard", event))

    def test_leading_trailing_whitespace_standard(self) -> None:
        for event in _ALL_CANONICAL_EVENTS:
            with self.subTest(event=event):
                self.assertFalse(self._disabled_with_profile("  standard  ", event))

    def test_tab_whitespace_standard(self) -> None:
        for event in _ALL_CANONICAL_EVENTS:
            with self.subTest(event=event):
                self.assertFalse(self._disabled_with_profile("\tstandard\t", event))

    def test_uppercase_off_treated_as_off(self) -> None:
        for event in _ALL_CANONICAL_EVENTS:
            with self.subTest(event=event):
                self.assertTrue(self._disabled_with_profile("OFF", event))

    def test_uppercase_minimal_session_start_not_disabled(self) -> None:
        self.assertFalse(self._disabled_with_profile("MINIMAL", "SessionStart"))

    def test_uppercase_minimal_stop_disabled(self) -> None:
        self.assertTrue(self._disabled_with_profile("MINIMAL", "Stop"))

    def test_whitespace_minimal_session_start_not_disabled(self) -> None:
        self.assertFalse(self._disabled_with_profile("  minimal  ", "SessionStart"))

    def test_whitespace_minimal_stop_disabled(self) -> None:
        self.assertTrue(self._disabled_with_profile("  minimal  ", "Stop"))


# ===========================================================================
# 7. Unknown profile value — treated as "standard"
# ===========================================================================

class TestProfileUnknownValue(unittest.TestCase):
    """
    PRD §10: unknown values are treated as "standard".
    Operator-facing warning is acceptable but not required to be captured.
    """

    def _disabled_with_profile(self, profile_value: str, event: str) -> bool:
        with unittest.mock.patch.dict(
            os.environ,
            {"LIGHTMEM_HOOK_PROFILE": profile_value},
            clear=True,
        ):
            return lightmem_profile.disabled(event)

    def test_garbage_profile_does_not_disable_session_start(self) -> None:
        self.assertFalse(self._disabled_with_profile("garbage", "SessionStart"))

    def test_garbage_profile_does_not_disable_stop(self) -> None:
        self.assertFalse(self._disabled_with_profile("garbage", "Stop"))

    def test_garbage_profile_does_not_disable_any_event(self) -> None:
        for event in _ALL_CANONICAL_EVENTS:
            with self.subTest(event=event):
                self.assertFalse(self._disabled_with_profile("garbage", event))

    def test_numeric_string_profile_treated_as_standard(self) -> None:
        for event in _ALL_CANONICAL_EVENTS:
            with self.subTest(event=event):
                self.assertFalse(self._disabled_with_profile("99", event))

    def test_empty_profile_treated_as_standard(self) -> None:
        # An explicitly empty string for the profile is an unknown value → standard
        for event in _ALL_CANONICAL_EVENTS:
            with self.subTest(event=event):
                # Empty string stripped is "", not "standard"/"minimal"/"off"
                # → treated as standard → nothing disabled
                self.assertFalse(self._disabled_with_profile("", event))


# ===========================================================================
# 8. LIGHTMEM_DISABLED_HOOKS — per-event granular override
# ===========================================================================

class TestDisabledHooksSingleEntry(unittest.TestCase):
    """
    PRD §10: LIGHTMEM_DISABLED_HOOKS=<event> disables that specific event
    regardless of profile.  Other events are unaffected.
    """

    def _env(self, hooks: str, profile: str = "standard") -> dict:
        return {"LIGHTMEM_HOOK_PROFILE": profile, "LIGHTMEM_DISABLED_HOOKS": hooks}

    def test_stop_in_disabled_hooks_disables_stop(self) -> None:
        with unittest.mock.patch.dict(
            os.environ, self._env("Stop"), clear=True
        ):
            self.assertTrue(lightmem_profile.disabled("Stop"))

    def test_stop_in_disabled_hooks_does_not_disable_session_start(self) -> None:
        with unittest.mock.patch.dict(
            os.environ, self._env("Stop"), clear=True
        ):
            self.assertFalse(lightmem_profile.disabled("SessionStart"))

    def test_stop_in_disabled_hooks_does_not_disable_session_end(self) -> None:
        with unittest.mock.patch.dict(
            os.environ, self._env("Stop"), clear=True
        ):
            self.assertFalse(lightmem_profile.disabled("SessionEnd"))

    def test_session_start_in_disabled_hooks_disables_session_start(self) -> None:
        with unittest.mock.patch.dict(
            os.environ, self._env("SessionStart"), clear=True
        ):
            self.assertTrue(lightmem_profile.disabled("SessionStart"))

    def test_pre_compact_in_disabled_hooks_disables_pre_compact(self) -> None:
        with unittest.mock.patch.dict(
            os.environ, self._env("PreCompact"), clear=True
        ):
            self.assertTrue(lightmem_profile.disabled("PreCompact"))


class TestDisabledHooksMultipleEntries(unittest.TestCase):
    """
    PRD §10: LIGHTMEM_DISABLED_HOOKS accepts a comma-separated list.
    All listed events must be disabled; unlisted events must not be.
    """

    def _env(self, hooks: str, profile: str = "standard") -> dict:
        return {"LIGHTMEM_HOOK_PROFILE": profile, "LIGHTMEM_DISABLED_HOOKS": hooks}

    def test_stop_and_session_end_both_disabled(self) -> None:
        with unittest.mock.patch.dict(
            os.environ, self._env("Stop,SessionEnd"), clear=True
        ):
            self.assertTrue(lightmem_profile.disabled("Stop"))
            self.assertTrue(lightmem_profile.disabled("SessionEnd"))

    def test_stop_and_session_end_leaves_others_enabled(self) -> None:
        with unittest.mock.patch.dict(
            os.environ, self._env("Stop,SessionEnd"), clear=True
        ):
            for event in ["SessionStart", "PreCompact", "PostCompact",
                          "UserPromptSubmit", "PreToolUse", "PostToolUse"]:
                with self.subTest(event=event):
                    self.assertFalse(lightmem_profile.disabled(event))

    def test_all_events_in_disabled_hooks(self) -> None:
        # Listing every canonical event must disable every one of them
        all_hooks = ",".join(_ALL_CANONICAL_EVENTS)
        with unittest.mock.patch.dict(
            os.environ, self._env(all_hooks), clear=True
        ):
            for event in _ALL_CANONICAL_EVENTS:
                with self.subTest(event=event):
                    self.assertTrue(lightmem_profile.disabled(event))


# ===========================================================================
# 9. LIGHTMEM_DISABLED_HOOKS — whitespace and case insensitivity
# ===========================================================================

class TestDisabledHooksWhitespaceCase(unittest.TestCase):
    """
    PRD §10: LIGHTMEM_DISABLED_HOOKS entries are whitespace-trimmed and
    case-insensitive.
    """

    def _env(self, hooks: str) -> dict:
        return {"LIGHTMEM_HOOK_PROFILE": "standard", "LIGHTMEM_DISABLED_HOOKS": hooks}

    def test_lowercase_stop_disables_stop(self) -> None:
        with unittest.mock.patch.dict(
            os.environ, self._env("stop"), clear=True
        ):
            self.assertTrue(lightmem_profile.disabled("Stop"))

    def test_uppercase_stop_disables_stop(self) -> None:
        with unittest.mock.patch.dict(
            os.environ, self._env("STOP"), clear=True
        ):
            self.assertTrue(lightmem_profile.disabled("Stop"))

    def test_whitespace_around_entries_trimmed(self) -> None:
        # "  stop  , sessionend " must match "Stop" and "SessionEnd"
        with unittest.mock.patch.dict(
            os.environ, self._env("  stop  , sessionend "), clear=True
        ):
            self.assertTrue(lightmem_profile.disabled("Stop"))
            self.assertTrue(lightmem_profile.disabled("SessionEnd"))

    def test_whitespace_around_entries_does_not_disable_others(self) -> None:
        with unittest.mock.patch.dict(
            os.environ, self._env("  stop  , sessionend "), clear=True
        ):
            for event in ["SessionStart", "PreCompact", "PostCompact",
                          "UserPromptSubmit", "PreToolUse", "PostToolUse"]:
                with self.subTest(event=event):
                    self.assertFalse(lightmem_profile.disabled(event))

    def test_hook_event_arg_case_insensitive_against_disabled_list(self) -> None:
        # hook_event "stop" (lowercase) matches "Stop" in the disabled list
        with unittest.mock.patch.dict(
            os.environ, self._env("Stop"), clear=True
        ):
            self.assertTrue(lightmem_profile.disabled("stop"))

    def test_hook_event_arg_uppercase_matches_disabled_list(self) -> None:
        with unittest.mock.patch.dict(
            os.environ, self._env("Stop"), clear=True
        ):
            self.assertTrue(lightmem_profile.disabled("STOP"))

    def test_mixed_whitespace_and_case_in_list(self) -> None:
        # "  STOP  , sessionEnd  ,  PRECOMPACT  "
        with unittest.mock.patch.dict(
            os.environ, self._env("  STOP  , sessionEnd  ,  PRECOMPACT  "), clear=True
        ):
            self.assertTrue(lightmem_profile.disabled("Stop"))
            self.assertTrue(lightmem_profile.disabled("SessionEnd"))
            self.assertTrue(lightmem_profile.disabled("PreCompact"))
            self.assertFalse(lightmem_profile.disabled("SessionStart"))

    def test_whitespace_only_value_is_treated_as_empty(self) -> None:
        # An operator who sets LIGHTMEM_DISABLED_HOOKS="   " (whitespace only)
        # should get the same behaviour as the unset default: no per-event mute.
        with unittest.mock.patch.dict(
            os.environ, self._env("   "), clear=True
        ):
            for event in ["SessionStart", "Stop", "SessionEnd", "PreCompact"]:
                with self.subTest(event=event):
                    self.assertFalse(lightmem_profile.disabled(event))


# ===========================================================================
# 10. Combined: LIGHTMEM_DISABLED_HOOKS + LIGHTMEM_HOOK_PROFILE interaction
# ===========================================================================

class TestDisabledHooksWithMinimalProfile(unittest.TestCase):
    """
    PRD §10: DISABLED_HOOKS only ADDS restrictions — it never relaxes profile
    restrictions.  Under 'minimal', SessionStart is allowed by profile; if it's
    also NOT in DISABLED_HOOKS, it remains enabled.  Stop is disabled by the
    profile; DISABLED_HOOKS can add to that but not remove it.
    """

    def _env(self, hooks: str, profile: str = "minimal") -> dict:
        return {"LIGHTMEM_HOOK_PROFILE": profile, "LIGHTMEM_DISABLED_HOOKS": hooks}

    def test_session_start_not_disabled_by_minimal_alone(self) -> None:
        # minimal profile + empty DISABLED_HOOKS → SessionStart runs
        with unittest.mock.patch.dict(
            os.environ, self._env(""), clear=True
        ):
            self.assertFalse(lightmem_profile.disabled("SessionStart"))

    def test_stop_disabled_by_minimal_profile_regardless_of_list(self) -> None:
        # Stop is disabled by minimal profile; DISABLED_HOOKS doesn't change that
        with unittest.mock.patch.dict(
            os.environ, self._env("Stop"), clear=True
        ):
            self.assertTrue(lightmem_profile.disabled("Stop"))

    def test_disabled_hooks_does_not_re_enable_profile_restriction(self) -> None:
        # Setting DISABLED_HOOKS=Stop when profile=minimal does NOT un-disable
        # Stop (it was already disabled by the profile).
        # More importantly: setting DISABLED_HOOKS=SessionStart under minimal
        # adds to restrictions (SessionStart now also in list) — but that is a
        # separate test (below).
        # Here: no additional hooks listed; minimal is the authority.
        with unittest.mock.patch.dict(
            os.environ, self._env(""), clear=True
        ):
            for event in _MINIMAL_DISABLED:
                with self.subTest(event=event):
                    self.assertTrue(lightmem_profile.disabled(event))

    def test_session_start_disabled_when_added_to_disabled_hooks_under_minimal(
        self,
    ) -> None:
        # DISABLED_HOOKS=SessionStart under minimal → SessionStart is now disabled
        # (disabled list adds to profile restrictions)
        with unittest.mock.patch.dict(
            os.environ, self._env("SessionStart"), clear=True
        ):
            self.assertTrue(lightmem_profile.disabled("SessionStart"))

    def test_disabled_hooks_adds_to_off_profile(self) -> None:
        # Under 'off', everything is already disabled.
        # Adding more events to DISABLED_HOOKS is a no-op (they're already disabled).
        with unittest.mock.patch.dict(
            os.environ,
            {"LIGHTMEM_HOOK_PROFILE": "off", "LIGHTMEM_DISABLED_HOOKS": "Stop"},
            clear=True,
        ):
            # All events still disabled (off profile dominates)
            for event in _ALL_CANONICAL_EVENTS:
                with self.subTest(event=event):
                    self.assertTrue(lightmem_profile.disabled(event))


# ===========================================================================
# 11. hook_event argument — case-insensitive matching
# ===========================================================================

class TestHookEventCaseInsensitivity(unittest.TestCase):
    """
    PRD §10: hook_event matching is case-insensitive throughout.
    disabled("sessionstart") and disabled("SessionStart") must agree.
    """

    def _disabled_standard(self, event: str) -> bool:
        with unittest.mock.patch.dict(
            os.environ, {"LIGHTMEM_HOOK_PROFILE": "standard"}, clear=True
        ):
            return lightmem_profile.disabled(event)

    def _disabled_minimal(self, event: str) -> bool:
        with unittest.mock.patch.dict(
            os.environ, {"LIGHTMEM_HOOK_PROFILE": "minimal"}, clear=True
        ):
            return lightmem_profile.disabled(event)

    def _disabled_off(self, event: str) -> bool:
        with unittest.mock.patch.dict(
            os.environ, {"LIGHTMEM_HOOK_PROFILE": "off"}, clear=True
        ):
            return lightmem_profile.disabled(event)

    def test_sessionstart_lowercase_not_disabled_under_standard(self) -> None:
        self.assertFalse(self._disabled_standard("sessionstart"))

    def test_sessionstart_uppercase_not_disabled_under_standard(self) -> None:
        self.assertFalse(self._disabled_standard("SESSIONSTART"))

    def test_stop_lowercase_not_disabled_under_standard(self) -> None:
        self.assertFalse(self._disabled_standard("stop"))

    def test_sessionstart_lowercase_not_disabled_under_minimal(self) -> None:
        # Spec explicitly calls out: disabled("sessionstart") (lowercase) should
        # be False under LIGHTMEM_HOOK_PROFILE=minimal (PRD test spec §11).
        self.assertFalse(self._disabled_minimal("sessionstart"))

    def test_sessionstart_canonical_not_disabled_under_minimal(self) -> None:
        self.assertFalse(self._disabled_minimal("SessionStart"))

    def test_stop_lowercase_disabled_under_minimal(self) -> None:
        self.assertTrue(self._disabled_minimal("stop"))

    def test_stop_uppercase_disabled_under_minimal(self) -> None:
        self.assertTrue(self._disabled_minimal("STOP"))

    def test_all_lowercase_events_disabled_under_off(self) -> None:
        lowercase_events = [e.lower() for e in _ALL_CANONICAL_EVENTS]
        for event in lowercase_events:
            with self.subTest(event=event):
                self.assertTrue(self._disabled_off(event))

    def test_all_uppercase_events_disabled_under_off(self) -> None:
        uppercase_events = [e.upper() for e in _ALL_CANONICAL_EVENTS]
        for event in uppercase_events:
            with self.subTest(event=event):
                self.assertTrue(self._disabled_off(event))


# ===========================================================================
# 12. Environment isolation — no state leaks between tests
# ===========================================================================

class TestEnvironmentIsolation(unittest.TestCase):
    """
    Verify that patching os.environ inside tests does not permanently modify the
    process environment.  patch.dict with clear=True must restore the original
    env after each test.
    """

    def test_env_vars_not_leaked_after_patch(self) -> None:
        original_profile = os.environ.get("LIGHTMEM_HOOK_PROFILE")
        original_disabled = os.environ.get("LIGHTMEM_DISABLED_HOOKS")

        with unittest.mock.patch.dict(
            os.environ,
            {"LIGHTMEM_HOOK_PROFILE": "off", "LIGHTMEM_DISABLED_HOOKS": "Stop"},
            clear=True,
        ):
            # Inside the patch, env is modified
            self.assertEqual(os.environ.get("LIGHTMEM_HOOK_PROFILE"), "off")

        # Outside the patch, original values must be restored
        self.assertEqual(os.environ.get("LIGHTMEM_HOOK_PROFILE"), original_profile)
        self.assertEqual(os.environ.get("LIGHTMEM_DISABLED_HOOKS"), original_disabled)


if __name__ == "__main__":
    unittest.main()
