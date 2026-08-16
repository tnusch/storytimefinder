import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import data  # noqa: E402

FAKE_CATALOG = {
    "generated_at": "2026-08-01T00:00:00Z",
    "items": [
        {
            "id": 1,
            "title": "Der König der Löwen (Hörspiel)",
            "thumbnail_url": None,
            "duration_seconds": 3120,
            "category": "disney",
            "age_tag": "all",
            "language": "de",
            "youtube_music_url": "https://music.youtube.com/watch?v=aaa",
        },
        {
            "id": 2,
            "title": "Die drei ??? und der seltsame Wecker",
            "thumbnail_url": None,
            "duration_seconds": 2760,
            "category": "hoerspiel",
            "age_tag": "6-10",
            "language": "de",
            "youtube_music_url": "https://music.youtube.com/watch?v=bbb",
        },
        {
            "id": 3,
            "title": "Der gestiefelte Kater",
            "thumbnail_url": None,
            "duration_seconds": None,
            "category": "classic",
            "age_tag": "3-6",
            "language": "de",
            "youtube_music_url": "https://music.youtube.com/watch?v=ccc",
        },
    ],
}


@pytest.fixture(autouse=True)
def fake_catalog(monkeypatch):
    monkeypatch.setattr(data, "_catalog_cache", FAKE_CATALOG)
    yield
    monkeypatch.setattr(data, "_catalog_cache", None)


def test_get_items_returns_all():
    assert len(data.get_items()) == 3


def test_search_by_query_matches_title_case_insensitively():
    results = data.search(query="könig")
    assert [i["id"] for i in results] == [1]


def test_search_by_category_filters():
    results = data.search(category="hoerspiel")
    assert [i["id"] for i in results] == [2]


def test_search_by_age_filters():
    results = data.search(age="3-6")
    assert [i["id"] for i in results] == [3]


def test_search_combines_filters_with_and_semantics():
    results = data.search(query="der", category="classic")
    assert [i["id"] for i in results] == [3]


def test_search_with_no_filters_returns_everything():
    assert len(data.search()) == 3


def test_get_categories_counts_and_sorts():
    categories = data.get_categories()
    slugs = [c["slug"] for c in categories]
    assert slugs == sorted(slugs)
    counts = {c["slug"]: c["count"] for c in categories}
    assert counts == {"classic": 1, "disney": 1, "hoerspiel": 1}


def test_get_age_tags_unique_and_sorted():
    assert data.get_age_tags() == ["3-6", "6-10", "all"]


@pytest.mark.parametrize(
    "seconds, expected",
    [
        (None, ""),
        (0, ""),
        (65, "1:05"),
        (3600, "1:00:00"),
        (3725, "1:02:05"),
    ],
)
def test_format_duration(seconds, expected):
    assert data.format_duration(seconds) == expected
