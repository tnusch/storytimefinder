"""
Loads data/catalog.json into memory and provides search/filter helpers.

The Flask app never touches SQLite or the YouTube API directly - it only
ever reads the denormalized catalog.json produced by refresh/refresh.py.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .i18n import translate

CATALOG_PATH = Path(__file__).resolve().parent.parent / "data" / "catalog.json"

_catalog_cache: dict | None = None


def _load_raw() -> dict:
    if not CATALOG_PATH.exists():
        return {"generated_at": None, "items": []}
    with CATALOG_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_catalog(force_reload: bool = False) -> dict:
    global _catalog_cache
    if _catalog_cache is None or force_reload:
        _catalog_cache = _load_raw()
    return _catalog_cache


def get_items() -> list[dict]:
    return load_catalog()["items"]


def get_generated_at() -> str | None:
    return load_catalog().get("generated_at")


def get_franchises() -> list[dict]:
    counts: dict[str, int] = {}
    for item in get_items():
        franchise = item.get("franchise")
        if not franchise:
            continue
        counts[franchise] = counts.get(franchise, 0) + 1
    return [{"slug": slug, "count": count} for slug, count in sorted(counts.items())]


# Fixed bracket order (youngest to oldest) - mirrors AGE_BRACKETS in
# refresh/refresh.py. Sorting age tags alphabetically would put "12_plus"
# between "0_3" and "3_5" (string sort), so this fixed order is used instead.
AGE_TAG_ORDER = ["0_3", "3_5", "6_8", "9_11", "12_plus"]


def get_age_tags() -> list[str]:
    present = {item.get("age_tag") for item in get_items() if item.get("age_tag")}
    return [tag for tag in AGE_TAG_ORDER if tag in present]


def get_languages() -> list[str]:
    values = {item.get("language") for item in get_items() if item.get("language")}
    return sorted(values)


def get_genres() -> list[str]:
    values = {item.get("genre") for item in get_items() if item.get("genre")}
    return sorted(values)


def get_moods() -> list[str]:
    values = {item.get("mood") for item in get_items() if item.get("mood")}
    return sorted(values)


def get_seasonal_values() -> list[str]:
    values = {item.get("seasonal") for item in get_items() if item.get("seasonal")}
    return sorted(values)


def has_awards() -> bool:
    """Whether any catalog item has a non-empty awards list - gates whether
    the award-winning filter toggle renders at all, same as the other
    filter groups only rendering when there's something to filter by."""
    return any(item.get("awards") for item in get_items())


def get_series_list() -> list[str]:
    """Every distinct `series` name - EXCEPT one whose franchise maps to
    only that one series. If a franchise has exactly one series under it,
    filtering by that series name would show the identical result set
    filtering by the franchise chip already does, so the series chip is
    redundant clutter and suppressed from the "Reihe" filter group.
    A series with no `franchise` at all, or one shared by more than one
    series, is never suppressed - this rule only ever removes a series
    that's fully redundant with an existing franchise chip, never a
    series with no franchise-level equivalent to fall back to."""
    all_series: set[str] = set()
    by_franchise: dict[str, set[str]] = {}
    for item in get_items():
        series = item.get("series")
        if not series:
            continue
        all_series.add(series)
        franchise = item.get("franchise")
        if franchise:
            by_franchise.setdefault(franchise, set()).add(series)

    redundant = {next(iter(s)) for s in by_franchise.values() if len(s) == 1}
    return sorted(all_series - redundant)


_UMLAUT_MAP = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}
_SLUG_INVALID_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    """'Bibi Blocksberg' -> 'bibi-blocksberg', 'Die drei ???' -> 'die-drei'.
    No slugify utility exists anywhere else in this repo (franchise/genre/
    mood/seasonal "slugs" are pre-enumerated fixed vocab values, never
    generated) - this is the first one, written for /series/<slug> only."""
    if not text:
        return ""
    text = text.lower()
    for src, dst in _UMLAUT_MAP.items():
        text = text.replace(src, dst)
    return _SLUG_INVALID_RE.sub("-", text).strip("-")


def _episode_sort_key(item: dict):
    """position_in_series ascending; an item with no position set always
    sorts last (by title, for determinism) rather than guessing at an
    order - a missing position is a curation gap, not something to infer.
    Shared by episodic episode ordering and sequel prev/next ordering."""
    pos = item.get("position_in_series")
    return (0, pos) if pos is not None else (1, item.get("title") or "")


def _first_present(items: list[dict], field: str):
    return next((i.get(field) for i in items if i.get(field)), None)


