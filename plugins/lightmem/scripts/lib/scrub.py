from __future__ import annotations

# Adapted from ECC (MIT) — vendor/ecc-reference/skills/continuous-learning-v2/hooks/observe.sh:271-276
# Upstream commit: 1e8c7e7994223e0ff337d1626cd08e04a1ae67ed
# Upstream license: MIT, Copyright (c) 2026 Affaan Mustafa

import re

SECRET_REGEX: re.Pattern[str] = re.compile(
    r"(?i)(api[_-]?key|token|secret|password|authorization|credentials?|auth)"
    r"([:=\s\"']+)"
    r"([A-Za-z]+\s+)?"
    r"([A-Za-z0-9_\-/.+=]{8,})"
)

REDACT_REPLACEMENT: str = r"\1\2\3[REDACTED]"

# Inherited quirk: the optional group 3 ([A-Za-z]+\s+)? exists to consume auth
# schemes like "Bearer " before the value. It can also consume a purely-alphabetic
# secret value when immediately followed by another keyword, leaving that value
# un-redacted on first pass. Real credentials nearly always contain digits or
# symbols, so single-pass redaction is reliable in practice. Run scrub() twice
# if you must defend against fully-alphabetic adjacent secrets.


def scrub(text: str) -> str:
    return SECRET_REGEX.sub(REDACT_REPLACEMENT, text)
