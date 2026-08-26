import sys
from datetime import datetime, timezone
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
            "mood": "calm",
            "seasonal": None,
            "awards": [{"name": "Deutscher Hörbuchpreis", "category": "Bestes Kinderhörbuch", "year": 2020}],
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
            "mood": "exciting",
            "seasonal": "halloween",
            "awards": [],
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
            # mood/seasonal/awards deliberately omitted - verifies the
            # getters tolerate an item synced before this schema existed.
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


def test_get_moods_unique_and_sorted():
    # item 3 has no "mood" key at all (pre-schema item) - must not error or
    # produce a bogus entry.
    assert data.get_moods() == ["calm", "exciting"]


def test_get_seasonal_values_excludes_unset():
    # item 1 has seasonal=None, item 3 has no "seasonal" key at all - neither
    # should show up, only item 2's "halloween".
    assert data.get_seasonal_values() == ["halloween"]


def test_has_awards_true_when_any_item_has_a_nonempty_awards_list():
    assert data.has_awards() is True


def test_has_awards_false_when_none_do(monkeypatch):
    no_awards_catalog = {
        "generated_at": FAKE_CATALOG["generated_at"],
        "items": [{**item, "awards": []} for item in FAKE_CATALOG["items"]],
    }
    monkeypatch.setattr(data, "_catalog_cache", no_awards_catalog)
    assert data.has_awards() is False


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
        (3600, "60to90"),
        (5399, "60to90"),
        (5400, "90to120"),
        (7199, "90to120"),
        (7200, "2to3h"),
        (10799, "2to3h"),
        (10800, "over3h"),
        (14400, "over3h"),
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


@pytest.mark.parametrize(
    "value, lang, expected",
    [
        (None, "de", ""),
        ("", "de", ""),
        ("2026-08-16T12:00:00Z", "de", "heute"),
        ("2026-08-15T12:00:00Z", "de", "gestern"),
        ("2026-08-14T12:00:00Z", "de", "vor 2 Tagen"),
        ("2026-08-10T12:00:00Z", "de", "vor 6 Tagen"),
        ("2026-08-09T12:00:00Z", "de", "vor 1 Woche"),
        ("2026-08-02T12:00:00Z", "de", "vor 2 Wochen"),
        ("2026-07-01T12:00:00Z", "de", "01.07.2026"),
        (None, "en", ""),
        ("2026-08-16T12:00:00Z", "en", "today"),
        ("2026-08-15T12:00:00Z", "en", "yesterday"),
        ("2026-08-14T12:00:00Z", "en", "2 days ago"),
        ("2026-08-09T12:00:00Z", "en", "1 week ago"),
        ("2026-08-02T12:00:00Z", "en", "2 weeks ago"),
        ("2026-07-01T12:00:00Z", "en", "1 Jul 2026"),
    ],
)
def test_format_relative_date(value, lang, expected):
    now = datetime(2026, 8, 16, 15, 0, 0, tzinfo=timezone.utc)
    assert data.format_relative_date(value, lang, now=now) == expected
