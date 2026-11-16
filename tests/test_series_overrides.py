"""SERIES_OVERRIDES centralizes genre/franchise/min_age for every series
with an entry - episodic, sequel, or untyped - not just episodic ones."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "refresh"))
import refresh  # noqa: E402


@pytest.mark.parametrize("series_type", ["episodic", "sequel", None])
def test_check_missing_fields_satisfied_by_any_series_entry(series_type):
    overrides = {"a": {"description": "d", "source_release_year": 2001, "series": "Toy Story"}}
    meta = {"genre": ["adventure"], "min_age": 4}
    if series_type:
        meta["series_type"] = series_type
    assert refresh.check_missing_fields(overrides, {"a": "Toy Story 2"}, {"Toy Story": meta}) == []


def test_check_missing_fields_still_flags_series_without_entry():
    overrides = {"a": {"description": "d", "source_release_year": 2001, "series": "Toy Story"}}
    warnings = refresh.check_missing_fields(overrides, {"a": "Toy Story 2"}, {})
    assert warnings == [("'Toy Story 2' (a) is missing: min_age, genre", ["a"])]
