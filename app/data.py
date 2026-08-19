"""
Loads data/catalog.json into memory and provides search/filter helpers.

The Flask app never touches SQLite or the YouTube API directly - it only
ever reads the denormalized catalog.json produced by refresh/refresh.py.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

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


def get_series_list() -> list[str]:
    values = {item.get("series") for item in get_items() if item.get("series")}
    return sorted(values)


# Duration is filtered by fixed buckets rather than raw seconds - order matters
# here (shortest to longest), unlike the alphabetically-sorted lists above.
DURATION_BUCKETS = [
    {"slug": "under30", "min": 0, "max": 1800},
    {"slug": "30to60", "min": 1800, "max": 3600},
    {"slug": "1to2h", "min": 3600, "max": 7200},
    {"slug": "over2h", "min": 7200, "max": None},
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


def format_duration(seconds: int | None) -> str:
    if not seconds:
        return ""
    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"
