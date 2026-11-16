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
    "seasonal",
    "awards",
    "variant",
)
INT_FIELDS = {"position_in_series", "min_age", "source_release_year"}
SERIES_OVERRIDE_FIELDS = ("series_type", "genre", "franchise", "min_age")
SERIES_OVERRIDE_INT_FIELDS = {"min_age"}


class InvalidAwardsJSON(ValueError):
    """Raised by _parse_suggestion_form() when the awards textarea's content
    isn't a valid JSON array - lets suggestions_action() flash a clear error
    and abort the whole apply instead of silently dropping the field."""


@bp.route("/")
def index():
    return redirect(url_for("admin.sources"))


def _render_sources(**extra):
    """The Sources screen, plus any bulk-add state (pasted list, generated
    prompt, import preview rows) - those are rendered straight back from a
    POST rather than stored anywhere, since they're scratch state for one
    add-from-a-list round-trip."""
    return render_template(
        "sources.html",
        sources=file_ops.list_sources(),
        source_types=SOURCE_TYPES,
        source_warnings=file_ops.get_source_warnings(),
        series_names=file_ops.get_series_names(),
        **extra,
    )


@bp.route("/sources")
def sources():
    return _render_sources()


@bp.route("/sources/prompt", methods=["POST"])
def sources_prompt():
    """Bulk add, step 1: pasted list of YouTube Music links/titles -> a
    Claude.ai prompt (see file_ops.build_source_prompt())."""
    raw = request.form.get("source_list", "")
    items = file_ops.parse_source_list(raw)
    if not items:
        flash("No YouTube Music album/playlist/channel links found in the pasted list.", "error")
        return _render_sources(source_list=raw)
    return _render_sources(
        source_list=raw,
        source_items=items,
        source_prompt=file_ops.build_source_prompt(items, file_ops.get_series_names()),
    )


@bp.route("/sources/import", methods=["POST"])
def sources_import_preview():
    """Bulk add, step 2: Claude's JSON reply -> editable preview rows (album
    browse ids resolved, duplicates flagged). Writes nothing."""
    raw = request.form.get("json", "")
    try:
        rows = file_ops.prepare_source_import(raw)
    except ValueError as exc:
        flash(str(exc), "error")
        return _render_sources(import_json=raw)
    return _render_sources(import_json=raw, import_rows=rows)


@bp.route("/sources/import/confirm", methods=["POST"])
def sources_import_confirm():
    """Bulk add, step 3: write the rows the curator kept checked in the
    preview - see file_ops.add_imported_sources()."""
    form = request.form
    rows = []
    for i in range(int(form.get("row_count", 0) or 0)):
        if form.get(f"include_{i}") != "on":
            continue
        row = {
            "youtube_id": form.get(f"youtube_id_{i}", "").strip(),
            "type": form.get(f"type_{i}", "").strip(),
            "label": form.get(f"label_{i}", "").strip(),
            "series": form.get(f"series_{i}", "").strip(),
            "language": form.get(f"language_{i}", "").strip() or "de",
        }
        if row["type"] not in SOURCE_TYPES or not row["youtube_id"] or not row["label"]:
            flash(f"Skipped a row with a missing type/id/label ({row['youtube_id'] or 'no id'}).", "error")
            continue
        rows.append(row)
    if not rows:
        flash("Nothing selected to import.", "error")
        return redirect(url_for("admin.sources"))

    report = file_ops.add_imported_sources(rows)
    flash(f"Added {len(report['added'])} source(s) to sources.py.", "success")
    if report["skipped"]:
        flash(f"Skipped id(s) already in sources.py: {', '.join(report['skipped'])}", "error")
    return redirect(url_for("admin.sources"))


