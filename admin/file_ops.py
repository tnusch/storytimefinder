"""
Local-only file surgery for the admin tool: read/write refresh/sources.py,
refresh/overrides.py, and data/claude_suggestions.json without a full
parse+rewrite of the Python files.

A full round-trip through Python's `ast` module would parse fine but
*cannot* reproduce comments on write (ast doesn't track them at all), which
would destroy the hand-written per-field comments and per-entry title
comments those two files rely on (see their own docstrings). Instead this
uses the same targeted regex-insertion approach `refresh/generate_overrides_stubs.py`
already established: find a well-known anchor or existing block by text
pattern, and only ever touch the specific lines being changed - everything
else in the file passes through completely untouched.

Never imported by app/ or refresh/ - this module (and the rest of admin/)
is admin-only tooling, never deployed. See admin/__init__.py.
"""

from __future__ import annotations

import importlib
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REFRESH_DIR = ROOT / "refresh"
SOURCES_PATH = REFRESH_DIR / "sources.py"
OVERRIDES_PATH = REFRESH_DIR / "overrides.py"
SUGGESTIONS_PATH = ROOT / "data" / "claude_suggestions.json"
FETCHED_ITEMS_PATH = ROOT / "data" / "fetched_items.json"
DISMISSED_WARNINGS_PATH = ROOT / "data" / "dismissed_warnings.json"

if str(REFRESH_DIR) not in sys.path:
    sys.path.insert(0, str(REFRESH_DIR))


def _reload(name: str):
    """Import (or re-import) a refresh/ module fresh, so edits made via this
    tool - or by hand, in an editor, between requests - are always reflected.
    This is a long-running dev server process, not a one-shot script, so the
    default import-once caching would otherwise serve stale data."""
    if name in sys.modules:
        importlib.reload(sys.modules[name])
    else:
        importlib.import_module(name)
    return sys.modules[name]


def list_sources() -> list[dict]:
    return list(_reload("sources").SOURCES)


def list_overrides() -> dict:
    return dict(_reload("overrides").ITEM_OVERRIDES)


def list_series_overrides() -> dict:
    """overrides.py's SERIES_OVERRIDES - series-level series_type/genre/
    franchise/mood/min_age for an episodic series, keyed by series name
    (not an entry id). Editable via apply_series_override() below (the
    Suggestions screen's "Episodic series metadata" section). Also used by
    get_consistency_warnings() to make check_missing_fields() aware of
    which items are covered by a series-level entry instead of their own."""
    return dict(_reload("overrides").SERIES_OVERRIDES)


def get_series_names() -> list[str]:
    """Every distinct series name currently in use - the union of every
    ITEM_OVERRIDES entry's `series` value and every SERIES_OVERRIDES key
    (a series can exist in SERIES_OVERRIDES before any item actually
    references it yet, e.g. right after adding it via the admin UI).
    Powers the Suggestions screen's "pick an existing series, or add a new
    one" picker for the per-item `series` field."""
    overrides = list_overrides()
    from_items = {o.get("series") for o in overrides.values() if o.get("series")}
    from_series_overrides = set(list_series_overrides().keys())
    return sorted(from_items | from_series_overrides)


# Each fixed vocabulary refresh.py validates overrides against - see
# overrides.py's docstring for what each is used for. "const" is the name of
# the module-level set in refresh.py; "i18n_prefix" is the translation key
# prefix (app/i18n.py's "<prefix>_<slug>" keys) a new value also needs so it
# displays as a real label instead of its raw slug - None for "award",
# since award NAMES are shown as-is, not translated through a slug.
VALUE_LIST_CONFIG = {
    "genre": {"const": "GENRE_VALUES", "i18n_prefix": "genre"},
    "franchise": {"const": "FRANCHISE_VALUES", "i18n_prefix": "franchise"},
    "mood": {"const": "MOOD_VALUES", "i18n_prefix": "mood"},
    "seasonal": {"const": "SEASONAL_VALUES", "i18n_prefix": "seasonal"},
    "award": {"const": "AWARD_VALUES", "i18n_prefix": None},
}
SLUG_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def get_value_list(list_name: str) -> list[str]:
    const_name = VALUE_LIST_CONFIG[list_name]["const"]
    return sorted(getattr(_reload("refresh"), const_name))


def get_genre_values() -> list[str]:
    return get_value_list("genre")


def get_franchise_values() -> list[str]:
    return get_value_list("franchise")


