"""
Standalone refresh job: YouTube Data API -> SQLite -> data/catalog.json

Run this OUTSIDE of Vercel (GitHub Actions, a home-lab cron, or by hand).
It never runs inside the Flask app / Vercel request path.

Usage:
    python refresh/refresh.py

Environment:
    YOUTUBE_API_KEY              required, YouTube Data API v3 key
    STORYTIMEFINDER_DB_PATH       default: data/storytimefinder.db
    STORYTIMEFINDER_CATALOG_PATH  default: data/catalog.json

Compliance notes (YouTube API Developer Policies §III.E):
  - We intentionally never fetch or store statistics (view/like/subscriber
    counts) - only snippet (title, thumbnail) and contentDetails (duration).
    That sidesteps the "re-verify stats within 30 days" requirement entirely.
  - We never compute a derived popularity/ranking score.
  - This script is meant to be run on a schedule of at most 30 days
    (weekly recommended); it fully re-syncs every active source and removes
    items no longer returned by YouTube (deleted/private videos), so the
    exported catalog always reflects current API state.
"""

from __future__ import annotations

import logging
import os
import re
import sqlite3
import sys
import json
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import SOURCES  # noqa: E402
from overrides import ITEM_OVERRIDES  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("refresh")

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("STORYTIMEFINDER_DB_PATH", ROOT / "data" / "storytimefinder.db"))
CATALOG_PATH = Path(os.environ.get("STORYTIMEFINDER_CATALOG_PATH", ROOT / "data" / "catalog.json"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY,
    type TEXT NOT NULL CHECK(type IN ('channel', 'playlist', 'album')),
    youtube_id TEXT NOT NULL UNIQUE,
    label TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT 'de',
    category TEXT NOT NULL,
    age_tag TEXT,
    active BOOLEAN NOT NULL DEFAULT 1,
    added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    video_id TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    thumbnail_url TEXT,
    duration_seconds INTEGER,
    youtube_music_url TEXT NOT NULL,
    description TEXT,
    release_date TEXT,
    publisher TEXT,
    series TEXT,
    position_in_series INTEGER,
    genre TEXT,
    last_refreshed TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_items_source ON items(source_id);
"""

ISO8601_DURATION_RE = re.compile(
    r"^P(?:(?P<days>\d+)D)?"
    r"(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?$"
)


def parse_iso8601_duration(value: str) -> int | None:
    """Parse an ISO 8601 duration (e.g. 'PT1H2M3S') into whole seconds."""
    if not value:
        return None
    match = ISO8601_DURATION_RE.match(value)
    if not match:
        return None
    parts = match.groupdict(default="0")
    days, hours, minutes, seconds = (int(parts[k]) for k in ("days", "hours", "minutes", "seconds"))
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def get_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def sync_sources(conn: sqlite3.Connection) -> None:
    """Upsert the SOURCES seed list into the sources table."""
    for src in SOURCES:
        conn.execute(
            """
            INSERT INTO sources (type, youtube_id, label, language, category, age_tag, active)
            VALUES (:type, :youtube_id, :label, :language, :category, :age_tag, :active)
            ON CONFLICT(youtube_id) DO UPDATE SET
                type = excluded.type,
                label = excluded.label,
                language = excluded.language,
                category = excluded.category,
                age_tag = excluded.age_tag,
                active = excluded.active
            """,
            src,
        )
    conn.commit()


def get_active_sources(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    return conn.execute("SELECT * FROM sources WHERE active = 1").fetchall()


def resolve_uploads_playlist_id(youtube, channel_id: str) -> str | None:
    resp = youtube.channels().list(part="contentDetails", id=channel_id).execute()
    items = resp.get("items", [])
    if not items:
        return None
    return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]


def fetch_playlist_video_ids(youtube, playlist_id: str) -> list[str]:
    video_ids: list[str] = []
    page_token = None
    while True:
        resp = (
            youtube.playlistItems()
            .list(
                part="contentDetails",
                playlistId=playlist_id,
                maxResults=50,
                pageToken=page_token,
            )
            .execute()
        )
        for item in resp.get("items", []):
            video_ids.append(item["contentDetails"]["videoId"])
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return video_ids


def fetch_video_details(youtube, video_ids: list[str]) -> dict[str, dict]:
    """Fetch metadata for a list of video ids, batched 50 at a time.

    Everything here comes straight from the API (snippet + contentDetails).
    Fields the API has no concept of - series, episode number, genre - are
    layered in separately from overrides.py.
    """
    details: dict[str, dict] = {}
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i : i + 50]
        resp = youtube.videos().list(part="snippet,contentDetails", id=",".join(chunk)).execute()
        for item in resp.get("items", []):
            vid = item["id"]
            snippet = item["snippet"]
            thumbnails = snippet.get("thumbnails", {})
            thumb = (
                thumbnails.get("high")
                or thumbnails.get("medium")
                or thumbnails.get("default")
                or {}
            )
            details[vid] = {
                "title": snippet.get("title", ""),
                "thumbnail_url": thumb.get("url"),
                "duration_seconds": parse_iso8601_duration(
                    item["contentDetails"].get("duration", "")
                ),
                "description": snippet.get("description") or None,
                "release_date": snippet.get("publishedAt"),
                "publisher": snippet.get("channelTitle"),
            }
    return details


def sync_source_items(conn: sqlite3.Connection, youtube, source: sqlite3.Row) -> tuple[int, int, int]:
    """Sync one source's items. Returns (added, updated, removed)."""
    if source["type"] == "channel":
        playlist_id = resolve_uploads_playlist_id(youtube, source["youtube_id"])
        if playlist_id is None:
            log.warning("Channel %s (%s) not found, skipping", source["youtube_id"], source["label"])
            return (0, 0, 0)
    else:
        playlist_id = source["youtube_id"]

    video_ids = fetch_playlist_video_ids(youtube, playlist_id)
    details = fetch_video_details(youtube, video_ids)

    existing = {
        row["video_id"]: row["id"]
        for row in conn.execute(
            "SELECT id, video_id FROM items WHERE source_id = ?", (source["id"],)
        ).fetchall()
    }

    added = updated = 0
    seen_video_ids = set()
    now = datetime.now(timezone.utc).isoformat()

    for vid in video_ids:
        info = details.get(vid)
        if info is None:
            continue  # video returned by playlist but not resolvable (private/deleted)
        seen_video_ids.add(vid)
        youtube_music_url = f"https://music.youtube.com/watch?v={vid}"
        override = ITEM_OVERRIDES.get(vid, {})
        publisher = override.get("publisher", info["publisher"])
        series = override.get("series")
        position_in_series = override.get("position_in_series")
        genre = override.get("genre")

        if vid in existing:
            conn.execute(
                """
                UPDATE items
                SET title = ?, thumbnail_url = ?, duration_seconds = ?,
                    youtube_music_url = ?, description = ?, release_date = ?,
                    publisher = ?, series = ?, position_in_series = ?,
                    genre = ?, last_refreshed = ?
                WHERE id = ?
                """,
                (
                    info["title"],
                    info["thumbnail_url"],
                    info["duration_seconds"],
                    youtube_music_url,
                    info["description"],
                    info["release_date"],
                    publisher,
                    series,
                    position_in_series,
                    genre,
                    now,
                    existing[vid],
                ),
            )
            updated += 1
        else:
            conn.execute(
                """
                INSERT INTO items
                    (source_id, video_id, title, thumbnail_url, duration_seconds,
                     youtube_music_url, description, release_date, publisher,
                     series, position_in_series, genre, last_refreshed)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source["id"],
                    vid,
                    info["title"],
                    info["thumbnail_url"],
                    info["duration_seconds"],
                    youtube_music_url,
                    info["description"],
                    info["release_date"],
                    publisher,
                    series,
                    position_in_series,
                    genre,
                    now,
                ),
            )
            added += 1

    stale_ids = [row_id for vid, row_id in existing.items() if vid not in seen_video_ids]
    removed = len(stale_ids)
    if stale_ids:
        conn.executemany("DELETE FROM items WHERE id = ?", [(rid,) for rid in stale_ids])

    conn.commit()
    return (added, updated, removed)


def export_catalog(conn: sqlite3.Connection) -> int:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT items.id, items.title, items.thumbnail_url, items.duration_seconds,
               items.youtube_music_url, items.description, items.release_date,
               items.publisher, items.series, items.position_in_series,
               items.genre,
               sources.category, sources.age_tag, sources.language
        FROM items
        JOIN sources ON sources.id = items.source_id
        WHERE sources.active = 1
        ORDER BY items.title COLLATE NOCASE
        """
    ).fetchall()

    catalog = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "items": [dict(row) for row in rows],
    }

    CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CATALOG_PATH.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(rows)


def main() -> None:
    load_dotenv()
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        log.error("YOUTUBE_API_KEY is not set (see .env.example)")
        sys.exit(1)

    conn = get_db()
    sync_sources(conn)
    sources = get_active_sources(conn)

    if not sources:
        log.warning("No active sources configured - edit refresh/sources.py")
        export_catalog(conn)
        return

    youtube = build("youtube", "v3", developerKey=api_key)

    total_added = total_updated = total_removed = 0
    processed = 0
    for source in sources:
        log.info("Syncing source: %s (%s)", source["label"], source["youtube_id"])
        try:
            added, updated, removed = sync_source_items(conn, youtube, source)
        except HttpError as exc:
            log.error("YouTube API error for source %s: %s", source["label"], exc)
            continue
        processed += 1
        total_added += added
        total_updated += updated
        total_removed += removed
        log.info("  +%d added, %d updated, -%d removed", added, updated, removed)

    item_count = export_catalog(conn)
    log.info(
        "Done. %d/%d sources processed. +%d added, %d updated, -%d removed. "
        "catalog.json now has %d items.",
        processed,
        len(sources),
        total_added,
        total_updated,
        total_removed,
        item_count,
    )


if __name__ == "__main__":
    main()
