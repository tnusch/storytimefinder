from flask import Blueprint, abort, render_template

from . import data

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    entries = data.get_grid_entries()
    return render_template(
        "index.html",
        items=entries,
        total_count=data.get_total_audiobook_count(entries),
        series_count=data.get_series_card_count(entries),
        episode_count=data.get_episode_count_in_series(entries),
        sequel_context=data.get_sequel_context(),
        franchises=data.get_franchises(),
        age_tags=data.get_age_tags(),
        series_list=data.get_series_list(),
        languages=data.get_languages(),
        genres=data.get_genres(),
        moods=data.get_moods(),
        seasonal_values=data.get_seasonal_values(),
        has_awards=data.has_awards(),
        duration_buckets=data.get_duration_buckets(),
        release_decades=data.get_release_decades(),
        generated_at=data.get_generated_at(),
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
