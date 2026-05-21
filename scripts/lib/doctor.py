from __future__ import annotations

import dataclasses
import os
import re
import time
from pathlib import Path
from typing import Callable, Literal

from scripts.lib import journal, markers, scrub, topics


@dataclasses.dataclass(frozen=True)
class CheckResult:
    status: Literal["pass", "warn", "fail"]
    name: str
    message: str
    fix_hint: str | None = None


_RETENTION_DAYS_DEFAULT: int = 30
_JOURNAL_TAIL_LINES: int = 500
_LINK_RE: re.Pattern[str] = re.compile(r"\[([^\]]*)\]\(([^)#][^)]*)\)")


def _retention_days() -> int:
    raw = os.environ.get("LIGHTMEM_RETENTION_DAYS", "")
    if raw.strip():
        try:
            val = int(raw.strip())
            if val > 0:
                return val
        except ValueError:
            pass
    return _RETENTION_DAYS_DEFAULT


def _topics_dir(repo_root: Path) -> Path:
    return repo_root / ".claude/lightmem/topics"


def _lightmem_dir(repo_root: Path) -> Path:
    return repo_root / ".claude/lightmem"


def check_claude_md_exists(repo_root: Path) -> CheckResult:
    p = repo_root / "CLAUDE.md"
    if p.exists():
        return CheckResult("pass", "claude_md_exists", "CLAUDE.md exists.")
    return CheckResult(
        "warn",
        "claude_md_exists",
        "CLAUDE.md not found in repo root.",
        "Run `/lightmem:init` to create CLAUDE.md with the gateway block.",
    )


def check_claude_md_has_gateway(repo_root: Path) -> CheckResult:
    p = repo_root / "CLAUDE.md"
    if not p.exists():
        return CheckResult(
            "warn",
            "claude_md_has_gateway",
            "CLAUDE.md does not exist; cannot check for gateway marker.",
        )
    text = p.read_text(encoding="utf-8")
    if markers.GATEWAY_START in text:
        return CheckResult("pass", "claude_md_has_gateway", "Gateway marker found in CLAUDE.md.")
    return CheckResult(
        "warn",
        "claude_md_has_gateway",
        "LIGHTMEM:GATEWAY:START marker missing from CLAUDE.md.",
        "Run `/lightmem:init` to insert the gateway block.",
    )


def check_claude_md_size_warn(repo_root: Path) -> CheckResult:
    p = repo_root / "CLAUDE.md"
    if not p.exists():
        return CheckResult("pass", "claude_md_size_warn", "CLAUDE.md absent; size check skipped.")
    size = p.stat().st_size
    if size > 8192:
        return CheckResult(
            "warn",
            "claude_md_size_warn",
            f"CLAUDE.md is {size} bytes (> 8 KB warn threshold).",
            "Move non-gateway content into topic files under .claude/lightmem/topics/.",
        )
    return CheckResult(
        "pass", "claude_md_size_warn", f"CLAUDE.md is {size} bytes (within 8 KB warn limit)."
    )


def check_claude_md_size_fail(repo_root: Path) -> CheckResult:
    p = repo_root / "CLAUDE.md"
    if not p.exists():
        return CheckResult("pass", "claude_md_size_fail", "CLAUDE.md absent; size check skipped.")
    size = p.stat().st_size
    if size > 16384:
        return CheckResult(
            "fail",
            "claude_md_size_fail",
            f"CLAUDE.md is {size} bytes (> 16 KB hard limit).",
            "Move content to topic files. CLAUDE.md must stay under 16 KB.",
        )
    return CheckResult(
        "pass", "claude_md_size_fail", f"CLAUDE.md is {size} bytes (within 16 KB fail limit)."
    )


def check_lightmem_dir_exists(repo_root: Path) -> CheckResult:
    p = _lightmem_dir(repo_root)
    if p.is_dir():
        return CheckResult("pass", "lightmem_dir_exists", ".claude/lightmem/ directory exists.")
    return CheckResult(
        "warn",
        "lightmem_dir_exists",
        ".claude/lightmem/ directory not found.",
        "Run `/lightmem:init` to create the LightMem skeleton.",
    )


