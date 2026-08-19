from flask import Blueprint, render_template

from . import data

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    return render_template(
        "index.html",
        items=data.get_items(),
        franchises=data.get_franchises(),
        age_tags=data.get_age_tags(),
        series_list=data.get_series_list(),
        languages=data.get_languages(),
        genres=data.get_genres(),
        duration_buckets=data.get_duration_buckets(),
        release_decades=data.get_release_decades(),
        generated_at=data.get_generated_at(),
    )


@bp.route("/impressum")
def impressum():
    return render_template("impressum.html")
