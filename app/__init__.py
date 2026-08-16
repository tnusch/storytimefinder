from flask import Flask, g, request

from . import data
from .i18n import DEFAULT_LANGUAGE, resolve_language, translate


def create_app() -> Flask:
    app = Flask(__name__)

    app.jinja_env.filters["duration"] = data.format_duration
    app.jinja_env.filters["duration_bucket"] = data.duration_bucket_slug
    app.jinja_env.filters["release_year"] = data.release_year
    app.jinja_env.filters["release_decade"] = data.release_decade
    app.jinja_env.filters["local_date"] = data.format_date

    # A true Jinja global (not a context_processor value) so `t()` also works
    # inside macros imported via `{% from %}`, which don't inherit the
    # calling template's context unless imported "with context".
    app.jinja_env.globals["t"] = lambda key, **kw: translate(getattr(g, "lang", DEFAULT_LANGUAGE), key, **kw)

    @app.before_request
    def set_language() -> None:
        g.lang = resolve_language(request.accept_languages, request.args.get("lang"))

    @app.context_processor
    def inject_lang() -> dict:
        return {"lang": getattr(g, "lang", DEFAULT_LANGUAGE)}

    from .routes import bp

    app.register_blueprint(bp)

    return app


app = create_app()