def get_mood_values() -> list[str]:
    return get_value_list("mood")


def get_seasonal_values() -> list[str]:
    return get_value_list("seasonal")


def get_award_values() -> list[str]:
    return get_value_list("award")


def _load_fetched_items() -> dict:
    if not FETCHED_ITEMS_PATH.exists():
        return {"sources": {}, "items": {}}
    try:
        data = json.loads(FETCHED_ITEMS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"sources": {}, "items": {}}
    data.setdefault("items", {})
    data.setdefault("sources", {})
    return data


def get_item_info() -> dict[str, dict]:
    """entry_id (video/album id) -> {"title": ..., "thumbnail_url": ...,
    "youtube_music_url": ...}, best-effort - used only to illustrate
    overrides.py entries and pending suggestions in the admin UI (e.g. a
    direct "open on YouTube Music" link per item), never to decide what
    gets written anywhere.

    Merges two sources: data/fetched_items.json's staged items (covers a
    brand-new item that has a suggestion but hasn't been synced yet) and
    storytimefinder.db's items table (covers anything already synced, which
    by then has usually been pruned out of fetched_items.json - see
    refresh.py's sync_source()). The DB is read second so it wins if both
    somehow have an entry for the same id. Either or both can be empty/
    missing (e.g. right after --clean-fetched/--clean-db, or before the
    first sync ever) - callers should treat a missing id as "no title/image/
    link available" rather than an error. `youtube_music_url` itself is
    already the fully-formed watch/playlist URL (built once, in
    refresh.py's build_track_entries()/build_album_entry(), or read
    straight off the DB column) - nothing here needs to guess whether an
    id is a video or an album/playlist id to construct it.
    """
    info: dict[str, dict] = {}
    for entry_id, item in _load_fetched_items()["items"].items():
        info[entry_id] = {
            "title": item.get("title"),
            "thumbnail_url": item.get("thumbnail_url"),
            "youtube_music_url": item.get("youtube_music_url"),
        }

    db_path = _reload("refresh").DB_PATH
    if Path(db_path).exists():
        conn = sqlite3.connect(db_path)
        try:
            rows = conn.execute("SELECT video_id, title, thumbnail_url, youtube_music_url FROM items").fetchall()
            for video_id, title, thumbnail_url, youtube_music_url in rows:
                info[video_id] = {
                    "title": title,
                    "thumbnail_url": thumbnail_url,
                    "youtube_music_url": youtube_music_url,
                }
        except sqlite3.OperationalError:
            pass
        finally:
            conn.close()
    return info


