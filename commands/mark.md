---
description: Quickly append a note to the LightMem inbox for later promotion to a topic. Usage: /lightmem:mark <text>
allowed-tools: Bash(python3:*)
---

Append one item to `.claude/lightmem/inbox/pending.md` without confirmation.
This is the zero-friction fast path — review and promote with `/lightmem:update`.

## Resolve LIGHTMEM_PLUGIN_ROOT

Before running any snippet, resolve `LIGHTMEM_PLUGIN_ROOT` to the absolute path
of the LightMem plugin directory (the directory containing `skills/`). Use the
`CLAUDE_PLUGIN_ROOT` environment variable if set, otherwise locate it via
`find ~/.claude/plugins/cache/lightmem -maxdepth 4 -name "inbox.py" | head -1`
and walk up to the package root.

## Append the item

```python
import sys
sys.path.insert(0, LIGHTMEM_PLUGIN_ROOT)
from pathlib import Path
from scripts.lib import inbox

repo_root = Path.cwd()
text = "$ARGUMENTS"  # the full text after /lightmem:mark

path = inbox.append_pending(repo_root, text, source="mark")
print(f"Appended to {path}")
```

## Report the result

Confirm the item was added. Remind the user that `/lightmem:update` is the
promotion step that writes to actual topic files.
