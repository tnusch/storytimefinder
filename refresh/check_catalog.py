"""
Data quality checks for the published catalog - run as a step in the
GitHub Action right after --sync (see .github/workflows/refresh.yml), on
the same runner where storytimefinder.db still exists even though it's
gitignored and never committed. Also safe to run by hand at any time.

Three independent checks:

1. Schema validation (reads data/catalog.json) - no blank titles, no
   malformed youtube_music_url/thumbnail_url, no two items pointing at the
   same underlying YouTube video/playlist id. catalog.json never exposes a
   raw `video_id` field (see export_catalog() in refresh.py - only the
   DB's own internal `id` primary key is exported, which is trivially
   unique by construction), so "duplicate video ids" is checked by parsing
   the real YouTube id back out of each item's youtube_music_url instead -
   that's the id that actually matters for "do two cards link to the same
   thing". These are real data-integrity bugs, never expected in normal
   operation, so this check's failures are always fatal (nonzero exit).

2. Link liveness (reads data/catalog.json) - a HEAD request per item, BUT
   NOT against youtube_music_url directly: music.youtube.com is a
   JavaScript single-page app whose server always answers HTTP 200 for any
   /watch or /playlist path, real id or not (verified by hand - a
   nonexistent video id still comes back 200) - a "not found" state is
   rendered client-side, invisible to a plain HTTP request. Instead this
   HEADs YouTube's oEmbed endpoint
   (https://www.youtube.com/oembed?url=...&format=json) with the same id,
   which does give a real 400 for a video/playlist that no longer exists
   and 200 with metadata for one that does (also verified by hand, for
   both a video and a playlist id) - see _oembed_check_url(). Still
   network-dependent and can false-positive (rate limiting, a transient
   YouTube error, a runner-side network hiccup), so by default it's
   report-only; pass --fail-on-broken-links to make a confirmed-dead link
   fail the run too. Distinguishes "confirmed broken" (400/404, oEmbed's
   own "not found" signal) from "inconclusive" (anything else non-2xx,
   e.g. 403/429/5xx/timeout) - only the former counts toward
   --fail-on-broken-links.

3. Staleness (reads storytimefinder.db, NOT catalog.json - last_refreshed
   isn't part of the public export) - flags items whose last_refreshed is
   within --stale-warning-days of the 30-day YouTube API compliance window
   (see CLAUDE.md's "Compliance constraints"), so a source that started
   silently failing --check-removed (e.g. a deleted channel) gets noticed
   before it actually breaches the 30-day requirement. Purely informational
   - never affects the exit code. Skipped with a note if storytimefinder.db
   doesn't exist (e.g. running this against a machine that only ever
   pulled a committed catalog.json, never ran the refresh job itself).

Usage:
    python refresh/check_catalog.py                          # run all checks
    python refresh/check_catalog.py --skip-link-check         # skip the network-dependent HEAD requests
    python refresh/check_catalog.py --fail-on-broken-links    # also exit 1 on a confirmed-dead link
    python refresh/check_catalog.py --stale-warning-days 23   # override the staleness threshold (default 23)

Environment:
    STORYTIMEFINDER_CATALOG_PATH  default: data/catalog.json
    STORYTIMEFINDER_DB_PATH       default: data/storytimefinder.db
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sqlite3
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("check_catalog")

ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = Path(os.environ.get("STORYTIMEFINDER_CATALOG_PATH", ROOT / "data" / "catalog.json"))
DB_PATH = Path(os.environ.get("STORYTIMEFINDER_DB_PATH", ROOT / "data" / "storytimefinder.db"))

LINK_TIMEOUT_SECONDS = 8
# A plain urllib request with no User-Agent gets a disproportionate share of
# 403s from YouTube (bot-blocking, not an actual dead link) - a realistic
# browser UA cuts that down a lot, though not to zero, which is exactly why
# the link check treats non-404/410 failures as "inconclusive" rather than
# "broken" below.
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}
# Status codes oEmbed itself uses for "this specific resource is gone", as
# opposed to "something in between is unhappy right now" - only these count
# as a confirmed-broken link for --fail-on-broken-links. oEmbed returns 400
# for an unresolvable video/playlist id (verified by hand); 404 is included
# too as a reasonable alternate "not found" signal.
CONFIRMED_BROKEN_STATUSES = {400, 404}
OEMBED_ENDPOINT = "https://www.youtube.com/oembed"

STALE_WARNING_DAYS_DEFAULT = 23  # days; compliance limit is 30 (see CLAUDE.md)
COMPLIANCE_LIMIT_DAYS = 30


def load_catalog() -> list[dict]:
    if not CATALOG_PATH.exists():
        log.error("%s does not exist - nothing to check", CATALOG_PATH)
        sys.exit(1)
    try:
        data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        log.error("%s is not valid JSON: %s", CATALOG_PATH, exc)
        sys.exit(1)
    items = data.get("items")
    if not isinstance(items, list):
        log.error("%s has no top-level 'items' array", CATALOG_PATH)
        sys.exit(1)
    return items


def _is_well_formed_url(value: str, expected_netloc: str | None = None) -> bool:
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return False
    if expected_netloc is not None and parsed.netloc != expected_netloc:
        return False
    return True


def _extract_youtube_id(youtube_music_url: str) -> str | None:
    """Pull the real YouTube video/playlist id back out of a catalog item's
    youtube_music_url - the actual identity that matters for "do two items
    point at the same YouTube resource", since catalog.json never exports
    the raw video_id column directly (see this module's docstring)."""
    query = parse_qs(urlparse(youtube_music_url).query)
    for param in ("v", "list"):
        values = query.get(param)
        if values:
            return f"{param}:{values[0]}"
    return None


def check_schema(items: list[dict]) -> list[str]:
    """Fatal-if-nonempty: blank titles, malformed URLs, duplicate YouTube
    ids. These indicate a real bug in the refresh pipeline, not something
    that legitimately varies run to run - unlike the link/staleness checks
    below, any finding here is a hard failure."""
    errors: list[str] = []
    seen_youtube_ids: dict[str, list[str]] = {}

    for item in items:
        label = item.get("title") or f"id={item.get('id')!r}"

        title = item.get("title")
        if not isinstance(title, str) or not title.strip():
            errors.append(f"{label}: blank/missing title")

        youtube_music_url = item.get("youtube_music_url")
        if not isinstance(youtube_music_url, str) or not _is_well_formed_url(
            youtube_music_url, expected_netloc="music.youtube.com"
        ):
            errors.append(f"{label}: malformed youtube_music_url {youtube_music_url!r}")
        else:
            youtube_id = _extract_youtube_id(youtube_music_url)
            if youtube_id is None:
                errors.append(f"{label}: youtube_music_url has no v=/list= id: {youtube_music_url!r}")
            else:
                seen_youtube_ids.setdefault(youtube_id, []).append(label)

        thumbnail_url = item.get("thumbnail_url")
        if thumbnail_url is not None and not _is_well_formed_url(thumbnail_url):
            errors.append(f"{label}: malformed thumbnail_url {thumbnail_url!r}")

    for youtube_id, labels in seen_youtube_ids.items():
        if len(labels) > 1:
            errors.append(f"Duplicate YouTube id {youtube_id!r} shared by {len(labels)} items: {labels}")

    return errors


def _oembed_url(youtube_music_url: str) -> str:
    """oEmbed accepts a music.youtube.com URL as-is (verified by hand - no
    need to rewrite it to www.youtube.com first)."""
    return f"{OEMBED_ENDPOINT}?url={quote(youtube_music_url, safe='')}&format=json"


def check_links(items: list[dict]) -> tuple[list[str], list[str]]:
    """Returns (confirmed_broken, inconclusive) - see this module's
    docstring for the distinction. Best-effort HEAD request per item
    against YouTube's oEmbed endpoint (not youtube_music_url itself - see
    the docstring for why); network errors/timeouts land in `inconclusive`,
    never `confirmed_broken`, since they say nothing about whether the
    resource itself still exists."""
    confirmed_broken: list[str] = []
    inconclusive: list[str] = []

    for item in items:
        label = item.get("title") or f"id={item.get('id')!r}"
        url = item.get("youtube_music_url")
        if not isinstance(url, str):
            continue  # already flagged by check_schema()

        request = urllib.request.Request(_oembed_url(url), method="HEAD", headers=REQUEST_HEADERS)
        try:
            with urllib.request.urlopen(request, timeout=LINK_TIMEOUT_SECONDS) as response:
                status = response.status
        except urllib.error.HTTPError as exc:
            status = exc.code
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            inconclusive.append(f"{label}: could not reach {url} ({exc})")
            continue

        if status in CONFIRMED_BROKEN_STATUSES:
            confirmed_broken.append(f"{label}: {url} no longer resolves (oEmbed HTTP {status})")
        elif status != 200:
            inconclusive.append(f"{label}: {url} returned oEmbed HTTP {status}")

    return confirmed_broken, inconclusive


def check_staleness(days_threshold: int) -> list[str]:
    """Reads storytimefinder.db directly (last_refreshed isn't part of the
    public catalog.json export) and flags items not refreshed recently
    enough to comfortably clear the 30-day compliance window before their
    next scheduled --check-removed run. Returns [] (with a log note, not an
    error) if the DB file isn't present - this check simply doesn't apply
    on a machine that never ran the refresh job."""
    if not DB_PATH.exists():
        log.info("%s not found - skipping staleness check (nothing to compare against)", DB_PATH)
        return []

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT items.title, items.last_refreshed
            FROM items JOIN sources ON sources.id = items.source_id
            WHERE sources.active = 1
            """
        ).fetchall()
    finally:
        conn.close()

    now = datetime.now(timezone.utc)
    warnings: list[str] = []
    for row in rows:
        raw = row["last_refreshed"]
        try:
            last_refreshed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if last_refreshed.tzinfo is None:
                last_refreshed = last_refreshed.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            warnings.append(f"{row['title']}: unparsable last_refreshed {raw!r}")
            continue

        age_days = (now - last_refreshed).total_seconds() / 86400
        if age_days >= days_threshold:
            warnings.append(
                f"{row['title']}: last refreshed {age_days:.1f} day(s) ago "
                f"(compliance limit is {COMPLIANCE_LIMIT_DAYS} days) - run --check-removed soon"
            )
    return warnings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--skip-link-check",
        action="store_true",
        help="Skip the network-dependent HEAD-request link liveness check.",
    )
    parser.add_argument(
        "--fail-on-broken-links",
        action="store_true",
        help="Exit 1 if any item's youtube_music_url returns a confirmed-broken status (404/410). "
        "Off by default since link checks can be affected by transient network issues.",
    )
    parser.add_argument(
        "--stale-warning-days",
        type=int,
        default=STALE_WARNING_DAYS_DEFAULT,
        help=f"Flag items not refreshed in at least this many days (default: {STALE_WARNING_DAYS_DEFAULT}, "
        f"compliance limit is {COMPLIANCE_LIMIT_DAYS}).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    items = load_catalog()
    log.info("Loaded %d item(s) from %s", len(items), CATALOG_PATH)

    exit_code = 0

    schema_errors = check_schema(items)
    if schema_errors:
        log.error("Schema validation FAILED (%d issue(s)):", len(schema_errors))
        for error in schema_errors:
            log.error("  - %s", error)
        exit_code = 1
    else:
        log.info("Schema validation passed (%d item(s) checked)", len(items))

    if args.skip_link_check:
        log.info("Skipping link liveness check (--skip-link-check)")
    else:
        confirmed_broken, inconclusive = check_links(items)
        if confirmed_broken:
            log.warning("%d confirmed-broken link(s):", len(confirmed_broken))
            for line in confirmed_broken:
                log.warning("  - %s", line)
            if args.fail_on_broken_links:
                exit_code = 1
        if inconclusive:
            log.warning("%d inconclusive link check result(s) (not treated as failures):", len(inconclusive))
            for line in inconclusive:
                log.warning("  - %s", line)
        if not confirmed_broken and not inconclusive:
            log.info("Link liveness check passed (%d item(s) checked)", len(items))

    stale = check_staleness(args.stale_warning_days)
    if stale:
        log.warning("%d item(s) approaching the %d-day compliance limit:", len(stale), COMPLIANCE_LIMIT_DAYS)
        for line in stale:
            log.warning("  - %s", line)

    if exit_code:
        log.error("Data quality check FAILED")
    else:
        log.info("Data quality check passed")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
