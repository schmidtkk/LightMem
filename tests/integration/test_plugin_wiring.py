from __future__ import annotations

"""
Integration tests for Round 7 — plugin wiring.

Validates that the plugin manifest, live hook configuration, reference
documentation, README, CLAUDE.md, skill files, and templates all conform to
PRD_v0.2.md without executing a single Claude Code hook process.

Spec references:
    PRD §4.1  — plugin manifest shape
    PRD §4.3  — live hooks/hooks.json shape
    PRD §4.4  — reference hooks/memory-persistence/ separation
    PRD §6    — hook event names and responsibilities
    PRD §10   — env vars (no impact here, but drives event-name canon)
    PRD §12   — acceptance criteria

Run from any directory:
    python3 -W error -m unittest discover tests
"""

import json
import re
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Canonical event names that v0.1 registers (PRD §4.3, §6).
_EXPECTED_EVENTS = {"SessionStart", "Stop", "SessionEnd", "PreCompact", "UserPromptSubmit"}


# ---------------------------------------------------------------------------
# Helper: collect every command string from hooks/hooks.json
# ---------------------------------------------------------------------------

def _all_commands(hooks_data: dict) -> list[str]:
    """Return every 'command' string nested inside hooks_data['hooks']."""
    commands: list[str] = []
    for event_blocks in hooks_data.get("hooks", {}).values():
        for block in event_blocks:
            for entry in block.get("hooks", []):
                if "command" in entry:
                    commands.append(entry["command"])
    return commands


# ---------------------------------------------------------------------------
# §4.1  Plugin manifest
# ---------------------------------------------------------------------------

class TestPluginManifest(unittest.TestCase):
    """Validates .claude-plugin/plugin.json against PRD §4.1."""

    _MANIFEST_PATH = _REPO_ROOT / ".claude-plugin" / "plugin.json"

    def _load(self) -> dict:
        """Parse and return the manifest; skip the test if the file is absent."""
        if not self._MANIFEST_PATH.exists():
            self.skipTest(f"Manifest not yet created: {self._MANIFEST_PATH}")
        with self._MANIFEST_PATH.open(encoding="utf-8") as fh:
            return json.load(fh)

    # --- existence ----------------------------------------------------------

    def test_manifest_exists(self) -> None:
        self.assertTrue(
            self._MANIFEST_PATH.exists(),
            f"Plugin manifest missing: {self._MANIFEST_PATH}",
        )

    # --- parseability -------------------------------------------------------

    def test_manifest_is_valid_json(self) -> None:
        raw = self._MANIFEST_PATH.read_text(encoding="utf-8")
        try:
            json.loads(raw)
        except json.JSONDecodeError as exc:
            self.fail(f"plugin.json is not valid JSON: {exc}")

    # --- required string fields ---------------------------------------------

    def test_manifest_has_required_fields(self) -> None:
        manifest = self._load()
        for field in ("name", "version", "description"):
            with self.subTest(field=field):
                self.assertIn(
                    field,
                    manifest,
                    f"plugin.json missing required field '{field}'",
                )
                self.assertIsInstance(
                    manifest[field],
                    str,
                    f"plugin.json field '{field}' must be a string",
                )

    def test_manifest_name_is_lightmem(self) -> None:
        manifest = self._load()
        self.assertEqual(
            manifest.get("name"),
            "lightmem",
            "plugin.json 'name' must be 'lightmem' (PRD §4.1)",
        )

    def test_manifest_version_is_semver(self) -> None:
        manifest = self._load()
        version = manifest.get("version", "")
        self.assertRegex(
            version,
            r"^\d+\.\d+\.\d+$",
            f"plugin.json 'version' must be semver X.Y.Z, got {version!r}",
        )

    # --- skills field -------------------------------------------------------

    def test_manifest_skills_field_is_list(self) -> None:
        manifest = self._load()
        self.assertIn("skills", manifest, "plugin.json must have a 'skills' field")
        self.assertIsInstance(
            manifest["skills"], (list, str), "plugin.json 'skills' must be a list or path string"
        )

    def test_manifest_skills_directory_exists(self) -> None:
        """The path(s) listed in skills must resolve to an existing directory."""
        manifest = self._load()
        raw_skills = manifest.get("skills", [])
        skills_entries: list = [raw_skills] if isinstance(raw_skills, str) else raw_skills
        for entry in skills_entries:
            # entry may be a string like "./skills/" or a dict with a path key
            if isinstance(entry, str):
                skill_path_str = entry
            elif isinstance(entry, dict):
                skill_path_str = entry.get("path", "")
            else:
                self.fail(f"Unexpected skills entry type: {type(entry)!r}: {entry!r}")

            # Resolve relative to repo root (the manifest lives in .claude-plugin/,
            # but relative paths in skills conventionally mean repo-root-relative
            # because that is where Claude Code resolves them from).
            # Strip leading './' for Path resolution.
            skill_path_str = skill_path_str.lstrip("./")
            candidate = _REPO_ROOT / skill_path_str
            self.assertTrue(
                candidate.exists(),
                f"Skills directory referenced in plugin.json does not exist: {candidate}",
            )

    # --- hooks field must be absent -----------------------------------------

    def test_manifest_does_not_have_hooks_field(self) -> None:
        """PRD §4.1: 'hooks' is intentionally omitted from plugin.json."""
        manifest = self._load()
        self.assertNotIn(
            "hooks",
            manifest,
            "plugin.json must NOT contain a 'hooks' field (PRD §4.1); "
            "hook wiring belongs in hooks/hooks.json",
        )

    # --- license ------------------------------------------------------------

    def test_manifest_license_is_mit(self) -> None:
        manifest = self._load()
        self.assertEqual(
            manifest.get("license"),
            "MIT",
            "plugin.json 'license' must be 'MIT'",
        )


