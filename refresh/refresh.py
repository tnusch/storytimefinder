"""
Standalone refresh job: YouTube Data API -> SQLite -> data/catalog.json

Run this OUTSIDE of Vercel (GitHub Actions, a home-lab cron, or by hand).
It never runs inside the Flask app / Vercel request path.

Split into two independent phases - see run_fetch()/run_sync() below:
  --fetch  talks to YouTube/Claude, writes ONLY to data/fetched_items.json
           (raw metadata staging) and data/claude_suggestions.json (review
           queue). Never touches storytimefinder.db or catalog.json.
  --sync   the only phase that writes storytimefinder.db and catalog.json.
           Reads data/fetched_items.json (from a prior --fetch) plus
           overrides.py. Never touches the YouTube or Claude APIs.
This lets curation (reviewing Claude's suggestions, editing overrides.py)
happen between a --fetch and the --sync that actually publishes it, without
either step blocking on the other. A --sync with no prior --fetch for a
given source just skips it (logs a warning) rather than deleting its items.

Usage:
    python refresh/refresh.py --fetch                              # pull new metadata + suggestions only
    python refresh/refresh.py --sync                                # rebuild storytimefinder.db + catalog.json from what's staged
    python refresh/refresh.py --fetch --log-responses                # also log raw YouTube API responses
    python refresh/refresh.py --fetch --clean-db                    # wipe storytimefinder.db first (see --clean-db's help)
    python refresh/refresh.py --fetch --clean-fetched                # wipe fetched_items.json first, forcing a full re-fetch
    python refresh/refresh.py --regenerate-suggestion YOUTUBE_ID    # refresh one item's Claude suggestion only

--clean-db and --clean-fetched each wipe only their own file
(storytimefinder.db / data/fetched_items.json respectively) - see their
--help text for exactly what each does and doesn't force a re-fetch of.

Environment:
    YOUTUBE_API_KEY               required for --fetch, YouTube Data API v3 key
    ANTHROPIC_API_KEY             optional, Claude API key - used to generate each new
                                  item's Claude suggestion (description plus
                                  best-effort series/genre/franchise/min_age/
                                  source_release_year/mood/seasonal/awards) in one
                                  combined call (see generate_metadata_suggestions()) -
                                  all ten fields are written to data/claude_suggestions.json
                                  for manual review, NEVER directly into the catalog (see
                                  overrides.py). awards uses the web search tool to verify
                                  real wins; the other nine fields never call out. If unset,
                                  new items are fetched with no suggestions at all.
    STORYTIMEFINDER_DB_PATH       default: data/storytimefinder.db
    STORYTIMEFINDER_CATALOG_PATH  default: data/catalog.json
    STORYTIMEFINDER_SUGGESTIONS_PATH     default: data/claude_suggestions.json
    STORYTIMEFINDER_FETCHED_ITEMS_PATH   default: data/fetched_items.json

Compliance notes (YouTube API Developer Policies §III.E):
  - We intentionally never fetch or store statistics (view/like/subscriber
    counts) - only snippet (title, thumbnail) and contentDetails (duration).
    That sidesteps the "re-verify stats within 30 days" requirement entirely.
  - We never compute a derived popularity/ranking score.
  - --fetch is meant to be run on a schedule of at most 30 days (weekly
    recommended) - it's the phase that enumerates each source's current
    items via playlistItems.list, which is what --sync uses to delete items
    no longer returned by YouTube. Running --fetch alone does NOT remove
    anything from the live catalog by itself - --sync has to run afterward
    for a detected removal to actually take effect, so in practice run them
    back-to-back (as the GitHub Action does) unless you're deliberately
    holding a --sync back for review.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sqlite3
import sys
import json
from datetime import datetime, timezone
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import SOURCES  # noqa: E402
from overrides import ITEM_OVERRIDES  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("refresh")

# Set from --log-responses in main(); read by log_api_response() below.
LOG_API_RESPONSES = False


def log_api_response(label: str, resp: dict) -> None:
    """Log a raw YouTube API response verbatim, gated by --log-responses."""
    if LOG_API_RESPONSES:
        log.info("API response [%s]:\n%s", label, json.dumps(resp, indent=2, ensure_ascii=False))

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("STORYTIMEFINDER_DB_PATH", ROOT / "data" / "storytimefinder.db"))
CATALOG_PATH = Path(os.environ.get("STORYTIMEFINDER_CATALOG_PATH", ROOT / "data" / "catalog.json"))
SUGGESTIONS_PATH = Path(
    os.environ.get("STORYTIMEFINDER_SUGGESTIONS_PATH", ROOT / "data" / "claude_suggestions.json")
)
FETCHED_ITEMS_PATH = Path(
    os.environ.get("STORYTIMEFINDER_FETCHED_ITEMS_PATH", ROOT / "data" / "fetched_items.json")
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY,
    type TEXT NOT NULL CHECK(type IN ('channel', 'playlist', 'album')),
    youtube_id TEXT NOT NULL UNIQUE,
    label TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT 'de',
    active BOOLEAN NOT NULL DEFAULT 1,
    added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    -- A real YouTube video id for 'channel'/'playlist' sources (one row per
    -- video), or the playlist/album id itself for 'album' sources (one row
    -- for the whole album) - see build_track_entries()/build_album_entry().
    video_id TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    thumbnail_url TEXT,
    duration_seconds INTEGER,
    youtube_music_url TEXT NOT NULL,
    description TEXT,
    series TEXT,
    position_in_series INTEGER,
    -- genre/franchise/min_age/source_release_year are per-item, curated
    -- entirely through overrides.py - there's no API source for any of
    -- them, so they're always None unless ITEM_OVERRIDES sets them
    -- explicitly. genre/franchise are each checked against a fixed value
    -- list (see GENRE_VALUES/FRANCHISE_VALUES below and overrides.py's
    -- docstring).
    genre TEXT,
    franchise TEXT,
    -- Precise minimum age from the publisher/retailer, e.g. 4. Override-only
    -- input; age_tag (below) is derived from it, not set directly - see
    -- derive_age_tag().
    min_age INTEGER,
    -- Coarse, filterable age bracket computed from min_age via
    -- derive_age_tag() - one of AGE_BRACKETS' slugs, or None if min_age is
    -- unset. Stored (not computed at read time) so app/data.py's filtering
    -- stays a plain catalog.json read, same as every other field.
    age_tag TEXT,
    -- Year the SOURCE film/book was originally released - NOT the audiobook
    -- production's own release/upload date, which is often ambiguous across
    -- multiple editions and reissues. Override-only, year only (no API
    -- source for this - YouTube's publishedAt is the audiobook upload date,
    -- deliberately not used here).
    source_release_year INTEGER,
    -- Override-only, no API source, same as everything above. Single value
    -- from MOOD_VALUES - a subjective/generative read of the story's tone,
    -- not a factual claim, but still gated behind human review like every
    -- other field (see overrides.py's docstring).
    mood TEXT,
    -- Override-only. Single value from SEASONAL_VALUES, or NULL for the
    -- (expected-to-be-majority) non-seasonal case - never force a value.
    seasonal TEXT,
    -- Override-only. JSON-serialized array of {"name","category","year"}
    -- objects, e.g. '[]' or '[{"name": "...", "category": "...", "year": 2026}]'.
    -- Factual claims - Claude is asked to verify these with web search
    -- rather than infer them, but still only ever a suggestion for a human
    -- to review (see generate_metadata_suggestions()/AWARD_VALUES below).
    awards TEXT NOT NULL DEFAULT '[]',
    last_refreshed TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_items_source ON items(source_id);
"""