@bp.route("/sources/add", methods=["POST"])
def sources_add():
    entry = {
        "type": request.form.get("type", "").strip(),
        "youtube_id": file_ops.extract_youtube_id(request.form.get("youtube_id", "")),
        "label": request.form.get("label", "").strip(),
        "language": request.form.get("language", "de").strip() or "de",
        "active": request.form.get("active") == "on",
    }
    if entry["youtube_id"].startswith("MPREb_"):
        resolved = file_ops.resolve_album_browse_id(entry["youtube_id"])
        if not resolved:
            flash("Couldn't resolve that YouTube Music album link to a playlist id - use the album's Share link instead.", "error")
            return redirect(url_for("admin.sources"))
        entry["youtube_id"] = resolved
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


@bp.route("/sources/<path:youtube_id>", methods=["POST"])
def sources_action(youtube_id):
    action = request.form.get("action")
    if action == "update":
        fields = {
            "type": request.form.get("type", "").strip(),
            "label": request.form.get("label", "").strip(),
            "active": request.form.get("active") == "on",
        }
        if fields["type"] not in SOURCE_TYPES or not fields["label"]:
            flash("Type and label are required.", "error")
            return redirect(url_for("admin.sources"))
        try:
            file_ops.update_source(youtube_id, fields)
        except ValueError as exc:
            flash(f"Could not update source: {exc}", "error")
            return redirect(url_for("admin.sources"))
        flash(f"Updated {fields['label']!r}.", "success")
    elif action == "remove":
        try:
            file_ops.remove_source(youtube_id)
        except ValueError as exc:
            flash(f"Could not remove source: {exc}", "error")
            return redirect(url_for("admin.sources"))
        flash(f"Removed {youtube_id!r} from sources.py.", "success")
    return redirect(url_for("admin.sources"))


_WARNING_DISMISS_REDIRECTS = {
    "suggestions": "admin.suggestions", "catalog": "admin.catalog",
    "sources": "admin.sources", "values": "admin.values",
}


@bp.route("/warnings/dismiss", methods=["POST"])
def warnings_dismiss():
    """Shared by every screen with a consistency/source/tile warning box
    (Suggestions, Sources, Values) - `screen` picks which page to redirect
    back to, `warning` is the exact warning text to ignore (see
    file_ops.dismiss_warning())."""
    warning = request.form.get("warning", "")
    screen = request.form.get("screen", "")
    endpoint = _WARNING_DISMISS_REDIRECTS.get(screen, "admin.sources")
    if warning:
        file_ops.dismiss_warning(warning)
        flash("Warning ignored - it won't be shown again unless it changes.", "success")
    return redirect(url_for(endpoint))


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
    if request.form.get("skip_claude") == "on":
        flags.append("--skip-claude")

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
    return render_template(
        "values.html",
        lists=lists,
        list_config=file_ops.VALUE_LIST_CONFIG,
        tile_thumbnail_warnings=file_ops.get_tile_thumbnail_warnings(),
        tile_thumbnails=file_ops.get_tile_thumbnails(),
        tile_categories=file_ops.get_tile_categories(),
        tile_value_options=file_ops.get_tile_value_options(),
        hidden_tiles=file_ops.get_hidden_tiles(),
    )


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


@bp.route("/values/tile-thumbnails", methods=["POST"])
def tile_thumbnails_set():
    category = request.form.get("category", "")
    value = request.form.get("value", "")
    url = request.form.get("url", "")
    hidden = request.form.get("hidden") == "on"

    try:
        file_ops.set_tile_thumbnail(category, value, url)
        file_ops.set_tile_hidden(category, value, hidden)
    except ValueError as exc:
        flash(f"Could not save tile: {exc}", "error")
        return redirect(url_for("admin.values"))

    if value.strip():
        flash(f"Saved tile {category!r}:{value.strip()!r}.", "success")
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


@bp.app_template_global()
def series_anchor(name: str) -> str:
    """`#series-<anchor>` link target on the Series screen, for templates."""
    return file_ops.series_anchor(name)


def _editor_context(series_overrides: dict) -> dict:
    """Template values every screen with item edit forms (Review, Catalog)
    needs for field_grid() and the series-lock script."""
    return {
        "genre_values": file_ops.get_genre_values(),
        "franchise_values": file_ops.get_franchise_values(),
        "seasonal_values": file_ops.get_seasonal_values(),
        "variant_values": file_ops.get_variant_values(),
        "series_overrides": series_overrides,
        "series_names": file_ops.get_series_names(),
    }


