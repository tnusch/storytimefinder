from __future__ import annotations

import json
import subprocess
import sys

from flask import Blueprint, flash, redirect, render_template, request, url_for

from . import file_ops

bp = Blueprint("admin", __name__)

SOURCE_TYPES = ("album", "channel", "playlist")
SUGGESTION_FIELDS = (
    "description",
    "series",
    "position_in_series",
    "genre",
    "franchise",
    "min_age",
    "source_release_year",
    "mood",
    "seasonal",
    "awards",
)
INT_FIELDS = {"position_in_series", "min_age", "source_release_year"}


class InvalidAwardsJSON(ValueError):
    """Raised by _parse_suggestion_form() when the awards textarea's content
    isn't a valid JSON array - lets suggestions_action() flash a clear error
    and abort the whole apply instead of silently dropping the field."""


@bp.route("/")
def index():
    return redirect(url_for("admin.sources"))


@bp.route("/sources")
def sources():
    return render_template("sources.html", sources=file_ops.list_sources(), source_types=SOURCE_TYPES)


@bp.route("/sources/add", methods=["POST"])
def sources_add():
    entry = {
        "type": request.form.get("type", "").strip(),
        "youtube_id": request.form.get("youtube_id", "").strip(),
        "label": request.form.get("label", "").strip(),
        "language": request.form.get("language", "de").strip() or "de",
        "active": request.form.get("active") == "on",
    }
    if entry["type"] not in SOURCE_TYPES or not entry["youtube_id"] or not entry["label"]:
        flash("Type, YouTube ID, and label are all required.", "error")
        return redirect(url_for("admin.sources"))

    try:
        file_ops.add_source(entry)
    except (ValueError, RuntimeError) as exc:
        flash(f"Could not add source: {exc}", "error")
        return redirect(url_for("admin.sources"))

    flash(f"Added {entry['label']!r} to sources.py.", "success")
    return redirect(url_for("admin.sources"))


def _run_refresh_subprocess(flags: list[str]) -> tuple[str, int | None]:
    """Run refresh/refresh.py as a subprocess with the given flags, waiting
    for it to finish. Returns (combined stdout+stderr, returncode) - None
    for returncode on a timeout.

    Script path and cwd are derived from file_ops.REFRESH_DIR at call time
    (not a module-level constant computed at import time) so tests can
    point file_ops at a scratch copy and this follows - see
    file_ops.py's docstring. Getting this wrong means this silently
    executes the real refresh/refresh.py against real API keys and real
    data instead of a test fixture.
    """
    refresh_script = file_ops.REFRESH_DIR / "refresh.py"
    project_root = file_ops.REFRESH_DIR.parent
    try:
        result = subprocess.run(
            [sys.executable, str(refresh_script), *flags],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=600,
        )
        return (result.stdout or "") + (result.stderr or ""), result.returncode
    except subprocess.TimeoutExpired as exc:
        return f"Timed out after {exc.timeout}s.\n\n{exc.stdout or ''}{exc.stderr or ''}", None


@bp.route("/check-removed")
def check_removed():
    return render_template("check_removed.html", output=None, returncode=None)


@bp.route("/check-removed/run", methods=["POST"])
def check_removed_run():
    flags = ["--check-removed"]
    if request.form.get("clean_fetched") == "on":
        flags.append("--clean-fetched")
    if request.form.get("log_responses") == "on":
        flags.append("--log-responses")

    output, returncode = _run_refresh_subprocess(flags)
    return render_template("check_removed.html", output=output, returncode=returncode, flags=flags)


@bp.route("/fetch")
def fetch():
    return render_template("fetch.html", output=None, returncode=None)


@bp.route("/fetch/run", methods=["POST"])
def fetch_run():
    flags = ["--fetch"]
    if request.form.get("clean_db") == "on":
        flags.append("--clean-db")
    if request.form.get("clean_fetched") == "on":
        flags.append("--clean-fetched")
    if request.form.get("log_responses") == "on":
        flags.append("--log-responses")

    output, returncode = _run_refresh_subprocess(flags)
    return render_template("fetch.html", output=output, returncode=returncode, flags=flags)


@bp.route("/sync")
def sync():
    return render_template("sync.html", output=None, returncode=None)


@bp.route("/sync/run", methods=["POST"])
def sync_run():
    flags = ["--sync"]
    output, returncode = _run_refresh_subprocess(flags)
    return render_template("sync.html", output=output, returncode=returncode, flags=flags)


@bp.route("/values")
def values():
    lists = {name: file_ops.get_value_list(name) for name in file_ops.VALUE_LIST_CONFIG}
    return render_template("values.html", lists=lists, list_config=file_ops.VALUE_LIST_CONFIG)


