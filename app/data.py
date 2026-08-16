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

CATEGORY_LABELS = {
    "hoerspiel": "Hörspiel",
    "disney": "Disney",
    "classic": "Klassiker",
}

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


def get_category_label(slug: str) -> str:
    return CATEGORY_LABELS.get(slug, slug.title())


def get_categories() -> list[dict]:
    counts: dict[str, int] = {}
    for item in get_items():
        counts[item["category"]] = counts.get(item["category"], 0) + 1
    return [
        {"slug": slug, "label": get_category_label(slug), "count": count}
        for slug, count in sorted(counts.items())
    ]


def get_age_tags() -> list[str]:
    tags = {item.get("age_tag") for item in get_items() if item.get("age_tag")}
    return sorted(tags)


def search(query: str | None = None, category: str | None = None, age: str | None = None) -> list[dict]:
    items = get_items()

    if category:
        items = [i for i in items if i.get("category") == category]

    if age:
        items = [i for i in items if i.get("age_tag") == age]

    if query:
        q = query.strip().lower()
        if q:
            items = [i for i in items if q in i["title"].lower()]

    return items


def format_date_de(value: str | None) -> str:
    """Format an ISO 8601 timestamp as a typical German date, e.g. '16.08.2026'."""
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    return parsed.strftime("%d.%m.%Y")


def format_duration(seconds: int | None) -> str:
    if not seconds:
        return ""
    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"
