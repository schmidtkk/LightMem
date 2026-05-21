# Third-party attribution

LightMem incorporates patterns, regex strings, constants, and small code idioms adapted from the [ECC](https://github.com/affaan-m/ECC) project by Affaan Mustafa (MIT License). A pinned, read-only copy of the source files we drew from lives in [`vendor/ecc-reference/`](vendor/ecc-reference/) along with the full upstream `LICENSE`.

## Scope of adaptation

This is **not** a fork. LightMem is a from-scratch Python implementation with a different architecture (CLAUDE.md gateway + structured index + topics taxonomy) and a different runtime (pure-stdlib Python 3.10+ vs. ECC's Node.js). We borrow specific, well-tested idioms — primarily:

1. **Patterns**: hook output JSON envelope shape, marker-delimited idempotent block updates, stale-replay guard wrapper for SessionStart injection, env-var-driven kill switches.
2. **Regex strings**: secret-scrub pattern.
3. **Constants**: `MAX_STDIN`, default `SESSION_START_MAX_CHARS`.
4. **Algorithms**: transcript-UUID derivation of `shortId`, worktree-match-beats-project-name session selection.

Each ported file in LightMem's `lib/` carries a header comment of the form:

```python
# Adapted from ECC (MIT) — <upstream/path>:<line-range>
# Upstream commit: 1e8c7e7994223e0ff337d1626cd08e04a1ae67ed
# Upstream license: MIT, Copyright (c) 2026 Affaan Mustafa
```

## MIT License (ECC)

```
MIT License

Copyright (c) 2026 Affaan Mustafa

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
```

The full upstream notice is also preserved at [`vendor/ecc-reference/LICENSE`](vendor/ecc-reference/LICENSE).

## Future ECC-derived files

When porting new patterns from ECC, append a row to the table below in the same PR that introduces the ported code:

| LightMem file | Adapted from | Pattern |
|---------------|--------------|---------|
| `scripts/lib/scrub.py` | `vendor/ecc-reference/skills/continuous-learning-v2/hooks/observe.sh` L271-276 | Secret-scrub regex |
| `scripts/lib/session_id.py` | `vendor/ecc-reference/scripts/hooks/session-end.js` L211-220 | Transcript-UUID → shortId derivation |
| `scripts/lib/stdin_io.py` | `vendor/ecc-reference/scripts/hooks/session-end.js` L114 | 1 MB stdin cap via MAX_STDIN constant |
| `scripts/lib/injection.py` | `vendor/ecc-reference/scripts/hooks/session-start.js` L580-606, L668-700 | stale-replay guard envelope + SessionStart JSON output shape |
| `scripts/lib/budget.py` | `vendor/ecc-reference/scripts/hooks/session-start.js` L92-145 | LIGHTMEM_SESSION_START_MAX_CHARS budget + truncation marker |
| `scripts/lib/journal.py` | `vendor/ecc-reference/skills/continuous-learning-v2/hooks/observe.sh` L286-293 | File-size rotation + atomic rename pattern for JSONL journal |
| `scripts/hooks/pre_compact.py` | `vendor/ecc-reference/scripts/hooks/pre-compact.js` L1-48 | Minimal PreCompact event logger (compaction-log append + session file annotation) |