@bp.route("/suggestions")
def suggestions():
    """Review screen: pending Claude suggestions (one card at a time by
    default) plus the two Claude.ai prompt builders. Applied overrides live
    on the Catalog screen, series-level metadata on the Series screen."""
    suggestions_data = file_ops.load_suggestions()
    overrides_data = file_ops.list_overrides()
    item_info = file_ops.get_item_info()
    consistency_warnings = file_ops.get_consistency_warnings()
    series_overrides = file_ops.list_series_overrides()
    return render_template(
        "suggestions.html",
        # Consistency-warning-flagged cards come first - see
        # order_by_consistency_warnings()'s own docstring.
        suggestions=file_ops.order_by_consistency_warnings(suggestions_data, consistency_warnings),
        warning_count=len(consistency_warnings),
        item_info=item_info,
        description_prompt=file_ops.build_description_prompt(suggestions_data, overrides_data, item_info),
        metadata_prompts=file_ops.build_metadata_prompts(
            suggestions_data, overrides_data, item_info, series_overrides
        ),
        **_editor_context(series_overrides),
    )


@bp.route("/catalog")
def catalog():
    """Catalog screen: every applied override as a filterable table (see
    file_ops.build_catalog_rows()), with a summary bar, grouped consistency
    warnings, per-row editors and bulk actions."""
    suggestions_data = file_ops.load_suggestions()
    overrides_data = file_ops.list_overrides()
    item_info = file_ops.get_item_info()
    warning_groups = file_ops.get_grouped_consistency_warnings()
    consistency_warnings = [pair for _, pairs in warning_groups for pair in pairs]
    series_overrides = file_ops.list_series_overrides()
    diffs = _compute_override_diffs(overrides_data, suggestions_data)
    # A warning's "Jump to" link: same-page anchor for an applied item, the
    # Review screen's card for one that only exists as a pending suggestion.
    warning_links = {}
    for _, entry_ids in consistency_warnings:
        for entry_id in entry_ids:
            warning_links[entry_id] = (
                f"#entry-{entry_id}" if entry_id in overrides_data
                else url_for("admin.suggestions", _anchor=f"entry-{entry_id}")
            )
    rows = file_ops.build_catalog_rows(overrides_data, item_info, series_overrides, consistency_warnings, diffs)
    summary = {
        "total": len(rows),
        "complete": sum(1 for r in rows if not (r["missing"] or r["warnings"] or r["diff_count"])),
        "missing": {
            field: sum(1 for r in rows if field in r["missing"])
            for field in ("description", "min_age", "genre", "source_release_year")
        },
        "warning": sum(1 for r in rows if r["warnings"]),
        "diff": sum(1 for r in rows if r["diff_count"]),
    }
    return render_template(
        "catalog.html",
        overrides=overrides_data,
        diffs=diffs,
        catalog_rows=rows,
        summary=summary,
        warning_groups=warning_groups,
        warning_links=warning_links,
        pending_count=len(suggestions_data),
        item_info=item_info,
        **_editor_context(series_overrides),
    )


CATALOG_BULK_ACTIONS = ("set_series", "clear_series", "number_positions", "set_seasonal", "set_variant")