def check_gitignore_present(repo_root: Path) -> CheckResult:
    gi = _lightmem_dir(repo_root) / ".gitignore"
    if not gi.exists():
        return CheckResult(
            "warn",
            "gitignore_present",
            ".claude/lightmem/.gitignore is missing.",
            "Run `/lightmem:init` to create the .gitignore with correct exclusions.",
        )
    text = gi.read_text(encoding="utf-8")
    missing: list[str] = []
    for entry in (
        "journal.jsonl", "sessions/", "archive/", "state.json",
        ".last-purge", "compaction-log.txt", "inbox/",
    ):
        if entry not in text:
            missing.append(entry)
    if missing:
        return CheckResult(
            "warn",
            "gitignore_present",
            f".claude/lightmem/.gitignore is missing entries: {', '.join(missing)}.",
            "Add the missing entries to .claude/lightmem/.gitignore.",
        )
    return CheckResult("pass", "gitignore_present", ".gitignore present with required exclusions.")


def check_topic_frontmatter_valid(repo_root: Path) -> CheckResult:
    td = _topics_dir(repo_root)
    if not td.is_dir():
        return CheckResult(
            "pass", "topic_frontmatter_valid", "No topics directory; skipping frontmatter check."
        )
    required = {"id", "kind", "summary", "status"}
    bad: list[str] = []
    for md_file in td.rglob("*.md"):
        try:
            text = md_file.read_text(encoding="utf-8")
            fm, _ = topics.parse_frontmatter(text)
            if not fm or not required.issubset(fm.keys()):
                bad.append(str(md_file.relative_to(repo_root)))
        except Exception:
            bad.append(str(md_file.relative_to(repo_root)))
    if bad:
        files = ", ".join(bad)
        return CheckResult(
            "fail",
            "topic_frontmatter_valid",
            f"Topic files with missing/invalid frontmatter: {files}.",
            "Each topic file must have id, kind, summary, and status in YAML frontmatter.",
        )
    return CheckResult(
        "pass", "topic_frontmatter_valid", "All topic files have valid frontmatter."
    )


def check_topic_id_matches_filename(repo_root: Path) -> CheckResult:
    td = _topics_dir(repo_root)
    if not td.is_dir():
        return CheckResult(
            "pass",
            "topic_id_matches_filename",
            "No topics directory; skipping id-filename check.",
        )
    bad: list[str] = []
    for md_file in td.rglob("*.md"):
        try:
            text = md_file.read_text(encoding="utf-8")
            fm, _ = topics.parse_frontmatter(text)
            if fm.get("id") != md_file.stem:
                bad.append(str(md_file.relative_to(repo_root)))
        except Exception:
            bad.append(str(md_file.relative_to(repo_root)))
    if bad:
        files = ", ".join(bad)
        return CheckResult(
            "fail",
            "topic_id_matches_filename",
            f"Topic files where frontmatter id != filename stem: {files}.",
            "Rename the file or update the id field so they match.",
        )
    return CheckResult(
        "pass", "topic_id_matches_filename", "All topic ids match their filenames."
    )


def check_slug_is_kebab_case(repo_root: Path) -> CheckResult:
    td = _topics_dir(repo_root)
    if not td.is_dir():
        return CheckResult(
            "pass", "slug_is_kebab_case", "No topics directory; skipping slug check."
        )
    bad: list[str] = []
    for md_file in td.rglob("*.md"):
        try:
            text = md_file.read_text(encoding="utf-8")
            fm, _ = topics.parse_frontmatter(text)
            slug = fm.get("id", md_file.stem)
            if not topics.is_valid_slug(str(slug)):
                bad.append(str(md_file.relative_to(repo_root)))
        except Exception:
            bad.append(str(md_file.relative_to(repo_root)))
    if bad:
        files = ", ".join(bad)
        return CheckResult(
            "fail",
            "slug_is_kebab_case",
            f"Topic slugs that are not valid kebab-case: {files}.",
            "Slugs must match ^[a-z][a-z0-9-]*$. Rename files and update id fields.",
        )
    return CheckResult("pass", "slug_is_kebab_case", "All topic slugs are valid kebab-case.")


def check_no_duplicate_slugs(repo_root: Path) -> CheckResult:
    td = _topics_dir(repo_root)
    if not td.is_dir():
        return CheckResult(
            "pass", "no_duplicate_slugs", "No topics directory; skipping duplicate check."
        )
    seen: dict[str, str] = {}
    dupes: list[str] = []
    for md_file in td.rglob("*.md"):
        try:
            text = md_file.read_text(encoding="utf-8")
            fm, _ = topics.parse_frontmatter(text)
            slug = str(fm.get("id", md_file.stem))
            rel = str(md_file.relative_to(repo_root))
            if slug in seen:
                dupes.append(f"{slug} ({seen[slug]} vs {rel})")
            else:
                seen[slug] = rel
        except Exception:
            pass
    if dupes:
        return CheckResult(
            "fail",
            "no_duplicate_slugs",
            f"Duplicate topic slugs found: {'; '.join(dupes)}.",
            "Each topic id must be unique across the entire topics directory.",
        )
    return CheckResult("pass", "no_duplicate_slugs", "No duplicate topic slugs found.")