# Fixed vocabularies for the genre/franchise overrides - see overrides.py's
# docstring. Not enforced via a DB CHECK constraint (changing the list would
# need a schema migration); sync_source_items() logs a warning instead if an
# override uses a value outside these sets, so a typo is caught without
# hard-failing the whole refresh run.
GENRE_VALUES = {
    "fairy_tale",
    "adventure",
    "mystery",
    "fantasy",
    "educational",
    "bedtime_story",
    "classic",
    "comedy",
}
FRANCHISE_VALUES = {
    "disney",
    "pixar",
    "dreamworks",
    "marvel",
    "star_wars",
    "bibi_blocksberg",
    "benjamin_bluemchen",
    "die_drei_fragezeichen",
    "tkkg",
}
MOOD_VALUES = {
    "calm",
    "funny",
    "spooky",
    "adventurous",
    "heartwarming",
    "exciting",
    "silly",
    "gentle",
}
SEASONAL_VALUES = {
    "winter",
    "christmas",
    "halloween",
    "easter",
    "summer",
    "birthday",
}
# Starter list, not a claim of completeness - a soft consistency check (same
# warning-not-block treatment as GENRE_VALUES/FRANCHISE_VALUES), meant to be
# extended by hand as more real awards get curated. Seeded with the one
# award already referenced indirectly in overrides.py's min_age docs
# ("Deutscher Kinderhoerbuchpreis BEO Kategorie II/III") plus its general
# (non-children's-specific) sibling award.
AWARD_VALUES = {
    "Deutscher Hörbuchpreis",
    "Deutscher Kinderhörbuchpreis",
}

# (slug, inclusive lower bound, exclusive upper bound - None means no upper
# bound) - see derive_age_tag(). Order matters: it's iterated in order and
# the first matching bracket wins.
AGE_BRACKETS = [
    ("0_3", 0, 3),
    ("3_5", 3, 6),
    ("6_8", 6, 9),
    ("9_11", 9, 12),
    ("12_plus", 12, None),
]


def derive_age_tag(min_age: int | None) -> str | None:
    """Bracket a precise minimum age down to a coarse, filterable age_tag.

    Brackets (see AGE_BRACKETS): 0_3 (toddlers, very short attention span,
    sound/music-driven content), 3_5 (kindergarten age, matches most "ab
    3/4/5" publisher labels), 6_8 (early readers, most Disney Hoerspiele
    land here), 9_11 (matches Deutscher Kinderhoerbuchpreis BEO Kategorie
    II), 12_plus (matches BEO Kategorie III, older/literary content).

    Single-select by design, not multi-select: a catalog item has exactly
    one min_age, so exactly one bracket, avoiding overlapping-bracket
    filter UI complexity. If a source gives conflicting minimum ages across
    editions, that's resolved before it gets here - overrides.py's min_age
    should already be the lower of the two (see its docstring) - this
    function just does the bracket lookup.
    """
    if not isinstance(min_age, int) or min_age < 0:
        return None
    for slug, low, high in AGE_BRACKETS:
        if min_age >= low and (high is None or min_age < high):
            return slug
    return None

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
            INSERT INTO sources (type, youtube_id, label, language, active)
            VALUES (:type, :youtube_id, :label, :language, :active)
            ON CONFLICT(youtube_id) DO UPDATE SET
                type = excluded.type,
                label = excluded.label,
                language = excluded.language,
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
    log_api_response(f"channels.list id={channel_id}", resp)
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
        log_api_response(f"playlistItems.list playlistId={playlist_id} page={page_token}", resp)
        for item in resp.get("items", []):
            video_ids.append(item["contentDetails"]["videoId"])
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return video_ids


def select_thumbnail(thumbnails: dict) -> dict:
    """Pick the best available thumbnail, preferring sizes with the video's
    true (usually 16:9) aspect ratio over YouTube's legacy 4:3-padded ones.

    `high`/`standard`/`default` (hqdefault/sddefault/default.jpg) are
    fixed 4:3 frames - for any 16:9 video, that bakes visible black
    letterboxing bars into the image itself (verified: hqdefault is a
    literal 480x360 JPEG, not just CSS-cropped). `medium`/`maxres`
    (mqdefault/maxresdefault.jpg) are the true 16:9 aspect with no bars, so
    they're preferred even though `medium` is lower-resolution than `high` -
    a smaller correct image beats a bigger letterboxed one, since
    `.card-thumb`'s `object-fit: cover` only crops, it can't remove bars
    that are already part of the pixels.
    """
    return (
        thumbnails.get("maxres")
        or thumbnails.get("medium")
        or thumbnails.get("high")
        or thumbnails.get("standard")
        or thumbnails.get("default")
        or {}
    )


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
        log_api_response(f"videos.list id={','.join(chunk)}", resp)
        for item in resp.get("items", []):
            vid = item["id"]
            snippet = item["snippet"]
            thumb = select_thumbnail(snippet.get("thumbnails", {}))
            details[vid] = {
                "title": snippet.get("title", ""),
                "thumbnail_url": thumb.get("url"),
                "duration_seconds": parse_iso8601_duration(
                    item["contentDetails"].get("duration", "")
                ),
                "description": snippet.get("description") or None,
            }
    return details


def fetch_album_details(youtube, playlist_id: str) -> dict | None:
    """Fetch title/description/thumbnail for a playlist as a whole."""
    resp = youtube.playlists().list(part="snippet", id=playlist_id).execute()
    log_api_response(f"playlists.list id={playlist_id}", resp)
    items = resp.get("items", [])
    if not items:
        return None
    snippet = items[0]["snippet"]
    thumb = select_thumbnail(snippet.get("thumbnails", {}))
    return {
        "title": snippet.get("title", ""),
        "thumbnail_url": thumb.get("url"),
        "description": snippet.get("description") or None,
    }