class TestCodexPluginManifest(unittest.TestCase):
    """Validates .codex-plugin/plugin.json for Codex CLI installs."""

    _MANIFEST_PATH = _REPO_ROOT / ".codex-plugin" / "plugin.json"

    def _load(self) -> dict:
        if not self._MANIFEST_PATH.exists():
            self.skipTest(f"Codex manifest not yet created: {self._MANIFEST_PATH}")
        with self._MANIFEST_PATH.open(encoding="utf-8") as fh:
            return json.load(fh)

    def test_codex_manifest_exists(self) -> None:
        self.assertTrue(
            self._MANIFEST_PATH.exists(),
            f"Codex plugin manifest missing: {self._MANIFEST_PATH}",
        )

    def test_codex_manifest_has_required_fields(self) -> None:
        manifest = self._load()
        for field in ("name", "version", "description", "interface"):
            with self.subTest(field=field):
                self.assertIn(field, manifest)

    def test_codex_manifest_points_to_skills_and_hooks(self) -> None:
        manifest = self._load()
        self.assertEqual(manifest.get("skills"), "./skills/")
        self.assertEqual(manifest.get("hooks"), "./hooks/hooks.json")


class TestCodexMarketplace(unittest.TestCase):
    """Validates repository-local Codex marketplace metadata."""

    _MARKETPLACE = _REPO_ROOT / ".agents" / "plugins" / "marketplace.json"

    def _load(self) -> dict:
        if not self._MARKETPLACE.exists():
            self.skipTest(f"Codex marketplace not yet created: {self._MARKETPLACE}")
        with self._MARKETPLACE.open(encoding="utf-8") as fh:
            return json.load(fh)

    def test_codex_marketplace_exists(self) -> None:
        self.assertTrue(self._MARKETPLACE.exists())

    def test_codex_marketplace_contains_lightmem_entry(self) -> None:
        data = self._load()
        entries = {entry.get("name"): entry for entry in data.get("plugins", [])}
        self.assertIn("lightmem", entries)
        entry = entries["lightmem"]
        self.assertEqual(entry.get("source", {}).get("source"), "local")
        self.assertEqual(entry.get("source", {}).get("path"), "./plugins/lightmem")
        self.assertEqual(entry.get("policy", {}).get("installation"), "AVAILABLE")
        self.assertEqual(entry.get("policy", {}).get("authentication"), "ON_INSTALL")

    def test_codex_marketplace_path_resolves_to_plugin_root(self) -> None:
        data = self._load()
        entries = {entry.get("name"): entry for entry in data.get("plugins", [])}
        entry = entries["lightmem"]
        rel_path = entry.get("source", {}).get("path", "")
        plugin_root = (_REPO_ROOT / rel_path).resolve()
        self.assertTrue((plugin_root / ".codex-plugin" / "plugin.json").is_file())