@bp.route("/catalog/bulk", methods=["POST"])
def catalog_bulk():
    """Catalog screen bulk actions on the selected rows. `entry_ids` is a
    JSON list in the table's current visible order - that order is what
    number_positions numbers by."""
    try:
        entry_ids = [str(e) for e in json.loads(request.form.get("entry_ids") or "[]")]
    except ValueError:
        entry_ids = []
    known = file_ops.list_overrides()
    entry_ids = [e for e in entry_ids if e in known]
    action = request.form.get("action", "")
    if not entry_ids or action not in CATALOG_BULK_ACTIONS:
        flash("Select at least one row and an action.", "error")
        return redirect(url_for("admin.catalog"))

    if action == "set_series":
        name = request.form.get("series", "").strip()
        if not name:
            flash("Enter a series name to assign.", "error")
            return redirect(url_for("admin.catalog"))
        for entry_id in entry_ids:
            file_ops.apply_override(entry_id, {"series": name})
        flash(f"Assigned {len(entry_ids)} item(s) to series {name!r}.", "success")
    elif action == "clear_series":
        for entry_id in entry_ids:
            file_ops.remove_override_fields(entry_id, ("series", "position_in_series"))
        flash(f"Removed series and position from {len(entry_ids)} item(s).", "success")
    elif action == "number_positions":
        try:
            start = int(request.form.get("start") or 1)
        except ValueError:
            start = 1
        for offset, entry_id in enumerate(entry_ids):
            file_ops.apply_override(entry_id, {"position_in_series": start + offset})
        flash(f"Numbered {len(entry_ids)} item(s) {start}-{start + len(entry_ids) - 1} in table order.", "success")
    elif action == "set_seasonal":
        value = request.form.get("seasonal", "").strip()
        if value and value not in file_ops.get_seasonal_values():
            flash(f"Unknown seasonal value {value!r}.", "error")
            return redirect(url_for("admin.catalog"))
        for entry_id in entry_ids:
            if value:
                file_ops.apply_override(entry_id, {"seasonal": value})
            else:
                file_ops.remove_override_fields(entry_id, ("seasonal",))
        what = f"Set seasonal to {value!r}" if value else "Cleared seasonal"
        flash(f"{what} on {len(entry_ids)} item(s).", "success")
    elif action == "set_variant":
        value = request.form.get("variant", "").strip()
        if value and value not in file_ops.get_variant_values():
            flash(f"Unknown variant {value!r}.", "error")
            return redirect(url_for("admin.catalog"))
        for entry_id in entry_ids:
            if value:
                file_ops.apply_override(entry_id, {"variant": value})
            else:
                file_ops.remove_override_fields(entry_id, ("variant",))
        what = f"Marked as {value!r}" if value else "Moved back to the main line"
        flash(f"{what}: {len(entry_ids)} item(s).", "success")
    return redirect(url_for("admin.catalog"))


@bp.route("/series")
def series():
    """Series screen: every series (with or without a SERIES_OVERRIDES
    entry), its members and their positions - see file_ops.build_series_rows()."""
    return render_template(
        "series.html",
        series_rows=file_ops.build_series_rows(
            file_ops.list_overrides(), file_ops.list_series_overrides(), file_ops.get_item_info()
        ),
        genre_values=file_ops.get_genre_values(),
        franchise_values=file_ops.get_franchise_values(),
    )


def _series_redirect(name: str):
    return redirect(url_for("admin.series", _anchor=f"series-{file_ops.series_anchor(name)}"))


@bp.route("/series/<path:series_name>/save", methods=["POST"])
def series_save(series_name):
    """Create or update a series entry. Authoritative: blank fields are
    removed from the entry (see file_ops.save_series_override()). On create,
    `strip_members` also removes the members' own now-ignored
    genre/franchise/min_age."""
    existed = series_name in file_ops.list_series_overrides()
    fields = _parse_series_override_form(request.form)
    if not any(v not in (None, "", []) for v in fields.values()):
        flash("Nothing to save - set at least one field.", "error")
        return _series_redirect(series_name)
    try:
        file_ops.save_series_override(series_name, fields)
    except ValueError as exc:
        flash(f"Could not save series metadata: {exc}", "error")
        return _series_redirect(series_name)
    message = f"{'Updated' if existed else 'Created'} series entry for {series_name!r}."
    if not existed and request.form.get("strip_members") == "on":
        stripped = file_ops.strip_series_resolved_fields(series_name)
        message += f" Removed now-redundant genre/franchise/min age from {stripped} member(s)."
    flash(message, "success")
    return _series_redirect(series_name)


