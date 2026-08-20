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
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REFRESH_DIR = ROOT / "refresh"
SOURCES_PATH = REFRESH_DIR / "sources.py"
OVERRIDES_PATH = REFRESH_DIR / "overrides.py"
SUGGESTIONS_PATH = ROOT / "data" / "claude_suggestions.json"
FETCHED_ITEMS_PATH = ROOT / "data" / "fetched_items.json"

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
    """entry_id (video/album id) -> {"title": ..., "thumbnail_url": ...},
    best-effort - used only to illustrate overrides.py entries and pending
    suggestions in the admin UI, never to decide what gets written anywhere.

    Merges two sources: data/fetched_items.json's staged items (covers a
    brand-new item that has a suggestion but hasn't been synced yet) and
    storytimefinder.db's items table (covers anything already synced, which
    by then has usually been pruned out of fetched_items.json - see
    refresh.py's sync_source()). The DB is read second so it wins if both
    somehow have an entry for the same id. Either or both can be empty/
    missing (e.g. right after --clean-fetched/--clean-db, or before the
    first sync ever) - callers should treat a missing id as "no title/image
    available" rather than an error.
    """
    info: dict[str, dict] = {}
    for entry_id, item in _load_fetched_items()["items"].items():
        info[entry_id] = {"title": item.get("title"), "thumbnail_url": item.get("thumbnail_url")}

    db_path = _reload("refresh").DB_PATH
    if Path(db_path).exists():
        conn = sqlite3.connect(db_path)
        try:
            rows = conn.execute("SELECT video_id, title, thumbnail_url FROM items").fetchall()
            for video_id, title, thumbnail_url in rows:
                info[video_id] = {"title": title, "thumbnail_url": thumbnail_url}
        except sqlite3.OperationalError:
            pass
        finally:
            conn.close()
    return info


def get_series_consistency_warnings() -> list[str]:
    """Runs refresh.py's series consistency check (same two rules as
    overrides.py's own docstring: items sharing a `series` disagreeing on
    genre/franchise/mood/seasonal, or two items claiming the same
    position_in_series) directly against the current ITEM_OVERRIDES, via
    check_overrides_series_consistency() - so these show up on the
    Suggestions screen immediately as you edit overrides.py, without
    needing a --sync first the way the CLI's own version (run during
    --sync, logged to the console) does."""
    overrides = list_overrides()
    titles = {entry_id: info["title"] for entry_id, info in get_item_info().items() if info.get("title")}
    return _reload("refresh").check_overrides_series_consistency(overrides, titles)


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
