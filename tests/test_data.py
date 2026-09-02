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


def test_get_series_list_excludes_empty_and_franchise_redundant_series():
    # FAKE_CATALOG's only series, "Die drei ???" (item 2), is also the sole
    # series under franchise "die_drei_fragezeichen" - so besides excluding
    # items with no series at all (items 1 and 3), it's now ALSO suppressed
    # as redundant with that franchise's own chip (see
    # test_get_series_list_franchise_suppression below for a fixture that
    # isolates just that rule).
    assert data.get_series_list() == []


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


def test_get_series_groups_empty_when_no_series_metadata():
    # FAKE_CATALOG's item 2 has series="Die drei ???" but catalog.json has
    # no top-level "series" section at all - series_type is manual/
    # curated (via overrides.py's SERIES_OVERRIDES), never inferred, so a
    # series must NOT be grouped just because items share its name.
    assert data.get_series_groups() == []


@pytest.mark.parametrize(
    "text, expected_slug",
    [
        ("Bibi Blocksberg", "bibi-blocksberg"),
        ("Die drei ???", "die-drei"),
        ("Käpt'n Blaubär", "kaept-n-blaubaer"),
        ("", ""),
    ],
)
def test_slugify(text, expected_slug):
    assert data.slugify(text) == expected_slug


SERIES_CATALOG = {
    "generated_at": "2026-08-01T00:00:00Z",
    "series": {
        "Bibi Blocksberg": {
            "series_type": "episodic", "genre": "adventure", "franchise": None,
            "mood": "funny", "min_age": 4, "age_tag": "3_5",
        },
        "Findet Nemo": {
            "series_type": "sequel", "genre": None, "franchise": None,
            "mood": None, "min_age": None, "age_tag": None,
        },
    },
    "items": [
        {
            "id": 10, "title": "Bibi Ep2", "series": "Bibi Blocksberg",
            "position_in_series": 2, "thumbnail_url": None,
            # genre/mood/age_tag deliberately NOT set here - they're
            # series-resolved now (see the "series" section above),
            # matching how sync_source() actually writes an episodic
            # item's row (identical values copied from the series row).
            "genre": "adventure", "age_tag": "3_5",
            "franchise": None, "mood": "funny", "seasonal": None, "language": "de", "awards": [],
            "youtube_music_url": "https://music.youtube.com/watch?v=bibi2",
        },
        {
            "id": 11, "title": "Bibi Ep1", "series": "Bibi Blocksberg",
            "position_in_series": 1, "thumbnail_url": "https://x/thumb1.jpg",
            "genre": "adventure", "age_tag": "3_5",
            "franchise": None, "mood": "funny", "seasonal": None, "language": "de", "awards": [],
            "youtube_music_url": "https://music.youtube.com/watch?v=bibi1",
        },
        {
            "id": 12, "title": "Bibi Ep3", "series": "Bibi Blocksberg",
            "position_in_series": None, "thumbnail_url": None,
            "genre": "adventure", "age_tag": "3_5",
            "franchise": None, "mood": "funny", "seasonal": None, "language": "de", "awards": [],
            "youtube_music_url": "https://music.youtube.com/watch?v=bibi3",
        },
        {
            "id": 13, "title": "Findet Nemo", "series": "Findet Nemo",
            "position_in_series": 1, "age_tag": "3_5", "youtube_music_url": "https://music.youtube.com/watch?v=nemo",
            "genre": "adventure", "franchise": "disney", "mood": "heartwarming", "seasonal": None,
            "language": "de", "awards": [],
        },
        {
            "id": 14, "title": "Findet Dorie", "series": "Findet Nemo",
            "position_in_series": 2, "age_tag": "3_5", "youtube_music_url": "https://music.youtube.com/watch?v=dorie",
            "genre": "adventure", "franchise": "disney", "mood": "heartwarming", "seasonal": None,
            "language": "de", "awards": [],
        },
        {
            "id": 15, "title": "Old Show", "series": "Old Show",
            "position_in_series": None, "age_tag": None, "youtube_music_url": "https://music.youtube.com/watch?v=old",
            "genre": None, "franchise": None, "mood": None, "seasonal": None, "language": "de", "awards": [],
        },
        {
            "id": 16, "title": "Standalone", "series": None,
            "youtube_music_url": "https://music.youtube.com/watch?v=standalone",
        },
    ],
}


def test_get_series_groups_only_collapses_episodic(monkeypatch):
    monkeypatch.setattr(data, "_catalog_cache", SERIES_CATALOG)
    groups = data.get_series_groups()
    assert len(groups) == 1
    assert groups[0]["series"] == "Bibi Blocksberg"


def test_get_series_groups_sorts_by_position_and_unset_last(monkeypatch):
    monkeypatch.setattr(data, "_catalog_cache", SERIES_CATALOG)
    group = data.get_series_groups()[0]
    assert [e["id"] for e in group["episodes"]] == [11, 10, 12]


def test_get_series_groups_slug_thumbnail_and_series_level_metadata(monkeypatch):
    monkeypatch.setattr(data, "_catalog_cache", SERIES_CATALOG)
    group = data.get_series_groups()[0]
    assert group["slug"] == "bibi-blocksberg"
    assert group["episode_count"] == 3
    # First episode in sort order with a non-null thumbnail wins.
    assert group["thumbnail_url"] == "https://x/thumb1.jpg"
    # A single curated value now, straight from the "series" section -
    # not derived/spanned from episodes.
    assert group["age_tag"] == "3_5"
    assert group["genre"] == "adventure"
    assert group["mood"] == "funny"