SUGGESTION_MODEL = "claude-haiku-4-5-20251001"
# Raised from the original 500 to leave headroom for the web search tool's
# result blocks (see generate_metadata_suggestions()) on top of the JSON
# answer itself.
SUGGESTION_MAX_TOKENS = 1024
# Web search is only meant to verify awards - max_uses bounds it so a single
# item's suggestion call can't spiral into many searches.
AWARDS_WEB_SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search", "max_uses": 3}
DESCRIPTION_LANGUAGE_NAMES = {"de": "German", "en": "English"}
SUGGESTION_MAX_ATTEMPTS = 2

# Keys generate_metadata_suggestions() always returns, all None if the client
# is missing or the call fails outright.
EMPTY_SUGGESTIONS = {
    "description": None,
    "series": None,
    "position_in_series": None,
    "genre": None,
    "franchise": None,
    "min_age": None,
    "source_release_year": None,
    "mood": None,
    "seasonal": None,
    "awards": [],
}

_TITLE_PAREN_RE = re.compile(r"[\(\[][^)\]]*[\)\]]")
_TITLE_PREFIX_RE = re.compile(r"^(album\s*-\s*|kapitel\s*\d+\s*:?\s*|chapter\s*\d+\s*:?\s*)", re.IGNORECASE)
_TITLE_STOPWORDS = {
    "der", "die", "das", "und", "von", "zum", "zur", "ein", "eine", "the", "and", "of", "a", "an",
}
_CODE_FENCE_RE = re.compile(r"^```[a-zA-Z]*\n?|\n?```$")


def _title_keywords(title: str) -> list[str]:
    """Distinctive words from a title (names, franchise words) - used to check
    whether a generated description echoes the title back instead of just
    describing the story."""
    cleaned = _TITLE_PAREN_RE.sub("", title)
    cleaned = _TITLE_PREFIX_RE.sub("", cleaned)
    return [
        word
        for word in re.findall(r"[\wÀ-ÿ]+", cleaned)
        if len(word) >= 4 and word.lower() not in _TITLE_STOPWORDS
    ]


def _description_leaks_title(description: str, title: str) -> bool:
    description_lower = description.lower()
    return any(
        re.search(rf"\b{re.escape(word.lower())}\b", description_lower) for word in _title_keywords(title)
    )


def _parse_suggestion_json(raw_text: str) -> dict | None:
    """Parse Claude's JSON response, tolerating a ```json ... ``` code fence
    (a common LLM habit even when told not to use one) and, since the web
    search tool was added for awards (see AWARDS_WEB_SEARCH_TOOL), a bit of
    explanatory prose Claude sometimes wraps around the JSON after reasoning
    about search results - despite being told the final message must be
    ONLY the object. Falls back to extracting the first {...} span and
    parsing that if the whole string isn't valid JSON on its own."""
    try:
        text = _CODE_FENCE_RE.sub("", raw_text.strip())
    except AttributeError:
        return None
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


def _clean_str(value) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _clean_int(value) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value)
    return None


def _validate_awards(raw) -> list[dict]:
    """Coerce/validate a suggested `awards` value - drops anything that
    isn't a well-formed {"name", "category", "year"} object, clamps `year`
    to a plausible range, and logs (doesn't drop) an entry whose `name`
    isn't in AWARD_VALUES, same warning-not-block treatment as genre/
    franchise: AWARD_VALUES is a starter list, not a hard allowlist."""
    if not isinstance(raw, list):
        return []
    cleaned = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        name = _clean_str(entry.get("name"))
        if not name:
            continue
        if name not in AWARD_VALUES:
            log.warning(
                "Suggested award %r is not in AWARD_VALUES %s - keeping it, add it to the "
                "list by hand if it's legitimate",
                name, sorted(AWARD_VALUES),
            )
        year = _clean_int(entry.get("year"))
        if year is not None and not (1900 <= year <= 2100):
            year = None
        cleaned.append({"name": name, "category": _clean_str(entry.get("category")), "year": year})
    return cleaned


def _validate_suggested_fields(raw: dict) -> dict:
    """Coerce/validate the nine non-description fields from a parsed Claude
    response - genre/franchise/mood/seasonal are dropped (set None) if
    Claude proposed a value outside their fixed lists, min_age/
    source_release_year are dropped if not a sane non-negative int /
    plausible year, awards go through _validate_awards(). These are
    suggestions for a human to review (see save_suggestions()), never
    written to the catalog directly, but there's no reason to keep an
    obviously-bad value around."""
    genre = _clean_str(raw.get("genre"))
    if genre not in GENRE_VALUES:
        genre = None
    franchise = _clean_str(raw.get("franchise"))
    if franchise not in FRANCHISE_VALUES:
        franchise = None
    min_age = _clean_int(raw.get("min_age"))
    if min_age is not None and min_age < 0:
        min_age = None
    source_release_year = _clean_int(raw.get("source_release_year"))
    if source_release_year is not None and not (1850 <= source_release_year <= 2100):
        source_release_year = None
    mood = _clean_str(raw.get("mood"))
    if mood not in MOOD_VALUES:
        mood = None
    seasonal = _clean_str(raw.get("seasonal"))
    if seasonal not in SEASONAL_VALUES:
        seasonal = None
    return {
        "series": _clean_str(raw.get("series")),
        "position_in_series": _clean_int(raw.get("position_in_series")),
        "genre": genre,
        "franchise": franchise,
        "min_age": min_age,
        "source_release_year": source_release_year,
        "mood": mood,
        "seasonal": seasonal,
        "awards": _validate_awards(raw.get("awards")),
    }


def _final_text_block(message) -> str:
    """Extract the answer text from a Claude response. Can't just use
    content[0].text - with the web search tool enabled (see
    generate_metadata_suggestions()), the response may include
    server_tool_use/web_search_tool_result blocks *before* the final text
    block, so content[0] isn't reliably the answer anymore. Returns "" if no
    text block is present at all (e.g. the model only emitted tool calls)."""
    text_blocks = [block.text for block in message.content if getattr(block, "type", None) == "text"]
    return text_blocks[-1] if text_blocks else ""