# ---------------------------------------------------------------------------
# §4.3  Live hook configuration
# ---------------------------------------------------------------------------

class TestLiveHooksJson(unittest.TestCase):
    """Validates hooks/hooks.json against PRD §4.3."""

    _HOOKS_PATH = _REPO_ROOT / "hooks" / "hooks.json"

    def _load(self) -> dict:
        if not self._HOOKS_PATH.exists():
            self.skipTest(f"hooks/hooks.json not yet created: {self._HOOKS_PATH}")
        with self._HOOKS_PATH.open(encoding="utf-8") as fh:
            return json.load(fh)

    # --- existence / parse --------------------------------------------------

    def test_hooks_json_exists(self) -> None:
        self.assertTrue(
            self._HOOKS_PATH.exists(),
            f"Live hook config missing: {self._HOOKS_PATH}",
        )

    def test_hooks_json_is_valid_json(self) -> None:
        raw = self._HOOKS_PATH.read_text(encoding="utf-8")
        try:
            json.loads(raw)
        except json.JSONDecodeError as exc:
            self.fail(f"hooks/hooks.json is not valid JSON: {exc}")

    def test_hooks_json_has_top_level_hooks_key(self) -> None:
        data = self._load()
        self.assertIn(
            "hooks",
            data,
            "hooks/hooks.json must have a top-level 'hooks' object",
        )
        self.assertIsInstance(
            data["hooks"], dict, "hooks/hooks.json 'hooks' must be a dict"
        )

    # --- SessionStart -------------------------------------------------------

    def test_session_start_registered(self) -> None:
        """PRD §4.3: SessionStart has startup/resume/clear/compact matcher, type='command',
        command references session_start.py, timeout is int."""
        data = self._load()
        hooks_map: dict = data["hooks"]
        self.assertIn(
            "SessionStart",
            hooks_map,
            "hooks/hooks.json must register a 'SessionStart' event",
        )
        blocks = hooks_map["SessionStart"]
        self.assertGreater(
            len(blocks), 0, "SessionStart must have at least one block"
        )
        block = blocks[0]
        matcher = block.get("matcher", "")
        for source in ("startup", "resume", "clear", "compact"):
            self.assertIn(
                source,
                matcher,
                f"SessionStart matcher must include {source!r}, got {matcher!r}",
            )
        entries = block.get("hooks", [])
        self.assertGreater(
            len(entries), 0, "SessionStart block must have at least one hooks entry"
        )
        entry = entries[0]
        self.assertEqual(
            entry.get("type"),
            "command",
            f"SessionStart hooks entry 'type' must be 'command', got {entry.get('type')!r}",
        )
        command: str = entry.get("command", "")
        self.assertIn(
            "session_start.py",
            command,
            f"SessionStart command must reference 'session_start.py', got {command!r}",
        )
        self.assertIsInstance(
            entry.get("timeout"),
            int,
            f"SessionStart 'timeout' must be an int, got {entry.get('timeout')!r}",
        )

    # --- Stop ---------------------------------------------------------------

    def test_stop_registered_async(self) -> None:
        """PRD §4.3 + D4: Stop block has async=true, int timeout, references stop.py."""
        data = self._load()
        hooks_map: dict = data["hooks"]
        self.assertIn(
            "Stop", hooks_map, "hooks/hooks.json must register a 'Stop' event"
        )
        blocks = hooks_map["Stop"]
        self.assertGreater(len(blocks), 0, "Stop must have at least one block")

        # Find the hooks entry that references stop.py
        found_entry: dict | None = None
        for block in blocks:
            for entry in block.get("hooks", []):
                if "stop.py" in entry.get("command", ""):
                    found_entry = entry
                    break
            if found_entry:
                break

        self.assertIsNotNone(
            found_entry,
            "Stop hooks must have an entry whose command references 'stop.py'",
        )
        self.assertTrue(
            found_entry.get("async") is True,  # type: ignore[union-attr]
            f"Stop hooks entry must have 'async': true (PRD D4), got {found_entry.get('async')!r}",  # type: ignore[union-attr]
        )
        self.assertIsInstance(
            found_entry.get("timeout"),  # type: ignore[union-attr]
            int,
            f"Stop 'timeout' must be an int, got {found_entry.get('timeout')!r}",  # type: ignore[union-attr]
        )

    # --- SessionEnd ---------------------------------------------------------

    def test_session_end_registered(self) -> None:
        """PRD §4.3: SessionEnd is registered, command references session_end.py."""
        data = self._load()
        hooks_map: dict = data["hooks"]
        self.assertIn(
            "SessionEnd",
            hooks_map,
            "hooks/hooks.json must register a 'SessionEnd' event",
        )
        commands = []
        for block in hooks_map["SessionEnd"]:
            for entry in block.get("hooks", []):
                commands.append(entry.get("command", ""))
        self.assertTrue(
            any("session_end.py" in c for c in commands),
            f"SessionEnd must have a command referencing 'session_end.py', got {commands!r}",
        )

    # --- PreCompact ---------------------------------------------------------

    def test_pre_compact_registered(self) -> None:
        """PRD §4.3: PreCompact is registered, command references pre_compact.py."""
        data = self._load()
        hooks_map: dict = data["hooks"]
        self.assertIn(
            "PreCompact",
            hooks_map,
            "hooks/hooks.json must register a 'PreCompact' event",
        )
        commands = []
        for block in hooks_map["PreCompact"]:
            for entry in block.get("hooks", []):
                commands.append(entry.get("command", ""))
        self.assertTrue(
            any("pre_compact.py" in c for c in commands),
            f"PreCompact must have a command referencing 'pre_compact.py', got {commands!r}",
        )

    def test_user_prompt_submit_registered(self) -> None:
        """v0.2: UserPromptSubmit is registered, command references user_prompt_submit.py."""
        data = self._load()
        hooks_map: dict = data["hooks"]
        self.assertIn(
            "UserPromptSubmit",
            hooks_map,
            "hooks/hooks.json must register a 'UserPromptSubmit' event",
        )
        commands = []
        for block in hooks_map["UserPromptSubmit"]:
            for entry in block.get("hooks", []):
                commands.append(entry.get("command", ""))
        self.assertTrue(
            any("user_prompt_submit.py" in c for c in commands),
            f"UserPromptSubmit must have a command referencing 'user_prompt_submit.py', "
            f"got {commands!r}",
        )

    # --- command-level invariants -------------------------------------------

    def test_all_hook_commands_use_plugin_root(self) -> None:
        """PRD §4.3: every command must reference $CLAUDE_PLUGIN_ROOT (or ${…})."""
        data = self._load()
        for cmd in _all_commands(data):
            self.assertTrue(
                "$CLAUDE_PLUGIN_ROOT" in cmd or "${CLAUDE_PLUGIN_ROOT}" in cmd,
                f"Hook command does not reference $CLAUDE_PLUGIN_ROOT: {cmd!r}",
            )

    def test_all_hook_commands_invoke_python3(self) -> None:
        """PRD D1: pure-stdlib Python 3.10+. Every command must start with python3."""
        data = self._load()
        for cmd in _all_commands(data):
            self.assertTrue(
                cmd.strip().startswith("python3"),
                f"Hook command must start with 'python3' (PRD D1): {cmd!r}",
            )

    def test_referenced_hook_scripts_all_exist(self) -> None:
        """Every script path embedded in a command must exist on disk."""
        data = self._load()
        # Pattern: anything after $CLAUDE_PLUGIN_ROOT (with optional braces / quotes)
        # e.g.  python3 "$CLAUDE_PLUGIN_ROOT"/scripts/hooks/session_start.py
        #       python3 "${CLAUDE_PLUGIN_ROOT}"/scripts/hooks/session_start.py
        pattern = re.compile(r'\$\{?CLAUDE_PLUGIN_ROOT\}?"?/([^\s"\']+)')
        for cmd in _all_commands(data):
            match = pattern.search(cmd)
            self.assertIsNotNone(
                match,
                f"Could not parse script path from command: {cmd!r}",
            )
            relative_path: str = match.group(1)  # type: ignore[union-attr]
            script_path = _REPO_ROOT / relative_path
            self.assertTrue(
                script_path.exists(),
                f"Hook script referenced in hooks.json does not exist on disk: "
                f"{script_path} (from command: {cmd!r})",
            )

    def test_no_unexpected_hook_events(self) -> None:
        """PRD §6 / §13 anti-goals: only the 4 expected events are registered in v0.1."""
        data = self._load()
        registered: set = set(data["hooks"].keys())
        unexpected = registered - _EXPECTED_EVENTS
        self.assertEqual(
            unexpected,
            set(),
            f"hooks/hooks.json registers unexpected event(s): {unexpected}. "
            f"PreToolUse, PostToolUse are deferred to v0.3+ (PRD §6.6, §6.7).",
        )