def get_series_metadata() -> dict[str, dict]:
    """catalog.json's "series" section - series_type/genre/franchise/mood/
    min_age/age_tag for an episodic series, keyed by series name (see
    refresh.py's export_catalog()/sync_series()). This is the single
    source of truth for series_type now - there's no per-item series_type
    field anymore (it used to live on each item, but genre/franchise/mood/
    min_age for an episodic series are curated once in overrides.py's
    SERIES_OVERRIDES rather than repeated per episode, and series_type
    moved there with them - see overrides.py's docstring). A series absent
    here (the common case) is neither episodic nor sequel - just a plain
    filterable `series` name, same as before this feature existed."""
    return load_catalog().get("series", {})


def get_series_groups() -> list[dict]:
    """One entry per distinct `series` name with series_type == "episodic"
    in get_series_metadata() - the collapsed-card half of the feature.

    Each group: slug, series, episodes (sorted by _episode_sort_key),
    episode_count, thumbnail_url (first episode's, in sort order, with a
    non-null thumbnail), age_tag/genre/franchise/mood (straight from the
    series-level metadata - a single curated value now, not derived by
    scanning episodes), seasonal/language (first non-null value found
    across episodes - seasonal isn't part of SERIES_OVERRIDES, so it's
    still whatever the episodes happen to agree on), awards (first
    non-empty episode's awards list, else []). Sorted by series name,
    case-insensitive (matches get_series_list()).
    """
    series_meta = get_series_metadata()
    episodic_names = {name for name, meta in series_meta.items() if meta.get("series_type") == "episodic"}

    by_series: dict[str, list[dict]] = {}
    for item in get_items():
        if item.get("series") in episodic_names:
            by_series.setdefault(item["series"], []).append(item)

    groups = []
    for series, episodes in by_series.items():
        episodes = sorted(episodes, key=_episode_sort_key)
        meta = series_meta.get(series, {})
        groups.append({
            "slug": slugify(series),
            "series": series,
            "episodes": episodes,
            "episode_count": len(episodes),
            "thumbnail_url": _first_present(episodes, "thumbnail_url"),
            "age_tag": meta.get("age_tag"),
            "genre": meta.get("genre"),
            "franchise": meta.get("franchise"),
            "mood": meta.get("mood"),
            "seasonal": _first_present(episodes, "seasonal"),
            "language": _first_present(episodes, "language"),
            "awards": next((e["awards"] for e in episodes if e.get("awards")), []),
        })
    return sorted(groups, key=lambda g: g["series"].lower())


def get_series_group_by_slug(slug: str) -> dict | None:
    return next((g for g in get_series_groups() if g["slug"] == slug), None)


def get_sequel_context() -> dict:
    """Maps an item's catalog `id` -> {"position", "total", "prev", "next"}
    for every item whose `series` has series_type == "sequel" in
    get_series_metadata() - what _item_card.html needs to render the
    "Teil N von M" badge and davor:/danach: cross-links (each pointing at
    the sibling's own youtube_music_url - no internal page exists to link
    to instead, by design). Items that don't qualify simply have no key
    here; item_card() looks its own id up and renders nothing extra if
    absent. "position" is the item's own position_in_series (None if
    unset - the badge is then omitted, but prev/next links still work
    using _episode_sort_key()'s same sorts-last-if-unset ordering).
    """
    series_meta = get_series_metadata()
    sequel_names = {name for name, meta in series_meta.items() if meta.get("series_type") == "sequel"}

    by_series: dict[str, list[dict]] = {}
    for item in get_items():
        if item.get("series") in sequel_names:
            by_series.setdefault(item["series"], []).append(item)

    context: dict = {}
    for members in by_series.values():
        ordered = sorted(members, key=_episode_sort_key)
        total = len(ordered)
        for i, item in enumerate(ordered):
            context[item["id"]] = {
                "position": item.get("position_in_series"),
                "total": total,
                "prev": ordered[i - 1] if i > 0 else None,
                "next": ordered[i + 1] if i < total - 1 else None,
            }
    return context


def get_grid_entries() -> list[dict]:
    """The exact mixed list index() renders: every item that isn't a
    member of a collapsed episodic group passes through unchanged
    (standalone items AND every "sequel" item both stay individual cards
    - sequel badging is additive, attached separately at render time via
    get_sequel_context(), not by this function), plus one synthetic
    {"kind": "series", ...group} entry per get_series_groups() result.
    Sorted together by title (series name for group entries),
    case-insensitive, matching catalog.json's own default order.
    """
    groups = get_series_groups()
    grouped_ids = {e["id"] for g in groups for e in g["episodes"]}
    entries = [item for item in get_items() if item["id"] not in grouped_ids]
    entries += [{"kind": "series", **g} for g in groups]
    entries.sort(key=lambda e: (e["series"] if e.get("kind") == "series" else e.get("title") or "").lower())
    return entries


