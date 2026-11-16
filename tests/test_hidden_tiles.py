"""Series tiles are opt-in (HIDDEN_BY_DEFAULT + SHOWN_TILES); every other
category stays opt-out via HIDDEN_TILES."""

from app import data, hidden_tiles


def test_series_tiles_hidden_unless_shown(monkeypatch):
    monkeypatch.setattr(hidden_tiles, "SHOWN_TILES", {"series": ["Bibi Blocksberg"]})
    monkeypatch.setattr(hidden_tiles, "HIDDEN_TILES", {"series": ["Bibi Blocksberg"], "genre": ["fantasy"]})
    assert not data.is_tile_hidden("series", "Bibi Blocksberg")  # HIDDEN_TILES ignored for series
    assert data.is_tile_hidden("series", "Some New Series")
    assert data.is_tile_hidden("genre", "fantasy")
    assert not data.is_tile_hidden("genre", "mystery")