def check_topic_status_valid(repo_root: Path) -> CheckResult:
    td = _topics_dir(repo_root)
    if not td.is_dir():
        return CheckResult(
            "pass", "topic_status_valid", "No topics directory; skipping status check."
        )
    bad: list[str] = []
    for md_file in td.rglob("*.md"):
        try:
            text = md_file.read_text(encoding="utf-8")
            fm, _ = topics.parse_frontmatter(text)
            status = fm.get("status")
            if status not in topics.VALID_STATUSES:
                bad.append(str(md_file.relative_to(repo_root)))
        except Exception:
            bad.append(str(md_file.relative_to(repo_root)))
    if bad:
        files = ", ".join(bad)
        valid = ", ".join(sorted(topics.VALID_STATUSES))
        return CheckResult(
            "fail",
            "topic_status_valid",
            f"Topic files with invalid status: {files}.",
            f"Status must be one of: {valid}.",
        )
    return CheckResult("pass", "topic_status_valid", "All topic statuses are valid.")


def check_superseded_by_resolves(repo_root: Path) -> CheckResult:
    td = _topics_dir(repo_root)
    if not td.is_dir():
        return CheckResult(
            "pass",
            "superseded_by_resolves",
            "No topics directory; skipping superseded_by check.",
        )
    all_topics = topics.walk_topics(td)
    all_slugs = {t.id for t in all_topics}
    bad: list[str] = []
    for t in all_topics:
        superseded_by = t.frontmatter.get("superseded_by")
        if superseded_by and superseded_by not in all_slugs:
            bad.append(f"{t.id} -> {superseded_by}")
    if bad:
        return CheckResult(
            "fail",
            "superseded_by_resolves",
            f"superseded_by references to non-existent slugs: {', '.join(bad)}.",
            "Create the referenced topic or clear the superseded_by field.",
        )
    return CheckResult(
        "pass", "superseded_by_resolves", "All superseded_by references resolve to known slugs."
    )


def check_no_broken_relative_links(repo_root: Path) -> CheckResult:
    td = _topics_dir(repo_root)
    if not td.is_dir():
        return CheckResult(
            "pass",
            "no_broken_relative_links",
            "No topics directory; skipping link check.",
        )
    lightmem_dir = _lightmem_dir(repo_root).resolve()
    broken: list[str] = []
    for md_file in td.rglob("*.md"):
        try:
            text = md_file.read_text(encoding="utf-8")
            _, body = topics.parse_frontmatter(text)
            for _label, target in _LINK_RE.findall(body):
                # Skip external and anchor-only links.
                if target.startswith(("http://", "https://", "mailto:")):
                    continue
                resolved = (md_file.parent / target).resolve()
                # Only flag links that resolve inside the lightmem directory.
                try:
                    resolved.relative_to(lightmem_dir)
                except ValueError:
                    continue
                if not resolved.exists():
                    broken.append(
                        f"{md_file.relative_to(repo_root)}: [{target}]"
                    )
        except Exception:
            pass
    if broken:
        return CheckResult(
            "warn",
            "no_broken_relative_links",
            f"Broken relative links found: {', '.join(broken)}.",
            "Update or remove links pointing to missing files.",
        )
    return CheckResult("pass", "no_broken_relative_links", "No broken relative links found.")


def check_journal_size_ok(repo_root: Path) -> CheckResult:
    jp = journal.journal_path(repo_root)
    if not jp.exists():
        return CheckResult("pass", "journal_size_ok", "journal.jsonl does not exist.")
    size = jp.stat().st_size
    max_bytes = journal.read_max_mb() * 1024 * 1024
    if size > max_bytes:
        return CheckResult(
            "warn",
            "journal_size_ok",
            f"journal.jsonl is {size} bytes (> {journal.read_max_mb()} MB).",
            "The Stop hook should rotate it automatically; check hook profile settings.",
        )
    return CheckResult(
        "pass",
        "journal_size_ok",
        f"journal.jsonl is {size} bytes (within {journal.read_max_mb()} MB limit).",
    )


