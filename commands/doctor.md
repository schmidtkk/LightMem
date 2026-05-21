---
description: Run all 17 LightMem integrity checks (CLAUDE.md size, gateway presence, topic frontmatter validity, duplicate slugs, broken links, secret scan, journal size, archive purge freshness). Prints a pass/warn/fail report.
allowed-tools: Bash(python3:*)
---

Run all 17 LightMem integrity checks against the current repository and print a structured report.

## Invoke the doctor

```python
import sys, os
sys.path.insert(0, os.environ['CLAUDE_PLUGIN_ROOT'])
from pathlib import Path
from scripts.lib import doctor

repo_root = Path.cwd()
results = doctor.run_all(repo_root)
pass_count, warn_count, fail_count = doctor.summary(results)
```

## Format and print the report

Display the results grouped as follows:

1. **Summary line** at the top:
   ```
   LightMem doctor: <pass_count> passed, <warn_count> warnings, <fail_count> failed
   ```

2. **Passed checks** (brief, one line each):
   ```
   [PASS] claude_md_exists — CLAUDE.md exists.
   ```

3. **Warnings** (with fix hint if present):
   ```
   [WARN] gitignore_present — .claude/lightmem/.gitignore is missing.
          Fix: Run `/lightmem:init` to create the .gitignore with correct exclusions.
   ```

4. **Failures** (with fix hint if present):
   ```
   [FAIL] topic_frontmatter_valid — Topic files with missing/invalid frontmatter: ...
          Fix: Each topic file must have id, kind, summary, and status in YAML frontmatter.
   ```

Show all 17 checks: passes first, then warnings, then failures so the most urgent issues are prominent.

If `fail_count > 0`: flag clearly that failures must be resolved before LightMem will function correctly.
If only warnings: confirm LightMem will still function but advisory issues exist.
If all pass: confirm the installation is healthy.