# ---------------------------------------------------------------------------
# §4.4  Reference hooks documentation
# ---------------------------------------------------------------------------

class TestReferenceHooksJson(unittest.TestCase):
    """Validates hooks/memory-persistence/ against PRD §4.4."""

    _MEM_DIR = _REPO_ROOT / "hooks" / "memory-persistence"
    _README = _MEM_DIR / "README.md"
    _REF_JSON = _MEM_DIR / "hooks.json"

    def _load_ref(self) -> dict:
        if not self._REF_JSON.exists():
            self.skipTest(f"Reference hooks.json not yet created: {self._REF_JSON}")
        with self._REF_JSON.open(encoding="utf-8") as fh:
            return json.load(fh)

    # --- README ---

    def test_reference_readme_exists(self) -> None:
        self.assertTrue(
            self._README.exists(),
            f"hooks/memory-persistence/README.md missing: {self._README}",
        )
        size = self._README.stat().st_size
        self.assertGreater(
            size, 0, "hooks/memory-persistence/README.md must be non-empty"
        )

    # --- reference hooks.json ---

    def test_reference_hooks_json_exists(self) -> None:
        self.assertTrue(
            self._REF_JSON.exists(),
            f"hooks/memory-persistence/hooks.json missing: {self._REF_JSON}",
        )

    def test_reference_hooks_json_lists_expected_events(self) -> None:
        """PRD §4.4: reference file enumerates each event; must match _EXPECTED_EVENTS."""
        ref = self._load_ref()
        self.assertIn(
            "events",
            ref,
            "hooks/memory-persistence/hooks.json must have an 'events' array",
        )
        events = ref["events"]
        self.assertIsInstance(events, list, "'events' must be a list")
        self.assertEqual(
            len(events),
            len(_EXPECTED_EVENTS),
            f"hooks/memory-persistence/hooks.json must list exactly {len(_EXPECTED_EVENTS)} events "
            f"(got {len(events)}): {[e.get('event') for e in events]}",
        )

    def test_reference_hooks_json_event_shape(self) -> None:
        """PRD §4.4: each event entry has event, id, script, purpose, blocking."""
        ref = self._load_ref()
        required_fields = {"event", "id", "script", "purpose", "blocking"}
        for i, event_entry in enumerate(ref.get("events", [])):
            with self.subTest(event_index=i, event=event_entry.get("event")):
                for field in required_fields:
                    self.assertIn(
                        field,
                        event_entry,
                        f"Event entry #{i} ({event_entry.get('event')!r}) missing "
                        f"required field '{field}' in hooks/memory-persistence/hooks.json",
                    )

    def test_reference_hooks_json_event_names_match_live(self) -> None:
        """PRD §4.4: reference event names must exactly match live hooks.json keys."""
        live_path = _REPO_ROOT / "hooks" / "hooks.json"
        if not live_path.exists():
            self.skipTest("hooks/hooks.json not yet created; cannot compare")
        with live_path.open(encoding="utf-8") as fh:
            live_data = json.load(fh)
        live_events: set = set(live_data.get("hooks", {}).keys())

        ref = self._load_ref()
        ref_events: set = {e.get("event") for e in ref.get("events", [])}

        self.assertEqual(
            ref_events,
            live_events,
            f"Event names in hooks/memory-persistence/hooks.json ({sorted(ref_events)}) "
            f"must match keys in hooks/hooks.json ({sorted(live_events)})",
        )


