"""admin/file_ops.py's build_catalog_rows() - the data behind the
Suggestions screen's filterable "Applied overrides" table."""

from admin import file_ops


def test_build_catalog_rows_resolves_series_values_and_flags():
    overrides = {
        "ep1": {"series": "TKKG", "position_in_series": 2, "description": "d", "source_release_year": 1981,
                "genre": ["family"]},  # stale per-item genre - the series entry wins
        "solo": {"description": "", "genre": ["fantasy"], "min_age": 6, "awards": [{"name": "X"}]},
    }
    item_info = {"ep1": {"title": "Folge 2", "thumbnail_url": "t.jpg", "language": "de"}}
    series_overrides = {"TKKG": {"series_type": "episodic", "genre": ["mystery"], "franchise": "tkkg", "min_age": 8}}
    warnings = [("dup position", ["ep1"]), ("other", ["x"])]
    diffs = {"solo": {"description": "new", "min_age": 5}}

    rows = {r["entry_id"]: r for r in file_ops.build_catalog_rows(overrides, item_info, series_overrides, warnings, diffs)}

    ep1 = rows["ep1"]
    assert (ep1["genre"], ep1["franchise"], ep1["min_age"], ep1["from_series"]) == (["mystery"], "tkkg", 8, True)
    assert ep1["series_type"] == "episodic" and ep1["missing"] == [] and ep1["warnings"] == ["dup position"]
    assert ep1["title"] == "Folge 2"

    solo = rows["solo"]
    assert solo["from_series"] is False and solo["genre"] == ["fantasy"]
    assert solo["missing"] == ["description", "source_release_year"]
    assert solo["title"] == "solo"  # falls back to the entry id when no title is known
    assert solo["diff_count"] == 2 and solo["has_awards"] is True
