<div align="center">

# 🧠 LightMem

**Structured project memory for Claude Code.**

🌐 **[English](#english)** · **[中文](#中文-zh)**

</div>

---

<a id="english"></a>

# English

> **Structured project memory for Claude Code.**
> CLAUDE.md is the gateway. `.claude/lightmem/topics/` is the database.

Tired of re-explaining your repo to Claude on every session? LightMem maintains a structured, team-shareable knowledge base under `.claude/lightmem/` that survives every session, every compaction, every agent swap — and lives in plain markdown that keeps working even if you uninstall the plugin.

```
┌─────────────────────────────────────────────────────────────────────┐
│  every new Claude Code session                                      │
│                                                                     │
│   SessionStart hook  ─►  composes hot context  ─►  inject ≤8 KB     │
│         ▲                                                           │
│         │   reads from                                              │
│         │                                                           │
│  ┌──────┴──────────────────────────────────────────┐                │
│  │ .claude/lightmem/topics/                        │                │
│  │   ├─ mission.md          (singleton)            │                │
│  │   ├─ architecture.md                            │                │
│  │   ├─ roadmap.md                                 │                │
│  │   ├─ decisions/    *.md  (ADR-style)            │                │
│  │   ├─ constraints/  *.md  (non-negotiables)      │                │
│  │   ├─ gotchas/      *.md  (known failure modes)  │                │
│  │   └─ workflows/    *.md  (recurring ops)        │                │
│  └─────────────────────────────────────────────────┘                │
│         ▲                                                           │
│         │ user curates via /lightmem:init, /lightmem:doctor         │
│                                                                     │
│   Stop hook  ─►  append-only journal.jsonl  (per turn, scrubbed)    │
│   SessionEnd ─►  marker-fenced session summary                      │
│   PreCompact ─►  compaction log                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Why LightMem?

|                                     | Native CLAUDE.md alone | LightMem |
|-------------------------------------|------------------------|----------|
| Loaded every session                | ✅                     | ✅ (as gateway router) |
| Structured by semantic kind         | ❌ flat prose          | ✅ decisions / constraints / gotchas / workflows / mission / architecture / roadmap |
| Team-shareable via `git`            | ⚠️ but bloats fast     | ✅ topics dir is committable; runtime state gitignored |
| Indexed & searchable                | ❌ grep only           | ✅ filesystem **is** the index — no central JSON to merge-conflict |
| Survives plugin removal             | n/a                    | ✅ pure markdown — uninstall the plugin, your knowledge stays |
| Auto-injects on session start       | ❌ user must remember  | ✅ `SessionStart` hook composes a compact summary |
| Per-turn audit log                  | ❌                     | ✅ `Stop` hook journals every turn (with secret scrubbing) |
| Stale-replay attack guard           | ❌                     | ✅ inherited from ECC issue #1534 |
| Secret scrubbing on every write     | ❌                     | ✅ regex on `journal.jsonl`, session files, topic bodies |
| LLM calls in hot path               | n/a                    | ❌ **zero in v0.1** — pure stdlib Python, deterministic |
| Cost per session                    | $0                     | **$0** (no background LLM in v0.1) |

LightMem solves a different problem from "auto-learning user preferences" plugins like [ECC](https://github.com/affaan-m/ECC): it captures **durable project knowledge** — the kind of thing a new teammate needs on day one — not personal coding habits.

## Install

LightMem ships as a Claude Code marketplace plugin. Three install paths:

**1. Try it once (no install)**

```bash
git clone https://github.com/schmidtkk/LightMem.git ~/LightMem
claude --plugin-dir ~/LightMem
```

The plugin is active for that session only. Good for kicking the tires.

**2. Install permanently from local clone**

```bash
git clone https://github.com/schmidtkk/LightMem.git ~/LightMem
claude plugin marketplace add ~/LightMem
claude plugin install lightmem@lightmem
```

Use `--scope project` to share with your team (pinned in `.claude/settings.json`), or `--scope local` (gitignored) for a personal install on a specific repo.

**3. Install from GitHub**

```bash
claude plugin marketplace add schmidtkk/LightMem
claude plugin install lightmem@lightmem
```

**Verify**

```bash
claude
> /lightmem:doctor
```

You should see 17 checks. On an uninitialized repo, several will warn — that's expected. Run `/lightmem:init` to fix them.

## Quick start (5 minutes to value)

```bash
cd ~/my-research-project
claude
```

First session in an uninitialized repo, you'll see:

```
LightMem detected this repo has no memory. Run `/lightmem:init` to set up.
```

Initialize:

```
> /lightmem:init
```

LightMem will:
1. Detect any existing `CLAUDE.md` and ask: append fenced block (default), backup+rewrite, or abort.
2. Create the `.claude/lightmem/` skeleton with 7 topic templates.
3. Write a `.gitignore` so runtime artifacts stay out of git.

Now open `.claude/lightmem/topics/mission.md`, write one paragraph about what your repo is for. Add a constraint. Record a decision. Commit them. **From the next session onward, Claude sees them automatically — no re-explaining.**

## Slash commands

| Command | What it does |
|---------|--------------|
| `/lightmem:init` | Interactive bootstrap. Detects existing CLAUDE.md, offers 3 modes (append-fenced default, backup+rewrite, abort). Idempotent on re-runs. |
| `/lightmem:doctor` | 17 integrity checks: size limits, gateway presence, frontmatter validity, slug collisions, broken links, secret scan (journal + topics + sessions), archive purge freshness, premature `inbox/`. |
| `/lightmem:index` | Regenerate `.claude/lightmem/index.md` (human-readable topic table) from frontmatter. |

Future (see [ROADMAP.md](./ROADMAP.md)):

| Command | Version | What it will do |
|---------|---------|------------------|
| `/lightmem:update` | v0.2 | Convert recent discussion into proposed topic edits (manual curation). |
| `/lightmem:retrieve <query>` | v0.3 | SQLite FTS5 search; auto-inject relevant topics via `UserPromptSubmit`. |
| `/lightmem:curate` | v0.4 | Opt-in Haiku-driven background curator with 13 ECC safeguards. |

## Environment variables

| Variable | Default | Effect |
|----------|---------|--------|
| `LIGHTMEM_HOOK_PROFILE` | `standard` | `standard` / `minimal` / `off`. `off` short-circuits every hook with zero I/O. |
| `LIGHTMEM_DISABLED_HOOKS` | (empty) | Comma-separated canonical event names to skip, e.g. `Stop,SessionEnd`. |
| `LIGHTMEM_SESSION_START_MAX_CHARS` | `8000` | Cap on injected `additionalContext` size. |
| `LIGHTMEM_SESSION_START_CONTEXT` | (unset) | `off` / `0` / `false` disables injection entirely. |
| `LIGHTMEM_RETENTION_DAYS` | `30` | Auto-purge threshold for `sessions/` and `archive/`. |
| `LIGHTMEM_JOURNAL_MAX_MB` | `5` | Rotation threshold for `journal.jsonl`. |
| `LIGHTMEM_LOG_LEVEL` | `WARNING` | stdlib `logging` level (stderr only, never stdout). |
| `LIGHTMEM_LOG_FILE` | `.claude/lightmem/lightmem.log` | Where hook scripts log. |

## What gets created

```
your-repo/
├── CLAUDE.md                            # gateway block fenced inside
└── .claude/
    └── lightmem/
        ├── .gitignore                   # excludes runtime artifacts
        ├── state.json                   # schema_version, installed_at
        ├── topics/                      # ★ commit these ★
        │   ├── mission.md
        │   ├── architecture.md
        │   ├── roadmap.md
        │   ├── decisions/example-decision.md
        │   ├── constraints/example-constraint.md
        │   ├── gotchas/example-gotcha.md
        │   └── workflows/example-workflow.md
        ├── journal.jsonl                # gitignored — per-turn audit log
        ├── sessions/                    # gitignored — marker-fenced summaries
        └── archive/                     # gitignored — rotated journals
```

Commit `topics/*.md`. Everything else is runtime state.

## How it works

1. **`SessionStart`** — on uninitialized repo injects a single nudge. On initialized repo composes a compact summary (mission head + active constraints + topic counts + recent decisions, ≤8 KB) and injects via `additionalContext`. On `source=resume` appends the matching prior-session summary wrapped in a **stale-replay guard** (inoculation against ECC issue #1534).
2. **`Stop`** (async) — atomically appends a JSONL entry (timestamp, session_id, transcript UUID tail, git branch, model, SHA-256 hash, scrubbed 200-char excerpt, touched files) to `journal.jsonl`. Honors `stop_hook_active` re-entry guard. Rotates at 5 MB.
3. **`SessionEnd`** — walks transcript, writes marker-fenced summary to `sessions/<date>-<shortId>.md`. Re-runs replace only the fenced region. Auto-purges old archives once per day.
4. **`PreCompact`** — appends to `compaction-log.txt` and annotates today's session file. <30 LOC. Observation, not synthesis.

All four hooks: **pure stdlib Python**, **zero LLM calls**, **`sys.exit(0)` on any exception**, **deterministic**.

## Features

- 🎯 **Structured topic taxonomy** — 7 semantic kinds map to how humans actually structure project knowledge
- 📦 **Team-shareable via git** — `topics/` is committable; runtime state is auto-gitignored
- 🛡️ **Security-first** — secret-scrubbing regex on every write path
- 🚪 **Marker-fenced idempotency** — hooks mutate only `<!-- LIGHTMEM:X:START -->...END -->` regions
- 🩺 **Doctor with 17 concrete checks** — every check has an executable predicate
- 🎛️ **Killswitch env vars** — `LIGHTMEM_HOOK_PROFILE=off` short-circuits all I/O
- 🧪 **867 tests under `python3 -W error`** — unit + integration + plugin wiring
- 🪶 **Pure stdlib** — Python 3.10+. Zero dependencies. Zero `pip install`.
- 📜 **Survives plugin removal** — your topic markdowns work without LightMem installed

## FAQ

<details>
<summary><b>Why not just put everything in CLAUDE.md?</b></summary>

CLAUDE.md is loaded into every session's context budget. Letting it grow unboundedly burns tokens and entangles stable rules with episodic state. LightMem treats CLAUDE.md as an L0 router (≤8 KB warn / ≤16 KB fail) and puts the actual database in `.claude/lightmem/topics/`, only injecting a compact summary per session.
</details>

<details>
<summary><b>How is this different from ECC?</b></summary>

ECC learns your **personal coding patterns** (per-user, per-machine, outside your repo). LightMem captures **project-level decisions and constraints** that need to travel with the codebase. They're orthogonal — you can run both. LightMem borrows ECC's battle-tested patterns but solves a different problem.
</details>

<details>
<summary><b>Does it call any LLMs?</b></summary>

**No — zero LLM calls in v0.1.** Every hook is deterministic stdlib Python. v0.4 will add an opt-in background curator (Haiku), strictly opt-in and disabled by default.
</details>

<details>
<summary><b>What happens to my existing CLAUDE.md?</b></summary>

`/lightmem:init` detects it and asks: (1) append a fenced LightMem block (recommended; existing content untouched), (2) backup to `CLAUDE.md.bak.<ts>` and rewrite from template, or (3) abort and print the block for manual paste. Re-running `/lightmem:init` replaces only the fenced region.
</details>

<details>
<summary><b>What about Windows?</b></summary>

v0.1 is tested on Linux and macOS. Windows is on the v0.2 roadmap — most code is platform-agnostic, file locking and shell-quoting need explicit Windows handling.
</details>

<details>
<summary><b>How do I disable LightMem temporarily?</b></summary>

```bash
LIGHTMEM_HOOK_PROFILE=off claude
```

Every LightMem hook short-circuits before any I/O. Equivalent to uninstalling without touching files.
</details>

<details>
<summary><b>Where does my memory live? Is it sent anywhere?</b></summary>

Entirely local to your repo at `.claude/lightmem/`. **Zero telemetry, zero network calls** (D13 in PRD §2 — locked invariant). Committed topics are visible to whoever has access to your repo; runtime artifacts stay machine-local because they're gitignored.
</details>

<details>
<summary><b>Per-repo install only (not global)?</b></summary>

```bash
claude plugin install lightmem@lightmem --scope project   # team-shared
claude plugin install lightmem@lightmem --scope local     # personal, gitignored
```
</details>

## Roadmap

- [x] **v0.1.0** — MVP: 4 hooks, 3 skills, 17 doctor checks, 867 tests. Secret scrubbing on all write paths. Stale-replay guard. (this release)
- [ ] **v0.2.0** — `/lightmem:update` skill. Windows support. Worktree-aware resume injection.
- [ ] **v0.3.0** — `UserPromptSubmit` retrieval over SQLite FTS5.
- [ ] **v0.4.0** — Opt-in Haiku curator subagent with all 13 ECC observer safeguards.
- [ ] **v0.5.0** — Optional `sentence-transformers` semantic retrieval. Monorepo path-scoping.

Full plan + risk register: [ROADMAP.md](./ROADMAP.md).

## Documentation

| Doc | What it is |
|-----|------------|
| [ROADMAP.md](./ROADMAP.md) | v0.1 → v0.5 plan, risk register, v0.1.1 backlog. |
| [CLAUDE.md](./CLAUDE.md) | Plugin source repo gateway / contributor guide. |
| [LICENSE-NOTICE.md](./LICENSE-NOTICE.md) | ECC attribution + ported-files table. |

## Acknowledgements

LightMem borrows battle-tested patterns from [ECC](https://github.com/affaan-m/ECC) (MIT, by Affaan Mustafa): the stale-replay guard text, secret-scrub regex, marker-fenced idempotent block updates, transcript-UUID-based session file naming (fixes ECC upstream issue #1494), and the reference-vs-live hook config separation pattern. Each ported file carries an attribution header pointing to the pinned upstream commit; full table in [LICENSE-NOTICE.md](./LICENSE-NOTICE.md).

## Contributing

```bash
python3 -W error -m unittest discover tests
```

Suite must be green (867/867). Style: pure stdlib Python 3.10+, `from __future__ import annotations` at top of every file, type hints on public functions, no function docstrings (WHY-only `#` comments), all identifiers in English. ECC-derived files must carry the attribution header (see [LICENSE-NOTICE.md](./LICENSE-NOTICE.md)).

## License

[MIT](./LICENSE). © 2026 LightMem contributors.

---

<a id="中文-zh"></a>

# 中文

> **给 Claude Code 用的结构化项目记忆。**
> CLAUDE.md 是网关入口。`.claude/lightmem/topics/` 才是数据库。

每次 session 都要跟 Claude 重新解释一遍项目背景？LightMem 在 `.claude/lightmem/` 下维护一份**结构化、团队可共享**的知识库，跨 session、跨 compaction、跨 agent 切换都不丢失——而且全部是纯 markdown，**即使卸载插件也照样能读**。

```
┌─────────────────────────────────────────────────────────────────────┐
│  每一次新的 Claude Code session                                     │
│                                                                     │
│   SessionStart hook  ─►  组合热上下文  ─►  注入 ≤8 KB               │
│         ▲                                                           │
│         │   读取自                                                  │
│         │                                                           │
│  ┌──────┴──────────────────────────────────────────┐                │
│  │ .claude/lightmem/topics/                        │                │
│  │   ├─ mission.md          (单例)                 │                │
│  │   ├─ architecture.md                            │                │
│  │   ├─ roadmap.md                                 │                │
│  │   ├─ decisions/    *.md  (ADR 风格的决策)       │                │
│  │   ├─ constraints/  *.md  (硬约束)               │                │
│  │   ├─ gotchas/      *.md  (已知陷阱)             │                │
│  │   └─ workflows/    *.md  (常用流程)             │                │
│  └─────────────────────────────────────────────────┘                │
│         ▲                                                           │
│         │ 用户通过 /lightmem:init、/lightmem:doctor 维护             │
│                                                                     │
│   Stop hook  ─►  追加 journal.jsonl  (每个 turn,带密钥涂抹)         │
│   SessionEnd ─►  marker 围栏的 session 摘要                         │
│   PreCompact ─►  压缩日志                                           │
└─────────────────────────────────────────────────────────────────────┘
```

## 为什么用 LightMem？

|                                | 仅靠原生 CLAUDE.md     | LightMem |
|--------------------------------|------------------------|----------|
| 每次 session 加载              | ✅                     | ✅ (作为网关路由) |
| 按语义分类结构化               | ❌ 平铺散文            | ✅ 决策/约束/陷阱/流程/使命/架构/路线图 |
| 通过 `git` 团队共享            | ⚠️ 但极易膨胀          | ✅ topics 目录可提交；运行时状态自动 gitignore |
| 可索引可检索                   | ❌ 只能 grep           | ✅ 文件系统**就是**索引——无中心化 JSON，没合并冲突 |
| 卸载插件后能否继续工作         | n/a                    | ✅ 纯 markdown——卸载插件，知识仍在 |
| Session 开始自动注入           | ❌ 用户得自己记得      | ✅ `SessionStart` hook 自动组合压缩摘要 |
| 每个 turn 的审计日志           | ❌                     | ✅ `Stop` hook 自动 journal（带密钥涂抹） |
| 防 stale-replay 攻击           | ❌                     | ✅ 继承自 ECC issue #1534 修复 |
| 每个写入路径的密钥涂抹         | ❌                     | ✅ regex 覆盖 `journal.jsonl` / sessions / topic 正文 |
| 热路径里调 LLM                 | n/a                    | ❌ **v0.1 零调用**——纯 stdlib Python，确定性 |
| 每个 session 的成本            | $0                     | **$0** (v0.1 无后台 LLM) |

LightMem 跟 [ECC](https://github.com/affaan-m/ECC) 这类"自动学习用户偏好"的插件解决的是**不同问题**：它捕获**项目级的持久知识**——新队友第一天上手需要看到的东西——而不是个人编码习惯。

## 安装

LightMem 作为 Claude Code marketplace 插件发布。三种安装方式：

**1. 一次性试用（不安装）**

```bash
git clone https://github.com/schmidtkk/LightMem.git ~/LightMem
claude --plugin-dir ~/LightMem
```

仅当前 session 生效。试水用。

**2. 从本地 clone 永久安装**

```bash
git clone https://github.com/schmidtkk/LightMem.git ~/LightMem
claude plugin marketplace add ~/LightMem
claude plugin install lightmem@lightmem
```

加 `--scope project` 共享给团队（写入 `.claude/settings.json`），加 `--scope local` 走 gitignore 仅个人使用。

**3. 直接从 GitHub 安装**

```bash
claude plugin marketplace add schmidtkk/LightMem
claude plugin install lightmem@lightmem
```

**验证**

```bash
claude
> /lightmem:doctor
```

应该看到 17 项检查。未初始化的 repo 会有几条 warn，正常——跑 `/lightmem:init` 修复。

## 5 分钟快速上手

```bash
cd ~/my-research-project
claude
```

未初始化 repo 的第一个 session 你会看到：

```
LightMem detected this repo has no memory. Run `/lightmem:init` to set up.
```

初始化：

```
> /lightmem:init
```

LightMem 会：
1. 检测已有 `CLAUDE.md`，问你三选一：append 围栏块（默认）、备份+重写、放弃。
2. 创建 `.claude/lightmem/` 骨架 + 7 个 topic 模板。
3. 写 `.gitignore` 把运行时产物（`journal.jsonl`、`sessions/`、`state.json`）排除在外。

然后打开 `.claude/lightmem/topics/mission.md`，写一段话说明这个 repo 是干什么的。加一条约束到 `topics/constraints/`，记录一个决策到 `topics/decisions/`，提交它们。**从下一个 session 开始，Claude 自动看到这些——再也不用重复解释。**

## 斜杠命令

| 命令 | 做什么 |
|------|--------|
| `/lightmem:init` | 交互式 bootstrap。检测已有 CLAUDE.md，给三选项（默认 append-fenced / 备份重写 / 放弃）。re-run 幂等。 |
| `/lightmem:doctor` | 17 项完整性检查：大小限制、gateway 标记、frontmatter 合法性、slug 重复、坏链、密钥扫描（journal + topics + sessions）、归档清理新旧、过早出现的 `inbox/`。 |
| `/lightmem:index` | 从 frontmatter 重新生成 `.claude/lightmem/index.md`（人类可读的 topic 表格）。 |

未来版本（见 [ROADMAP.md](./ROADMAP.md)）：

| 命令 | 版本 | 做什么 |
|------|------|--------|
| `/lightmem:update` | v0.2 | 把最近对话转成候选 topic 编辑（人工 curation，hook 不调 LLM）。 |
| `/lightmem:retrieve <query>` | v0.3 | SQLite FTS5 检索；`UserPromptSubmit` 自动注入相关 topic。 |
| `/lightmem:curate` | v0.4 | opt-in Haiku 后台 curator，自带 13 条 ECC 安全网。 |

## 环境变量

| 变量 | 默认值 | 作用 |
|------|--------|------|
| `LIGHTMEM_HOOK_PROFILE` | `standard` | `standard` / `minimal` / `off`。`off` 让每个 hook 在零 I/O 处短路。 |
| `LIGHTMEM_DISABLED_HOOKS` | (空) | 逗号分隔的事件名，跳过这些 hook，例：`Stop,SessionEnd`。 |
| `LIGHTMEM_SESSION_START_MAX_CHARS` | `8000` | 注入 `additionalContext` 的硬上限。 |
| `LIGHTMEM_SESSION_START_CONTEXT` | (未设) | 设为 `off` / `0` / `false` 完全禁用注入。 |
| `LIGHTMEM_RETENTION_DAYS` | `30` | 清理 `sessions/` 和 `archive/` 的阈值。 |
| `LIGHTMEM_JOURNAL_MAX_MB` | `5` | `journal.jsonl` 轮转阈值。 |
| `LIGHTMEM_LOG_LEVEL` | `WARNING` | stdlib `logging` 级别（只写 stderr，永不污染 stdout）。 |
| `LIGHTMEM_LOG_FILE` | `.claude/lightmem/lightmem.log` | hook 脚本日志位置。 |

## 创建出来的目录结构

```
your-repo/
├── CLAUDE.md                            # 内部有围栏块，外面不动
└── .claude/
    └── lightmem/
        ├── .gitignore                   # 排除运行时产物
        ├── state.json                   # schema_version, installed_at
        ├── topics/                      # ★ 提交这些 ★
        │   ├── mission.md
        │   ├── architecture.md
        │   ├── roadmap.md
        │   ├── decisions/example-decision.md
        │   ├── constraints/example-constraint.md
        │   ├── gotchas/example-gotcha.md
        │   └── workflows/example-workflow.md
        ├── journal.jsonl                # gitignore — 每个 turn 的审计日志
        ├── sessions/                    # gitignore — marker 围栏的 session 摘要
        └── archive/                     # gitignore — 轮转后的旧 journal
```

提交 `topics/*.md`，其余都是运行时状态。

## 工作原理

1. **`SessionStart`** —— 未初始化 repo 注入一句提示。已初始化 repo 组合精炼摘要（mission 头 + active 约束 + topic 计数 + 最近决策，≤8 KB）通过 `additionalContext` 注入。`source=resume` 时追加匹配的上一个 session 摘要，外面包一层 **stale-replay 防护**（防 ECC issue #1534 类型的 bug）。
2. **`Stop`** (async) —— 原子追加一条 JSONL 记录（时间戳、session_id、transcript UUID 尾段、git branch、model、完整消息的 SHA-256、涂抹后的 200 字符摘要、被改动的文件）到 `journal.jsonl`。遵守 `stop_hook_active` 重入守卫。文件超 5 MB 自动轮转。
3. **`SessionEnd`** —— 遍历 transcript，把摘要写到 `sessions/<date>-<shortId>.md` 的 marker 围栏块里。re-run 只替换围栏内部。每天自动清理超期归档。
4. **`PreCompact`** —— 追加一行到 `compaction-log.txt`，并在今天的 session 文件里加一行标注。<30 行代码。只观察、不综合。

4 个 hook 全部：**纯 stdlib Python**、**零 LLM 调用**、**任何异常都 `sys.exit(0)`**（hook 永远不阻塞 Claude）、**完全确定性**。

## Features

- 🎯 **结构化 topic 分类** —— 7 种语义化分类，对应人类组织项目知识的真实方式
- 📦 **通过 git 团队共享** —— `topics/` 可提交；运行时状态自动 gitignore
- 🛡️ **安全优先** —— 每个写入路径都过密钥涂抹正则
- 🚪 **Marker 围栏幂等更新** —— hook 只动 `<!-- LIGHTMEM:X:START -->...END -->` 区域，外面的内容你随便写
- 🩺 **doctor 17 项具体检查** —— 每条都有可执行的 predicate，不含糊
- 🎛️ **Killswitch 环境变量** —— `LIGHTMEM_HOOK_PROFILE=off` 零 I/O 全短路
- 🧪 **867 个测试在 `python3 -W error` 下通过** —— 单测 + 集成 + plugin wiring
- 🪶 **纯 stdlib** —— Python 3.10+。零依赖。零 `pip install`。
- 📜 **能挺过卸载** —— 即使没装 LightMem，你的 topic markdown 也照样能读

## FAQ

<details>
<summary><b>为什么不直接把所有内容塞进 CLAUDE.md？</b></summary>

CLAUDE.md 每次 session 都全文加载，吃掉 context budget。让它无限增长不仅烧 token，还会把稳定规则和临时状态搅在一起。LightMem 把 CLAUDE.md 当 L0 路由（≤8 KB 警告 / ≤16 KB fail），真正的数据库放在 `.claude/lightmem/topics/`，每个 session 只注入一份精炼摘要。
</details>

<details>
<summary><b>跟 ECC 的 continuous-learning 有啥区别？</b></summary>

ECC 学习你的**个人编码习惯**（per-user、per-machine、不进 repo）。LightMem 捕获**项目级的决策和约束**，需要跟随 codebase 走。两者正交，可以同时跑。LightMem 借用了 ECC 的成熟模式（stale-replay 防护、密钥涂抹、transcript-UUID keying），但解决的是不同问题。
</details>

<details>
<summary><b>会不会调 LLM？</b></summary>

**v0.1 零 LLM 调用。** 每个 hook 都是确定性 stdlib Python。v0.4 会加 opt-in 的后台 curator（Haiku），但严格 opt-in，默认关闭。
</details>

<details>
<summary><b>我已有的 CLAUDE.md 会怎么样？</b></summary>

`/lightmem:init` 检测到它，告诉你它的大小和结构，让你三选一：(1) 顶部追加一个围栏好的 LightMem block——原有内容不动（推荐），(2) 备份到 `CLAUDE.md.bak.<ts>`，从模板重写新的 CLAUDE.md，(3) 放弃，把 block 打印出来让你手动粘贴。re-run `/lightmem:init` 只替换围栏内的部分。
</details>

<details>
<summary><b>Windows 支持？</b></summary>

v0.1 测试覆盖 Linux 和 macOS。Windows 在 v0.2 路线图——多数代码跨平台，文件锁和 shell 引用需要显式处理。
</details>

<details>
<summary><b>怎么临时关掉 LightMem？</b></summary>

```bash
LIGHTMEM_HOOK_PROFILE=off claude
```

每个 LightMem hook 在零 I/O 处短路。效果等同于卸载但不动文件。
</details>

<details>
<summary><b>记忆存哪？会上传吗？</b></summary>

完全本地，存在 repo 的 `.claude/lightmem/`。**零遥测、零网络调用、零回家** (D13 在 PRD §2，锁定不变量)。提交的 topic 对有 repo 访问权限的人可见；运行时产物因为 gitignore 留在本机。
</details>

<details>
<summary><b>能只装某一个 repo 而不全局安装吗？</b></summary>

```bash
claude plugin install lightmem@lightmem --scope project   # 团队共享
claude plugin install lightmem@lightmem --scope local     # 个人，gitignore
```
</details>

## Roadmap

- [x] **v0.1.0** —— MVP：4 个 hook，3 个 skill，17 项 doctor 检查，867 个测试。每个写入路径都涂抹密钥。stale-replay 防护。（本次发布）
- [ ] **v0.2.0** —— `/lightmem:update` skill。Windows 支持。worktree 感知的 resume 注入。
- [ ] **v0.3.0** —— `UserPromptSubmit` 检索（SQLite FTS5）。
- [ ] **v0.4.0** —— opt-in Haiku curator 子代理，自带 13 条 ECC 安全网。
- [ ] **v0.5.0** —— 可选 `sentence-transformers` 语义检索。monorepo path-scoping。

完整计划+风险登记：[ROADMAP.md](./ROADMAP.md)。

## 文档地图

| 文档 | 内容 |
|------|------|
| [ROADMAP.md](./ROADMAP.md) | v0.1 → v0.5 计划、风险登记、v0.1.1 backlog。 |
| [CLAUDE.md](./CLAUDE.md) | 插件源码 repo 的网关 / 贡献者指南。 |
| [LICENSE-NOTICE.md](./LICENSE-NOTICE.md) | ECC 归属 + ported 文件表。 |

## 致谢

LightMem 借用了 [ECC](https://github.com/affaan-m/ECC) 项目（MIT，作者 Affaan Mustafa）的成熟模式：stale-replay 防护文本、密钥涂抹正则、marker-fenced 幂等块更新、transcript-UUID 命名 session 文件（修 ECC upstream issue #1494）、reference-vs-live hook config 分离模式。每个 port 过来的文件都带着指向 pinned upstream commit 的归属头；完整表格在 [LICENSE-NOTICE.md](./LICENSE-NOTICE.md)。

## 贡献

```bash
python3 -W error -m unittest discover tests
```

测试必须全绿（今天是 867/867）。风格：纯 stdlib Python 3.10+，每个文件头部 `from __future__ import annotations`，public 函数加类型注解，**不写**函数 docstring（WHY-only 的 `#` 注释），所有标识符英文。ECC 派生文件必须带归属头（见 [LICENSE-NOTICE.md](./LICENSE-NOTICE.md)）。

## 协议

[MIT](./LICENSE)。© 2026 LightMem 贡献者。

ECC 派生的模式按 [MIT](https://github.com/affaan-m/ECC/blob/main/LICENSE) 单独在 [LICENSE-NOTICE.md](./LICENSE-NOTICE.md) 归属。
