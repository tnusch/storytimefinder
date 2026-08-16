from flask import Blueprint, abort, render_template, request

from . import data

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    return render_template(
        "index.html",
        items=data.get_items(),
        categories=data.get_categories(),
        age_tags=data.get_age_tags(),
        generated_at=data.get_generated_at(),
        searched=False,
    )


@bp.route("/search")
def search():
    query = request.args.get("q", "").strip()
    results = data.search(query=query)

    return render_template(
        "index.html",
        items=results,
        categories=data.get_categories(),
        age_tags=data.get_age_tags(),
        generated_at=data.get_generated_at(),
        searched=True,
        query=query,
    )


@bp.route("/category/<slug>")
def category(slug):
    known_slugs = {c["slug"] for c in data.get_categories()}
    if slug not in known_slugs:
        abort(404)

    items = data.search(category=slug)

    return render_template(
        "category.html",
        items=items,
        category_slug=slug,
        category_label=data.get_category_label(slug),
        categories=data.get_categories(),
        generated_at=data.get_generated_at(),
    )


@bp.route("/impressum")
def impressum():
    return render_template("impressum.html")
