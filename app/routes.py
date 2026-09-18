from flask import Blueprint, abort, g, render_template

from . import data
from .i18n import translate

bp = Blueprint("main", __name__)


def _tile(category: str, value: str, label: str) -> dict:
    return {"value": value, "label": label, "thumbnail_url": data.get_tile_thumbnail(category, value)}


def _build_tile_data(age_tags, genres, series_list, franchises) -> dict:
    """Guided filter UI's sidebar+tile data (see index.html's
    .guided-filters section) - one tile per value in each of the four
    categories (Alter/Genre/Reihe/Franchise - Dauer was removed as a
    guided-filter category; duration stays filterable, just only via its
    advanced-panel chip, same as seasonal/etc), reusing the exact same
    value lists the (now advanced-panel-only) chip groups already render
    from, so both UIs always offer the same choices - except a value
    hidden via hidden_tiles.py (see data.is_tile_hidden()), which is
    filtered out of the tile grid here but still fully filterable through
    its chip; hiding is a guided-UI declutter tool, not a data change.
    Labels are resolved here (not in the template) since translate() needs
    g.lang but data.py deliberately stays Flask-context-free - series
    names aren't translated at all, same as everywhere else in this app."""
    lang = g.lang
    return {
        "age": [_tile("age", a, translate(lang, f"age_tag_{a}")) for a in age_tags if not data.is_tile_hidden("age", a)],
        "genre": [_tile("genre", gv, translate(lang, f"genre_{gv}")) for gv in genres if not data.is_tile_hidden("genre", gv)],
        "series": [_tile("series", s, s) for s in series_list if not data.is_tile_hidden("series", s)],
        "franchise": [
            _tile("franchise", f["slug"], translate(lang, f"franchise_{f['slug']}"))
            for f in franchises
            if not data.is_tile_hidden("franchise", f["slug"])
        ],
    }


@bp.route("/")
def index():
    entries = data.get_grid_entries()
    age_tags = data.get_age_tags()
    duration_buckets = data.get_duration_buckets()
    genres = data.get_genres()
    series_list = data.get_series_list()
    franchises = data.get_franchises()
    return render_template(
        "index.html",
        items=entries,
        total_count=data.get_total_audiobook_count(entries),
        series_count=data.get_series_card_count(entries),
        episode_count=data.get_episode_count_in_series(entries),
        sequel_context=data.get_sequel_context(),
        franchises=franchises,
        age_tags=age_tags,
        languages=data.get_languages(),
        genres=genres,
        seasonal_values=data.get_seasonal_values(),
        has_awards=data.has_awards(),
        duration_buckets=duration_buckets,
        release_decades=data.get_release_decades(),
        generated_at=data.get_generated_at(),
        tile_data=_build_tile_data(age_tags, genres, series_list, franchises),
    )


@bp.route("/series/<slug>")
def series_detail(slug):
    group = data.get_series_group_by_slug(slug)
    if group is None:
        abort(404)
    return render_template("series_detail.html", group=group, generated_at=data.get_generated_at())


@bp.route("/impressum")
def impressum():
    return render_template("impressum.html")