@bp.route("/values/add", methods=["POST"])
def values_add():
    list_name = request.form.get("list_name", "")
    value = request.form.get("value", "")
    label_de = request.form.get("label_de", "").strip() or None
    label_en = request.form.get("label_en", "").strip() or None

    try:
        file_ops.add_value_list_entry(list_name, value, label_de, label_en)
    except ValueError as exc:
        flash(f"Could not add value: {exc}", "error")
        return redirect(url_for("admin.values"))

    flash(f"Added {value.strip()!r} to {list_name}.", "success")
    return redirect(url_for("admin.values"))


def _compute_override_diffs(overrides: dict, suggestions: dict) -> dict[str, dict]:
    """For every entry_id present in both `overrides` and `suggestions`,
    return {field: suggested_value} for each field where the pending
    suggestion has a non-empty value that disagrees with the current
    override - used to annotate Applied-overrides cards with inline
    "Suggested: ..." hints (see suggestions.html) so a regenerated
    suggestion's differences are visible without cross-referencing two
    separate cards. An entry/field with nothing worth flagging is simply
    absent from the result, not present with an empty dict."""
    diffs: dict[str, dict] = {}
    for entry_id, override in overrides.items():
        suggestion = suggestions.get(entry_id)
        if not suggestion:
            continue
        entry_diff = {
            field: suggestion.get(field)
            for field in SUGGESTION_FIELDS
            if suggestion.get(field) not in (None, "", []) and suggestion.get(field) != override.get(field)
        }
        if entry_diff:
            diffs[entry_id] = entry_diff
    return diffs


@bp.route("/suggestions")
def suggestions():
    suggestions_data = file_ops.load_suggestions()
    overrides_data = file_ops.list_overrides()
    return render_template(
        "suggestions.html",
        suggestions=suggestions_data,
        overrides=overrides_data,
        diffs=_compute_override_diffs(overrides_data, suggestions_data),
        consistency_warnings=file_ops.get_consistency_warnings(),
        item_info=file_ops.get_item_info(),
        genre_values=file_ops.get_genre_values(),
        franchise_values=file_ops.get_franchise_values(),
        mood_values=file_ops.get_mood_values(),
        seasonal_values=file_ops.get_seasonal_values(),
    )


def _parse_suggestion_form(form) -> dict:
    """Raises InvalidAwardsJSON if the awards textarea doesn't parse as a
    JSON array - callers should catch it and flash an error rather than
    letting a typo silently turn into an empty/dropped awards field."""
    fields = {}
    for name in SUGGESTION_FIELDS:
        raw = form.get(name, "").strip()
        if name == "awards":
            if not raw:
                fields[name] = []
                continue
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise InvalidAwardsJSON(str(exc)) from exc
            if not isinstance(parsed, list):
                raise InvalidAwardsJSON("must be a JSON array, e.g. [] or [{...}]")
            fields[name] = parsed
            continue
        if not raw:
            fields[name] = None
            continue
        if name in INT_FIELDS:
            try:
                fields[name] = int(raw)
            except ValueError:
                fields[name] = None
        else:
            fields[name] = raw
    return fields


@bp.route("/suggestions/<path:entry_id>/regenerate", methods=["POST"])
def suggestions_regenerate(entry_id):
    output, returncode = _run_refresh_subprocess(["--regenerate-suggestion", entry_id])
    if returncode == 0:
        flash(f"Regenerated suggestion for {entry_id!r}.", "success")
    else:
        detail = output.strip().splitlines()[-1] if output.strip() else "no output"
        flash(f"Regenerating suggestion for {entry_id!r} failed (exit {returncode}): {detail}", "error")
    return redirect(url_for("admin.suggestions"))


@bp.route("/suggestions/<path:entry_id>", methods=["POST"])
def suggestions_action(entry_id):
    action = request.form.get("action")
    if action == "apply":
        try:
            fields = _parse_suggestion_form(request.form)
        except InvalidAwardsJSON as exc:
            flash(f"Could not parse the awards field as JSON ({exc}) - fix it and try again.", "error")
            return redirect(url_for("admin.suggestions"))
        file_ops.apply_override(entry_id, fields)
        was_pending = entry_id in file_ops.load_suggestions()
        file_ops.dismiss_suggestion(entry_id)
        if was_pending:
            flash("Applied to overrides.py and removed from the review queue.", "success")
        else:
            flash("Saved changes to overrides.py.", "success")
    elif action == "dismiss":
        file_ops.dismiss_suggestion(entry_id)
        flash("Dismissed - nothing was written to overrides.py.", "success")
    return redirect(url_for("admin.suggestions"))
