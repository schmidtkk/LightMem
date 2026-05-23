# LightMem Roadmap

> **Status:** v0.1.0 released. Suite 867/867 green under `python3 -W error -m unittest discover tests`.

---

## v0.1.0 — MVP (current)

Shipped:

- 4 hooks wired in `hooks/hooks.json`: `SessionStart`, `Stop` (async), `SessionEnd`, `PreCompact`.
- 3 skills: `/lightmem:init` (interactive bootstrap, 3-option CLAUDE.md handling), `/lightmem:doctor` (17 integrity checks), `/lightmem:index` (regenerate topic index).
- 14 lib modules under `scripts/lib/` (pure-stdlib Python 3.10+, zero external deps).
- 17 doctor checks: CLAUDE.md size, gateway presence, frontmatter validity, slug uniqueness, broken links, secret scan across journal + topics + sessions, archive purge freshness, premature `inbox/`.
- Secret scrubbing regex applied on every write path.
- Stale-replay guard wrapper around any historical-content injection (inoculation against ECC issue #1534).
- 867 tests (unit + integration via real subprocess + plugin wiring).
- 7 ECC-derived files individually attributed in [`LICENSE-NOTICE.md`](./LICENSE-NOTICE.md).

---

## v0.1.1 — hardening (next)

Independent review of v0.1.0 surfaced 6 follow-up items beyond the 3 HIGH ship-blockers (already fixed before tag):

| # | Severity | Item | File |
|---|----------|------|------|
| C4 | MEDIUM | Stale-replay guard is instruction-only — does not escape slash commands / `ARGUMENTS=` / "ignore above" content inside the historical summary. Reduces issue #1534 likelihood but does not defeat the class structurally. Plan: escape command-like lines, add a postlude reminder. | `scripts/lib/injection.py` |
| C5 | MEDIUM | `_prior_session_summary()` reverse-sorts all `*.md` and injects the newest — doesn't match worktree/project as it should. Multi-worktree repos may inject unrelated history. | `scripts/hooks/session_start.py` |
| C6 | MEDIUM | Budget documented as bytes but enforced as Python characters; CJK/emoji-heavy context can exceed UTF-8 byte budget by up to 4×. | `scripts/lib/budget.py` |
| C7 | MEDIUM | `secret_scan` regex matches normal prose like `"token budget planning"`. Make doctor findings warnings unless separator is `:`/`=`, or use stricter keyword-specific patterns. | `scripts/lib/scrub.py`, `scripts/lib/doctor.py` |
| C8 | LOW | Link checker doesn't strip URL fragments — `[x](target.md#section)` looks broken because the literal `#section` is included in the resolved path. | `scripts/lib/doctor.py` |
| C9 | LOW | Integration tests use `sys.executable + PYTHONPATH`, not the live `python3 "${CLAUDE_PLUGIN_ROOT}/..."` shell command. A `sys.path.insert` bootstrap regression would slip through. Add a smoke test that evaluates the actual command string with a space-containing plugin root. | `tests/integration/test_hook_session_start.py`, `hooks/hooks.json` |

---

## v0.2.0 — manual curation + Windows

### Memory architecture (settled design)

```
Authoritative  →  .claude/lightmem/topics/          ← single source of truth
Gateways       →  CLAUDE.md, AGENTS.md              ← routing only, no facts
Runtime        →  journal.jsonl, sessions/, archive/ ← audit / continuity
Native memory  →  personal / session cache only      ← never project source of truth
```

Direction is one-way: **native memory → LightMem topics**. No bidirectional sync.
Every write to `topics/` requires explicit human confirmation.

### Gateway hard rule (enforced in CLAUDE.md gateway block and skills)

`update mem` / `记住` / `写入项目记忆` → `/lightmem:update` only.
Direct writes to `CLAUDE.md` body are forbidden for durable project facts.

### Deliverables

- **`/lightmem:mark <text>`** — zero-friction inbox append; no confirmation required.
- **`[mem]` inline tag** — `UserPromptSubmit` hook scans user messages; lines containing `[mem]` are extracted and appended to `inbox/pending.md` automatically.
- **`inbox/pending.md`** — staging area; `inbox.py` lib (`append_pending`, `read_pending`, `clear_pending`, `extract_mem_tags`).
- **`/lightmem:update`** — reads inbox + Claude/Codex native project memory, presents candidates, user confirms per-item, writes to `topics/`, patches `index.md` incrementally.
- **`patch_index_entry(repo_root, topic_id)`** in `index_builder.py` — updates or inserts one row without full rebuild.
- **`UserPromptSubmit` hook** in `hooks/hooks.json` — pure stdlib, exits 0 on any error.
- Windows support: file locking fallback chain, shell-quoting paths, CRLF handling already in v0.1 H3 fix.
- Worktree-aware resume-injection (C5 above) lands here.

---

## v0.3.0 — Codex adapter + retrieval

### Codex adapter

Principle: **adapt each agent to LightMem's topic store, not the reverse.**

- `templates/AGENTS.md.tmpl` — Codex gateway; reads same `.claude/lightmem/topics/`; contains no project facts.
- `.codex-plugin/plugin.json` + Codex hooks (lifecycle remapped: no `SessionEnd` equivalent → use `Stop`/`PostCompact`).
- Codex slash commands: `/lightmem:update`, `/lightmem:mark`, `/lightmem:doctor` reusing Python core.
- Enhanced `/lightmem:doctor`: checks that both `CLAUDE.md` and `AGENTS.md` gateways exist and point to the same `topics/`; warns if native memory contains project facts.

### Retrieval

- `UserPromptSubmit` hook with SQLite FTS5 search over `topics/*.md` bodies + frontmatter.
- Inject top 3-5 relevant snippets per prompt, capped at 2 KB total.
- `/lightmem:retrieve <query>` for manual queries.

---

## v0.4.0 — opt-in background curator

- `agents/lightmem-curator.md` Haiku subagent (opt-in, default off).
- All 13 ECC observer safeguards adopted as table stakes: self-loop prevention, signal throttling, cooldown, idle exit, secret scrub, atomic rotation, stale-PID cleanup, lock fallback chain, agent_id filter, entrypoint whitelist, path exclusions, file-size rotation, auto-purge.
- `inbox/` reintroduced for human-in-the-loop review.

---

## v0.5.0 — semantic retrieval + monorepo

- Optional `sentence-transformers` semantic retrieval (extras_require).
- Monorepo path-scoped memory via `CwdChanged` hook.

---

## Risk register

Inherited footgun classes that LightMem inoculates against:

| # | Risk | Upstream incident | LightMem fix |
|---|------|-------------------|--------------|
| RK1 | Stale-replay: model re-executes old slash commands from injected summary | ECC #1534 | `injection.STALE_REPLAY_GUARD_PRELUDE` wraps any historical content |
| RK2 | Subprocess overwrites parent session file when `session_id` is shared | ECC #1494 | `session_id.derive_short_id` keys on `transcript_path` UUID, not `session_id` |
| RK3 | Self-observation runaway when background LLM observes its own tool calls | ECC #521 | v0.1 has zero background LLM; v0.4 must adopt all 13 ECC safeguards before enabling |
| RK4 | Secret leakage to disk | — | `scrub.scrub()` on every write path: journal entries, session summaries, doctor scans of topic bodies |
| RK5 | Merge conflicts on shared index | — | Per-file frontmatter (no central `index.json`); filesystem IS the index |
| RK6 | CLAUDE.md context bloat | — | Doctor `claude_md_size_warn` (8 KB) / `claude_md_size_fail` (16 KB) |
| RK7 | Hook latency breaks UX | — | Stop hook `async: true`; all hooks `exit 0` on error |
| RK8 | Cross-platform path / lock differences | — | Linux + macOS in v0.1, Windows in v0.2 |

---

## Anti-roadmap (things LightMem will NOT do)

- **Personal-pattern instinct learning.** That problem belongs to other tools; LightMem is project knowledge, not user behavior.
- **Auto-promotion from journal to topics without human review.** Even with v0.4's curator, promotion is human-in-the-loop.
- **Cross-project / global memory aggregation.** LightMem is repo-local. User cross-project preferences belong in `~/.claude/CLAUDE.md`.
- **Repo-history mining.** One-shot import is fine in v0.5 if asked, but not core.
- **Hosted/cloud sync.** Memory is git-versioned; that is the sync mechanism.
- **Telemetry of any kind.** Locked invariant.