# ---------------------------------------------------------------------------
# README.md
# ---------------------------------------------------------------------------

class TestReadme(unittest.TestCase):
    """Validates README.md against PRD §4.2 layout and §7 skill surface."""

    _README = _REPO_ROOT / "README.md"

    def _read(self) -> str:
        if not self._README.exists():
            self.skipTest(f"README.md not yet created: {self._README}")
        return self._README.read_text(encoding="utf-8")

    def test_readme_exists(self) -> None:
        self.assertTrue(
            self._README.exists(),
            f"README.md missing at repo root: {self._README}",
        )
        size = self._README.stat().st_size
        self.assertGreater(
            size,
            500,
            f"README.md is too small ({size} bytes); expected a non-trivial document "
            f"with at least 500 bytes",
        )

    def test_readme_mentions_lightmem(self) -> None:
        content = self._read()
        self.assertTrue(
            "LightMem" in content or "lightmem" in content,
            "README.md must mention 'LightMem' or 'lightmem'",
        )

    def test_readme_mentions_slash_commands(self) -> None:
        """PRD §7 / D10: skill names use /lightmem:<name> (full prefix, colon sep)."""
        content = self._read()
        for cmd in ("/lightmem:init", "/lightmem:doctor", "/lightmem:index"):
            with self.subTest(command=cmd):
                self.assertIn(
                    cmd,
                    content,
                    f"README.md must mention the slash command '{cmd}' (PRD §7)",
                )

    def test_readme_mentions_install(self) -> None:
        """README.md must have an installation section."""
        content = self._read()
        # Accept any casing of "Install" in a markdown header
        self.assertTrue(
            re.search(r"#+\s+.*[Ii]nstall", content) is not None,
            "README.md must have a section header containing 'Install' or 'install'",
        )


