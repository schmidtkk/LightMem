---
description: Regenerate .claude/lightmem/index.md from the current topic files. Useful after adding or removing topics.
allowed-tools: Bash(python3:*)
---

Regenerate the human-readable topic index at `.claude/lightmem/index.md` by walking all topic files.

## Invoke the index builder

```python
import sys, os
sys.path.insert(0, os.environ['CLAUDE_PLUGIN_ROOT'])
from pathlib import Path
from scripts.lib import index_builder, topics

repo_root = Path.cwd()
index_path = index_builder.write_index_md(repo_root)

topics_dir = repo_root / ".claude/lightmem/topics"
all_topics = topics.walk_topics(topics_dir) if topics_dir.is_dir() else []
print(f"Wrote {index_path} ({len(all_topics)} topics indexed)")
```

## Report the result

Tell the user:
- The absolute path to the written `index.md` file.
- How many topics were indexed in total.
- If zero topics were found, suggest running `/lightmem:init` first to create the topic templates.

The index is a human-readable convenience file; the source of truth is always the individual topic files in `.claude/lightmem/topics/`.
