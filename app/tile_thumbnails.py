"""
Manually-curated cover images for the guided filter UI's tiles (see
app/data.py's get_tile_thumbnail()), keyed by category then value - e.g.
TILE_THUMBNAILS["genre"]["superhero"]. Config, not schema: this has no sync
pipeline of its own and is never touched by refresh/refresh.py - it's a
plain hand-edited Python dict, same spirit as overrides.py's
SERIES_OVERRIDES but living here since it's a read-side-only concern (the
same "a manually-curated dict co-located with its consumer" pattern as this
package's own i18n.py TRANSLATIONS dict).

A category/value pair with no entry here isn't an error - get_tile_thumbnail()
falls back to any one matching catalog item's own thumbnail, and that
fallback usage is what get_tile_thumbnail_warnings() surfaces in the admin
UI's Values screen for manual review. Add an entry here once you've picked a
better representative image than whatever the fallback happened to land on.

Categories match the four guided-filter sidebar entries and their
`data-filter-type` values: "age", "genre", "series", "franchise".
("duration" was removed as a guided-filter category - Dauer is still
filterable, just only via its advanced-panel chip, same as seasonal/etc.)
"""

from __future__ import annotations

TILE_THUMBNAILS: dict[str, dict[str, str]] = {
    "age": {},
    "genre": {},
    "series": {},
    "franchise": {},
}