def generate_metadata_suggestions(claude_client, title: str, language: str) -> dict:
    """One combined Claude call per new item: a description, plus
    best-effort suggestions for series/position_in_series/genre/franchise/
    min_age/source_release_year/mood/seasonal/awards - a single request
    instead of ten, to keep token spend down. Only called for items not
    already in the DB (see sync_source_items) - already-synced items don't
    trigger another call (and more API usage) on every re-sync.

    None of these ten fields are EVER written to the catalog/DB directly -
    all are suggestions only, for a human to review in
    data/claude_suggestions.json (see save_suggestions()) and, if they agree,
    copy into overrides.py by hand. overrides.py always wins; nothing here is
    ever treated as authoritative, `description` included - see
    sync_source_items(), which reads `description` from ITEM_OVERRIDES
    exactly like every other field.

    mood/seasonal are generative judgment calls (no web search needed -
    the prompt tells Claude not to search for them); awards is a factual
    claim, so the web search tool (AWARDS_WEB_SEARCH_TOOL) is enabled on
    this call specifically so Claude can verify a real win instead of
    guessing. That's the only reason this call has a tool at all - the
    other nine fields never need one.

    Returns a dict with all of EMPTY_SUGGESTIONS' keys, each None (or `[]`
    for awards) if the client is missing, the call fails outright, or that
    particular field wasn't confidently determined. The description must
    never repeat the item's own title/name back - the title is already
    shown right next to it on the card, so that would be redundant. Since
    an LLM won't reliably honor a "don't mention X" instruction on every
    call, _description_leaks_title() checks the actual output and, if it
    still names the title, retries once with a firmer prompt (metadata
    fields get regenerated too, which is free within the same retry); if it
    leaks again, the description is dropped but whatever metadata was
    parsed is still returned.
    """
    if claude_client is None:
        return dict(EMPTY_SUGGESTIONS)
    language_name = DESCRIPTION_LANGUAGE_NAMES.get(language, language)
    genre_list = ", ".join(sorted(GENRE_VALUES))
    franchise_list = ", ".join(sorted(FRANCHISE_VALUES))
    mood_list = ", ".join(sorted(MOOD_VALUES))
    seasonal_list = ", ".join(sorted(SEASONAL_VALUES))
    award_list = ", ".join(sorted(AWARD_VALUES))
    parsed = None
    for attempt in range(SUGGESTION_MAX_ATTEMPTS):
        prompt = (
            f'The children\'s audio drama is called "{title}". Return ONLY a JSON object '
            "(no markdown, no extra text) with these fields:\n"
            f'- "description": one-sentence, max 130 character, spoiler-light description of '
            f"its story, in {language_name}. Describe the plot/theme only - do not use the "
            "title, franchise name, or any character names from it anywhere in this field.\n"
            '- "series": the name of the audiobook series this belongs to, if you recognize '
            'one (e.g. "Die drei ???"), otherwise null.\n'
            '- "position_in_series": that series\' episode/volume number as an integer, '
            "otherwise null.\n"
            f'- "genre": exactly one of [{genre_list}] that best fits, otherwise null.\n'
            f'- "franchise": exactly one of [{franchise_list}] if this belongs to one of '
            "these IP franchises, otherwise null.\n"
            '- "min_age": the publisher/retailer\'s recommended minimum age as an integer, '
            "only if you're reasonably confident, otherwise null.\n"
            '- "source_release_year": the year the SOURCE film or book this is based on was '
            "originally released (not this audiobook's own release) as an integer, only if "
            "known, otherwise null.\n"
            f'- "mood": exactly one of [{mood_list}] - your best-effort subjective read of the '
            "overall tone from the title/franchise/description context. This is a creative "
            "judgment call, not a factual lookup - do not use web search for this, always "
            "provide your best guess rather than null.\n"
            f'- "seasonal": exactly one of [{seasonal_list}] if the story is clearly tied to a '
            "specific season or holiday (e.g. explicitly Christmas- or Halloween-themed), "
            "otherwise null. Most titles are NOT seasonal - like mood, this is a subjective "
            "judgment call, not a web search - only set it when obvious, don't force a value.\n"
            '- "awards": an array of {"name": ..., "category": ..., "year": ...} objects for '
            "real, verifiable awards this SPECIFIC title has actually won - unlike the fields "
            "above, this IS a factual claim, so use web search to check rather than guessing. "
            f"Prefer these known award names when they apply: [{award_list}]. Return an empty "
            "array if you don't find a real, verifiable win - never guess or invent one.\n"
            "Only fill in a field if you're reasonably confident - use null (or an empty array "
            "for awards) rather than guessing, except mood which should always get a value. "
            "If you use web search to check for awards, your FINAL message must still contain "
            "ONLY the JSON object - do not add any explanation of what you searched for or found "
            "before or after it."
        )
        if attempt > 0:
            prompt += (
                f' Your previous answer\'s "description" field still named "{title}" or a '
                "character from it - rewrite just that field so the story is described "
                "generically, with no names from the title at all. Keep the other fields."
            )
        try:
            message = claude_client.messages.create(
                model=SUGGESTION_MODEL,
                max_tokens=SUGGESTION_MAX_TOKENS,
                messages=[{"role": "user", "content": prompt}],
                tools=[AWARDS_WEB_SEARCH_TOOL],
            )
        except Exception as exc:
            log.warning("Claude metadata suggestion failed for %r: %s", title, exc)
            return dict(EMPTY_SUGGESTIONS)

        raw_text = _final_text_block(message)
        parsed = _parse_suggestion_json(raw_text)
        if parsed is None:
            log.warning("Claude returned unparsable JSON for %r: %r", title, raw_text)
            continue

        description = _clean_str(parsed.get("description"))
        if description and not _description_leaks_title(description, title):
            result = {"description": description}
            result.update(_validate_suggested_fields(parsed))
            return result

    log.warning("Claude description for %r kept naming the title - leaving it blank", title)
    result = dict(EMPTY_SUGGESTIONS)
    if parsed:
        result.update(_validate_suggested_fields(parsed))
    return result


