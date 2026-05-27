---
description: Promote inbox items and native project memory entries into LightMem topics. The authoritative entry point for all structured memory updates.
allowed-tools: Bash(python3:*), Read, Write, AskUserQuestion
---

Gather memory candidates from inbox and native project memory, confirm each
with the user, then write to `.claude/lightmem/topics/` and patch `index.md`.

**Direction:** native memory → LightMem topics only. Never the reverse.

## Resolve LIGHTMEM_PLUGIN_ROOT

Before running any snippet, resolve `LIGHTMEM_PLUGIN_ROOT` to the absolute path
of the LightMem plugin directory (the directory containing `skills/`). Use the
`CLAUDE_PLUGIN_ROOT` environment variable if set; otherwise locate
`scripts/lib/inbox.py` under the installed Codex or Claude plugin cache and walk
up to the package root.

## Step 1 — Gather candidates

```python
import sys
sys.path.insert(0, LIGHTMEM_PLUGIN_ROOT)
from pathlib import Path
from scripts.lib import inbox

repo_root = Path.cwd()
pending = inbox.read_pending(repo_root)
print(f"Inbox items: {len(pending)}")
for i, item in enumerate(pending):
    print(f"  [{i}] {item}")
```

Then read native project memory files when the runtime provides them. Claude
Code project memory lives at `~/.claude/projects/<slug>/memory/`. Codex uses
repo instructions such as `AGENTS.md` rather than a separate project memory
directory, so only treat non-LightMem notes there as candidates when the user
explicitly asks you to migrate them.

Label each candidate with its source:
- `[inbox]` — from `inbox/pending.md`
- `[native]` — from Claude Code project memory or user-selected Codex repo notes

## Step 2 — List existing topics

```python
import sys
sys.path.insert(0, LIGHTMEM_PLUGIN_ROOT)
from pathlib import Path
from scripts.lib import topics

repo_root = Path.cwd()
topics_dir = repo_root / ".claude/lightmem/topics"
all_topics = topics.walk_topics(topics_dir) if topics_dir.is_dir() else []
print("Existing topics:")
for t in all_topics:
    print(f"  {t.id} ({t.kind}) — {t.frontmatter.get('summary', '')}")
```

## Step 3 — Present candidates and confirm

Present all candidates to the user and collect decisions. Track skipped items:

```python
# decisions maps candidate index → "update:<topic_id>" | "new" | "skip"
decisions = {}   # filled by user responses
skipped_items = []  # texts the user chose to skip

# After collecting responses, populate skipped_items:
for i, text in enumerate(all_candidates):
    if decisions.get(i) == "skip":
        skipped_items.append(text)
```

Use `AskUserQuestion` for each candidate (or batch them if there are many).
For each, ask the user to choose:
- Which existing topic to update, OR
- Create a new topic (collect id, kind, summary), OR
- Skip

## Step 4 — Write confirmed items

**Append to existing topic:**

```python
import sys
sys.path.insert(0, LIGHTMEM_PLUGIN_ROOT)
from pathlib import Path
from datetime import datetime, timezone
from scripts.lib import index_builder, scrub

repo_root = Path.cwd()
topic_path = repo_root / ".claude/lightmem/topics/<TOPIC_FILE>"
today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
addition = scrub.scrub("<CONFIRMED_TEXT>")

existing = topic_path.read_text(encoding="utf-8")
updated = existing.rstrip("\n") + f"\n\n### {today}\n\n{addition}\n"
topic_path.write_text(updated, encoding="utf-8")

index_builder.patch_index_entry(repo_root, "<TOPIC_ID>")
print(f"Updated {topic_path.name} and patched index.")
```

**Create new topic:**

```python
import sys
sys.path.insert(0, LIGHTMEM_PLUGIN_ROOT)
from pathlib import Path
from scripts.lib import index_builder, scrub

repo_root = Path.cwd()
topics_dir = repo_root / ".claude/lightmem/topics"
topics_dir.mkdir(parents=True, exist_ok=True)

topic_id = "<SLUG>"
kind     = "<KIND>"   # mission/architecture/decision/constraint/workflow/gotcha/roadmap
summary  = "<SUMMARY>"
body     = scrub.scrub("<CONFIRMED_TEXT>")

content = (
    f"---\nid: {topic_id}\nkind: {kind}\nsummary: {summary}\nstatus: active\n---\n\n"
    f"{body}\n"
)
(topics_dir / f"{topic_id}.md").write_text(content, encoding="utf-8")
index_builder.patch_index_entry(repo_root, topic_id)
print(f"Created {topic_id}.md and patched index.")
```

## Step 5 — Clear promoted inbox items

Clear the inbox after all confirmed items are written. Re-append any skipped
items so they survive for the next run:

```python
import sys
sys.path.insert(0, LIGHTMEM_PLUGIN_ROOT)
from pathlib import Path
from scripts.lib import inbox

repo_root = Path.cwd()
inbox.clear_pending(repo_root)
# Re-append skipped items:
for skipped_text in skipped_items:
    inbox.append_pending(repo_root, skipped_text, source="skipped")
print("Inbox cleared.")
```

## Step 6 — Report

Tell the user how many items were promoted and to which topics, how many
remain in the inbox, and remind them that native memory entries can now be
deleted or marked as migrated.

## Hard rules

- **Never write project facts to `CLAUDE.md` or `AGENTS.md`** — they are gateway routers only.
- **Every topic write requires explicit user confirmation** from Step 3.
- **Always `scrub.scrub()` text** before writing to any topic file.
