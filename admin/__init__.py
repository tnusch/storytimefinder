"""
Local-only admin tool for StorytimeFinder's curation workflow: add sources,
run refresh.py with common flags, and review/apply/dismiss Claude's
metadata suggestions into overrides.py.

NEVER deploy this. It writes directly to refresh/sources.py and
refresh/overrides.py on whatever machine it runs on, and executes
refresh/refresh.py as a subprocess - it has no authentication of its own,
so it must only ever be run locally. Flask's dev server binds to
127.0.0.1 by default (no --host flag) - keep it that way. It is
deliberately not registered in vercel.json/api/index.py and never should
be; app/ (the deployed site) never imports anything from here.

Run with:
    flask --app admin run --port 5050
"""

from flask import Flask


def create_app() -> Flask:
    app = Flask(__name__)
    # Only used to sign the flash-message session cookie for this local,
    # single-user tool - not a meaningful secret.
    app.config["SECRET_KEY"] = "storytimefinder-admin-local-only"

    from .routes import bp

    app.register_blueprint(bp)

    return app


app = create_app()