def load_suggestions() -> dict:
    """Load the existing Claude suggestions review file, if any (see
    save_suggestions()). Tolerates a missing or corrupt file - starts fresh
    rather than failing the whole refresh run over a scratch file."""
    if not SUGGESTIONS_PATH.exists():
        return {}
    try:
        return json.loads(SUGGESTIONS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        log.warning("Could not read %s - starting with an empty suggestions file", SUGGESTIONS_PATH)
        return {}


def save_suggestions(suggestions: dict) -> None:
    SUGGESTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUGGESTIONS_PATH.write_text(
        json.dumps(suggestions, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )


def load_fetched_items() -> dict:
    """Load the fetch-phase staging file (see fetch_source()/save_fetched_items()).

    Shape: {"sources": {source_youtube_id: {"current_item_ids": [...], "fetched_at": ...}},
            "items": {entry_id: {...entry fields..., "source_youtube_id": ...}}}
    `sources` is how sync_source() detects removals without ever calling the
    YouTube API itself; `items` is raw metadata for not-yet-synced items,
    pruned by sync_source() once it consumes each one. Tolerates a missing
    or corrupt file - starts fresh rather than failing the whole run over a
    scratch file.
    """
    if not FETCHED_ITEMS_PATH.exists():
        return {"sources": {}, "items": {}}
    try:
        data = json.loads(FETCHED_ITEMS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        log.warning("Could not read %s - starting with no staged fetch data", FETCHED_ITEMS_PATH)
        return {"sources": {}, "items": {}}
    data.setdefault("sources", {})
    data.setdefault("items", {})
    return data


def save_fetched_items(fetched_items: dict) -> None:
    FETCHED_ITEMS_PATH.parent.mkdir(parents=True, exist_ok=True)
    FETCHED_ITEMS_PATH.write_text(
        json.dumps(fetched_items, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )


def record_suggestion(suggestions: dict, entry_id: str, title: str, result: dict) -> None:
    """Add/update one item's entry in the in-memory suggestions accumulator -
    only if Claude proposed at least one field worth a human reviewing (an
    all-empty suggestion isn't worth cluttering the file with - `[]` counts
    as empty here too, same as None, since that's awards' "nothing found"
    default). This now includes `description` too, same as the other fields
    - nothing from Claude reaches the catalog/DB directly (see
    sync_source_items()); a human has to copy an approved value into
    overrides.py by hand. `suggestions` is mutated in place; see
    save_suggestions() for the eventual write, and load_suggestions() for
    why previously-recorded entries for other items are preserved across
    runs."""
    fields = {key: result.get(key) for key in EMPTY_SUGGESTIONS}
    if not any(value not in (None, []) for value in fields.values()):
        return
    suggestions[entry_id] = {
        "title": title,
        "suggested_at": datetime.now(timezone.utc).isoformat(),
        **fields,
    }


def build_track_entries(
    video_ids: list[str], video_details: dict[str, dict], claude_client, language: str, suggestions: dict
) -> list[dict]:
    """One catalog entry per video - used for 'channel' and 'playlist' sources.

    Entries deliberately carry no `description` - Claude's suggestion (see
    generate_metadata_suggestions()) is recorded for human review only; the
    actual `description` written to the DB always comes from
    ITEM_OVERRIDES, same as genre/franchise/etc (see sync_source_items()).
    """
    entries = []
    for vid in video_ids:
        info = video_details.get(vid)
        if info is None:
            continue  # video returned by playlist but not resolvable (private/deleted)
        result = generate_metadata_suggestions(claude_client, info["title"], language)
        record_suggestion(suggestions, vid, info["title"], result)
        entries.append(
            {
                "id": vid,
                "title": info["title"],
                "thumbnail_url": info["thumbnail_url"],
                "duration_seconds": info["duration_seconds"],
                "youtube_music_url": f"https://music.youtube.com/watch?v={vid}",
            }
        )
    return entries


def build_album_entry(
    youtube,
    playlist_id: str,
    video_ids: list[str],
    video_details: dict[str, dict],
    claude_client,
    language: str,
    label: str,
    suggestions: dict,
) -> list[dict]:
    """A single catalog entry for the whole album - used for 'album' sources.

    An audiobook album is usually split across many YouTube tracks (one per
    chapter); those should show up in the catalog as one audiobook, not one
    row per chapter. Duration is the sum of every resolvable chapter. Title
    is always the source's curated `label` from sources.py, never the raw
    YouTube playlist title (which tends to be noisy, e.g. "Album - Findet
    Nemo (Hoerspiel zum Disney/Pixar Film)") - an album source collapses to
    exactly one item, so the label maps 1:1 onto it and re-syncing must
    never silently overwrite a manual edit to it with whatever YouTube
    happens to call the playlist. The returned entry carries no
    `description` - Claude's suggestion (from that same label) is recorded
    for human review only; the actual `description` written to the DB
    always comes from ITEM_OVERRIDES (see sync_source_items()).

    Thumbnail prefers the first chapter's over the playlist's own:
    playlists().list returns a signed, session-scoped thumbnail URL
    (i9.ytimg.com/s_p/<playlist_id>/...?sqp=...&rs=...) that expires within
    hours, whereas videos().list returns a stable, unsigned URL
    (i.ytimg.com/vi/<video_id>/...) that doesn't. Since catalog.json is
    committed and only refreshed weekly, an expiring thumbnail URL would
    show as a broken image for most of that week - so thumbnail_url prefers
    the first chapter's (stable) thumbnail, only falling back to the
    playlist's own (expiring) one if no chapter thumbnail is available.
    """
    album = fetch_album_details(youtube, playlist_id) or {}
    first = video_details.get(video_ids[0]) if video_ids else None

    durations = [
        video_details[vid]["duration_seconds"]
        for vid in video_ids
        if video_details.get(vid) and video_details[vid]["duration_seconds"]
    ]

    thumbnail_url = (first["thumbnail_url"] if first else None) or album.get("thumbnail_url")

    result = generate_metadata_suggestions(claude_client, label, language)
    record_suggestion(suggestions, playlist_id, label, result)

    return [
        {
            "id": playlist_id,
            "title": label,
            "thumbnail_url": thumbnail_url,
            "duration_seconds": sum(durations) if durations else None,
            "youtube_music_url": f"https://music.youtube.com/playlist?list={playlist_id}",
        }
    ]


def get_existing_items(conn: sqlite3.Connection, source_id: int) -> dict[str, sqlite3.Row]:
    """Already-synced items for a source, keyed by video_id (or album id)."""
    conn.row_factory = sqlite3.Row
    return {
        row["video_id"]: row
        for row in conn.execute("SELECT * FROM items WHERE source_id = ?", (source_id,)).fetchall()
    }


def get_existing_items_by_youtube_id(conn: sqlite3.Connection, source_youtube_id: str) -> dict[str, sqlite3.Row]:
    """Same as get_existing_items(), but looked up by the source's own
    youtube_id rather than its DB id - tolerates the source having no
    `sources` row at all yet (a source that's never been synced), returning
    an empty dict rather than erroring. Read-only; used by fetch_source(),
    which must never write to the `sources`/`items` tables (see its
    docstring) - this lets it still know what's already synced without
    calling sync_sources() first.
    """
    conn.row_factory = sqlite3.Row
    source_row = conn.execute("SELECT id FROM sources WHERE youtube_id = ?", (source_youtube_id,)).fetchone()
    if source_row is None:
        return {}
    return {
        row["video_id"]: row
        for row in conn.execute("SELECT * FROM items WHERE source_id = ?", (source_row["id"],)).fetchall()
    }


def row_to_entry(row: sqlite3.Row) -> dict:
    """Rebuild an entry dict from an already-synced DB row - no API call needed.

    No `description` here either, for the same reason build_track_entries()/
    build_album_entry() don't carry one - it's computed fresh from
    ITEM_OVERRIDES every time in sync_source(), never read back off a prior
    entry.
    """
    return {
        "id": row["video_id"],
        "title": row["title"],
        "thumbnail_url": row["thumbnail_url"],
        "duration_seconds": row["duration_seconds"],
        "youtube_music_url": row["youtube_music_url"],
    }


def fetch_source(youtube, claude_client, source: dict, conn: sqlite3.Connection, fetched_items: dict, suggestions: dict) -> int:
    """Fetch phase for one source. Returns how many new items were fetched.

    Always enumerates the source's current items via playlistItems.list
    (cheap, 1 unit/page) and records that full id list into
    `fetched_items["sources"][source_youtube_id]` - this is what sync_source()
    later uses to detect removals, since sync never calls the YouTube API
    itself. Then fetches full metadata + a Claude suggestion (the expensive
    calls) only for items not already synced (checked read-only via
    get_existing_items_by_youtube_id() - never via sync_sources(), which
    this never calls) and not already staged from a previous --fetch run,
    storing the result into `fetched_items["items"]`.

    `source` is a plain dict from sources.py's SOURCES list, not a DB row -
    deliberately, so this works correctly for a source that's never been
    synced before. Writes ONLY to the in-memory `fetched_items`/`suggestions`
    dicts (saved by the caller) - never to the database or catalog.json.
    """
    if source["type"] == "channel":
        playlist_id = resolve_uploads_playlist_id(youtube, source["youtube_id"])
        if playlist_id is None:
            log.warning("Channel %s (%s) not found, skipping", source["youtube_id"], source["label"])
            return 0
    else:
        playlist_id = source["youtube_id"]

    video_ids = fetch_playlist_video_ids(youtube, playlist_id)
    current_item_ids = [playlist_id] if source["type"] == "album" else video_ids

    fetched_items["sources"][source["youtube_id"]] = {
        "current_item_ids": current_item_ids,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }

    existing = get_existing_items_by_youtube_id(conn, source["youtube_id"])
    staged_items = fetched_items["items"]

    if source["type"] == "album":
        if playlist_id in existing or playlist_id in staged_items:
            return 0
        video_details = fetch_video_details(youtube, video_ids)
        entries = build_album_entry(
            youtube, playlist_id, video_ids, video_details, claude_client, source["language"], source["label"], suggestions,
        )
    else:
        new_ids = [vid for vid in video_ids if vid not in existing and vid not in staged_items]
        if not new_ids:
            return 0
        video_details = fetch_video_details(youtube, new_ids)
        entries = build_track_entries(new_ids, video_details, claude_client, source["language"], suggestions)

    for entry in entries:
        staged_items[entry["id"]] = {**entry, "source_youtube_id": source["youtube_id"]}

    return len(entries)


def sync_source(conn: sqlite3.Connection, source: sqlite3.Row, fetched_items: dict) -> tuple[int, int, int] | None:
    """Sync phase for one source. Returns (added, updated, removed), or None
    (logging a warning, touching nothing) if this source has no staged fetch
    data at all yet - run --fetch first.

    Applies whatever fetch_source() staged in `fetched_items` into the
    database: `current_item_ids` (recorded per source at fetch time) is
    compared against what's already in the DB to find both new items to
    insert (pulled from `fetched_items["items"]`, then pruned from there
    once consumed) and stale ones to delete - the same removal-detection
    the old combined sync used to do inline, just using data staged earlier
    instead of a live playlistItems.list call. Never calls the YouTube or
    Claude APIs.
    """
    staged_source = fetched_items["sources"].get(source["youtube_id"])
    if staged_source is None:
        log.warning(
            "No fetched data for source %s (%s) - run --fetch first, skipping",
            source["youtube_id"], source["label"],
        )
        return None

    current_item_ids = staged_source["current_item_ids"]
    staged_items = fetched_items["items"]
    existing = get_existing_items(conn, source["id"])
    existing_ids = {vid: row["id"] for vid, row in existing.items()}

    entries = []
    for entry_id in current_item_ids:
        if entry_id in existing:
            entry = row_to_entry(existing[entry_id])
            if source["type"] == "album":
                entry["title"] = source["label"]  # sources.py always wins over the stored title
            entries.append(entry)
        elif entry_id in staged_items:
            entries.append(staged_items[entry_id])
        else:
            log.warning(
                "Item %s (source %s) is listed as current but has no staged metadata - "
                "run --fetch again, skipping this item",
                entry_id, source["youtube_id"],
            )

    added = updated = 0
    seen_ids = set()
    now = datetime.now(timezone.utc).isoformat()

    for entry in entries:
        entry_id = entry["id"]
        seen_ids.add(entry_id)
        override = ITEM_OVERRIDES.get(entry_id, {})
        description = override.get("description")
        series = override.get("series")
        position_in_series = override.get("position_in_series")
        genre = override.get("genre")
        if genre and genre not in GENRE_VALUES:
            log.warning("Item %s: genre %r is not in GENRE_VALUES %s", entry_id, genre, sorted(GENRE_VALUES))
        franchise = override.get("franchise")
        if franchise and franchise not in FRANCHISE_VALUES:
            log.warning(
                "Item %s: franchise %r is not in FRANCHISE_VALUES %s", entry_id, franchise, sorted(FRANCHISE_VALUES)
            )
        if "age_tag" in override:
            log.warning(
                "Item %s: 'age_tag' override is ignored - age_tag is now derived from 'min_age' instead",
                entry_id,
            )
        min_age = override.get("min_age")
        age_tag = derive_age_tag(min_age)
        source_release_year = override.get("source_release_year")
        mood = override.get("mood")
        if mood and mood not in MOOD_VALUES:
            log.warning("Item %s: mood %r is not in MOOD_VALUES %s", entry_id, mood, sorted(MOOD_VALUES))
        seasonal = override.get("seasonal")
        if seasonal and seasonal not in SEASONAL_VALUES:
            log.warning(
                "Item %s: seasonal %r is not in SEASONAL_VALUES %s", entry_id, seasonal, sorted(SEASONAL_VALUES)
            )
        awards_json = json.dumps(override.get("awards") or [], ensure_ascii=False)

        if entry_id in existing_ids:
            conn.execute(
                """
                UPDATE items
                SET title = ?, thumbnail_url = ?, duration_seconds = ?,
                    youtube_music_url = ?, description = ?,
                    series = ?, position_in_series = ?,
                    genre = ?, franchise = ?, min_age = ?, age_tag = ?, source_release_year = ?,
                    mood = ?, seasonal = ?, awards = ?,
                    last_refreshed = ?
                WHERE id = ?
                """,
                (
                    entry["title"],
                    entry["thumbnail_url"],
                    entry["duration_seconds"],
                    entry["youtube_music_url"],
                    description,
                    series,
                    position_in_series,
                    genre,
                    franchise,
                    min_age,
                    age_tag,
                    source_release_year,
                    mood,
                    seasonal,
                    awards_json,
                    now,
                    existing_ids[entry_id],
                ),
            )
            updated += 1
        else:
            conn.execute(
                """
                INSERT INTO items
                    (source_id, video_id, title, thumbnail_url, duration_seconds,
                     youtube_music_url, description,
                     series, position_in_series, genre, franchise, min_age, age_tag,
                     source_release_year, mood, seasonal, awards, last_refreshed)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source["id"],
                    entry_id,
                    entry["title"],
                    entry["thumbnail_url"],
                    entry["duration_seconds"],
                    entry["youtube_music_url"],
                    description,
                    series,
                    position_in_series,
                    genre,
                    franchise,
                    min_age,
                    age_tag,
                    source_release_year,
                    mood,
                    seasonal,
                    awards_json,
                    now,
                ),
            )
            added += 1
            staged_items.pop(entry_id, None)  # consumed - prune from the fetch cache

    stale_ids = [row["id"] for vid, row in existing.items() if vid not in seen_ids]
    removed = len(stale_ids)
    if stale_ids:
        conn.executemany("DELETE FROM items WHERE id = ?", [(rid,) for rid in stale_ids])

    conn.commit()
    return (added, updated, removed)


def regenerate_suggestion(
    conn: sqlite3.Connection, claude_client, youtube_id: str, suggestions: dict, fetched_items: dict | None = None
) -> bool:
    """Force-regenerate one item's Claude suggestion (description plus the
    other nine fields) and record it into `suggestions` for review.

    `youtube_id` is the item's video_id column - a real YouTube video id for
    'channel'/'playlist' sources, or the playlist/album id for an 'album'
    source. Unlike the normal sync path, this always calls Claude regardless
    of whether the item is "new" - it's an explicit, single-item override of
    the quota-saving reuse rule, for getting a fresh suggestion to review
    without a full --clean-db resync.

    Looks up the item's title/language from storytimefinder.db first (the
    common case - it's already synced). If the DB has no row for it - e.g.
    --fetch has staged it into data/fetched_items.json but --sync hasn't run
    locally yet, so nothing's in the DB even though the item is perfectly
    real - falls back to that staging data instead, cross-referencing
    SOURCES for the language (staged items don't carry it directly, only
    their source does). Returns False (and logs an error) if the item isn't
    found in either place.

    Deliberately does NOT touch the `items` table either way - description
    is override-only now, same as every other suggested field (see
    sync_source()), so there's nothing for this to write to the DB; it only
    updates the review file. Run refresh.py again after copying an approved
    value into overrides.py to actually apply it.
    """
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        """
        SELECT items.title, sources.language
        FROM items JOIN sources ON sources.id = items.source_id
        WHERE items.video_id = ?
        """,
        (youtube_id,),
    ).fetchone()

    if row is not None:
        title, language = row["title"], row["language"]
    else:
        staged = (fetched_items or {}).get("items", {}).get(youtube_id)
        if staged is None:
            log.error(
                "No item found with video id %r in storytimefinder.db or data/fetched_items.json "
                "- run --fetch first",
                youtube_id,
            )
            return False
        title = staged["title"]
        source = next((s for s in SOURCES if s["youtube_id"] == staged.get("source_youtube_id")), None)
        language = source["language"] if source else "de"

    result = generate_metadata_suggestions(claude_client, title, language)
    record_suggestion(suggestions, youtube_id, title, result)
    log.info("Regenerated suggestion for %r (%s): %r", title, youtube_id, result)
    return True


def export_catalog(conn: sqlite3.Connection) -> int:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT items.id, items.title, items.thumbnail_url, items.duration_seconds,
               items.youtube_music_url, items.description,
               items.series, items.position_in_series,
               items.genre, items.franchise, items.min_age, items.age_tag, items.source_release_year,
               items.mood, items.seasonal, items.awards,
               sources.language
        FROM items
        JOIN sources ON sources.id = items.source_id
        WHERE sources.active = 1
        ORDER BY items.title COLLATE NOCASE
        """
    ).fetchall()

    catalog_items = []
    for row in rows:
        item = dict(row)
        # awards is stored as a JSON TEXT column (see SCHEMA) - decode it
        # back into a real array so catalog.json holds nested JSON, not a
        # JSON-string-within-JSON.
        item["awards"] = json.loads(item["awards"]) if item.get("awards") else []
        catalog_items.append(item)

    catalog = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "items": catalog_items,
    }

    CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CATALOG_PATH.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--fetch",
        action="store_true",
        help=(
            "Fetch phase: pull new items' metadata from YouTube and a Claude suggestion for "
            "each, staging both into data/fetched_items.json and data/claude_suggestions.json. "
            "Never touches storytimefinder.db or catalog.json - run --sync afterward to "
            "actually publish anything this finds."
        ),
    )
    mode.add_argument(
        "--sync",
        action="store_true",
        help=(
            "Sync phase: the only mode that writes storytimefinder.db and catalog.json. Reads "
            "whatever the most recent --fetch staged (plus overrides.py) - never touches the "
            "YouTube or Claude APIs itself. A source with no prior --fetch is skipped with a "
            "warning, not treated as having zero items."
        ),
    )
    mode.add_argument(
        "--regenerate-suggestion",
        metavar="YOUTUBE_ID",
        help=(
            "Regenerate the Claude suggestion (description plus the other six fields) for a "
            "single already-synced item (its video id, or playlist/album id for an 'album' "
            "source) and write it to data/claude_suggestions.json for review. Like --fetch, "
            "never touches storytimefinder.db or catalog.json. Requires ANTHROPIC_API_KEY; "
            "does not touch the YouTube API."
        ),
    )
    parser.add_argument(
        "--log-responses",
        action="store_true",
        help="With --fetch: also log raw YouTube API responses (verbose - useful for debugging).",
    )
    parser.add_argument(
        "--clean-db",
        action="store_true",
        help=(
            "Delete the local SQLite DB first. Only affects storytimefinder.db - "
            "data/fetched_items.json (see --clean-fetched) is untouched, so items already "
            "staged from an earlier --fetch are still skipped by fetch_source()'s new-item "
            "check, not re-fetched. With --sync, the rebuilt catalog only contains whatever is "
            "currently staged in fetched_items.json - if that's been pruned down to nothing by "
            "a prior --sync, run --fetch first so there's something to rebuild from."
        ),
    )
    parser.add_argument(
        "--clean-fetched",
        action="store_true",
        help=(
            "Delete data/fetched_items.json first. Only affects the fetch-phase staging file - "
            "storytimefinder.db (see --clean-db) is untouched. With --fetch, this forces every "
            "item to be re-fetched/re-suggested from scratch (even ones already staged from an "
            "earlier --fetch), since the staging file's 'already staged' check has nothing left "
            "to find. With --sync alone (no fresh --fetch first), this leaves the catalog empty - "
            "combine it with --fetch, not --sync."
        ),
    )
    return parser.parse_args()


def run_fetch(claude_client) -> None:
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        log.error("YOUTUBE_API_KEY is not set (see .env.example)")
        sys.exit(1)
    if claude_client is None:
        log.warning("ANTHROPIC_API_KEY is not set - new items will be fetched with no Claude suggestions")

    conn = get_db()  # read-only use here: only ever SELECTs, never INSERT/UPDATE/DELETE - see fetch_source()
    active_sources = [s for s in SOURCES if s.get("active")]
    if not active_sources:
        log.warning("No active sources configured - edit refresh/sources.py")
        return

    youtube = build("youtube", "v3", developerKey=api_key)
    fetched_items = load_fetched_items()
    suggestions = load_suggestions()

    processed = 0
    total_new = 0
    for source in active_sources:
        log.info("Fetching source: %s (%s)", source["label"], source["youtube_id"])
        try:
            new_count = fetch_source(youtube, claude_client, source, conn, fetched_items, suggestions)
        except HttpError as exc:
            log.error("YouTube API error for source %s: %s", source["label"], exc)
            continue
        processed += 1
        total_new += new_count
        log.info("  %d new item(s) fetched", new_count)

    save_fetched_items(fetched_items)
    save_suggestions(suggestions)
    log.info(
        "Fetch done. %d/%d sources processed, %d new item(s) staged in %s. Run --sync to publish.",
        processed, len(active_sources), total_new, FETCHED_ITEMS_PATH,
    )


def _series_consistency_warnings(by_series: dict[str, list[tuple[str, dict]]]) -> list[str]:
    """Core of the series consistency check, shared by the DB-backed
    _check_series_consistency() (run during --sync) and the ITEM_OVERRIDES-
    backed check_overrides_series_consistency() (run against overrides.py
    directly, e.g. from the admin UI, without needing a prior --sync).

    `by_series` maps a series name to a list of (label, fields) tuples -
    `label` is whatever the caller wants shown in a warning (a title, an
    entry id, ...), `fields` is a dict with genre/franchise/mood/seasonal/
    position_in_series keys. Returns human-readable warning strings (never
    logs or raises itself) for two likely curation mistakes:
      - items sharing a series disagreeing on genre/franchise/mood/seasonal
        - a real series is usually consistent on all four, so a mismatch is
          more often a typo/forgotten field than a deliberate choice.
      - two items in the same series claiming the same position_in_series -
        almost always a copy-paste mistake.
    """
    warnings = []
    for series, entries in sorted(by_series.items()):
        if len(entries) < 2:
            continue

        for field in ("genre", "franchise", "mood", "seasonal"):
            values = {fields.get(field) for _, fields in entries if fields.get(field)}
            if len(values) > 1:
                detail = ", ".join(f"{label!r}={fields.get(field)!r}" for label, fields in entries)
                warnings.append(f"Series {series!r} has inconsistent {field} across its items: {detail}")

        positions: dict[int, list[str]] = {}
        for label, fields in entries:
            position = fields.get("position_in_series")
            if position is None:
                continue
            positions.setdefault(position, []).append(label)
        for position, labels in positions.items():
            if len(labels) > 1:
                warnings.append(
                    f"Series {series!r} has {len(labels)} items sharing position_in_series={position}: {labels}"
                )
    return warnings


def _check_series_consistency(conn: sqlite3.Connection) -> None:
    """Log warnings (via _series_consistency_warnings()) for likely
    curation mistakes across ITEM_OVERRIDES' `series` entries, read back
    from storytimefinder.db post-sync - purely informational, never blocks
    the sync or changes what gets written (overrides.py is always trusted
    as-is, same as every other override field). Checks run across all
    sources, not just one - a series could in principle span more than one.
    """
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT title, series, position_in_series, genre, franchise, mood, seasonal "
        "FROM items WHERE series IS NOT NULL"
    ).fetchall()

    by_series: dict[str, list[tuple[str, dict]]] = {}
    for row in rows:
        by_series.setdefault(row["series"], []).append((row["title"], dict(row)))

    for warning in _series_consistency_warnings(by_series):
        log.warning(warning)


