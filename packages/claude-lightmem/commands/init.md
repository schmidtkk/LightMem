---
description: Initialize or refresh LightMem memory scaffolding for the current repository. Creates .claude/lightmem/ plus CLAUDE.md and AGENTS.md gateways.
allowed-tools: Bash(python3:*), AskUserQuestion
---

Initialize or refresh LightMem memory scaffolding for the current repository.

## Step 1 — Inspect the repo

Before running any snippet, resolve `LIGHTMEM_PLUGIN_ROOT` to the absolute path of the LightMem plugin directory (the directory containing `skills/`). Use the `CLAUDE_PLUGIN_ROOT` environment variable if set; otherwise locate `scripts/lib/index_builder.py` under the installed Codex or Claude plugin cache and walk up to the package root.

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

if plan.existing_agents_md:
    agents_md = repo_root / "AGENTS.md"
    size_kb = agents_md.stat().st_size / 1024
    text = agents_md.read_text(encoding="utf-8")
    has_fence = "<!-- LIGHTMEM:GATEWAY:START -->" in text
    print(f"Detected existing AGENTS.md ({size_kb:.1f} KB, {'has gateway fence' if has_fence else 'no gateway fence'}).")
else:
    print("No existing AGENTS.md found.")

if plan.existing_lightmem_dir:
    print(".claude/lightmem/ already exists.")
else:
    print(".claude/lightmem/ not yet initialized.")

if plan.topics_to_create:
    print(f"Topics to create: {', '.join(plan.topics_to_create)}")
```

## Step 2 — Prompt the user

Use `AskUserQuestion` to ask:

> How would you like to handle CLAUDE.md and AGENTS.md?

Offer these options (in order):
1. **Append fenced gateway blocks** (Recommended) — adds LightMem gateway blocks at the top of CLAUDE.md and AGENTS.md without removing existing content
2. **Backup and rewrite** — backs up existing files to `<name>.bak.<ts>`, then writes the LightMem templates
3. **Abort** — skip gateway file changes; user will paste the gateway blocks manually

## Step 3 — Apply the chosen action

Map choice to mode: option 1 → `append_fenced`, option 2 → `backup_rewrite`, option 3 → `abort`.

Then run:

```python
import sys
sys.path.insert(0, LIGHTMEM_PLUGIN_ROOT)
from pathlib import Path
from scripts.lib import init_helper

repo_root = Path.cwd()
mode = "<chosen_mode>"  # one of: append_fenced, backup_rewrite, abort

plan = init_helper.inspect_repo(repo_root)
if not plan.existing_lightmem_dir or plan.topics_to_create:
    init_helper.create_skeleton(repo_root)

result_paths = init_helper.update_gateway_files(repo_root, mode)

if result_paths:
    for result_path in result_paths:
        print(f"Written: {result_path}")
else:
    print("Aborted. Paste the gateway blocks printed above into CLAUDE.md and AGENTS.md manually.")
```

## Step 4 — Report the result

Tell the user which files were created or modified. Mention both `CLAUDE.md` and `AGENTS.md` gateway updates. Suggest running `/lightmem:doctor` to verify the installation. Remind them to edit the topic templates (especially `mission.md`) with real project content.

Re-running `/lightmem:init` on an already-initialized repo is safe — it only refreshes the gateway block and skips existing topic files.
