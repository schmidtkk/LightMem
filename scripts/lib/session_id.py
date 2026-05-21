from __future__ import annotations

# Adapted from ECC (MIT) — vendor/ecc-reference/scripts/hooks/session-end.js:211-220
# Upstream commit: 1e8c7e7994223e0ff337d1626cd08e04a1ae67ed
# Upstream license: MIT, Copyright (c) 2026 Affaan Mustafa

import os
import re

_UUID_RE: re.Pattern[str] = re.compile(
    r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.jsonl$",
    re.IGNORECASE,
)


def _sanitize_short_id(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s)


def derive_short_id(transcript_path: str | None) -> str | None:
    if not transcript_path:
        return None
    m = _UUID_RE.search(os.path.basename(transcript_path))
    if not m:
        return None
    return _sanitize_short_id(m.group(1)[-8:].lower())