def check_overrides_series_consistency(overrides: dict, labels: dict | None = None) -> list[str]:
    """Same two checks as _check_series_consistency(), but reading directly
    from an ITEM_OVERRIDES-shaped dict instead of storytimefinder.db - lets
    these warnings surface at curation time (e.g. in the admin UI's
    Suggestions screen) without requiring a --sync first. `labels`
    optionally maps entry_id -> a human-readable name (e.g. a title) for
    nicer messages; an entry_id missing from it is labeled by its raw id.
    Returns the warning strings (doesn't log them itself - the CLI's
    --sync path uses _check_series_consistency() instead, which does).
    """
    labels = labels or {}
    by_series: dict[str, list[tuple[str, dict]]] = {}
    for entry_id, override in overrides.items():
        series = override.get("series")
        if not series:
            continue
        by_series.setdefault(series, []).append((labels.get(entry_id, entry_id), override))
    return _series_consistency_warnings(by_series)


def run_sync() -> None:
    conn = get_db()
    sync_sources(conn)
    sources = get_active_sources(conn)

    if not sources:
        log.warning("No active sources configured - edit refresh/sources.py")
        export_catalog(conn)
        return

    fetched_items = load_fetched_items()

    total_added = total_updated = total_removed = 0
    processed = 0
    for source in sources:
        log.info("Syncing source: %s (%s)", source["label"], source["youtube_id"])
        result = sync_source(conn, source, fetched_items)
        if result is None:
            continue
        added, updated, removed = result
        processed += 1
        total_added += added
        total_updated += updated
        total_removed += removed
        log.info("  +%d added, %d updated, -%d removed", added, updated, removed)

    save_fetched_items(fetched_items)
    _check_series_consistency(conn)
    item_count = export_catalog(conn)
    log.info(
        "Sync done. %d/%d sources processed. +%d added, %d updated, -%d removed. "
        "catalog.json now has %d items.",
        processed,
        len(sources),
        total_added,
        total_updated,
        total_removed,
        item_count,
    )


def main() -> None:
    global LOG_API_RESPONSES
    args = parse_args()
    LOG_API_RESPONSES = args.log_responses

    if args.clean_db and DB_PATH.exists():
        DB_PATH.unlink()
        log.info("--clean-db: deleted %s, starting from a clean database", DB_PATH)

    if args.clean_fetched and FETCHED_ITEMS_PATH.exists():
        FETCHED_ITEMS_PATH.unlink()
        log.info("--clean-fetched: deleted %s, starting from no staged fetch data", FETCHED_ITEMS_PATH)

    load_dotenv()
    anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY")
    claude_client = Anthropic(api_key=anthropic_api_key) if anthropic_api_key else None

    if args.regenerate_suggestion:
        if claude_client is None:
            log.error("ANTHROPIC_API_KEY is not set - cannot regenerate a suggestion")
            sys.exit(1)
        conn = get_db()
        suggestions = load_suggestions()
        fetched_items = load_fetched_items()
        if not regenerate_suggestion(conn, claude_client, args.regenerate_suggestion, suggestions, fetched_items):
            sys.exit(1)
        save_suggestions(suggestions)
        return

    if args.fetch:
        run_fetch(claude_client)
        return

    run_sync()


if __name__ == "__main__":
    main()
