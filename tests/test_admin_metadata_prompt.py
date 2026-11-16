"""Tests for the admin Suggestions screen's Metadata prompt builder and its
JSON import (admin/file_ops.py). Uses fixture dicts plus a temp
claude_suggestions.json - never the real project data."""

import json

import pytest

from admin import file_ops


def test_candidates_include_only_items_missing_core_fields():
    overrides = {
        "complete": {"description": "d", "min_age": 4, "genre": ["family"], "source_release_year": 1990},
        "partial": {"description": "d"},
    }
    suggestions = {"suggested": {"title": "Suggested", "description": "d", "min_age": 5,
                                 "genre": ["fantasy"], "source_release_year": 2001}}
    item_info = {
        "complete": {"title": "Complete", "language": "de"},
        "partial": {"title": "Partial", "language": "en"},
        "untouched": {"title": "Untouched", "language": None},
        "suggested": {"title": "Suggested", "language": "de"},
    }
    candidates = file_ops.get_metadata_prompt_candidates(suggestions, overrides, item_info, {})
    assert candidates == [
        ("partial", "Partial", None, "en"),
        ("untouched", "Untouched", None, "de"),
    ]


def test_candidates_respect_episodic_series_exemption():
    overrides = {"ep1": {"description": "d", "source_release_year": 1999, "series": "TKKG"}}
    item_info = {"ep1": {"title": "Folge 1", "language": "de"}}
    series_overrides = {"TKKG": {"series_type": "episodic", "genre": ["mystery"], "min_age": 8}}
    assert file_ops.get_metadata_prompt_candidates({}, overrides, item_info, series_overrides) == []
    # Without the series-level entry, genre/min_age are genuinely missing.
    assert file_ops.get_metadata_prompt_candidates({}, overrides, item_info, {}) != []


def test_build_metadata_prompts_chunks_and_includes_ids():
    item_info = {f"id{i}": {"title": f"Title {i}", "language": "de"} for i in range(5)}
    prompts = file_ops.build_metadata_prompts({}, {}, item_info, {}, chunk_size=2)
    assert len(prompts) == 3
    assert "id0 | Title 0 | - | de" in prompts[0]
    assert "id4 | Title 4 | - | de" in prompts[2]
    assert "```json" in prompts[0]


def test_build_metadata_prompts_empty_when_nothing_missing():
    assert file_ops.build_metadata_prompts({}, {}, {}, {}) == []


@pytest.fixture
def scratch_suggestions(tmp_path, monkeypatch):
    path = tmp_path / "claude_suggestions.json"
    monkeypatch.setattr(file_ops, "SUGGESTIONS_PATH", path)
    monkeypatch.setattr(
        file_ops,
        "get_item_info",
        lambda: {"vid1": {"title": "Der kleine Drache"}, "vid2": {"title": "Pumuckl"}},
    )
    path.write_text(json.dumps({
        "vid2": {"title": "Pumuckl", "suggested_at": "x", "description": None, "series": "Pumuckl",
                 "position_in_series": None, "genre": [], "franchise": None, "min_age": 5,
                 "source_release_year": None, "seasonal": None, "awards": []},
    }), encoding="utf-8")
    return path


def test_import_validates_merges_and_reports(scratch_suggestions):
    reply = """Here you go:
```json
{
  "vid1": {"description": "Ein Abenteuer über Mut und Freundschaft.", "genre": ["adventure", "bogus"],
           "franchise": "not_a_franchise", "min_age": "4", "source_release_year": 1975, "seasonal": null},
  "vid2": {"description": "Ein Kobold namens Pumuckl macht Unfug.", "min_age": null, "source_release_year": 1962},
  "nope": {"description": "x"},
  "bad": "not an object"
}
```"""
    report = file_ops.import_metadata_suggestions(reply)
    assert report["imported"] == ["vid1", "vid2"]
    assert report["unknown"] == ["nope"]
    assert report["invalid"] == ["bad"]
    assert report["description_title_words"] == ["vid2 (Pumuckl)"]

    saved = json.loads(scratch_suggestions.read_text(encoding="utf-8"))
    assert saved["vid1"]["genre"] == ["adventure"]
    assert saved["vid1"]["franchise"] is None
    assert saved["vid1"]["min_age"] == 4
    assert saved["vid1"]["title"] == "Der kleine Drache"
    # Existing pending values survive an empty imported value; new ones fill in.
    assert saved["vid2"]["min_age"] == 5
    assert saved["vid2"]["series"] == "Pumuckl"
    assert saved["vid2"]["source_release_year"] == 1962
    # Kept despite the title-word match - the curator reviews it on the card.
    assert saved["vid2"]["description"] == "Ein Kobold namens Pumuckl macht Unfug."
    assert "nope" not in saved


def test_import_rejects_text_without_json(scratch_suggestions):
    with pytest.raises(ValueError):
        file_ops.import_metadata_suggestions("Sorry, I couldn't find anything.")


def test_import_keeps_description_that_reuses_title_words(tmp_path, monkeypatch):
    monkeypatch.setattr(file_ops, "SUGGESTIONS_PATH", tmp_path / "claude_suggestions.json")
    entry_id = "OLAK5uy_sofia"
    title = "Sofia die Erste - Abenteuer in der Wüste / Der Haustier-Wettbewerb"
    monkeypatch.setattr(file_ops, "get_item_info", lambda: {entry_id: {"title": title}})
    description = ("Eine Reise in ein fernes Wüstenreich und ein Haustier-Wettbewerb stellen "
                   "eine junge Prinzessin vor neue Herausforderungen.")
    reply = json.dumps({entry_id: {"description": description, "series": "Sofia die Erste",
                                   "position_in_series": 5, "genre": ["adventure", "family"],
                                   "franchise": "disney", "min_age": 4, "source_release_year": 2013,
                                   "seasonal": None}})
    report = file_ops.import_metadata_suggestions(reply)
    assert report["description_title_words"] == [f"{entry_id} (Haustier, Wettbewerb)"]
    saved = json.loads((tmp_path / "claude_suggestions.json").read_text(encoding="utf-8"))
    assert saved[entry_id]["description"] == description


@pytest.mark.parametrize("series_type", ["sequel", None])
def test_candidates_exempt_any_series_entry_not_just_episodic(series_type):
    overrides = {"film2": {"description": "d", "source_release_year": 2004, "series": "Shrek"}}
    item_info = {"film2": {"title": "Shrek 2", "language": "de"}}
    meta = {"genre": ["fantasy"], "min_age": 4}
    if series_type:
        meta["series_type"] = series_type
    assert file_ops.get_metadata_prompt_candidates({}, overrides, item_info, {"Shrek": meta}) == []
