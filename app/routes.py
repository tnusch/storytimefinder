from flask import Blueprint, abort, render_template

from . import data

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    return render_template(
        "index.html",
        items=data.get_items(),
        age_tags=data.get_age_tags(),
        series_list=data.get_series_list(),
        languages=data.get_languages(),
        publishers=data.get_publishers(),
        genres=data.get_genres(),
        duration_buckets=data.get_duration_buckets(),
        release_decades=data.get_release_decades(),
        generated_at=data.get_generated_at(),
    )


@bp.route("/category/<slug>")
def category(slug):
    known_slugs = {c["slug"] for c in data.get_categories()}
    if slug not in known_slugs:
        abort(404)

    items = [item for item in data.get_items() if item.get("category") == slug]

    return render_template(
        "category.html",
        items=items,
        category_slug=slug,
        generated_at=data.get_generated_at(),
    )


@bp.route("/impressum")
def impressum():
    return render_template("impressum.html")