# ---------------------------------------------------------------------------
# CLAUDE.md — updated per Round 7 spec
# ---------------------------------------------------------------------------

class TestClaudeMdUpdated(unittest.TestCase):
    """Validates CLAUDE.md references and size budget (PRD §5.2)."""

    _CLAUDE_MD = _REPO_ROOT / "CLAUDE.md"

    def _read(self) -> str:
        if not self._CLAUDE_MD.exists():
            self.skipTest(f"CLAUDE.md not yet present: {self._CLAUDE_MD}")
        return self._CLAUDE_MD.read_text(encoding="utf-8")

    def test_claude_md_references_readme(self) -> None:
        # Public-facing repo: CLAUDE.md should point contributors at the README
        # (internal PRD docs are not part of the OSS distribution).
        content = self._read()
        self.assertIn(
            "README.md",
            content,
            "CLAUDE.md must reference 'README.md' as the contributor entry point",
        )

    def test_claude_md_references_roadmap(self) -> None:
        content = self._read()
        self.assertIn(
            "ROADMAP.md",
            content,
            "CLAUDE.md must reference 'ROADMAP.md' (PRD §15 / Round 7 requirement)",
        )

    def test_claude_md_size_within_budget(self) -> None:
        """PRD §5.2: CLAUDE.md ≤ 8 KB is the warn threshold; hard limit is 16 KB.
        We enforce the warn threshold (8192 bytes) here to keep the dev-loop file
        well clear of the agent disruption boundary."""
        size = self._CLAUDE_MD.stat().st_size
        self.assertLessEqual(
            size,
            8192,
            f"CLAUDE.md is {size} bytes, exceeding the 8 KB warn threshold "
            f"(PRD §5.2). Move content to topic files.",
        )


