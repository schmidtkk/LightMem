# Memory Persistence Hooks

These lifecycle hook definitions document LightMem's memory persistence contract for the Claude Code plugin.

This directory is the **stable, human-readable lifecycle definition surface** — not the active hook configuration. The live config loaded by Claude Code is [`hooks/hooks.json`](../hooks.json).

The executable implementations live in `scripts/hooks/`:

- `session_start.py` — detects repo state, injects bounded prior context or a first-run suggestion.
- `stop.py` — appends one JSONL audit line to `journal.jsonl` after each assistant turn (async).
- `session_end.py` — writes a per-session summary file under `.claude/lightmem/sessions/`.
- `pre_compact.py` — logs a compaction event and annotates the active session file.

## Lifecycle Contract

| Event | Hook ID | Script | Purpose | Blocking |
|---|---|---|---|---|
| `SessionStart` | `lightmem:session-start` | `scripts/hooks/session_start.py` | Detect repo state; inject compact hot context (initialized) or single-line nudge (uninitialized) via `additionalContext`. Matcher: `startup\|resume`. | no |
| `Stop` | `lightmem:stop` | `scripts/hooks/stop.py` | Append one JSONL entry to `journal.jsonl` after every assistant turn. Async — zero perceived latency. Scrubs secrets before persisting. | no (async) |
| `SessionEnd` | `lightmem:session-end` | `scripts/hooks/session_end.py` | Write per-session summary to `.claude/lightmem/sessions/<date>-<shortId>.md` using idempotent marker blocks. Runs once-per-day auto-purge of old sessions and archive files. | no |
| `PreCompact` | `lightmem:pre-compact` | `scripts/hooks/pre_compact.py` | Append a timestamped line to `compaction-log.txt`; annotate the active session file. Minimal by design — no state synthesis. | no |

## Operator Expectations

- All hooks check `LIGHTMEM_HOOK_PROFILE` and `LIGHTMEM_DISABLED_HOOKS` before any I/O and early-return if disabled.
- `LIGHTMEM_HOOK_PROFILE=off` short-circuits every hook with zero filesystem writes.
- Context injected at session start is bounded by `LIGHTMEM_SESSION_START_MAX_CHARS` (default 8000 bytes).
- Any prior-session content is wrapped in a mandatory stale-replay guard envelope (see `scripts/lib/injection.py`).
- Every hook exits 0 on any internal exception — hooks must never disrupt the agent.

## Related Files

- [`hooks/hooks.json`](../hooks.json) — live hook graph (auto-loaded by Claude Code)
- [`hooks/memory-persistence/hooks.json`](hooks.json) — this directory's reference copy
- [`scripts/hooks/session_start.py`](../../scripts/hooks/session_start.py)
- [`scripts/hooks/stop.py`](../../scripts/hooks/stop.py)
- [`scripts/hooks/session_end.py`](../../scripts/hooks/session_end.py)
- [`scripts/hooks/pre_compact.py`](../../scripts/hooks/pre_compact.py)
- [`scripts/lib/injection.py`](../../scripts/lib/injection.py) — stale-replay guard + output envelope
- [`PRD_v0.2.md`](../../PRD_v0.2.md) §6 — full hook behavior specification