@bp.route("/series/<path:series_name>/positions", methods=["POST"])
def series_positions(series_name):
    """Save every member's position at once. A blank field clears that
    member's position."""
    overrides = file_ops.list_overrides()
    changed = 0
    for key, raw in request.form.items():
        if not key.startswith("pos_"):
            continue
        entry_id, raw = key[4:], raw.strip()
        if entry_id not in overrides:
            continue
        current = overrides[entry_id].get("position_in_series")
        if raw == "":
            if current is not None:
                file_ops.remove_override_fields(entry_id, ("position_in_series",))
                changed += 1
            continue
        try:
            value = int(raw)
        except ValueError:
            flash(f"Skipped non-numeric position {raw!r}.", "error")
            continue
        if value != current:
            file_ops.apply_override(entry_id, {"position_in_series": value})
            changed += 1
    flash(f"Updated {changed} position(s) in {series_name!r}.", "success")
    return _series_redirect(series_name)


@bp.route("/series/<path:series_name>/rename", methods=["POST"])
def series_rename(series_name):
    new_name = request.form.get("new_name", "").strip()
    try:
        count = file_ops.rename_series(series_name, new_name)
    except ValueError as exc:
        flash(str(exc), "error")
        return _series_redirect(series_name)
    flash(f"Renamed {series_name!r} to {new_name!r} ({count} item(s) updated).", "success")
    return _series_redirect(new_name)


@bp.route("/series/<path:series_name>/remove", methods=["POST"])
def series_remove(series_name):
    try:
        count = file_ops.remove_series_override(series_name)
    except ValueError as exc:
        flash(str(exc), "error")
        return _series_redirect(series_name)
    flash(
        f"Removed the series entry for {series_name!r}; its genre/franchise/min age were copied onto "
        f"{count} member(s).",
        "success",
    )
    return _series_redirect(series_name)


@bp.route("/suggestions/import", methods=["POST"])
def suggestions_import():
    """Paste-back half of the Metadata prompt builder - see
    file_ops.import_metadata_suggestions(). Only ever writes to
    data/claude_suggestions.json; every imported value still has to be
    applied card by card."""
    raw = request.form.get("json", "")
    if not raw.strip():
        flash("Paste Claude's JSON reply first.", "error")
        return redirect(url_for("admin.suggestions"))
    try:
        report = file_ops.import_metadata_suggestions(raw)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("admin.suggestions"))

    flash(f"Imported {len(report['imported'])} suggestion(s) - review and apply them below.", "success")
    if report["unknown"]:
        flash(f"Skipped unknown id(s): {', '.join(report['unknown'])}", "error")
    if report["invalid"]:
        flash(f"Skipped malformed entr(ies): {', '.join(report['invalid'])}", "error")
    if report["description_title_words"]:
        flash(
            "Kept, but please check - description reuses words from the title: "
            + "; ".join(report["description_title_words"]),
            "error",
        )
    return redirect(url_for("admin.suggestions"))


def _parse_series_override_form(form) -> dict:
    fields = {}
    for name in SERIES_OVERRIDE_FIELDS:
        if name == "genre":
            # A <select multiple> - see the same special case in
            # _parse_suggestion_form().
            fields[name] = form.getlist("genre")
            continue
        raw = form.get(name, "").strip()
        if not raw:
            fields[name] = None
            continue
        if name in SERIES_OVERRIDE_INT_FIELDS:
            try:
                fields[name] = int(raw)
            except ValueError:
                fields[name] = None
        else:
            fields[name] = raw
    return fields


@bp.route("/series-overrides/add", methods=["POST"])
def series_overrides_add():
    name = request.form.get("series", "").strip()
    if not name:
        flash("Series name is required.", "error")
        return redirect(url_for("admin.series"))
    fields = _parse_series_override_form(request.form)
    try:
        file_ops.apply_series_override(name, fields)
    except ValueError as exc:
        flash(f"Could not add series metadata: {exc}", "error")
        return redirect(url_for("admin.series"))
    flash(f"Added series metadata for {name!r}.", "success")
    return _series_redirect(name)


