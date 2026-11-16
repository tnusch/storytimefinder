"""Series screen + Catalog bulk-action write operations in admin/file_ops.py,
run against a scratch overrides.py (never the real one)."""

import json

import pytest

from admin import file_ops

SCRATCH_OVERRIDES = '''"""Docstring mentioning SERIES_OVERRIDES (a `dict[str, dict]`) in prose only."""

SERIES_OVERRIDES: dict[str, dict] = {
    # Members disagreed before this entry existed.
    "Toy Story": {
        "series_type": "sequel",
        "genre": ["adventure"],
        "franchise": "pixar",
        "min_age": 4,
    },

    "Bibi Blocksberg": {
        "series_type": "episodic",
        "genre": ["fantasy"],
        "min_age": 4,
    },
}

ITEM_OVERRIDES: dict[str, dict] = {
    "ts1": {
        "series": "Toy Story",
        "position_in_series": 1,
        "description": "d1",
    },

    "ts2": {
        "series": "Toy Story",
        "position_in_series": 1,
        "seasonal": "christmas",
    },

    "solo": {
        "description": "d3",
        "genre": ["family"],
        "min_age": 3,
    },

    "w1": {
        "series": "Wieso",
        "genre": ["educational"],
        "min_age": 4,
    },

    "w2": {
        "series": "Wieso",
        "genre": ["educational"],
        "min_age": 5,
    },
}
'''


def _load(path):
    ns = {}
    exec(path.read_text(encoding="utf-8"), ns)
    return ns


@pytest.fixture
def scratch(tmp_path, monkeypatch):
    path = tmp_path / "overrides.py"
    path.write_text(SCRATCH_OVERRIDES, encoding="utf-8")
    suggestions = tmp_path / "claude_suggestions.json"
    suggestions.write_text(json.dumps({"p1": {"title": "x", "series": "Toy Story"}}), encoding="utf-8")
    monkeypatch.setattr(file_ops, "OVERRIDES_PATH", path)
    monkeypatch.setattr(file_ops, "SUGGESTIONS_PATH", suggestions)
    monkeypatch.setattr(file_ops, "list_overrides", lambda: dict(_load(path)["ITEM_OVERRIDES"]))
    monkeypatch.setattr(file_ops, "list_series_overrides", lambda: dict(_load(path)["SERIES_OVERRIDES"]))
    return path, suggestions


def test_remove_override_fields(scratch):
    path, _ = scratch
    assert file_ops.remove_override_fields("ts2", ("seasonal", "position_in_series")) is True
    assert _load(path)["ITEM_OVERRIDES"]["ts2"] == {"series": "Toy Story"}
    assert file_ops.remove_override_fields("ts2", ("seasonal",)) is False  # already gone
    assert file_ops.remove_override_fields("nope", ("seasonal",)) is False


def test_save_series_override_is_authoritative(scratch):
    path, _ = scratch
    file_ops.save_series_override(
        "Toy Story", {"series_type": "sequel", "genre": ["adventure", "family"], "franchise": None, "min_age": 5}
    )
    assert _load(path)["SERIES_OVERRIDES"]["Toy Story"] == {
        "series_type": "sequel", "genre": ["adventure", "family"], "min_age": 5,
    }


def test_rename_series_updates_entry_members_and_suggestions(scratch):
    path, suggestions = scratch
    assert file_ops.rename_series("Toy Story", "Toy Story Saga") == 2
    ns = _load(path)
    assert "Toy Story" not in ns["SERIES_OVERRIDES"] and ns["SERIES_OVERRIDES"]["Toy Story Saga"]["min_age"] == 4
    assert {ns["ITEM_OVERRIDES"][e]["series"] for e in ("ts1", "ts2")} == {"Toy Story Saga"}
    assert json.loads(suggestions.read_text(encoding="utf-8"))["p1"]["series"] == "Toy Story Saga"


def test_rename_series_refuses_to_merge_two_entries(scratch):
    with pytest.raises(ValueError):
        file_ops.rename_series("Toy Story", "Bibi Blocksberg")


def test_remove_series_override_copies_values_onto_members(scratch):
    path, _ = scratch
    assert file_ops.remove_series_override("Toy Story") == 2
    ns = _load(path)
    assert "Toy Story" not in ns["SERIES_OVERRIDES"] and "Bibi Blocksberg" in ns["SERIES_OVERRIDES"]
    assert ns["ITEM_OVERRIDES"]["ts1"]["genre"] == ["adventure"] and ns["ITEM_OVERRIDES"]["ts1"]["min_age"] == 4
    assert ns["ITEM_OVERRIDES"]["ts2"]["franchise"] == "pixar"
    assert "Members disagreed" not in path.read_text(encoding="utf-8")  # its comment went with it


def test_create_entry_and_strip_members(scratch):
    path, _ = scratch
    suggested = file_ops.suggest_series_metadata([file_ops.list_overrides()[e] for e in ("w1", "w2")])
    assert suggested == {"genre": ["educational"], "franchise": None, "min_age": 4}  # min_age tie -> lower
    file_ops.save_series_override("Wieso", {"series_type": "episodic", **suggested})
    assert file_ops.strip_series_resolved_fields("Wieso") == 2
    ns = _load(path)
    assert ns["SERIES_OVERRIDES"]["Wieso"] == {"series_type": "episodic", "genre": ["educational"], "min_age": 4}
    assert ns["ITEM_OVERRIDES"]["w1"] == {"series": "Wieso"}


def test_build_series_rows_flags_position_problems():
    overrides = {
        "a": {"series": "S", "position_in_series": 1}, "b": {"series": "S", "position_in_series": 1},
        "c": {"series": "S", "position_in_series": 4}, "d": {"series": "S"},
        "x": {"series": "New", "genre": ["family"], "min_age": 3},
    }
    rows = {r["name"]: r for r in file_ops.build_series_rows(overrides, {"S": {"series_type": "sequel"}, "Empty": {}}, {})}
    s = rows["S"]
    assert [m["entry_id"] for m in s["members"]] == ["a", "b", "c", "d"]
    assert s["duplicate_positions"] == [1] and s["gaps"] == [2, 3] and s["unpositioned"] == 1
    assert rows["New"]["has_entry"] is False and rows["New"]["suggested"]["min_age"] == 3
    assert rows["Empty"]["members"] == [] and rows["S"]["anchor"] == "s"


def test_series_anchor():
    assert file_ops.series_anchor("Michel aus Lönneberga") == "michel-aus-loenneberga"
    assert file_ops.series_anchor("Wieso? Weshalb? Warum? ERSTLESER") == "wieso-weshalb-warum-erstleser"
