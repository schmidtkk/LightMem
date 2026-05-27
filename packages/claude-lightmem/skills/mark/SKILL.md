---
name: mark
description: Quickly append a note to the LightMem inbox for later promotion to a topic. Usage: /lightmem:mark <text to remember>
---

# /lightmem:mark

Append one item to `.claude/lightmem/inbox/pending.md` without confirmation.
This is the fast path — review and promote with `/lightmem:update`.

## Resolve LIGHTMEM_PLUGIN_ROOT

Before running any snippet, resolve `LIGHTMEM_PLUGIN_ROOT` to the absolute path
of the LightMem plugin directory (the directory containing `skills/`). Use the
`CLAUDE_PLUGIN_ROOT` environment variable if set; otherwise locate
`scripts/lib/inbox.py` under the installed Codex or Claude plugin cache and walk
up to the package root.

## Append the item

```python
import sys
sys.path.insert(0, LIGHTMEM_PLUGIN_ROOT)
from pathlib import Path
from scripts.lib import inbox

repo_root = Path.cwd()
text = "$ARGUMENTS"  # the full text after /lightmem:mark (interpolated by the agent runtime)

path = inbox.append_pending(repo_root, text, source="mark")
print(f"Appended to {path}")
print(f"Run /lightmem:update to promote to a topic.")
```

## Report the result

Tell the user the item was added to the inbox and remind them that
`/lightmem:update` is the promotion step.
