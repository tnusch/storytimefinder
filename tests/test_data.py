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
            "franchise": "disney",
            "min_age": None,
            "age_tag": None,
            "language": "de",
            "youtube_music_url": "https://music.youtube.com/watch?v=aaa",
            "description": "Simba muss lernen, ein guter König zu werden.",
            "source_release_year": 2020,
            "series": None,
            "position_in_series": None,
            "genre": "adventure",
        },
        {
            "id": 2,
            "title": "Die drei ??? und der seltsame Wecker",
            "thumbnail_url": None,
            "duration_seconds": 2760,
            "franchise": "die_drei_fragezeichen",
            "min_age": 13,
            "age_tag": "12_plus",
            "language": "de",
            "youtube_music_url": "https://music.youtube.com/watch?v=bbb",
            "description": "Ein Krimi-Hörspiel für Kinder.",
            "source_release_year": 2019,
            "series": "Die drei ???",
            "position_in_series": 78,
            "genre": "mystery",
        },
        {
            "id": 3,
            "title": "Der gestiefelte Kater",
            "thumbnail_url": None,
            "duration_seconds": None,
            "franchise": "pixar",
            "min_age": 4,
            "age_tag": "3_5",
            "language": "en",
            "youtube_music_url": "https://music.youtube.com/watch?v=ccc",
            "description": None,
            "source_release_year": None,
            "series": None,
            "position_in_series": None,
            "genre": "fairy_tale",
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


def test_get_franchises_counts_and_sorts():
    franchises = data.get_franchises()
    slugs = [f["slug"] for f in franchises]
    assert slugs == sorted(slugs)
    counts = {f["slug"]: f["count"] for f in franchises}
    assert counts == {"die_drei_fragezeichen": 1, "disney": 1, "pixar": 1}


def test_get_age_tags_bracket_ordered_and_excludes_unset():
    # item 1 has age_tag=None (no "all"/catch-all value) - must not show up as a tag.
    # item 2 is "12_plus" and item 3 is "3_5" - a plain alphabetical sort would put
    # "12_plus" first (string "1" < "3"), so this also verifies AGE_TAG_ORDER is used.
    assert data.get_age_tags() == ["3_5", "12_plus"]


def test_get_languages_unique_and_sorted():
    assert data.get_languages() == ["de", "en"]


def test_get_genres_unique_and_sorted():
    assert data.get_genres() == ["adventure", "fairy_tale", "mystery"]


def test_get_series_list_excludes_empty():
    assert data.get_series_list() == ["Die drei ???"]


def test_get_release_decades_unique_sorted_excludes_missing():
    # item 3 has source_release_year=None - must not produce a bogus decade.
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
    "value, expected_decade",
    [
        (None, None),
        (0, None),
        (1999, "1990"),
        (2000, "2000"),
        (2009, "2000"),
        (2010, "2010"),
        (2019, "2010"),
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