@bp.route("/series-overrides/<path:series_name>", methods=["POST"])
def series_overrides_action(series_name):
    fields = _parse_series_override_form(request.form)
    try:
        file_ops.apply_series_override(series_name, fields)
    except ValueError as exc:
        flash(f"Could not update series metadata: {exc}", "error")
        return _series_redirect(series_name)
    flash(f"Updated series metadata for {series_name!r}.", "success")
    return _series_redirect(series_name)


def _parse_suggestion_form(form) -> dict:
    """Raises InvalidAwardsJSON if the awards textarea doesn't parse as a
    JSON array - callers should catch it and flash an error rather than
    letting a typo silently turn into an empty/dropped awards field."""
    fields = {}
    for name in SUGGESTION_FIELDS:
        if name == "genre":
            # A <select multiple> - form.get() would only ever return the
            # first selected value, so this needs getlist() instead of the
            # generic raw = form.get(...) every other field uses below.
            fields[name] = form.getlist("genre")
            continue
        raw = form.get(name, "").strip()
        if name == "series":
            # The Series field is a "pick an existing one, or add a new
            # one" picker (see field_grid() in suggestions.html) - a
            # "__new__" selection means the real value lives in the
            # companion `series_new` text input instead.
            if raw == "__new__":
                raw = form.get("series_new", "").strip()
            fields[name] = raw or None
            continue
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
        return redirect(request.referrer or url_for("admin.suggestions"))
    # The fresh suggestion lands in the Review queue - go to its card.
    return redirect(url_for("admin.suggestions", _anchor=f"entry-{entry_id}"))


@bp.route("/suggestions/<path:entry_id>", methods=["POST"])
def suggestions_action(entry_id):
    """Handles Apply/Apply & Next/Save/Save & Next/Dismiss for one card.
    `section` ("suggestion" or "override", a hidden field on every card's
    form) tells get_next_entry_id() which on-screen list to look in - the
    "& Next" actions (and Dismiss, which always removes the item from view)
    redirect to that next card's own #entry-<id> anchor instead of the page
    top, so working through many items in a row doesn't mean re-scrolling
    past everything already done each time; a plain Apply/Save redirects
    back to this same card's anchor instead, for a quick review-and-fix
    loop on one item. Both anchors gracefully fall back to no anchor (the
    page top) if there's nothing to point at (last item in the list, or -
    for the error path below - genuinely nowhere better to go)."""
    action = request.form.get("action")
    section = request.form.get("section", "suggestion")
    # The Applied overrides table sends the next *visible* row's id (its
    # own client-side filter/sort order), which is what "Next" should mean
    # there; fall back to the server-side order otherwise.
    next_entry_id = request.form.get("next_entry_id", "").strip() or file_ops.get_next_entry_id(section, entry_id)

    # Applied-override edits come from the Catalog screen, pending
    # suggestions from Review - go back to whichever one the form was on.
    screen = "admin.catalog" if section == "override" else "admin.suggestions"

    def redirect_to(target_entry_id):
        if target_entry_id:
            return redirect(url_for(screen, _anchor=f"entry-{target_entry_id}"))
        return redirect(url_for(screen))

    if action in ("apply", "apply_next"):
        try:
            fields = _parse_suggestion_form(request.form)
        except InvalidAwardsJSON as exc:
            flash(f"Could not parse the awards field as JSON ({exc}) - fix it and try again.", "error")
            return redirect_to(entry_id)
        file_ops.apply_override(entry_id, fields)
        was_pending = entry_id in file_ops.load_suggestions()
        file_ops.dismiss_suggestion(entry_id)
        if was_pending:
            flash("Applied to overrides.py and removed from the review queue.", "success")
        else:
            flash("Saved changes to overrides.py.", "success")
        return redirect_to(next_entry_id if action == "apply_next" else entry_id)
    elif action == "dismiss":
        file_ops.dismiss_suggestion(entry_id)
        flash("Dismissed - nothing was written to overrides.py.", "success")
        return redirect_to(next_entry_id)
    return redirect(url_for("admin.suggestions"))