def check_secret_scan(repo_root: Path) -> CheckResult:
    hits: list[str] = []

    jp = journal.journal_path(repo_root)
    if jp.exists():
        try:
            lines = jp.read_text(encoding="utf-8", errors="replace").splitlines()
            tail = lines[-_JOURNAL_TAIL_LINES:]
            for i, line in enumerate(tail, start=max(1, len(lines) - _JOURNAL_TAIL_LINES + 1)):
                if scrub.SECRET_REGEX.search(line):
                    hits.append(f"journal.jsonl line {i}")
        except Exception:
            pass

    td = _topics_dir(repo_root)
    if td.is_dir():
        for md_file in td.rglob("*.md"):
            try:
                text = md_file.read_text(encoding="utf-8", errors="replace")
                _, body = topics.parse_frontmatter(text)
                if scrub.SECRET_REGEX.search(body):
                    hits.append(str(md_file.relative_to(repo_root)))
            except Exception:
                pass

    # Session files are a second write path that resume injection reads back
    # into Claude's context — leaked credentials would travel across sessions.
    # See Codex H2.
    sd = _lightmem_dir(repo_root) / "sessions"
    if sd.is_dir():
        for sess_file in sd.glob("*.md"):
            try:
                text = sess_file.read_text(encoding="utf-8", errors="replace")
                if scrub.SECRET_REGEX.search(text):
                    hits.append(str(sess_file.relative_to(repo_root)))
            except Exception:
                pass

    if hits:
        locations = ", ".join(hits[:10])
        suffix = f" (and {len(hits) - 10} more)" if len(hits) > 10 else ""
        return CheckResult(
            "fail",
            "secret_scan",
            f"Potential secrets found in: {locations}{suffix}.",
            "Scrub the content with `scrub.scrub()` or remove the sensitive data.",
        )
    return CheckResult(
        "pass",
        "secret_scan",
        "No secrets detected in journal tail, topic bodies, or session files.",
    )


def check_archive_purge_recent(repo_root: Path) -> CheckResult:
    marker = _lightmem_dir(repo_root) / ".last-purge"
    if not marker.exists():
        return CheckResult(
            "warn",
            "archive_purge_recent",
            ".last-purge marker is missing.",
            "Run a session with the SessionEnd hook active to trigger the first purge.",
        )
    mtime = marker.stat().st_mtime
    age_days = (time.time() - mtime) / 86400
    threshold = _retention_days() * 2
    if age_days > threshold:
        return CheckResult(
            "warn",
            "archive_purge_recent",
            f".last-purge is {age_days:.1f} days old (threshold: {threshold} days).",
            "Check that the SessionEnd hook is running and LIGHTMEM_RETENTION_DAYS is set correctly.",
        )
    return CheckResult(
        "pass",
        "archive_purge_recent",
        f".last-purge is {age_days:.1f} days old (within {threshold}-day threshold).",
    )


def check_inbox_absent(repo_root: Path) -> CheckResult:
    inbox = _lightmem_dir(repo_root) / "inbox"
    if inbox.is_dir():
        return CheckResult(
            "warn",
            "inbox_absent",
            ".claude/lightmem/inbox/ exists (not supported until v0.4).",
            "Remove the inbox/ directory; the curator feature is not yet active.",
        )
    return CheckResult(
        "pass", "inbox_absent", ".claude/lightmem/inbox/ is correctly absent."
    )


ALL_CHECKS: list[Callable[[Path], CheckResult]] = [
    check_claude_md_exists,
    check_claude_md_has_gateway,
    check_claude_md_size_warn,
    check_claude_md_size_fail,
    check_lightmem_dir_exists,
    check_gitignore_present,
    check_topic_frontmatter_valid,
    check_topic_id_matches_filename,
    check_slug_is_kebab_case,
    check_no_duplicate_slugs,
    check_topic_status_valid,
    check_superseded_by_resolves,
    check_no_broken_relative_links,
    check_journal_size_ok,
    check_secret_scan,
    check_archive_purge_recent,
    check_inbox_absent,
]


def run_all(repo_root: Path) -> list[CheckResult]:
    results: list[CheckResult] = []
    for check_fn in ALL_CHECKS:
        name = check_fn.__name__.removeprefix("check_")
        try:
            result = check_fn(repo_root)
        except Exception as exc:
            result = CheckResult(
                "warn",
                name,
                f"check {name} errored: {exc}",
            )
        results.append(result)
    return results


def summary(results: list[CheckResult]) -> tuple[int, int, int]:
    pass_count = sum(1 for r in results if r.status == "pass")
    warn_count = sum(1 for r in results if r.status == "warn")
    fail_count = sum(1 for r in results if r.status == "fail")
    return pass_count, warn_count, fail_count