# ---------------------------------------------------------------------------
# Skill files — §7
# ---------------------------------------------------------------------------

class TestSkillFilesPresent(unittest.TestCase):
    """Validates that the three v0.1 skills exist with correct YAML frontmatter."""

    _SKILLS_ROOT = _REPO_ROOT / "skills"

    _SKILL_PATHS = {
        "init": _SKILLS_ROOT / "init" / "SKILL.md",
        "doctor": _SKILLS_ROOT / "doctor" / "SKILL.md",
        "index": _SKILLS_ROOT / "index" / "SKILL.md",
        "mark": _SKILLS_ROOT / "mark" / "SKILL.md",
        "update": _SKILLS_ROOT / "update" / "SKILL.md",
    }

    def _all_skill_paths(self) -> list[Path]:
        return list(self._SKILL_PATHS.values())

    def _read_skill(self, name: str) -> str:
        path = self._SKILL_PATHS[name]
        if not path.exists():
            self.skipTest(f"Skill file not yet created: {path}")
        return path.read_text(encoding="utf-8")

    # --- existence ----------------------------------------------------------

    def test_init_skill_exists(self) -> None:
        self.assertTrue(
            self._SKILL_PATHS["init"].exists(),
            f"skills/init/SKILL.md missing: {self._SKILL_PATHS['init']}",
        )

    def test_doctor_skill_exists(self) -> None:
        self.assertTrue(
            self._SKILL_PATHS["doctor"].exists(),
            f"skills/doctor/SKILL.md missing: {self._SKILL_PATHS['doctor']}",
        )

    def test_index_skill_exists(self) -> None:
        self.assertTrue(
            self._SKILL_PATHS["index"].exists(),
            f"skills/index/SKILL.md missing: {self._SKILL_PATHS['index']}",
        )

    def test_mark_skill_exists(self) -> None:
        self.assertTrue(
            self._SKILL_PATHS["mark"].exists(),
            f"skills/mark/SKILL.md missing: {self._SKILL_PATHS['mark']}",
        )

    def test_update_skill_exists(self) -> None:
        self.assertTrue(
            self._SKILL_PATHS["update"].exists(),
            f"skills/update/SKILL.md missing: {self._SKILL_PATHS['update']}",
        )

    # --- YAML frontmatter ---------------------------------------------------

    def _parse_frontmatter_block(self, content: str) -> str | None:
        """Return the raw frontmatter string (between the --- delimiters) or None."""
        if not content.startswith("---\n"):
            return None
        end = content.find("\n---", 4)
        if end == -1:
            return None
        return content[4:end]

    def test_each_skill_has_yaml_frontmatter(self) -> None:
        """PRD §7: SKILL.md uses YAML frontmatter (starts '---\\n', has closing '---')."""
        for name, path in self._SKILL_PATHS.items():
            if not path.exists():
                continue
            with self.subTest(skill=name):
                content = path.read_text(encoding="utf-8")
                self.assertTrue(
                    content.startswith("---\n"),
                    f"{path.relative_to(_REPO_ROOT)} must start with '---\\n' "
                    f"(YAML frontmatter open fence)",
                )
                # There must be a closing ---
                close_pos = content.find("\n---", 4)
                self.assertNotEqual(
                    close_pos,
                    -1,
                    f"{path.relative_to(_REPO_ROOT)} must have a closing '---' "
                    f"for the YAML frontmatter",
                )

    def test_each_skill_has_name_field(self) -> None:
        """PRD §7: frontmatter must contain 'name:' field."""
        for name, path in self._SKILL_PATHS.items():
            if not path.exists():
                continue
            with self.subTest(skill=name):
                content = path.read_text(encoding="utf-8")
                fm = self._parse_frontmatter_block(content)
                self.assertIsNotNone(
                    fm,
                    f"{path.relative_to(_REPO_ROOT)} has no parseable frontmatter block",
                )
                self.assertIn(
                    "name:",
                    fm,  # type: ignore[operator]
                    f"{path.relative_to(_REPO_ROOT)} frontmatter must contain 'name:' field",
                )

    def test_each_skill_has_description_field(self) -> None:
        """PRD §7: frontmatter must contain 'description:' field."""
        for name, path in self._SKILL_PATHS.items():
            if not path.exists():
                continue
            with self.subTest(skill=name):
                content = path.read_text(encoding="utf-8")
                fm = self._parse_frontmatter_block(content)
                self.assertIsNotNone(
                    fm,
                    f"{path.relative_to(_REPO_ROOT)} has no parseable frontmatter block",
                )
                self.assertIn(
                    "description:",
                    fm,  # type: ignore[operator]
                    f"{path.relative_to(_REPO_ROOT)} frontmatter must contain 'description:' field",
                )


