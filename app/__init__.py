from flask import Flask

from . import data


def create_app() -> Flask:
    app = Flask(__name__)

    app.jinja_env.filters["duration"] = data.format_duration
    app.jinja_env.filters["date_de"] = data.format_date_de

    from .routes import bp

    app.register_blueprint(bp)

    return app


app = create_app()
