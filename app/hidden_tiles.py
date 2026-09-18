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

Categories match the four guided-filter sidebar entries: "age", "genre",
"series", "franchise". ("duration" was removed as a guided-filter category
- Dauer is still filterable, just only via its advanced-panel chip.)
"""

from __future__ import annotations

HIDDEN_TILES: dict[str, list[str]] = {
    "age": [],
    "genre": [],
    "series": [
        "Alice im Wunderland",
        "Alles steht Kopf",
        "Arielle",
        "Bambi",
        "Bärenbrüder",
        "Cars",
        "Cinderella",
        "Das Dschungelbuch",
        "Das kleine WIR",
        "Der König der Löwen",
        "Die Eiskönigin",
        "Die Monster AG",
        "Die Schöne und das Biest",
        "Die Unglaublichen",
        "Dr. Brumm",
        "Drachenzähmen leicht gemacht",
        "Kung Fu Panda",
        "Lieselotte",
        "Lilo & Stitch",
        "Madagascar",
        "Marvels Iron Man und seine fantastischen Freunde",
        "Merida",
        "Michel aus Lönneberga",
        "Micky Maus",
        "Mulan",
        "National Geographic Kids",
        "Peter Pan",
        "Planes",
        "Pocahontas",
        "Ralph Reichts",
        "Shrek",
        "Susi und Strolch",
        "Tarzan",
        "Toy Story",
        "Vaiana",
        "Wieso? Weshalb? Warum? ERSTLESER",
        "Winnie Puuh",
        "Zoomania",
    ],
    "franchise": [
        "bibi_blocksberg",
    ],
}