def get_total_audiobook_count(entries: list[dict]) -> int:
    """Real audiobook count behind a get_grid_entries() list - a
    collapsed series entry counts as its episode_count, not as 1, so the
    "N Hörspiele" heading reflects actual content, not card count."""
    return sum(e.get("episode_count", 1) for e in entries)


def get_series_card_count(entries: list[dict]) -> int:
    """How many of `entries` are collapsed episodic-series cards
    (kind == "series") - the results-count heading's "in N series" half,
    only shown at all once this is non-zero (see get_episode_count_in_series())."""
    return sum(1 for e in entries if e.get("kind") == "series")


def get_episode_count_in_series(entries: list[dict]) -> int:
    """How many individual audiobooks are folded into a collapsed series
    card, across every series entry in `entries` - the results-count
    heading's "N episodes" half. Always <= get_total_audiobook_count(entries),
    since standalone/sequel items (which aren't collapsed) don't count here."""
    return sum(e.get("episode_count", 0) for e in entries if e.get("kind") == "series")


# Duration is filtered by fixed buckets rather than raw seconds - order matters
# here (shortest to longest), unlike the alphabetically-sorted lists above.
DURATION_BUCKETS = [
    {"slug": "under30", "min": 0, "max": 1800},
    {"slug": "30to60", "min": 1800, "max": 3600},
    {"slug": "60to90", "min": 3600, "max": 5400},
    {"slug": "90to120", "min": 5400, "max": 7200},
    {"slug": "2to3h", "min": 7200, "max": 10800},
    {"slug": "over3h", "min": 10800, "max": None},
]


def duration_bucket_slug(seconds: int | None) -> str | None:
    if not seconds:
        return None
    for bucket in DURATION_BUCKETS:
        if seconds >= bucket["min"] and (bucket["max"] is None or seconds < bucket["max"]):
            return bucket["slug"]
    return None


def get_duration_buckets() -> list[dict]:
    present = {duration_bucket_slug(item.get("duration_seconds")) for item in get_items()}
    return [b for b in DURATION_BUCKETS if b["slug"] in present]


def release_decade(source_release_year: int | None) -> str | None:
    """Bucket a source release year down to its decade, e.g. 2019 -> '2010' (2010er/2010s)."""
    if not source_release_year:
        return None
    return str((int(source_release_year) // 10) * 10)


def get_release_decades() -> list[str]:
    decades = {release_decade(item.get("source_release_year")) for item in get_items()}
    decades.discard(None)
    return sorted(decades, key=int)


_EN_MONTHS = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]


def format_date(value: str | None, lang: str = "de") -> str:
    """Format an ISO 8601 timestamp for display, e.g. '16.08.2026' (de) or '16 Aug 2026' (en)."""
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    if lang == "en":
        return f"{parsed.day} {_EN_MONTHS[parsed.month - 1]} {parsed.year}"
    return parsed.strftime("%d.%m.%Y")


def format_relative_date(value: str | None, lang: str = "de", now: datetime | None = None) -> str:
    """Format an ISO 8601 timestamp as a short relative label ('heute'/
    'today', 'vor 2 Tagen'/'2 days ago', ...). Falls back to the absolute
    date (format_date()) once it's more than a month old - "vor 6 Wochen"
    stops being a useful-at-a-glance label past that point, an absolute
    date is.

    `now` is only ever passed explicitly by tests - real callers always let
    it default to the actual current time, computed fresh per request since
    this is server-side rendered and "today" changes daily unlike the rest
    of the (otherwise static per catalog refresh) page.
    """
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)

    delta_days = max((now.date() - parsed.date()).days, 0)
    if delta_days == 0:
        return translate(lang, "date_today")
    if delta_days == 1:
        return translate(lang, "date_yesterday")
    if delta_days < 7:
        return translate(lang, "date_days_ago_other", n=delta_days)

    weeks = delta_days // 7
    if weeks < 5:
        key = "date_weeks_ago_one" if weeks == 1 else "date_weeks_ago_other"
        return translate(lang, key, n=weeks)

    return format_date(value, lang)


def format_duration(seconds: int | None) -> str:
    if not seconds:
        return ""
    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"
