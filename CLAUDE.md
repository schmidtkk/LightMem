# LightMem — Plugin Source Repository

LightMem is a Claude Code plugin that turns any repo into a structured, team-shareable, gateway-routed project memory database. This repository is the plugin's source; **do not install LightMem into this repo itself.**

## Authoritative documents

- **README:** [`README.md`](./README.md) — user-facing intro, install, slash commands.
- **Plan:** [`ROADMAP.md`](./ROADMAP.md) — versioned roadmap v0.1 through v0.5, risk register, ECC port schedule.
- **Attribution:** [`LICENSE-NOTICE.md`](./LICENSE-NOTICE.md) — ECC patterns adopted, per-file lineage.

## Design invariants

Changing any of these is a breaking design change. Discuss before changing.

- **Runtime and layout:** pure-stdlib Python 3.10+; project state in `<repo>/.claude/lightmem/` with gitignore for non-committable parts; hook scripts under `scripts/hooks/`, shared lib under `scripts/lib/`.
- **Hook semantics:** `Stop` runs `async: true` — zero perceived latency; `Stop` is journal-only, no auto-promotion of markers to topics; every hook exits 0 on any internal exception.
- **Bootstrap and UX:** first-run hook detects and suggests, never creates files; `/lightmem:init` offers interactive 3-option CLAUDE.md handling (append-fenced default, backup+rewrite, abort); no LLM calls inside any hook.
- **Memory model:** `CLAUDE.md` is the L0 gateway (router), not the database; hard limits ≤8 KB warn, ≤16 KB fail; no glob imports from CLAUDE.md.
- **Safety and privacy:** zero telemetry in v0.1; secrets scrubbed from journal, session files, and topic bodies before write; `LIGHTMEM_HOOK_PROFILE=off` short-circuits all hooks with zero I/O.

## v0.1 hooks

Four hooks are registered in [`hooks/hooks.json`](./hooks/hooks.json):

| Event | Script | Mode |
|-------|--------|------|
| `SessionStart` | `scripts/hooks/session_start.py` | sync, matcher `startup\|resume` |
| `Stop` | `scripts/hooks/stop.py` | async |
| `SessionEnd` | `scripts/hooks/session_end.py` | sync |
| `PreCompact` | `scripts/hooks/pre_compact.py` | sync |

Reference documentation (lifecycle contract, not loaded by Claude Code): [`hooks/memory-persistence/`](./hooks/memory-persistence/).

## Vendor pinning policy

`vendor/ecc-reference/` is a pinned, read-only snapshot of ECC at commit `1e8c7e7`. Do not auto-update it. Update deliberately, with a matching row added to [`LICENSE-NOTICE.md`](./LICENSE-NOTICE.md) for any newly ported pattern.

## Working language

All artifacts must be in English: code, comments, identifiers, file names, commit messages, documentation. Conversation with the user may be in any language.

## Rules for Claude when working in this repo

- Do not create `.claude/lightmem/` inside this repo — it would nest the system under itself.
- Do not introduce third-party Python dependencies; pure stdlib only.
- Skill files live under `skills/lightmem/<name>/SKILL.md` with full namespace `/lightmem:<name>`.
- Run `python3 -W error -m unittest discover tests` before declaring any change complete.