def load_dismissed_warnings() -> dict:
    """{warning_text: {"dismissed_at": ...}} - a human clicking "Ignore" on
    any consistency/source warning (see get_consistency_warnings()/
    get_source_warnings() below) writes here via dismiss_warning();
    nothing else ever writes to this file. Warnings are matched by their
    exact rendered text, not a stable id (none of the check functions
    produce one) - deliberate: if the underlying data changes enough that
    a warning's text changes too (e.g. a new id joins an existing
    duplicate-title group), that's a materially different situation and
    should resurface rather than staying silently ignored under the old
    wording. A warning that stops being generated at all (the issue got
    fixed) simply leaves its entry here unused - harmless, never pruned,
    same "permanent, no undo" shape as declined_sources.json's decline
    list."""
    if not DISMISSED_WARNINGS_PATH.exists():
        return {}
    try:
        return json.loads(DISMISSED_WARNINGS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_dismissed_warnings(dismissed: dict) -> None:
    DISMISSED_WARNINGS_PATH.write_text(
        json.dumps(dismissed, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )


def dismiss_warning(warning_text: str) -> None:
    """Ignore one warning by its exact text - it's filtered out of
    get_consistency_warnings()/get_source_warnings() from now on, on every
    screen that surfaces it, since both draw from this same shared
    dismissed-set rather than a per-screen one (the two checks' warning
    texts are never expected to collide)."""
    dismissed = load_dismissed_warnings()
    dismissed[warning_text] = {"dismissed_at": datetime.now(timezone.utc).isoformat()}
    save_dismissed_warnings(dismissed)


def _filter_dismissed(warnings: list[str]) -> list[str]:
    dismissed = load_dismissed_warnings()
    return [w for w in warnings if w not in dismissed]


def get_consistency_warnings() -> list[str]:
    """Runs three independent curation-consistency checks (all pure
    functions in refresh.py, see their own docstrings) directly against the
    current ITEM_OVERRIDES plus known item titles, so they show up on the
    Suggestions screen immediately as you edit overrides.py, without
    needing a --sync first:
      - series consistency - items sharing a `series` disagreeing on
        genre/franchise/mood/seasonal, or two items claiming the same
        position_in_series (check_overrides_series_consistency()).
      - duplicate titles - two different entry ids with the exact same
        title AND the same source_release_year (including both unset) -
        a known, differing release year (e.g. two separate film
        adaptations sharing a title) is not flagged (check_duplicate_titles()).
      - missing core fields - a known item whose override is missing
        description/min_age/genre/mood/source_release_year, including an
        item with no override entry at all - except genre/mood/min_age on
        an item belonging to an episodic series, which are satisfied by
        that series' SERIES_OVERRIDES entry instead (check_missing_fields()).
    Individually-ignored warnings (see dismiss_warning()) are filtered out
    before returning.
    """
    overrides = list_overrides()
    series_overrides = list_series_overrides()
    titles = {entry_id: info["title"] for entry_id, info in get_item_info().items() if info.get("title")}
    release_years = {entry_id: o.get("source_release_year") for entry_id, o in overrides.items()}
    refresh = _reload("refresh")
    warnings = (
        refresh.check_overrides_series_consistency(overrides, titles)
        + refresh.check_duplicate_titles(titles, release_years)
        + refresh.check_missing_fields(overrides, titles, series_overrides)
    )
    return _filter_dismissed(warnings)


def get_source_warnings() -> list[str]:
    """Runs refresh.py's check_duplicate_source_ids() directly against
    sources.py's current SOURCES list, so a duplicate youtube_id (see
    sources.html's warning box) is flagged the moment it's introduced -
    whether by hand-editing sources.py or via the "Add a new source" form
    below - without needing a --sync first. Individually-ignored warnings
    (see dismiss_warning()) are filtered out before returning."""
    return _filter_dismissed(_reload("refresh").check_duplicate_source_ids(list_sources()))


def load_suggestions() -> dict:
    if not SUGGESTIONS_PATH.exists():
        return {}
    try:
        return json.loads(SUGGESTIONS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_suggestions(suggestions: dict) -> None:
    SUGGESTIONS_PATH.write_text(
        json.dumps(suggestions, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )


def dismiss_suggestion(entry_id: str) -> None:
    """Remove one suggestion from the review queue without applying it -
    e.g. because none of its fields are worth keeping."""
    suggestions = load_suggestions()
    suggestions.pop(entry_id, None)
    save_suggestions(suggestions)


def _py_literal(value) -> str:
    """Render a Python value as source text, matching the quoting style
    already used throughout sources.py/overrides.py (double-quoted
    strings, literal non-ASCII characters rather than escapes).

    list/dict (needed for `awards`, a list of {"name","category","year"}
    dicts) are always rendered on a single line, deliberately - FIELD_LINE_RE/
    _apply_fields_to_body() below only ever match/replace one field per
    source line, so a multi-line value would break the existing entry
    instead of updating it (the old multi-line block would pass through
    unrecognized and the new value would get appended as a duplicate key).
    Awards lists are short (usually 0-2 entries) so this stays readable."""
    if value is None:
        return "None"
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ", ".join(_py_literal(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{_py_literal(k)}: {_py_literal(v)}" for k, v in value.items()) + "}"
    raise TypeError(f"Unsupported literal value type: {type(value)!r}")


SOURCES_ANCHOR_RE = re.compile(r"SOURCES\s*=\s*\[")
SOURCE_FIELDS = ("type", "youtube_id", "label", "language", "active")


def add_source(entry: dict) -> None:
    """Append a new source dict to sources.py's SOURCES list, inserted right
    after the opening bracket - existing entries (including the commented
    placeholder ones) are left completely untouched."""
    missing = [key for key in SOURCE_FIELDS if key not in entry]
    if missing:
        raise ValueError(f"Missing required source field(s): {', '.join(missing)}")

    content = SOURCES_PATH.read_text(encoding="utf-8")
    anchor = SOURCES_ANCHOR_RE.search(content)
    if not anchor:
        raise RuntimeError("Could not find 'SOURCES = [' in sources.py")

    lines = ["    {"]
    for key in SOURCE_FIELDS:
        lines.append(f'        "{key}": {_py_literal(entry[key])},')
    lines.append("    },")
    block = "\n".join(lines) + "\n"

    new_content = content[: anchor.end()] + "\n" + block + content[anchor.end() :]
    SOURCES_PATH.write_text(new_content, encoding="utf-8")


# Matches one SOURCES entry block ("    {\n...\n    },\n" plus its trailing
# blank-line separator, if any) - same non-greedy "stop at the next closing
# brace" shape as OVERRIDES_ANCHOR_RE's entries, but sources.py's blocks
# aren't individually keyed in the text the way overrides.py's are (there's
# no `"<id>": {` header), so a block is identified by scanning its body for
# a matching "youtube_id" line instead of anchoring a regex on the id itself.
SOURCE_BLOCK_RE = re.compile(r"    \{\n(?:.*\n)*?    \},\n\n?")
SOURCE_EDITABLE_FIELDS = ("type", "label", "active")


def _find_source_block(content: str, youtube_id: str) -> re.Match | None:
    """Locate the SOURCES entry block for `youtube_id` - returns the
    re.Match, or None if no entry has that id. If more than one entry
    shares the id (see refresh.check_duplicate_source_ids() - now flagged
    as a Sources-screen warning rather than expected in normal operation),
    only the first block in file order is matched; resolve the rest by
    hand."""
    needle = f'"youtube_id": "{youtube_id}"'
    for match in SOURCE_BLOCK_RE.finditer(content):
        if needle in match.group():
            return match
    return None


def remove_source(youtube_id: str) -> None:
    """Delete one entry from sources.py's SOURCES list entirely.

    This only edits sources.py - it never touches storytimefinder.db or
    catalog.json. sync_sources() upserts the `sources` table by youtube_id
    but never deletes a row for an id that's disappeared from sources.py
    (there's nothing for it to notice - the id is just gone), so removing
    an entry here while its DB row is still `active` would strand that
    row's catalog item(s) forever, unrecoverable by any future --sync. To
    fully retire a source: set active to False here first, run --sync once
    (so export_catalog()'s `WHERE sources.active = 1` filter drops it from
    catalog.json), and only remove the entry afterward - or just leave it
    inactive rather than removing it. This dance is NOT needed when the id
    is a genuine duplicate of another still-present entry (see
    refresh.check_duplicate_source_ids()) - the single underlying DB row is
    addressed by youtube_id, not by which sources.py entry references it,
    so removing one of two duplicate entries is always safe.

    Raises ValueError if no entry with that youtube_id exists.
    """
    content = SOURCES_PATH.read_text(encoding="utf-8")
    match = _find_source_block(content, youtube_id)
    if match is None:
        raise ValueError(f"No source with youtube_id {youtube_id!r}")

    new_content = content[: match.start()] + content[match.end() :]
    SOURCES_PATH.write_text(new_content, encoding="utf-8")


def update_source(youtube_id: str, fields: dict) -> None:
    """Update an existing sources.py entry's type/label/active in place -
    youtube_id is the lookup key and isn't editable here (remove the entry
    and add a new one to fix a typo'd id). Only keys present in `fields`
    (expected: a subset of SOURCE_EDITABLE_FIELDS) are changed; anything
    else in the entry, including `language`, passes through untouched.
    Reuses _apply_fields_to_body() (built for overrides.py's entries) to do
    the actual line replacement - both files write one field per line in
    the same `"key": value,` shape, and that function only ever touches
    lines matching FIELD_LINE_RE, so the block's opening `{`/closing `},`
    lines pass through unchanged automatically.

    Raises ValueError if no entry with that youtube_id exists.
    """
    content = SOURCES_PATH.read_text(encoding="utf-8")
    match = _find_source_block(content, youtube_id)
    if match is None:
        raise ValueError(f"No source with youtube_id {youtube_id!r}")

    new_block = _apply_fields_to_body(match.group(), fields)
    new_content = content[: match.start()] + new_block + content[match.end() :]
    SOURCES_PATH.write_text(new_content, encoding="utf-8")


OVERRIDES_ANCHOR_RE = re.compile(r"ITEM_OVERRIDES:\s*dict\[str,\s*dict\]\s*=\s*\{")
FIELD_LINE_RE = re.compile(r'^(\s*)#?\s*"(\w+)":\s*.*?,\s*$')


def _entry_block_re(entry_id: str) -> re.Pattern:
    escaped = re.escape(entry_id)
    return re.compile(rf'(    "{escaped}": \{{[^\n]*\n)((?:.*\n)*?)(    \}},\n)')


def _apply_fields_to_body(body: str, fields: dict) -> str:
    """Rewrite an entry block's body, replacing the line for each field in
    `fields` (commented or not) with a live line carrying the new value.
    Any line for a field NOT in `fields` - including its comment-or-not
    state - passes through unchanged. Fields with no existing line at all
    are appended at the end of the block."""
    remaining = dict(fields)
    out_lines = []
    for line in body.splitlines():
        match = FIELD_LINE_RE.match(line)
        field_name = match.group(2) if match else None
        if field_name in remaining:
            out_lines.append(f'        "{field_name}": {_py_literal(remaining.pop(field_name))},')
        else:
            out_lines.append(line)
    for field_name, value in remaining.items():
        out_lines.append(f'        "{field_name}": {_py_literal(value)},')
    return "\n".join(out_lines) + "\n"


def apply_override(entry_id: str, fields: dict) -> None:
    """Write `fields` into overrides.py for `entry_id`: updates the matching
    line inside its existing entry block if there is one (uncommenting a
    placeholder or replacing a prior value - every other line in the block,
    and the rest of the file, is untouched), or creates a new block (right
    after ITEM_OVERRIDES's opening brace) if the item has no entry yet at
    all. Fields whose value is None, "", or [] are skipped entirely - they're
    left exactly as they already were rather than being explicitly set to
    None, so leaving a review field blank (or an unset awards list) never
    overwrites something a human already filled in by hand.
    """
    fields = {k: v for k, v in fields.items() if v not in (None, "", [])}
    if not fields:
        return

    content = OVERRIDES_PATH.read_text(encoding="utf-8")
    anchor = OVERRIDES_ANCHOR_RE.search(content)
    if not anchor:
        raise RuntimeError("Could not find 'ITEM_OVERRIDES: dict[str, dict] = {' in overrides.py")

    # Only search the dict's own body for an existing block, not the whole
    # file - the module docstring's illustrative example above the dict may
    # itself contain a real entry id (it does, for Findet Nemo) and would
    # otherwise be matched instead of the real ITEM_OVERRIDES entry.
    head, body_region = content[: anchor.end()], content[anchor.end() :]
    match = _entry_block_re(entry_id).search(body_region)

    if match:
        header, body, footer = match.group(1), match.group(2), match.group(3)
        new_block = header + _apply_fields_to_body(body, fields) + footer
        new_body_region = body_region[: match.start()] + new_block + body_region[match.end() :]
        new_content = head + new_body_region
    else:
        lines = [f'    "{entry_id}": {{']
        for key, value in fields.items():
            lines.append(f'        "{key}": {_py_literal(value)},')
        lines.append("    },")
        block = "\n".join(lines) + "\n"
        new_content = head + "\n" + block + body_region

    OVERRIDES_PATH.write_text(new_content, encoding="utf-8")


SERIES_OVERRIDES_ANCHOR_RE = re.compile(r"SERIES_OVERRIDES:\s*dict\[str,\s*dict\]\s*=\s*\{")


def apply_series_override(series_name: str, fields: dict) -> None:
    """Write `fields` into overrides.py's SERIES_OVERRIDES for
    `series_name` - same create-or-update behavior as apply_override()
    (reuses _entry_block_re()/_apply_fields_to_body(), since both dicts
    write one `"key": {...}` block per entry in the same shape, just
    keyed by series name here instead of entry id), and the same
    "blank fields are never written" rule: fields whose value is None,
    "", or [] are skipped entirely rather than overwriting something
    already curated by hand.

    Raises ValueError if `series_name` is blank.
    """
    series_name = series_name.strip()
    if not series_name:
        raise ValueError("Series name cannot be empty")

    fields = {k: v for k, v in fields.items() if v not in (None, "", [])}
    if not fields:
        return

    content = OVERRIDES_PATH.read_text(encoding="utf-8")
    anchor = SERIES_OVERRIDES_ANCHOR_RE.search(content)
    if not anchor:
        raise RuntimeError("Could not find 'SERIES_OVERRIDES: dict[str, dict] = {' in overrides.py")

    head, body_region = content[: anchor.end()], content[anchor.end() :]
    match = _entry_block_re(series_name).search(body_region)

    if match:
        header, body, footer = match.group(1), match.group(2), match.group(3)
        new_block = header + _apply_fields_to_body(body, fields) + footer
        new_body_region = body_region[: match.start()] + new_block + body_region[match.end() :]
        new_content = head + new_body_region
    else:
        lines = [f'    "{series_name}": {{']
        for key, value in fields.items():
            lines.append(f'        "{key}": {_py_literal(value)},')
        lines.append("    },")
        block = "\n".join(lines) + "\n"
        new_content = head + "\n" + block + body_region

    OVERRIDES_PATH.write_text(new_content, encoding="utf-8")


VALUE_LIST_ANCHOR_RES = {
    name: re.compile(rf'{cfg["const"]}\s*=\s*\{{') for name, cfg in VALUE_LIST_CONFIG.items()
}
I18N_LANG_ANCHOR_RES = {
    "de": re.compile(r'"de":\s*\{'),
    "en": re.compile(r'"en":\s*\{'),
}


def _add_i18n_labels(prefix: str, slug: str, label_de: str, label_en: str) -> None:
    """Insert a new "<prefix>_<slug>" translation key into both language
    blocks of app/i18n.py's TRANSLATIONS dict, right after each dict's
    opening brace - same targeted-insertion approach as everywhere else in
    this module, not a full parse/rewrite.

    `ROOT` is read fresh here (not a frozen path built at import time) so
    tests that repoint file_ops.ROOT at a scratch copy are respected - see
    admin/routes.py's _run_refresh_subprocess() for the same reasoning.
    """
    i18n_path = ROOT / "app" / "i18n.py"
    content = i18n_path.read_text(encoding="utf-8")
    for lang, label in (("de", label_de), ("en", label_en)):
        anchor = I18N_LANG_ANCHOR_RES[lang].search(content)
        if not anchor:
            raise RuntimeError(f'Could not find "{lang}": {{ in app/i18n.py')
        line = f'        "{prefix}_{slug}": {_py_literal(label)},\n'
        content = content[: anchor.end()] + "\n" + line + content[anchor.end() :]
    i18n_path.write_text(content, encoding="utf-8")


def add_value_list_entry(list_name: str, value: str, label_de: str | None = None, label_en: str | None = None) -> None:
    """Add a new value to one of refresh.py's fixed vocabularies
    (GENRE_VALUES/FRANCHISE_VALUES/MOOD_VALUES/SEASONAL_VALUES/AWARD_VALUES),
    plus - for the four slug-based lists, not `award` - a matching
    "<prefix>_<slug>" translation key in both app/i18n.py language blocks.
    Without the i18n step, a new genre/franchise/mood/seasonal slug would
    still work for filtering/validation but show its raw slug instead of a
    translated label everywhere it's displayed.

    Raises ValueError (caught by the route, flashed to the user) if
    `list_name` is unknown, `value` is blank or already present, a
    slug-based list's `value` isn't `SLUG_RE`-shaped, or either label is
    missing for a slug-based list. Everything is validated before either
    file is touched, so a rejected submission never leaves refresh.py and
    app/i18n.py out of sync with each other.
    """
    if list_name not in VALUE_LIST_CONFIG:
        raise ValueError(f"Unknown value list: {list_name!r}")
    cfg = VALUE_LIST_CONFIG[list_name]

    value = value.strip()
    if not value:
        raise ValueError("Value cannot be empty")
    if value in get_value_list(list_name):
        raise ValueError(f"{value!r} is already in {cfg['const']}")

    if cfg["i18n_prefix"]:
        if not SLUG_RE.match(value):
            raise ValueError("Must be lowercase letters, digits, and underscores only, starting with a letter")
        label_de = (label_de or "").strip()
        label_en = (label_en or "").strip()
        if not label_de or not label_en:
            raise ValueError("Both a German and English label are required for this list")

    refresh_path = REFRESH_DIR / "refresh.py"
    content = refresh_path.read_text(encoding="utf-8")
    anchor = VALUE_LIST_ANCHOR_RES[list_name].search(content)
    if not anchor:
        raise RuntimeError(f"Could not find '{cfg['const']} = {{' in refresh.py")
    new_content = content[: anchor.end()] + "\n" + f"    {_py_literal(value)},\n" + content[anchor.end() :]
    refresh_path.write_text(new_content, encoding="utf-8")

    if cfg["i18n_prefix"]:
        _add_i18n_labels(cfg["i18n_prefix"], value, label_de, label_en)
