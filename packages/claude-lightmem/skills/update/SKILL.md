---
name: update
description: Promote inbox items and native project memory entries into LightMem topics. The single authoritative entry point for structured memory updates.
---

# /lightmem:update

Gather memory candidates from two sources, let the user confirm each, then
write confirmed items to `.claude/lightmem/topics/` and patch `index.md`.

**Single-direction only:** native memory → LightMem topics. Never the reverse.

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

Use `AskUserQuestion` for each decision, or present all candidates at once
and let the user specify per-candidate actions (update existing topic / create
new topic / skip).

## Step 4 — Write confirmed items

For each confirmed item:

**Appending to an existing topic body:**
Read the topic file, append the new fact to the body under a dated heading,
then write back:

```python
import sys
sys.path.insert(0, LIGHTMEM_PLUGIN_ROOT)
from pathlib import Path
from datetime import datetime, timezone
from scripts.lib import index_builder, scrub

repo_root = Path.cwd()
topic_path = repo_root / ".claude/lightmem/topics/<TOPIC_FILE>"
today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

existing = topic_path.read_text(encoding="utf-8")
addition = scrub.scrub("<CONFIRMED_TEXT>")
updated = existing.rstrip("\n") + f"\n\n### {today}\n\n{addition}\n"
topic_path.write_text(updated, encoding="utf-8")

# Patch index — update only this topic's row.
index_builder.patch_index_entry(repo_root, "<TOPIC_ID>")
print(f"Updated {topic_path} and patched index.")
```

**Creating a new topic:**
Write a new `.md` file with complete frontmatter, then patch the index:

```python
import sys
sys.path.insert(0, LIGHTMEM_PLUGIN_ROOT)
from pathlib import Path
from scripts.lib import index_builder, scrub

repo_root = Path.cwd()
topics_dir = repo_root / ".claude/lightmem/topics"
topics_dir.mkdir(parents=True, exist_ok=True)

topic_id = "<SLUG>"       # e.g. "auth-approach"
kind     = "<KIND>"       # mission/architecture/decision/constraint/workflow/gotcha/roadmap
summary  = "<SUMMARY>"
body     = scrub.scrub("<CONFIRMED_TEXT>")

content = (
    f"---\n"
    f"id: {topic_id}\n"
    f"kind: {kind}\n"
    f"summary: {summary}\n"
    f"status: active\n"
    f"---\n\n"
    f"{body}\n"
)
(topics_dir / f"{topic_id}.md").write_text(content, encoding="utf-8")

index_builder.patch_index_entry(repo_root, topic_id)
print(f"Created {topics_dir / topic_id}.md and patched index.")
```

## Step 5 — Clear promoted inbox items

After all confirmed items are written, clear the inbox:

```python
import sys
sys.path.insert(0, LIGHTMEM_PLUGIN_ROOT)
from pathlib import Path
from scripts.lib import inbox

repo_root = Path.cwd()
inbox.clear_pending(repo_root)
print("Inbox cleared.")
```

Only clear items that were **confirmed and written**. If the user skipped some,
leave them in the inbox for the next run.

To do this correctly: collect the indices of skipped items before clearing,
then re-append them after clearing:

```python
for skipped_text in skipped_items:
    inbox.append_pending(repo_root, skipped_text, source="skipped")
```

## Step 6 — Report the result

Tell the user:
- How many items were promoted and to which topics.
- How many were skipped (still in inbox).
- Remind them that native memory entries flagged as "migrated" can now be deleted.
- Suggest running `/lightmem:doctor` if anything looked unusual.

## Hard rules

- **Never write project facts directly to `CLAUDE.md` or `AGENTS.md`.**  
  They are gateway routers only. All durable facts go to `topics/`.
- **Never auto-promote without user confirmation.** Every write to `topics/` requires
  an explicit user choice in Step 3.
- **Secret scrub is mandatory.** Always pass text through `scrub.scrub()` before
  writing to any topic file.
