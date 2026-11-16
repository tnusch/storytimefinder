"""Tests for the admin Sources screen's "Add sources from a list" flow
(admin/file_ops.py): list parsing, prompt building, import preview, and
writing confirmed rows. Network and real project files are never touched -
the album-id resolver is stubbed and sources.py/overrides.py are scratch
copies in tmp_path."""

import ast

import pytest

from admin import file_ops

PASTED_LIST = """a)
<https://music.youtube.com/browse/MPREb_jOsKY2fB0dB>
20: Die Mystischen Inseln (Teil 3 & 4) [Hörspiel zum TV-Special]
<https://music.youtube.com/browse/MPREb_jOsKY2fB0dB>
Show• 2023

b)
<https://music.youtube.com/browse/MPREb_gssM5kPiizQ>
Sofia die Erste - Auf einmal Prinzessin (Hörspiel zum TV-Special)
<https://music.youtube.com/browse/MPREb_gssM5kPiizQ>
Show• 2023
"""


@pytest.mark.parametrize(
    "value, expected",
    [
        ("https://music.youtube.com/browse/MPREb_gssM5kPiizQ", "MPREb_gssM5kPiizQ"),
        ("https://music.youtube.com/playlist?list=OLAK5uy_abc", "OLAK5uy_abc"),
        ("https://www.youtube.com/channel/UCxyz", "UCxyz"),
        ("OLAK5uy_bare", "OLAK5uy_bare"),
        ("https://www.youtube.com/@somehandle", "https://www.youtube.com/@somehandle"),
    ],
)
def test_extract_youtube_id(value, expected):
    assert file_ops.extract_youtube_id(value) == expected


def test_parse_source_list_handles_copied_youtube_music_list():
    assert file_ops.parse_source_list(PASTED_LIST) == [
        {
            "youtube_id": "MPREb_jOsKY2fB0dB",
            "url": "https://music.youtube.com/browse/MPREb_jOsKY2fB0dB",
            "raw_title": "20: Die Mystischen Inseln (Teil 3 & 4) [Hörspiel zum TV-Special]",
        },
        {
            "youtube_id": "MPREb_gssM5kPiizQ",
            "url": "https://music.youtube.com/browse/MPREb_gssM5kPiizQ",
            "raw_title": "Sofia die Erste - Auf einmal Prinzessin (Hörspiel zum TV-Special)",
        },
    ]


def test_parse_source_list_title_on_same_line_and_unknown_links():
    text = "Pumuckl - Folge 1 https://music.youtube.com/playlist?list=OLAK5uy_one\nhttps://example.com/x\nnot a title"
    items = file_ops.parse_source_list(text)
    assert [(i["youtube_id"], i["raw_title"]) for i in items] == [("OLAK5uy_one", "Pumuckl - Folge 1")]


def test_build_source_prompt_lists_ids_and_series():
    items = file_ops.parse_source_list(PASTED_LIST)
    prompt = file_ops.build_source_prompt(items, ["Sofia die Erste", "TKKG"])
    assert "MPREb_jOsKY2fB0dB | 20: Die Mystischen Inseln" in prompt
    assert "Existing series names: Sofia die Erste, TKKG" in prompt
    assert "ask me" in prompt
    assert "```json" in prompt


def test_prepare_source_import_resolves_and_flags(monkeypatch):
    monkeypatch.setattr(file_ops, "list_sources", lambda: [{"youtube_id": "OLAK5uy_existing"}])
    resolved = {"MPREb_a": "OLAK5uy_new_a", "MPREb_dupe": "OLAK5uy_existing", "MPREb_fail": None}
    reply = """```json
{
  "MPREb_a": {"label": "Sofia die Erste - Auf einmal Prinzessin", "series": "Sofia die Erste", "language": "DE"},
  "MPREb_dupe": {"label": "Old one", "series": null, "language": "de"},
  "MPREb_fail": {"label": "Unresolvable", "series": null},
  "PLplaylist": {"label": "", "series": null, "language": "en"},
  "weird": {"label": "x"}
}
```"""
    rows = file_ops.prepare_source_import(reply, resolver=resolved.get)
    by_input = {r["input_id"]: r for r in rows}

    assert by_input["MPREb_a"] == {
        "input_id": "MPREb_a", "youtube_id": "OLAK5uy_new_a", "type": "album",
        "label": "Sofia die Erste - Auf einmal Prinzessin", "series": "Sofia die Erste",
        "language": "de", "error": None,
    }
    assert by_input["MPREb_dupe"]["error"] == "Already in sources.py."
    assert "resolve" in by_input["MPREb_fail"]["error"]
    assert by_input["PLplaylist"]["type"] == "playlist"
    assert by_input["PLplaylist"]["error"] == "No label in Claude's reply."
    assert by_input["weird"]["error"] == "Unrecognized id."


def test_prepare_source_import_rejects_non_json(monkeypatch):
    monkeypatch.setattr(file_ops, "list_sources", lambda: [])
    with pytest.raises(ValueError):
        file_ops.prepare_source_import("Which series is item 1?", resolver=lambda _: None)


@pytest.fixture
def scratch_files(tmp_path, monkeypatch):
    sources = tmp_path / "sources.py"
    sources.write_text('SOURCES = [\n    {\n        "type": "album",\n        "youtube_id": "OLAK5uy_existing",\n'
                       '        "label": "Old",\n        "language": "de",\n        "active": True,\n    },\n]\n',
                       encoding="utf-8")
    overrides = tmp_path / "overrides.py"
    overrides.write_text("ITEM_OVERRIDES: dict[str, dict] = {\n}\n", encoding="utf-8")
    monkeypatch.setattr(file_ops, "SOURCES_PATH", sources)
    monkeypatch.setattr(file_ops, "OVERRIDES_PATH", overrides)
    monkeypatch.setattr(
        file_ops, "list_sources",
        lambda: ast.literal_eval(sources.read_text(encoding="utf-8").split("=", 1)[1]),
    )
    return sources, overrides


def test_add_imported_sources_writes_in_order_with_series(scratch_files):
    sources, overrides = scratch_files
    rows = [
        {"youtube_id": "OLAK5uy_first", "type": "album", "label": "Sofia die Erste - A", "series": "Sofia die Erste", "language": "de"},
        {"youtube_id": "OLAK5uy_second", "type": "album", "label": "Standalone", "series": "", "language": "de"},
        {"youtube_id": "OLAK5uy_existing", "type": "album", "label": "Dupe", "series": "", "language": "de"},
    ]
    report = file_ops.add_imported_sources(rows)
    assert report == {"added": ["Sofia die Erste - A", "Standalone"], "skipped": ["OLAK5uy_existing"]}

    written = file_ops.list_sources()
    assert [s["youtube_id"] for s in written] == ["OLAK5uy_first", "OLAK5uy_second", "OLAK5uy_existing"]
    assert all(s["active"] for s in written)

    override_text = overrides.read_text(encoding="utf-8")
    assert '"OLAK5uy_first": {' in override_text
    assert '"series": "Sofia die Erste",' in override_text
    assert "OLAK5uy_second" not in override_text
