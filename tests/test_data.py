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
            "age_tag": None,
            "language": "de",
            "youtube_music_url": "https://music.youtube.com/watch?v=aaa",
            "description": "Simba muss lernen, ein guter König zu werden.",
            "release_date": "2020-01-01T00:00:00Z",
            "publisher": "Walt Disney Records",
            "series": None,
            "position_in_series": None,
            "genre": "Abenteuer",
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
            "description": "Ein Krimi-Hörspiel für Kinder.",
            "release_date": "2019-03-15T00:00:00Z",
            "publisher": "Europa",
            "series": "Die drei ???",
            "position_in_series": 78,
            "genre": "Krimi",
        },
        {
            "id": 3,
            "title": "Der gestiefelte Kater",
            "thumbnail_url": None,
            "duration_seconds": None,
            "category": "classic",
            "age_tag": "3-6",
            "language": "en",
            "youtube_music_url": "https://music.youtube.com/watch?v=ccc",
            "description": None,
            "release_date": None,
            "publisher": "Kiddinx",
            "series": None,
            "position_in_series": None,
            "genre": "Märchen",
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


def test_get_categories_counts_and_sorts():
    categories = data.get_categories()
    slugs = [c["slug"] for c in categories]
    assert slugs == sorted(slugs)
    counts = {c["slug"]: c["count"] for c in categories}
    assert counts == {"classic": 1, "disney": 1, "hoerspiel": 1}


def test_get_age_tags_unique_and_sorted_and_excludes_unset():
    # item 1 has age_tag=None (no "all"/catch-all value) - must not show up as a tag.
    assert data.get_age_tags() == ["3-6", "6-10"]


def test_get_publishers_unique_and_sorted():
    assert data.get_publishers() == ["Europa", "Kiddinx", "Walt Disney Records"]


def test_get_languages_unique_and_sorted():
    assert data.get_languages() == ["de", "en"]


def test_get_genres_unique_and_sorted():
    assert data.get_genres() == ["Abenteuer", "Krimi", "Märchen"]


def test_get_series_list_excludes_empty():
    assert data.get_series_list() == ["Die drei ???"]


def test_get_release_decades_unique_sorted_excludes_missing():
    # item 3 has release_date=None - must not produce a bogus decade.
    # Fixture items are 2019 (-> "2010") and 2020 (-> "2020").
    assert data.get_release_decades() == ["2010", "2020"]


@pytest.mark.parametrize(
    "seconds, expected_slug",
    [
        (None, None),
        (0, None),
        (1799, "under30"),
        (1800, "30to60"),
        (3599, "30to60"),
        (3600, "1to2h"),
        (7199, "1to2h"),
        (7200, "over2h"),
        (10800, "over2h"),
    ],
)
def test_duration_bucket_slug_boundaries(seconds, expected_slug):
    assert data.duration_bucket_slug(seconds) == expected_slug


def test_get_duration_buckets_only_returns_buckets_present_in_data():
    # Fixture items are 3120s and 2760s (both "30to60") and one with no duration.
    buckets = data.get_duration_buckets()
    assert [b["slug"] for b in buckets] == ["30to60"]


@pytest.mark.parametrize(
    "value, expected_year",
    [
        (None, None),
        ("", None),
        ("not-a-date", None),
        ("2019-03-15T00:00:00Z", "2019"),
    ],
)
def test_release_year(value, expected_year):
    assert data.release_year(value) == expected_year


@pytest.mark.parametrize(
    "value, expected_decade",
    [
        (None, None),
        ("", None),
        ("not-a-date", None),
        ("1999-12-31T00:00:00Z", "1990"),
        ("2000-01-01T00:00:00Z", "2000"),
        ("2009-12-31T00:00:00Z", "2000"),
        ("2010-01-01T00:00:00Z", "2010"),
        ("2019-03-15T00:00:00Z", "2010"),
    ],
)
def test_release_decade(value, expected_decade):
    assert data.release_decade(value) == expected_decade


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


@pytest.mark.parametrize(
    "value, lang, expected",
    [
        (None, "de", ""),
        ("", "de", ""),
        ("2026-08-16T00:00:00Z", "de", "16.08.2026"),
        ("2019-03-15T00:00:00Z", "de", "15.03.2019"),
        (None, "en", ""),
        ("2026-08-16T00:00:00Z", "en", "16 Aug 2026"),
        ("2019-03-15T00:00:00Z", "en", "15 Mar 2019"),
    ],
)
def test_format_date(value, lang, expected):
    assert data.format_date(value, lang) == expected
