"""
Guided-filter tile values hidden from the home page's sidebar+tile UI (see
app/routes.py's _build_tile_data()) - keyed by category, e.g.
HIDDEN_TILES["genre"] = ["educational"]. Config, not schema, same spirit as
tile_thumbnails.py - a plain hand-edited dict with no sync pipeline of its
own, editable through the admin UI's Values screen ("Manage tile
thumbnails" tables, a "Hidden" checkbox per row) rather than by hand.

Hiding a value only removes its TILE from the guided filter UI - the value
itself stays fully filterable via the (advanced-panel) chips, and still
shows normally on every item card that has it. This is a discovery-UI
declutter tool, not a content moderation or data-correction mechanism.

Series tiles are hidden by default (HIDDEN_BY_DEFAULT): a new series only
gets a tile once it's added to SHOWN_TILES (the same "Hidden" checkbox on
the Values screen, unchecked).

Categories match the four guided-filter sidebar entries: "age", "genre",
"series", "franchise". ("duration" was removed as a guided-filter category
- Dauer is still filterable, just only via its advanced-panel chip.)
"""

from __future__ import annotations

# Categories whose tiles are hidden unless explicitly listed in SHOWN_TILES
# (opt-in) - "series" grows with every new Reihe, most of which are small
# film series that would clutter the tile grid. HIDDEN_TILES is ignored for
# these categories; every other category stays opt-out via HIDDEN_TILES.
HIDDEN_BY_DEFAULT: tuple[str, ...] = ("series",)

SHOWN_TILES: dict[str, list[str]] = {
    "series": [
        "Bibi Blocksberg",
        "Marvels Spidey und seine Super-Freunde",
        "Pettersson und Findus",
        "Pippi Langstrumpf",
        "Sofia die Erste",
        "Woozle Goozle",
    ],
}

HIDDEN_TILES: dict[str, list[str]] = {
    "age": [],
    "genre": [],
    "series": [],
    "franchise": [
        "bibi_blocksberg",
    ],
}
