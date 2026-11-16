"""Per-item `variant` (remake / spin_off): only a sequel series' main line is
numbered and prev/next-linked; variants get a badge and, for a remake, a
link to the part it remakes."""

import sys
from pathlib import Path

from app import create_app, data
from admin import file_ops

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "refresh"))
import refresh  # noqa: E402


def _item(id_, title, position, year, variant=None):
    return {
        "id": id_, "title": title, "series": "Arielle", "position_in_series": position,
        "source_release_year": year, "variant": variant, "genre": ["fairy_tale"], "awards": [],
        "youtube_music_url": f"https://music.youtube.com/playlist?list=OLAK{id_}", "thumbnail_url": None,
        "duration_seconds": 3600, "description": None, "franchise": "disney", "min_age": 4, "age_tag": "3_5",
        "seasonal": None, "language": "de",
    }


ARIELLE_CATALOG = {
    "items": [
        _item(1, "Arielle, die Meerjungfrau", 1, 1989),
        _item(2, "Arielle, die Meerjungfrau 2 - Sehnsucht nach dem Meer", 2, 2000),
        _item(3, "Arielle, die Meerjungfrau - Wie alles begann", None, 2008, "spin_off"),
        _item(4, "Arielle, die Meerjungfrau", 1, 2023, "remake"),
    ],
    "generated_at": "2026-11-16T00:00:00Z",
    "series": {"Arielle": {"series_type": "sequel", "genre": ["fairy_tale"], "franchise": "disney",
                           "min_age": 4, "age_tag": "3_5"}},
}


def test_sequel_context_numbers_only_the_main_line(monkeypatch):
    monkeypatch.setattr(data, "_catalog_cache", ARIELLE_CATALOG)
    ctx = data.get_sequel_context()
    assert (ctx[1]["position"], ctx[1]["total"]) == (1, 2)  # was "Teil 1 von 4"
    assert ctx[1]["next"]["id"] == 2 and ctx[2]["next"] is None  # chain stays on the main line
    assert ctx[4] == {"position": None, "total": None, "prev": None, "next": None, "original": ARIELLE_CATALOG["items"][0]}
    assert ctx[3]["original"] is None


def test_item_card_renders_variant_badge_and_original_link(monkeypatch):
    monkeypatch.setattr(data, "_catalog_cache", ARIELLE_CATALOG)
    html = create_app().test_client().get("/?lang=de").get_data(as_text=True)
    assert "Neuverfilmung" in html and "Spin-off" in html
    assert "Original: Arielle, die Meerjungfrau (1989)" in html
    assert "Teil 1 von 2" in html and "Teil 1 von 4" not in html


def test_duplicate_position_check_ignores_variants():
    overrides = {
        "a": {"series": "Drachen", "position_in_series": 1},
        "b": {"series": "Drachen", "position_in_series": 1, "variant": "remake"},
    }
    assert refresh.check_overrides_series_consistency(overrides) == []
    overrides["b"].pop("variant")
    assert len(refresh.check_overrides_series_consistency(overrides)) == 1


def test_series_rows_ignore_variants_for_position_problems():
    overrides = {
        "a": {"series": "S", "position_in_series": 1},
        "b": {"series": "S", "position_in_series": 2},
        "r": {"series": "S", "position_in_series": 1, "variant": "remake"},
        "s": {"series": "S", "variant": "spin_off"},
    }
    row = file_ops.build_series_rows(overrides, {"S": {"series_type": "sequel"}}, {})[0]
    assert row["duplicate_positions"] == [] and row["unpositioned"] == 0 and row["gaps"] == []
