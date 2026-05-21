# vendor/ecc-reference/ — pinned snapshot for porting

This directory holds a **read-only, version-pinned reference copy** of selected files from the [ECC](https://github.com/affaan-m/ECC) project (MIT-licensed by Affaan Mustafa). It is **not** part of LightMem's runtime — no LightMem code imports from here. The files exist as a stable source for porting specific patterns into LightMem.

## Provenance

| Field | Value |
|-------|-------|
| Upstream | https://github.com/affaan-m/ECC |
| Pinned commit | `1e8c7e7994223e0ff337d1626cd08e04a1ae67ed` |
| Commit date | 2026-05-19 |
| License | MIT (see [LICENSE](LICENSE)) |
| Pulled into LightMem on | 2026-05-21 |

## Files vendored

| Path | Lines | Why kept |
|------|-------|----------|
| `.claude-plugin/plugin.json` | small | Minimal plugin manifest pattern (skills/commands array form) |
| `hooks/memory-persistence/README.md` | small | "reference vs live hook config" doc pattern |
| `hooks/memory-persistence/hooks.json` | small | Lifecycle contract format (events array, blocking flag) |
| `scripts/hooks/session-start.js` | 706 | Source of: `hookSpecificOutput.additionalContext` JSON envelope, `limitSessionStartContext` truncation marker, **stale-replay guard** envelope (issue #1534), `selectMatchingSession` (worktree > project-name matching), env-var kill switches (`ECC_SESSION_START_*`) |
| `scripts/hooks/session-end.js` | 328 | Source of: `SUMMARY_START_MARKER`/`END_MARKER` constants, transcript-UUID → shortId derivation (issue #1494), `buildSessionHeader` standardized format, `MAX_STDIN = 1MB` cap, idempotent block replacement via marker regex |
| `scripts/hooks/pre-compact.js` | 48 | Minimal PreCompact pattern (log + append marker) |
| `skills/continuous-learning-v2/hooks/observe.sh` | 498 | Source of: **secret-scrub regex** (lines 271-276), 5-layer skip guards (entrypoint / `ECC_HOOK_PROFILE` / `ECC_SKIP_OBSERVE` / `agent_id` / path exclusions), file-size rotation via atomic rename, `_is_windows_app_installer_stub` Windows guard — kept as **future reference** for v0.4+ observer work, not v0.1 |

## What gets ported and when

See [`../../ROADMAP.md`](../../ROADMAP.md) §6 "ECC snippet port schedule". Each LightMem `lib/*.py` file that originates from ECC must:

1. Carry a `# Adapted from ECC (MIT) — <upstream-path>:<line-range>` header
2. Be reviewed against the pinned snapshot here, not against upstream HEAD
3. Be listed in the root [`../../LICENSE-NOTICE.md`](../../LICENSE-NOTICE.md)

## What is *not* vendored

- ECC's continuous-learning observer system (observer-loop, observer agent, instinct-cli) — out of scope for LightMem v0.1-v0.3
- ECC's 230+ unrelated skills
- ECC's `scripts/lib/` (utils.js, observer-sessions.js, session-aliases.js, etc.) — we'll port primitives we need, not whole modules
- ECC's tests — LightMem has its own test plan in ROADMAP §5

## Updating

This snapshot is **deliberately stale**. We do not auto-sync with upstream. To refresh:

1. Decide what new pattern from upstream is worth pulling
2. `git clone` the upstream at the new commit
3. Copy the specific files needed; update the commit SHA in this README
4. Re-review affected ported code in `lib/`
5. Update `ROADMAP.md` if scope changes

The whole point of vendoring is to **decouple** LightMem's evolution from ECC's. Resist the urge to keep both in lockstep.