def test_get_series_group_by_slug_found_and_none_for_unknown(monkeypatch):
    monkeypatch.setattr(data, "_catalog_cache", SERIES_CATALOG)
    assert data.get_series_group_by_slug("bibi-blocksberg") is not None
    assert data.get_series_group_by_slug("does-not-exist") is None


def test_get_sequel_context_prev_next_and_position(monkeypatch):
    monkeypatch.setattr(data, "_catalog_cache", SERIES_CATALOG)
    ctx = data.get_sequel_context()
    assert ctx[13]["position"] == 1
    assert ctx[13]["total"] == 2
    assert ctx[13]["prev"] is None
    assert ctx[13]["next"]["id"] == 14
    assert ctx[14]["position"] == 2
    assert ctx[14]["prev"]["id"] == 13
    assert ctx[14]["next"] is None


def test_get_sequel_context_excludes_episodic_and_unset(monkeypatch):
    monkeypatch.setattr(data, "_catalog_cache", SERIES_CATALOG)
    ctx = data.get_sequel_context()
    assert set(ctx.keys()) == {13, 14}


def test_get_grid_entries_replaces_grouped_items_with_one_series_entry(monkeypatch):
    monkeypatch.setattr(data, "_catalog_cache", SERIES_CATALOG)
    entries = data.get_grid_entries()
    series_entries = [e for e in entries if e.get("kind") == "series"]
    assert len(series_entries) == 1
    assert series_entries[0]["episode_count"] == 3
    other_ids = {e["id"] for e in entries if e.get("kind") != "series"}
    # Sequel items stay individual, and so does "Old Show" (a series name
    # with no entry in catalog["series"] at all) and the standalone item -
    # only the episodic group collapses.
    assert other_ids == {13, 14, 15, 16}


def test_get_total_audiobook_count_sums_real_episodes(monkeypatch):
    monkeypatch.setattr(data, "_catalog_cache", SERIES_CATALOG)
    entries = data.get_grid_entries()
    # 3 Bibi episodes (as one card) + Nemo + Dorie + Old Show + Standalone.
    assert data.get_total_audiobook_count(entries) == 3 + 4


def test_get_series_metadata_reads_catalog_series_section(monkeypatch):
    monkeypatch.setattr(data, "_catalog_cache", SERIES_CATALOG)
    meta = data.get_series_metadata()
    assert meta["Bibi Blocksberg"]["series_type"] == "episodic"
    assert meta["Findet Nemo"]["series_type"] == "sequel"


def test_get_series_metadata_empty_when_catalog_has_no_series_section():
    # FAKE_CATALOG (the default autouse fixture) has no "series" key at all.
    assert data.get_series_metadata() == {}


FRANCHISE_SUPPRESSION_CATALOG = {
    "generated_at": "2026-08-01T00:00:00Z",
    "items": [
        # "Cars" franchise has TWO distinct series - both should stay.
        {"id": 20, "title": "Cars 1", "series": "Cars", "franchise": "pixar"},
        {"id": 21, "title": "Cars 2", "series": "Cars", "franchise": "pixar"},
        {"id": 22, "title": "Planes 1", "series": "Planes", "franchise": "pixar"},
        # "disney" franchise has exactly ONE series - "Toy Story" should be
        # suppressed as redundant with the franchise chip.
        {"id": 23, "title": "Toy Story 1", "series": "Toy Story", "franchise": "disney"},
        {"id": 24, "title": "Toy Story 2", "series": "Toy Story", "franchise": "disney"},
        # No franchise at all - never suppressed regardless of count.
        {"id": 25, "title": "Indie Ep 1", "series": "Indie Series", "franchise": None},
    ],
}


def test_get_series_list_keeps_series_when_franchise_has_multiple_series(monkeypatch):
    monkeypatch.setattr(data, "_catalog_cache", FRANCHISE_SUPPRESSION_CATALOG)
    series = data.get_series_list()
    assert "Cars" in series
    assert "Planes" in series


def test_get_series_list_suppresses_sole_series_of_a_franchise(monkeypatch):
    monkeypatch.setattr(data, "_catalog_cache", FRANCHISE_SUPPRESSION_CATALOG)
    assert "Toy Story" not in data.get_series_list()


def test_get_series_list_never_suppresses_series_with_no_franchise(monkeypatch):
    monkeypatch.setattr(data, "_catalog_cache", FRANCHISE_SUPPRESSION_CATALOG)
    assert "Indie Series" in data.get_series_list()


def test_get_series_card_count_and_episode_count_with_a_collapsed_series(monkeypatch):
    monkeypatch.setattr(data, "_catalog_cache", SERIES_CATALOG)
    entries = data.get_grid_entries()
    # SERIES_CATALOG has exactly one episodic series (Bibi Blocksberg, 3
    # episodes) among its grid entries - the rest (Nemo, Dorie, Old Show,
    # Standalone) are individual, non-series entries.
    assert data.get_series_card_count(entries) == 1
    assert data.get_episode_count_in_series(entries) == 3


def test_get_series_card_count_zero_when_nothing_collapsed():
    # The default FAKE_CATALOG fixture has no "series" catalog section at
    # all, so get_grid_entries() never produces a "series"-kind entry.
    entries = data.get_grid_entries()
    assert data.get_series_card_count(entries) == 0
    assert data.get_episode_count_in_series(entries) == 0
