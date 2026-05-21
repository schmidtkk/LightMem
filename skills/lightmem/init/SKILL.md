---
name: lightmem-init
description: Initialize or refresh LightMem in the current repo. Detects existing CLAUDE.md and prompts the user to choose append-fenced (default), backup+rewrite, or abort. Creates .claude/lightmem/ skeleton, topic templates, and state.json.
---

# /lightmem:init

Initialize or refresh LightMem memory scaffolding for the current repository.

## Step 1 — Inspect the repo

Run the following Python snippet to inspect the current repo state and print a summary:

```python
import sys
sys.path.insert(0, LIGHTMEM_PLUGIN_ROOT)
from pathlib import Path
from scripts.lib import init_helper

repo_root = Path.cwd()
plan = init_helper.inspect_repo(repo_root)

print(f"LightMem init for {repo_root}")
print()

if plan.existing_claude_md:
    claude_md = repo_root / "CLAUDE.md"
    size_kb = claude_md.stat().st_size / 1024
    text = claude_md.read_text(encoding="utf-8")
    has_fence = "<!-- LIGHTMEM:GATEWAY:START -->" in text
    print(f"Detected existing CLAUDE.md ({size_kb:.1f} KB, {'has gateway fence' if has_fence else 'no gateway fence'}).")
else:
    print("No existing CLAUDE.md found.")

if plan.existing_lightmem_dir:
    print(".claude/lightmem/ already exists.")
else:
    print(".claude/lightmem/ not yet initialized.")

if plan.topics_to_create:
    print(f"Topics to create: {', '.join(plan.topics_to_create)}")
```

Replace `LIGHTMEM_PLUGIN_ROOT` with the absolute path to the LightMem plugin directory (the directory containing this skills/ folder). You can find it from `__file__` or from the `CLAUDE_PLUGIN_ROOT` environment variable if set.

## Step 2 — Prompt the user

Show the user exactly this prompt (verbatim):

```
How would you like to handle CLAUDE.md?
  1) Append a fenced LightMem gateway block at the top (recommended)
  2) Backup existing to CLAUDE.md.bak.<ts>, then write LightMem template
  3) Abort and let me handle CLAUDE.md manually

Choice [1]:
```

Wait for the user's response. Default to option 1 if they press Enter or type nothing.

## Step 3 — Apply the chosen action

Map the user choice to a mode:
- Choice 1 (or empty/Enter) → `mode = "append_fenced"`
- Choice 2 → `mode = "backup_rewrite"`
- Choice 3 → `mode = "abort"`

Then run:

```python
import sys
sys.path.insert(0, LIGHTMEM_PLUGIN_ROOT)
from pathlib import Path
from scripts.lib import init_helper

repo_root = Path.cwd()
mode = "<chosen_mode>"  # one of: append_fenced, backup_rewrite, abort

# Create the skeleton (idempotent — won't overwrite existing topic files).
plan = init_helper.inspect_repo(repo_root)
if not plan.existing_lightmem_dir or plan.topics_to_create:
    init_helper.create_skeleton(repo_root)

# Update CLAUDE.md per user choice.
result_path = init_helper.update_claude_md(repo_root, mode)

if result_path:
    print(f"Written: {result_path}")
else:
    print("Aborted. Paste the gateway block printed above into your CLAUDE.md manually.")
```

## Step 4 — Report the result

After the skeleton is created and CLAUDE.md is updated, tell the user:

- Which files were created or modified (CLAUDE.md, .claude/lightmem/.gitignore, state.json, topic templates).
- If mode was `backup_rewrite`, mention the backup file path.
- If mode was `abort`, show the gateway block content and ask the user to paste it into CLAUDE.md.
- Suggest running `/lightmem:doctor` to verify the installation is healthy.
- Remind the user to edit the topic templates (especially mission.md) with real project content.

Re-running `/lightmem:init` on an already-initialized repo is safe. It only refreshes the CLAUDE.md gateway block and skips existing topic files.