# ---------------------------------------------------------------------------
# Templates — §4.2 layout
# ---------------------------------------------------------------------------

class TestTemplatesPresent(unittest.TestCase):
    """Validates the templates/ directory structure (PRD §4.2)."""

    _TMPL_ROOT = _REPO_ROOT / "templates"

    def test_claude_md_template_exists(self) -> None:
        path = self._TMPL_ROOT / "CLAUDE.md.tmpl"
        self.assertTrue(
            path.exists(),
            f"templates/CLAUDE.md.tmpl missing: {path}",
        )
        self.assertGreater(
            path.stat().st_size,
            0,
            "templates/CLAUDE.md.tmpl must be non-empty",
        )

    def test_agents_md_template_exists(self) -> None:
        path = self._TMPL_ROOT / "AGENTS.md.tmpl"
        self.assertTrue(
            path.exists(),
            f"templates/AGENTS.md.tmpl missing: {path}",
        )
        self.assertIn(
            ".claude/lightmem/topics",
            path.read_text(encoding="utf-8"),
            "templates/AGENTS.md.tmpl must route Codex to the shared topic store",
        )

    def test_gitignore_template_exists(self) -> None:
        path = self._TMPL_ROOT / "gitignore.tmpl"
        self.assertTrue(
            path.exists(),
            f"templates/gitignore.tmpl missing: {path}",
        )

    def test_gitignore_template_lists_runtime_artifacts(self) -> None:
        """PRD §5.5: non-committable runtime artifacts must be gitignored."""
        path = self._TMPL_ROOT / "gitignore.tmpl"
        if not path.exists():
            self.skipTest(f"templates/gitignore.tmpl not yet created: {path}")
        content = path.read_text(encoding="utf-8")
        for artifact in ("journal.jsonl", "sessions/", "state.json"):
            with self.subTest(artifact=artifact):
                self.assertIn(
                    artifact,
                    content,
                    f"templates/gitignore.tmpl must list '{artifact}' "
                    f"(PRD §5.5 non-committable state)",
                )

    def test_topic_templates_present(self) -> None:
        """PRD §4.2: templates/topics/ must have mission.md, architecture.md, roadmap.md."""
        topics_dir = self._TMPL_ROOT / "topics"
        for filename in ("mission.md", "architecture.md", "roadmap.md"):
            with self.subTest(file=filename):
                path = topics_dir / filename
                self.assertTrue(
                    path.exists(),
                    f"templates/topics/{filename} missing: {path}",
                )

    def test_topic_template_subdirs_present(self) -> None:
        """PRD §4.2 / §5.3: subdirectories decisions/, constraints/, workflows/,
        gotchas/ must each exist with at least one example file."""
        topics_dir = self._TMPL_ROOT / "topics"
        for subdir_name in ("decisions", "constraints", "workflows", "gotchas"):
            with self.subTest(subdir=subdir_name):
                subdir = topics_dir / subdir_name
                self.assertTrue(
                    subdir.exists() and subdir.is_dir(),
                    f"templates/topics/{subdir_name}/ directory missing: {subdir}",
                )
                example_files = list(subdir.iterdir())
                self.assertGreater(
                    len(example_files),
                    0,
                    f"templates/topics/{subdir_name}/ must contain at least one "
                    f"example file (found none in {subdir})",
                )


if __name__ == "__main__":
    unittest.main()
