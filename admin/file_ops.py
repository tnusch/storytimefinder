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
is admin-only tooling, never deployed. See admin/__init__.py. The reverse
does happen once, deliberately: get_tile_thumbnail_warnings() below imports
app.data (a narrow, one-directional exception) to reuse its tile-thumbnail
fallback detection against data/catalog.json rather than duplicating it -
this doesn't affect the "never imported by app/" guarantee above.
"""

from __future__ import annotations

import importlib
import json
import re
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REFRESH_DIR = ROOT / "refresh"
SOURCES_PATH = REFRESH_DIR / "sources.py"
OVERRIDES_PATH = REFRESH_DIR / "overrides.py"
TILE_THUMBNAILS_PATH = ROOT / "app" / "tile_thumbnails.py"
HIDDEN_TILES_PATH = ROOT / "app" / "hidden_tiles.py"
SUGGESTIONS_PATH = ROOT / "data" / "claude_suggestions.json"
FETCHED_ITEMS_PATH = ROOT / "data" / "fetched_items.json"
DISMISSED_WARNINGS_PATH = ROOT / "data" / "dismissed_warnings.json"

if str(REFRESH_DIR) not in sys.path:
    sys.path.insert(0, str(REFRESH_DIR))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


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
    franchise/min_age for a series (any series_type), keyed by series name
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


def get_variant_values() -> list[str]:
    """refresh.py's VARIANT_VALUES - a closed 2-value enum (remake,
    spin_off), deliberately not part of the Values screen's editable lists,
    same as SERIES_TYPE_VALUES."""
    return sorted(_reload("refresh").VARIANT_VALUES)


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
    "youtube_music_url": ..., "language": ...}, best-effort - used only to illustrate
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
    source_languages = {s["youtube_id"]: s.get("language") for s in list_sources()}
    info: dict[str, dict] = {}
    for entry_id, item in _load_fetched_items()["items"].items():
        info[entry_id] = {
            "title": item.get("title"),
            "thumbnail_url": item.get("thumbnail_url"),
            "youtube_music_url": item.get("youtube_music_url"),
            "language": source_languages.get(item.get("source_youtube_id")),
        }

    db_path = _reload("refresh").DB_PATH
    if Path(db_path).exists():
        conn = sqlite3.connect(db_path)
        try:
            rows = conn.execute(
                "SELECT i.video_id, i.title, i.thumbnail_url, i.youtube_music_url, s.language "
                "FROM items i LEFT JOIN sources s ON s.id = i.source_id"
            ).fetchall()
            for video_id, title, thumbnail_url, youtube_music_url, language in rows:
                info[video_id] = {
                    "title": title,
                    "thumbnail_url": thumbnail_url,
                    "youtube_music_url": youtube_music_url,
                    "language": language,
                }
        except sqlite3.OperationalError:
            pass
        finally:
            conn.close()
    return info


# Fixed instruction text for build_description_prompt() below - written once
# here rather than inline so the wording only has to be edited in one place.
DESCRIPTION_PROMPT_INSTRUCTIONS = (
    "Create a one-sentence, max 130 character, spoiler-light description of "
    "its story, in German. Describe the plot/theme only - do not use the "
    "title, franchise name, or any character names from it anywhere in this "
    "field."
)


def build_description_prompt(suggestions: dict, overrides: dict, item_info: dict) -> str:
    """Assembles a copy/paste-able prompt for generating descriptions by hand
    in a separate Claude.ai chat - the manual counterpart to refresh.py's
    --skip-claude flag, for a curator who fetches item metadata without
    paying for a Claude API call and wants to batch-generate descriptions
    themselves instead. Combines DESCRIPTION_PROMPT_INSTRUCTIONS with a
    de-duplicated, alphabetically-sorted, comma-separated list of every item
    currently shown on the Suggestions screen (both pending Claude
    suggestions and already-applied overrides) that has NO description yet
    anywhere - neither an applied override's `description` nor a pending
    suggestion's own Claude-suggested one - since an item that already has
    one doesn't need this manual workflow. Each is written as "Title" or,
    if it has a series, "Title (Series)" - the series annotation keeps an
    episodic series' individual episodes distinguishable from each other in
    the pasted list, since titles alone can otherwise look identical or too
    similar. For an entry_id present in both dicts, the suggestion's
    title/series wins (it's the fresher of the two, e.g. after clicking
    Regenerate suggestion for an already-curated item), but EITHER having a
    description is enough to exclude the item - checked independently of
    which title/series ends up used. Never sent anywhere itself - this only
    builds the text a curator copies out by hand into their own Claude.ai
    session."""
    entries: dict[str, tuple[str, str | None]] = {}
    for entry_id in set(overrides) | set(suggestions):
        override = overrides.get(entry_id, {})
        suggestion = suggestions.get(entry_id, {})
        if override.get("description") or suggestion.get("description"):
            continue
        if suggestion:
            title = suggestion.get("title") or entry_id
            series = suggestion.get("series")
        else:
            title = item_info.get(entry_id, {}).get("title") or entry_id
            series = override.get("series")
        entries[entry_id] = (title, series)

    labels = sorted(
        f"{title} ({series})" if series else title
        for title, series in entries.values()
    )
    return DESCRIPTION_PROMPT_INSTRUCTIONS + "\n\n" + ", ".join(labels)


# How many items go into one metadata prompt - small enough that Claude.ai's
# reply (one JSON entry per item) doesn't get cut off mid-object, and that
# web-searching each item stays within one turn.
METADATA_PROMPT_CHUNK_SIZE = 25


def _metadata_prompt_instructions() -> str:
    refresh = _reload("refresh")
    genre_list = ", ".join(sorted(refresh.GENRE_VALUES))
    franchise_list = ", ".join(sorted(refresh.FRANCHISE_VALUES))
    seasonal_list = ", ".join(sorted(refresh.SEASONAL_VALUES))
    return (
        "I curate a catalog of children's audio dramas (Hörspiele / audiobooks) on YouTube "
        "Music. For each item listed at the end, look it up (use web search - publisher, "
        "retailer, and Wikipedia pages are good sources) and return its metadata.\n\n"
        "Return ONLY one JSON object in a single ```json code block, keyed by each item's ID "
        "exactly as given, with one entry per listed item:\n"
        '{"<ID>": {"description": ..., "series": ..., "position_in_series": ..., "genre": [...], '
        '"franchise": ..., "min_age": ..., "source_release_year": ..., "seasonal": ...}, ...}\n\n'
        "Fields:\n"
        "- description: one sentence, max 130 characters, spoiler-light, describing the "
        "story's plot/theme, written in the item's language (de = German, en = English). "
        "Never use the title, franchise name, or any character names from it.\n"
        '- series: the audiobook series it belongs to (e.g. "Die drei ???"), else null. '
        "If a series hint is given, reuse that exact spelling.\n"
        "- position_in_series: its episode/volume number in that series as an integer, else null.\n"
        f"- genre: array of 1-3 values from [{genre_list}], or [] if none clearly fit.\n"
        f"- franchise: exactly one of [{franchise_list}] if it belongs to one, else null.\n"
        "- min_age: the publisher's/retailer's recommended minimum age as an integer. If "
        "sources disagree, use the LOWER value.\n"
        "- source_release_year: the year the SOURCE film or book was originally released "
        "(not this audio production's release), as an integer.\n"
        f"- seasonal: exactly one of [{seasonal_list}] only if the story is clearly tied to "
        "that season/holiday, else null. Most titles are not seasonal.\n\n"
        "Use null (or [] for genre) whenever you can't verify a value - don't guess. Use "
        "only the listed vocabulary values, spelled exactly as given.\n\n"
        "Items (ID | title | series hint | language):"
    )


def get_metadata_prompt_candidates(
    suggestions: dict, overrides: dict, item_info: dict, series_overrides: dict
) -> list[tuple[str, str, str | None, str]]:
    """(entry_id, title, series, language) for every known item that is
    still missing one of refresh.py's CORE_OVERRIDE_FIELDS once its applied
    override and its pending suggestion are taken together - i.e. items
    a batch Claude.ai pass would actually help with. Same series-level
    exemption for genre/min_age as check_missing_fields(). Items without a
    known title (neither a pending suggestion nor staged/synced data) are
    skipped - there's nothing meaningful to ask Claude about. Sorted by
    series then title, so a series' episodes stay together in the prompt."""
    refresh = _reload("refresh")
    core_fields, series_fields = refresh.CORE_OVERRIDE_FIELDS, refresh.SERIES_RESOLVED_FIELDS
    candidates = []
    for entry_id in set(suggestions) | set(overrides) | set(item_info):
        override = overrides.get(entry_id, {})
        suggestion = suggestions.get(entry_id, {})
        info = item_info.get(entry_id, {})
        title = suggestion.get("title") or info.get("title")
        if not title:
            continue
        series = override.get("series") or suggestion.get("series")
        has_series_meta = bool(series) and series in series_overrides
        missing = [
            field
            for field in core_fields
            if not (has_series_meta and field in series_fields)
            and not (override.get(field) or suggestion.get(field))
        ]
        if missing:
            candidates.append((entry_id, title, series, info.get("language") or "de"))
    candidates.sort(key=lambda c: ((c[2] or "").lower(), c[1].lower()))
    return candidates


def build_metadata_prompts(
    suggestions: dict,
    overrides: dict,
    item_info: dict,
    series_overrides: dict,
    chunk_size: int = METADATA_PROMPT_CHUNK_SIZE,
) -> list[str]:
    """Copy/paste-able prompts for batch-generating full metadata (all eight
    fields Claude is asked for during --fetch, not just a description) in a
    Claude.ai chat - e.g. on a Pro subscription instead of API spend. Unlike
    build_description_prompt(), each item carries its entry_id and Claude is
    asked to answer with one JSON object keyed by those ids, so the reply
    can be pasted straight back into import_metadata_suggestions() instead
    of copied field by field. Split into chunks of `chunk_size` items (one
    prompt each); returns [] if nothing needs filling in."""
    candidates = get_metadata_prompt_candidates(suggestions, overrides, item_info, series_overrides)
    if not candidates:
        return []
    instructions = _metadata_prompt_instructions()
    prompts = []
    for start in range(0, len(candidates), chunk_size):
        lines = [
            f"{entry_id} | {title} | {series or '-'} | {language}"
            for entry_id, title, series, language in candidates[start : start + chunk_size]
        ]
        prompts.append(instructions + "\n" + "\n".join(lines))
    return prompts


def import_metadata_suggestions(raw_text: str) -> dict[str, list[str]]:
    """Parse a pasted Claude.ai reply to build_metadata_prompts() and merge
    it into data/claude_suggestions.json - NEVER into overrides.py, so every
    imported value still goes through the same per-card review/Apply step
    as a --fetch suggestion does. Each entry is run through refresh.py's own
    _validate_suggested_fields() (out-of-vocabulary values dropped, implausible
    ints dropped). Its description gets the same title-word check as
    refresh.py's _description_leaks_title(), but unlike --fetch (which
    retries, then drops) a match here only WARNS and the description is kept:
    there's no retry on this path and every card is reviewed by hand anyway,
    and the check is word-level, so ordinary story words that happen to be
    in the title (e.g. "Abenteuer") trip it too.
    Non-empty imported values replace that item's pending suggestion field
    by field; an empty/invalid imported value never wipes an existing one.

    Raises ValueError if no JSON object can be found at all. Otherwise
    returns lists: "imported", "unknown" (no such item known to the admin
    UI - usually a mangled id), "invalid" (entry wasn't a JSON object) -
    all entry ids - and "description_title_words" ("<entry_id> (<matched
    words>)" per kept description that reuses title words)."""
    refresh = _reload("refresh")
    parsed = refresh._parse_suggestion_json(raw_text)
    if not isinstance(parsed, dict):
        raise ValueError("Couldn't find a JSON object in the pasted text.")

    suggestions = load_suggestions()
    item_info = get_item_info()
    report: dict[str, list[str]] = {"imported": [], "unknown": [], "invalid": [], "description_title_words": []}
    for entry_id, raw in parsed.items():
        entry_id = str(entry_id).strip()
        if not isinstance(raw, dict):
            report["invalid"].append(entry_id)
            continue
        existing = suggestions.get(entry_id, {})
        title = existing.get("title") or item_info.get(entry_id, {}).get("title")
        if not title:
            report["unknown"].append(entry_id)
            continue

        fields = refresh._validate_suggested_fields(raw)
        description = refresh._clean_str(raw.get("description"))
        if description:
            leaked = [
                word
                for word in refresh._title_keywords(title)
                if re.search(rf"\b{re.escape(word.lower())}\b", description.lower())
            ]
            if leaked:
                report["description_title_words"].append(f"{entry_id} ({', '.join(leaked)})")
        fields["description"] = description

        merged = {key: existing.get(key) for key in refresh.EMPTY_SUGGESTIONS}
        merged.update({key: value for key, value in fields.items() if value not in (None, [])})
        refresh.record_suggestion(suggestions, entry_id, title, merged, force=True)
        report["imported"].append(entry_id)

    if report["imported"]:
        save_suggestions(suggestions)
    return report


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


def _filter_dismissed_pairs(warnings: list[tuple[str, list[str]]]) -> list[tuple[str, list[str]]]:
    """Same as _filter_dismissed() but for the (text, entry_ids) shape
    get_consistency_warnings()'s three checks return - filters by `text`
    only, same exact-text dismissal rule as everywhere else in this file."""
    dismissed = load_dismissed_warnings()
    return [(text, entry_ids) for text, entry_ids in warnings if text not in dismissed]


def get_consistency_warnings() -> list[tuple[str, list[str]]]:
    """Runs three independent curation-consistency checks (all pure
    functions in refresh.py, see their own docstrings) directly against the
    current ITEM_OVERRIDES plus known item titles, so they show up on the
    Suggestions screen immediately as you edit overrides.py, without
    needing a --sync first:
      - series consistency - items sharing a `series` disagreeing on
        genre/franchise/seasonal, or two items claiming the same
        position_in_series (check_overrides_series_consistency()).
      - duplicate titles - two different entry ids with the exact same
        title AND the same source_release_year (including both unset) -
        a known, differing release year (e.g. two separate film
        adaptations sharing a title) is not flagged (check_duplicate_titles()).
      - missing core fields - a known item whose override is missing
        description/min_age/genre/source_release_year, including an
        item with no override entry at all - except genre/min_age on
        an item whose series has a SERIES_OVERRIDES entry (any
        series_type), which are satisfied by that entry instead
        (check_missing_fields()).
    Each returned entry is a (warning text, entry_ids) pair rather than a
    bare string - `suggestions.html` uses entry_ids to link the warning
    straight to the item card(s) it's about (see "entry-<id>" anchors on
    each card). Individually-ignored warnings (see dismiss_warning(), which
    still matches by the text half only) are filtered out before returning.
    """
    return [pair for _, pairs in get_grouped_consistency_warnings() for pair in pairs]


def get_grouped_consistency_warnings() -> list[tuple[str, list[tuple[str, list[str]]]]]:
    """Same three checks as get_consistency_warnings() (which flattens
    this), kept apart as (group label, pairs) so the Catalog screen can show
    each kind of warning in its own collapsible group. Groups with no
    (undismissed) warnings are left out."""
    overrides = list_overrides()
    series_overrides = list_series_overrides()
    titles = {entry_id: info["title"] for entry_id, info in get_item_info().items() if info.get("title")}
    release_years = {entry_id: o.get("source_release_year") for entry_id, o in overrides.items()}
    refresh = _reload("refresh")
    groups = [
        ("Series consistency", refresh.check_overrides_series_consistency(overrides, titles)),
        ("Duplicate titles", refresh.check_duplicate_titles(titles, release_years)),
        ("Missing core fields", refresh.check_missing_fields(overrides, titles, series_overrides)),
    ]
    filtered = [(label, _filter_dismissed_pairs(pairs)) for label, pairs in groups]
    return [(label, pairs) for label, pairs in filtered if pairs]


def order_by_consistency_warnings(entries: dict, warnings: list[tuple[str, list[str]]]) -> dict:
    """Reorders an entry_id-keyed dict (load_suggestions()'s or
    list_overrides()'s shape) so every entry_id named in at least one
    get_consistency_warnings() pair's entry_ids comes first - the
    Suggestions screen's whole point in flagging these is to get a curator
    to fix them, so they shouldn't be buried below every already-clean
    item on a long page. A stable partition, not a full re-sort: each of
    the two groups (flagged / not flagged) keeps its original relative
    order, so this doesn't fight load_suggestions()'s alphabetical order or
    ITEM_OVERRIDES's own literal order any more than necessary. Also used
    by get_next_entry_id() below, applying the identical reordering, so
    Suggestions' Apply & Next/Save & Next/Dismiss buttons keep jumping to
    whatever's actually next on screen rather than the pre-reorder
    position."""
    flagged_ids = {entry_id for _, entry_ids in warnings for entry_id in entry_ids}
    flagged = {eid: v for eid, v in entries.items() if eid in flagged_ids}
    rest = {eid: v for eid, v in entries.items() if eid not in flagged_ids}
    return {**flagged, **rest}


def build_catalog_rows(
    overrides: dict,
    item_info: dict,
    series_overrides: dict,
    warnings: list[tuple[str, list[str]]],
    diffs: dict,
) -> list[dict]:
    """One summary row per ITEM_OVERRIDES entry for the Suggestions screen's
    filterable "Applied overrides" table - the compact, scannable view of
    each item, with its full edit form opened on demand underneath. Pure
    (no I/O), so the view stays testable.

    genre/franchise/min_age show the value that actually reaches the
    catalog: the series entry's whenever the item's series has a
    SERIES_OVERRIDES entry (`from_series` is True then - see refresh.py's
    sync_source()), else the item's own. `missing` lists which
    CORE_OVERRIDE_FIELDS are still unset after that resolution - the same
    rule check_missing_fields() uses. `warnings` is every
    get_consistency_warnings() text naming this entry (already filtered for
    dismissed ones); `diff_count` is how many fields a pending suggestion
    would change (see admin/routes.py's _compute_override_diffs())."""
    refresh = _reload("refresh")
    core_fields, series_fields = refresh.CORE_OVERRIDE_FIELDS, refresh.SERIES_RESOLVED_FIELDS
    warnings_by_id: dict[str, list[str]] = {}
    for text, entry_ids in warnings:
        for entry_id in entry_ids:
            warnings_by_id.setdefault(entry_id, []).append(text)

    rows = []
    for entry_id, override in overrides.items():
        info = item_info.get(entry_id, {})
        series = override.get("series")
        series_meta = series_overrides.get(series) if series else None
        source = series_meta if series_meta is not None else override
        resolved = {field: source.get(field) for field in series_fields}
        values = {**override, **resolved}
        missing = [field for field in core_fields if not values.get(field)]
        rows.append(
            {
                "entry_id": entry_id,
                "title": info.get("title") or entry_id,
                "thumbnail_url": info.get("thumbnail_url"),
                "youtube_music_url": info.get("youtube_music_url"),
                "language": info.get("language"),
                "series": series,
                "series_type": (series_meta or {}).get("series_type"),
                "position_in_series": override.get("position_in_series"),
                "genre": resolved["genre"] or [],
                "franchise": resolved["franchise"],
                "min_age": resolved["min_age"],
                "from_series": series_meta is not None,
                "source_release_year": override.get("source_release_year"),
                "seasonal": override.get("seasonal"),
                "description": override.get("description"),
                "has_awards": bool(override.get("awards")),
                "variant": override.get("variant"),
                "missing": missing,
                "warnings": warnings_by_id.get(entry_id, []),
                "diff_count": len(diffs.get(entry_id, {})),
            }
        )
    return rows


def get_source_warnings() -> list[str]:
    """Runs refresh.py's check_duplicate_source_ids() directly against
    sources.py's current SOURCES list, so a duplicate youtube_id (see
    sources.html's warning box) is flagged the moment it's introduced -
    whether by hand-editing sources.py or via the "Add a new source" form
    below - without needing a --sync first. Individually-ignored warnings
    (see dismiss_warning()) are filtered out before returning."""
    return _filter_dismissed(_reload("refresh").check_duplicate_source_ids(list_sources()))


def get_tile_thumbnail_warnings() -> list[str]:
    """Runs app/data.py's get_tile_thumbnail_warnings() (pure, reads
    data/catalog.json - the same committed, published artifact every other
    check in this file already treats as authoritative) so a guided-filter
    tile falling back to a non-curated image is visible on the Values
    screen for manual review. This is the one place admin/ imports from
    app/ - a narrow, one-directional exception (nothing in app/ ever
    imports admin/, so the "never imported by app/" direction this module's
    own docstring describes still holds) rather than duplicating the tile-
    thumbnail resolution logic here. Individually-ignored warnings (see
    dismiss_warning()) are filtered out before returning, same as every
    other check on this screen."""
    return _filter_dismissed(_reload("app.data").get_tile_thumbnail_warnings())


TILE_THUMBNAILS_ANCHOR_RE = re.compile(r"TILE_THUMBNAILS:\s*dict\[str,\s*dict\[str,\s*str\]\]\s*=\s*\{")


def get_tile_categories() -> tuple[str, ...]:
    """The four guided-filter categories (age/duration/genre/series) -
    read live off app/data.py's TILE_CATEGORIES rather than hardcoded here,
    so this can't silently drift from the categories app/data.py actually
    resolves thumbnails for."""
    return tuple(_reload("app.data").TILE_CATEGORIES)


def get_tile_value_options() -> dict[str, list[str]]:
    """category -> every value currently offered as a guided-filter tile on
    the live site (get_age_tags()/get_genres()/get_series_list()/
    get_franchises(), the exact same functions app/routes.py's
    _build_tile_data() calls - "duration" is deliberately not one of these
    four, Dauer was removed as a guided-filter category) - populates the
    Values screen's "add a curated thumbnail" value dropdown, so it can
    never offer a value that isn't actually a real tile to begin with."""
    app_data = _reload("app.data")
    return {
        "age": list(app_data.get_age_tags()),
        "genre": list(app_data.get_genres()),
        "series": list(app_data.get_series_list()),
        "franchise": [f["slug"] for f in app_data.get_franchises()],
    }


def get_tile_thumbnails() -> dict[str, dict[str, str]]:
    """app/tile_thumbnails.py's current TILE_THUMBNAILS, read fresh (same
    _reload() pattern as every other refresh.py/overrides.py getter here) -
    the curated tile-image lookup the Values screen lets you edit and
    app/data.py's get_tile_thumbnail() reads at request time."""
    return {k: dict(v) for k, v in _reload("app.tile_thumbnails").TILE_THUMBNAILS.items()}


def _find_matching_brace(text: str, open_pos: int) -> int:
    """Index of the `}` that closes the `{` at `open_pos`, tracking nested
    brace depth - needed because TILE_THUMBNAILS is a two-level dict (a
    plain regex can't safely span nested braces), and simpler/more robust
    than trying to hand-write a regex that does."""
    depth = 0
    for i in range(open_pos, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    raise RuntimeError("Unbalanced braces while parsing tile_thumbnails.py")


def _format_tile_thumbnails(data: dict[str, dict[str, str]]) -> str:
    """Pretty-prints the whole TILE_THUMBNAILS assignment, one category per
    line-group, values sorted by key within each category for a stable,
    deterministic diff. Unlike overrides.py/sources.py's per-entry text
    surgery, this regenerates the entire dict literal rather than editing
    single lines in place - safe to do here because, unlike those two
    files, TILE_THUMBNAILS has no per-entry comments to preserve, and a
    series name (used as a genre/series tile's key) can contain spaces/
    punctuation that a `\\w+`-style field-line regex (see FIELD_LINE_RE
    above) can't match reliably anyway."""
    lines = ["TILE_THUMBNAILS: dict[str, dict[str, str]] = {"]
    for category in get_tile_categories():
        values = data.get(category, {})
        if not values:
            lines.append(f'    "{category}": {{}},')
            continue
        lines.append(f'    "{category}": {{')
        for value in sorted(values):
            key_literal = json.dumps(value, ensure_ascii=False)
            url_literal = json.dumps(values[value], ensure_ascii=False)
            lines.append(f"        {key_literal}: {url_literal},")
        lines.append("    },")
    lines.append("}")
    return "\n".join(lines) + "\n"


def set_tile_thumbnail(category: str, value: str, url: str) -> None:
    """Adds or updates one curated entry in app/tile_thumbnails.py's
    TILE_THUMBNAILS - the Values screen's "Guided filter tile thumbnails"
    section uses this both to fix a fallback flagged there and to edit an
    already-curated entry. Blank `value`/`url` is a no-op (leaves the file
    untouched), same "blank means don't write" convention every other
    apply-style form in this tool already follows. Raises ValueError for
    an unrecognized category - the form only ever submits one of the four
    known ones, so this only fires on a malformed/tampered request."""
    value = value.strip()
    url = url.strip()
    if not value or not url:
        return
    if category not in get_tile_categories():
        raise ValueError(f"Unknown tile category {category!r}")

    content = TILE_THUMBNAILS_PATH.read_text(encoding="utf-8")
    anchor = TILE_THUMBNAILS_ANCHOR_RE.search(content)
    if not anchor:
        raise RuntimeError("Could not find 'TILE_THUMBNAILS: dict[str, dict[str, str]] = {' in tile_thumbnails.py")
    open_brace = anchor.end() - 1
    close_brace = _find_matching_brace(content, open_brace)

    current = get_tile_thumbnails()
    current.setdefault(category, {})[value] = url

    new_block = _format_tile_thumbnails(current).rstrip("\n")
    new_content = content[: anchor.start()] + new_block + content[close_brace + 1 :]
    TILE_THUMBNAILS_PATH.write_text(new_content, encoding="utf-8")


HIDDEN_TILES_ANCHOR_RE = re.compile(r"HIDDEN_TILES:\s*dict\[str,\s*list\[str\]\]\s*=\s*\{")
SHOWN_TILES_ANCHOR_RE = re.compile(r"SHOWN_TILES:\s*dict\[str,\s*list\[str\]\]\s*=\s*\{")


def get_hidden_tiles() -> dict[str, list[str]]:
    """Which guided-filter tiles are currently hidden from the home page,
    per category, read fresh from app/hidden_tiles.py (same _reload()
    pattern as get_tile_thumbnails()). For a HIDDEN_BY_DEFAULT category
    (series) that's every offered value not opted in via SHOWN_TILES, so
    the Values screen's "Hidden" checkbox means the same thing everywhere."""
    module = _reload("app.hidden_tiles")
    hidden = {k: list(v) for k, v in module.HIDDEN_TILES.items()}
    options = None
    for category in module.HIDDEN_BY_DEFAULT:
        options = options or get_tile_value_options()
        shown = set(module.SHOWN_TILES.get(category, []))
        hidden[category] = [v for v in options.get(category, []) if v not in shown]
    return hidden


def _format_tile_lists(name: str, data: dict[str, list[str]], categories) -> str:
    """Pretty-prints a whole `name: dict[str, list[str]] = {...}` assignment
    (HIDDEN_TILES/SHOWN_TILES) - same "regenerate the entire dict literal"
    approach _format_tile_thumbnails() uses and for the same reason (no
    per-entry comments to preserve, series-name keys can contain characters
    a field-line regex can't match reliably)."""
    lines = [f"{name}: dict[str, list[str]] = {{"]
    for category in categories:
        values = sorted(set(data.get(category, [])))
        if not values:
            lines.append(f'    "{category}": [],')
            continue
        lines.append(f'    "{category}": [')
        for value in values:
            lines.append(f"        {json.dumps(value, ensure_ascii=False)},")
        lines.append("    ],")
    lines.append("}")
    return "\n".join(lines) + "\n"


def set_tile_hidden(category: str, value: str, hidden: bool) -> None:
    """Hides or shows one guided-filter tile by rewriting app/hidden_tiles.py -
    the Values screen's per-row "Hidden" checkbox. For most categories that
    adds/removes the value in HIDDEN_TILES; for a HIDDEN_BY_DEFAULT category
    (series) it's the inverse on SHOWN_TILES (showing = opting in). The value
    stays fully filterable via its chip either way - see hidden_tiles.py's
    docstring. Blank `value` is a no-op; idempotent in both directions.
    Raises ValueError for an unrecognized category, same as
    set_tile_thumbnail()."""
    value = value.strip()
    if not value:
        return
    if category not in get_tile_categories():
        raise ValueError(f"Unknown tile category {category!r}")

    module = _reload("app.hidden_tiles")
    if category in module.HIDDEN_BY_DEFAULT:
        name, anchor_re, add = "SHOWN_TILES", SHOWN_TILES_ANCHOR_RE, not hidden
        current = {k: list(v) for k, v in module.SHOWN_TILES.items()}
        categories = list(module.HIDDEN_BY_DEFAULT)
    else:
        name, anchor_re, add = "HIDDEN_TILES", HIDDEN_TILES_ANCHOR_RE, hidden
        current = {k: list(v) for k, v in module.HIDDEN_TILES.items()}
        categories = get_tile_categories()

    content = HIDDEN_TILES_PATH.read_text(encoding="utf-8")
    anchor = anchor_re.search(content)
    if not anchor:
        raise RuntimeError(f"Could not find '{name}: dict[str, list[str]] = {{' in hidden_tiles.py")
    open_brace = anchor.end() - 1
    close_brace = _find_matching_brace(content, open_brace)

    values = set(current.setdefault(category, []))
    if add:
        values.add(value)
    else:
        values.discard(value)
    current[category] = sorted(values)

    new_block = _format_tile_lists(name, current, categories).rstrip("\n")
    new_content = content[: anchor.start()] + new_block + content[close_brace + 1 :]
    HIDDEN_TILES_PATH.write_text(new_content, encoding="utf-8")


def load_suggestions() -> dict:
    if not SUGGESTIONS_PATH.exists():
        return {}
    try:
        return json.loads(SUGGESTIONS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def get_next_entry_id(section: str, entry_id: str) -> str | None:
    """The entry_id immediately after `entry_id` in the current on-screen
    order of the given section - "suggestion" reads load_suggestions()
    (whose on-disk order is alphabetical by entry_id, see
    save_suggestions()'s sort_keys=True), "override" reads list_overrides()
    (whose order matches ITEM_OVERRIDES's literal order in overrides.py) -
    then applies the exact same order_by_consistency_warnings() reordering
    admin/routes.py's suggestions() view applies before rendering, so this
    always matches what's actually next on screen (consistency-warning-
    flagged entries first, then everything else in its original order).
    Used by the Suggestions screen's "Apply & Next"/"Save & Next"/Dismiss
    actions to jump straight to the next card instead of back to the top
    of a long page - see admin/routes.py's suggestions_action(). Returns
    None if `entry_id` is last (or no longer present, e.g. already
    removed) - callers fall back to no anchor (the page top) in that
    case."""
    entries = load_suggestions() if section == "suggestion" else list_overrides()
    entries = order_by_consistency_warnings(entries, get_consistency_warnings())
    keys = list(entries.keys())
    try:
        index = keys.index(entry_id)
    except ValueError:
        return None
    return keys[index + 1] if index + 1 < len(keys) else None


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


_YOUTUBE_ID_URL_HOSTS = {"www.youtube.com", "youtube.com", "music.youtube.com", "m.youtube.com"}


def extract_youtube_id(value: str) -> str:
    """Accepts either a bare YouTube id (returned as-is) or a full YouTube/
    YouTube Music URL, from which the actual id is pulled out - lets the
    Sources screen take a pasted URL directly instead of requiring the id to
    already be extracted by hand. Handles a `list=` query param (playlist/
    album - e.g. music.youtube.com/playlist?list=... or
    youtube.com/watch?v=...&list=...), a `/channel/<id>` path segment, and a
    YouTube Music `/browse/<id>` album page (returns its `MPREb_...` browse
    id, which still has to go through resolve_album_browse_id() before it's
    usable as a sources.py `youtube_id`). Anything else - a bare id, or a
    URL shape that doesn't carry the id directly (e.g. an `@handle` channel
    URL, which needs a live API lookup to resolve to its real `UC...` id) -
    is returned unchanged, so the existing required-field validation still
    catches a genuinely bad value instead of this silently swallowing it.
    """
    value = value.strip()
    if "://" not in value:
        return value

    parsed = urllib.parse.urlparse(value)
    if parsed.netloc not in _YOUTUBE_ID_URL_HOSTS:
        return value

    query = urllib.parse.parse_qs(parsed.query)
    list_id = query.get("list", [""])[0]
    if list_id:
        return list_id

    path_parts = [p for p in parsed.path.split("/") if p]
    if len(path_parts) >= 2 and path_parts[0] in ("channel", "browse"):
        return path_parts[1]

    return value


def infer_source_type(youtube_id: str) -> str | None:
    """sources.py `type` implied by an id's prefix - "album" for a YouTube
    Music album (`OLAK5uy_...` playlist id, or its `MPREb_...` browse id),
    "playlist" for `PL...`, "channel" for `UC...`. None if unrecognized."""
    if youtube_id.startswith(("OLAK5uy_", "MPREb_")):
        return "album"
    if youtube_id.startswith("PL"):
        return "playlist"
    if youtube_id.startswith("UC"):
        return "channel"
    return None


YTM_BROWSE_URL = "https://music.youtube.com/browse/{}"
_OLAK_ID_RE = re.compile(r"OLAK5uy_[A-Za-z0-9_-]{20,}")


def resolve_album_browse_id(browse_id: str, timeout: float = 15) -> str | None:
    """Resolve a YouTube Music album browse id (`MPREb_...`, what a
    music.youtube.com/browse/... URL carries) to the album's `OLAK5uy_...`
    playlist id - the only form the YouTube Data API (and therefore
    refresh.py) accepts. The album page's server-rendered HTML embeds that
    playlist id (verified by hand: exactly one distinct OLAK5uy_ id per
    album page), so a plain GET is enough - no API key, no quota.

    This is the ONE network call anywhere in admin/ - a deliberate, narrow
    exception to its otherwise network-free text-file editing, made only on
    an explicit "Preview import" click. Returns None on any network error,
    or if the page doesn't contain exactly one candidate id, so a failure
    surfaces as a row error in the import preview rather than a guess."""
    request = urllib.request.Request(
        YTM_BROWSE_URL.format(urllib.parse.quote(browse_id)),
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
            "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            html = response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError):
        return None
    ids = set(_OLAK_ID_RE.findall(html))
    return ids.pop() if len(ids) == 1 else None


_URL_RE = re.compile(r"https?://[^\s<>()\"']+")
# Lines in a copied YouTube Music list that are metadata, not a title - e.g.
# "Show• 2023", "Album • 2019", a bare year, or a list marker like "a)".
_SOURCE_LIST_NOISE_RE = re.compile(
    r"^(?:(?:show|album|ep|single|hörbuch|audiobook|playlist|podcast)\b.*•.*|•.*|\d{4}|[a-z0-9]{1,3}[).])$",
    re.IGNORECASE,
)


def parse_source_list(raw_text: str) -> list[dict]:
    """Pull (youtube_id, url, raw_title) out of a free-form pasted list of
    YouTube Music links - e.g. copied straight from a YouTube Music search/
    artist page, where each entry looks like a URL line, the title line, the
    same URL again, then a "Show• 2023"-style metadata line. The title is the
    first non-noise line after an id's first URL (or any text on the URL's
    own line). De-duplicated by id, in first-seen order. URLs whose id isn't
    recognized (see infer_source_type()) are skipped. Done locally, not by
    Claude, so ids never pass through an LLM that could mangle them."""
    items: dict[str, dict] = {}
    current = None
    for line in raw_text.splitlines():
        line = line.strip()
        if not line:
            continue
        urls = _URL_RE.findall(line)
        if urls:
            youtube_id = extract_youtube_id(urls[0])
            if infer_source_type(youtube_id) is None:
                current = None
                continue
            current = youtube_id
            items.setdefault(youtube_id, {"youtube_id": youtube_id, "url": urls[0], "raw_title": ""})
            line = _URL_RE.sub("", line).strip(" <>\t|-")
            if not line:
                continue
        if current and not items[current]["raw_title"] and not _SOURCE_LIST_NOISE_RE.match(line):
            items[current]["raw_title"] = line
    return list(items.values())


def build_source_prompt(items: list[dict], series_names: list[str]) -> str:
    """Copy/paste-able Claude.ai prompt that turns parse_source_list()'s raw
    YouTube Music titles into clean sources.py labels plus a series guess,
    answered as one JSON object keyed by id - the paste-back half is
    prepare_source_import(). Claude is told to ask back rather than guess
    when a series is unclear (a Claude.ai chat is interactive, unlike the
    API path), and is given the existing series names so it reuses their
    exact spelling. Deliberately one prompt for the whole list (no
    chunking): neighboring items are the main context for guessing a
    series from a title that doesn't name it."""
    lines = [f"{item['youtube_id']} | {item['raw_title'] or '(no title found)'}" for item in items]
    return (
        "I'm adding children's audio dramas (Hörspiele) from YouTube Music to a catalog. "
        "Below is a list of albums (ID | raw title as shown on YouTube Music). For each one, "
        "produce a clean display label and the series it belongs to.\n\n"
        "Label rules:\n"
        '- Format: "<Series> - <Title>" if it belongs to a series, otherwise just "<Title>".\n'
        '- Remove episode numbers and prefixes (e.g. "20: ", "Folge 12 - "), "Album - ", and '
        'marketing suffixes such as "[Hörspiel zum TV-Special]", "(Hörspiel zum Kinofilm)", '
        '"Das Original-Hörspiel zum Film".\n'
        '- Keep parts that tell items apart, e.g. "(Teil 3 & 4)".\n'
        "- Keep the original language and spelling - don't translate.\n"
        "Examples:\n"
        '- "Sofia die Erste - Auf einmal Prinzessin (Hörspiel zum TV-Special)" -> '
        '"Sofia die Erste - Auf einmal Prinzessin"\n'
        '- "20: Die Mystischen Inseln (Teil 3 & 4) [Hörspiel zum TV-Special]", listed among '
        'other Sofia die Erste items -> "Sofia die Erste - Die Mystischen Inseln (Teil 3 & 4)"\n\n'
        "Series:\n"
        "- Infer it from the title, or from context: neighboring items, numbering, a matching "
        "production style. Reuse the exact spelling from the existing series list below when "
        "one matches.\n"
        "- If you're not confident which series an item belongs to (or whether it belongs to "
        "one at all), DON'T guess. First ask me - list those items with your best guesses - "
        "and only produce the JSON after I've answered.\n\n"
        'Language: "de" or "en" - the language of the audio drama.\n\n'
        "Once everything is clear, return ONLY one JSON object in a single ```json code block, "
        "keyed by each item's ID exactly as given, with one entry per listed item:\n"
        '{"<ID>": {"label": "...", "series": "..." or null, "language": "de"}, ...}\n\n'
        f"Existing series names: {', '.join(series_names) if series_names else '(none yet)'}\n\n"
        "Items (ID | raw title):\n" + "\n".join(lines)
    )


def prepare_source_import(raw_text: str, resolver=resolve_album_browse_id) -> list[dict]:
    """Parse a pasted Claude.ai reply to build_source_prompt() into preview
    rows for the Sources screen - nothing is written here; the curator
    reviews/edits the rows and confirms via add_imported_sources(). Each row:
    {"input_id", "youtube_id", "type", "label", "series", "language",
    "error"}. `MPREb_` browse ids are resolved to their `OLAK5uy_` playlist
    id via `resolver` (concurrently - one page fetch each). A row gets an
    `error` (and is unchecked by default in the preview) if its id isn't
    recognized or can't be resolved, it's already in sources.py or repeated
    within this import, or its label is missing. Raises ValueError if no
    JSON object can be found at all."""
    parsed = _reload("refresh")._parse_suggestion_json(raw_text)
    if not isinstance(parsed, dict):
        raise ValueError("Couldn't find a JSON object in the pasted text.")

    keys = [str(k).strip() for k in parsed]
    ids = {key: extract_youtube_id(key) for key in keys}
    browse_ids = sorted({i for i in ids.values() if i.startswith("MPREb_")})
    with ThreadPoolExecutor(max_workers=8) as pool:
        resolved = dict(zip(browse_ids, pool.map(resolver, browse_ids)))

    existing_ids = {s["youtube_id"] for s in list_sources()}
    seen: set[str] = set()
    rows = []
    for key, raw in zip(keys, parsed.values()):
        raw = raw if isinstance(raw, dict) else {}
        youtube_id = ids[key]
        language = raw.get("language") if isinstance(raw.get("language"), str) else ""
        row = {
            "input_id": key,
            "youtube_id": youtube_id,
            "type": infer_source_type(youtube_id),
            "label": raw.get("label").strip() if isinstance(raw.get("label"), str) else "",
            "series": raw.get("series").strip() if isinstance(raw.get("series"), str) else "",
            "language": language.strip().lower() or "de",
            "error": None,
        }
        if youtube_id.startswith("MPREb_"):
            row["youtube_id"] = resolved.get(youtube_id) or ""
        if row["type"] is None:
            row["error"] = "Unrecognized id."
        elif not row["youtube_id"]:
            row["error"] = "Couldn't resolve this album to a playlist id - add it by hand via its Share link."
        elif row["youtube_id"] in existing_ids:
            row["error"] = "Already in sources.py."
        elif row["youtube_id"] in seen:
            row["error"] = "Listed twice in this import."
        elif not row["label"]:
            row["error"] = "No label in Claude's reply."
        if row["youtube_id"]:
            seen.add(row["youtube_id"])
        rows.append(row)
    return rows


def add_imported_sources(rows: list[dict]) -> dict[str, list[str]]:
    """Write the curator-confirmed rows from the import preview: one new
    active sources.py entry per row, plus - for an album, whose
    ITEM_OVERRIDES key is its own playlist id - its `series` into
    overrides.py via apply_override() (the preview form is the human review
    step for that value). Channel/playlist sources get no series override,
    since their items are keyed by video ids not known until --fetch. Rows
    whose id is already in sources.py by now are skipped, not duplicated.
    Written in reverse so they end up in list order (add_source() inserts
    at the top of SOURCES). Returns {"added": [...labels], "skipped": [...ids]}."""
    existing_ids = {s["youtube_id"] for s in list_sources()}
    report: dict[str, list[str]] = {"added": [], "skipped": []}
    to_add = []
    for row in rows:
        if row["youtube_id"] in existing_ids:
            report["skipped"].append(row["youtube_id"])
            continue
        existing_ids.add(row["youtube_id"])
        to_add.append(row)
    for row in reversed(to_add):
        add_source(
            {
                "type": row["type"],
                "youtube_id": row["youtube_id"],
                "label": row["label"],
                "language": row["language"] or "de",
                "active": True,
            }
        )
        if row.get("series") and row["type"] == "album":
            apply_override(row["youtube_id"], {"series": row["series"]})
    report["added"] = [row["label"] for row in to_add]
    return report


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


def _remove_fields(anchor_re: re.Pattern, key: str, fields) -> bool:
    """Delete the `"<field>": ...,` lines for `fields` from the `key` block
    of the overrides.py dict found by `anchor_re` (ITEM_OVERRIDES or
    SERIES_OVERRIDES). Only single-line values are matched - every field
    this is used for (series, position_in_series, seasonal, genre,
    franchise, min_age) is written on one line. Returns whether anything
    changed; a missing block or field is a no-op, not an error."""
    fields = list(fields)
    if not fields:
        return False
    content = OVERRIDES_PATH.read_text(encoding="utf-8")
    anchor = anchor_re.search(content)
    if not anchor:
        raise RuntimeError("Could not find the dict anchor in overrides.py")
    head, body_region = content[: anchor.end()], content[anchor.end() :]
    match = _entry_block_re(key).search(body_region)
    if not match:
        return False
    names = "|".join(re.escape(f) for f in fields)
    new_body, count = re.subn(rf'^\s*#?\s*"(?:{names})":.*,[ \t]*\n', "", match.group(2), flags=re.M)
    if not count:
        return False
    new_block = match.group(1) + new_body + match.group(3)
    OVERRIDES_PATH.write_text(
        head + body_region[: match.start()] + new_block + body_region[match.end() :], encoding="utf-8"
    )
    return True


def remove_override_fields(entry_id: str, fields) -> bool:
    """Clear fields from one ITEM_OVERRIDES entry - the counterpart to
    apply_override(), whose "blank is never written" rule means it can't
    unset anything. Used by the Catalog screen's bulk actions."""
    return _remove_fields(OVERRIDES_ANCHOR_RE, entry_id, fields)


def save_series_override(series_name: str, fields: dict) -> None:
    """Authoritative save for the Series screen: unlike
    apply_series_override(), a blank value here (unchecked genres, "(none)"
    franchise/type, empty min age) REMOVES that field from the series entry
    instead of leaving the old value - the series form always shows every
    field, so blank means "unset it"."""
    apply_series_override(series_name, fields)
    blank = [k for k, v in fields.items() if v in (None, "", [])]
    _remove_fields(SERIES_OVERRIDES_ANCHOR_RE, series_name.strip(), blank)


def _series_members(series_name: str) -> list[str]:
    return [eid for eid, o in list_overrides().items() if o.get("series") == series_name]


def rename_series(old: str, new: str) -> int:
    """Rename a series everywhere it's referenced: its SERIES_OVERRIDES key
    (if it has an entry), every ITEM_OVERRIDES member's `series` value, and
    any pending suggestion in data/claude_suggestions.json that names it.
    Raises ValueError for a blank/unchanged name, or if `new` already has a
    SERIES_OVERRIDES entry while `old` has one too (merge those by hand).
    Renaming onto an existing series WITHOUT an entry of its own is allowed
    - that's how two spellings of one series get merged. Returns how many
    items were updated."""
    old, new = old.strip(), new.strip()
    if not new or new == old:
        raise ValueError("Enter a different, non-empty series name.")
    series_overrides = list_series_overrides()
    if old in series_overrides and new in series_overrides:
        raise ValueError(f"{new!r} already has its own series entry - merge the two by hand.")

    if old in series_overrides:
        content = OVERRIDES_PATH.read_text(encoding="utf-8")
        anchor = SERIES_OVERRIDES_ANCHOR_RE.search(content)
        head, body_region = content[: anchor.end()], content[anchor.end() :]
        match = _entry_block_re(old).search(body_region)
        new_header = f"    {_py_literal(new)}: {{\n"
        body_region = body_region[: match.start()] + new_header + body_region[match.start() + len(match.group(1)) :]
        OVERRIDES_PATH.write_text(head + body_region, encoding="utf-8")

    members = _series_members(old)
    for entry_id in members:
        apply_override(entry_id, {"series": new})

    suggestions = load_suggestions()
    touched = False
    for entry in suggestions.values():
        if entry.get("series") == old:
            entry["series"] = new
            touched = True
    if touched:
        save_suggestions(suggestions)
    return len(members)


def remove_series_override(series_name: str) -> int:
    """Delete a series' SERIES_OVERRIDES entry (plus any comment lines
    directly above it). Its genre/franchise/min_age are first copied onto
    every member's own ITEM_OVERRIDES entry, so removing the entry never
    silently strips curated values from the catalog - the members just go
    back to per-item values. The members keep their `series` name. Returns
    the number of members updated."""
    meta = list_series_overrides().get(series_name)
    if meta is None:
        raise ValueError(f"{series_name!r} has no series entry.")
    values = {f: meta.get(f) for f in _reload("refresh").SERIES_RESOLVED_FIELDS}
    members = _series_members(series_name)
    for entry_id in members:
        apply_override(entry_id, values)

    content = OVERRIDES_PATH.read_text(encoding="utf-8")
    anchor = SERIES_OVERRIDES_ANCHOR_RE.search(content)
    head, body_region = content[: anchor.end()], content[anchor.end() :]
    match = _entry_block_re(series_name).search(body_region)
    start, end = match.start(), match.end()
    # Swallow comment lines directly above the block and one blank line after it.
    while True:
        prev_line_start = body_region.rfind("\n", 0, start - 1) + 1
        if start > 0 and body_region[prev_line_start:start].lstrip().startswith("#"):
            start = prev_line_start
        else:
            break
    if body_region[end : end + 1] == "\n":
        end += 1
    OVERRIDES_PATH.write_text(head + body_region[:start] + body_region[end:], encoding="utf-8")
    return len(members)


def strip_series_resolved_fields(series_name: str) -> int:
    """Remove the now-ignored per-item genre/franchise/min_age from every
    member of a series that has a SERIES_OVERRIDES entry (sync_source()
    resolves those three from the series entry, and warns about stray
    per-item copies). Returns how many members changed."""
    fields = _reload("refresh").SERIES_RESOLVED_FIELDS
    return sum(1 for entry_id in _series_members(series_name) if remove_override_fields(entry_id, fields))


def suggest_series_metadata(member_overrides: list[dict]) -> dict:
    """Most-used genre/franchise/min_age across a series' members - the
    starting values offered when creating a series entry (same rule the
    initial SERIES_OVERRIDES migration used). A min_age tie picks the lower
    value, per overrides.py's lower-of-the-two rule; other ties keep the
    first-seen value. Unset values don't count."""
    from collections import Counter

    result = {}
    for field in _reload("refresh").SERIES_RESOLVED_FIELDS:
        values = [o.get(field) for o in member_overrides if o.get(field) not in (None, "", [])]
        if field == "genre":
            values = [tuple(sorted(v)) for v in values]
        if not values:
            result[field] = [] if field == "genre" else None
            continue
        counts = Counter(values)
        best = max(counts.values())
        tied = [v for v in counts if counts[v] == best]
        chosen = min(tied) if field == "min_age" else tied[0]
        result[field] = list(chosen) if field == "genre" else chosen
    return result


def series_anchor(name: str) -> str:
    """Stable, HTML-id-safe anchor for a series on the Series screen
    (`#series-<anchor>`) - lowercased, umlauts transliterated, every other
    run of non-[a-z0-9] collapsed to "-"."""
    name = name.lower()
    for src, dst in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        name = name.replace(src, dst)
    return re.sub(r"[^a-z0-9]+", "-", name).strip("-") or "series"


def build_series_rows(overrides: dict, series_overrides: dict, item_info: dict) -> list[dict]:
    """One row per series name for the Series screen - every
    SERIES_OVERRIDES key plus every `series` value any item uses. Pure (no
    I/O). Each row: name, has_entry, series_type, genre/franchise/min_age
    (the entry's, or the most-used member values as `suggested` when there's
    no entry), members (sorted by position, unset last, then title - same
    order as the public site), and problems: duplicate positions, members
    without a position, gaps in the 1..n numbering, and an entry with no
    members."""
    by_series: dict[str, list[str]] = {}
    for entry_id, o in overrides.items():
        if o.get("series"):
            by_series.setdefault(o["series"], []).append(entry_id)

    rows = []
    for name in sorted(set(by_series) | set(series_overrides), key=str.lower):
        meta = series_overrides.get(name)
        members = []
        for entry_id in by_series.get(name, []):
            o = overrides[entry_id]
            members.append(
                {
                    "entry_id": entry_id,
                    "title": item_info.get(entry_id, {}).get("title") or entry_id,
                    "position": o.get("position_in_series"),
                    "year": o.get("source_release_year"),
                    "variant": o.get("variant"),
                }
            )
        members.sort(key=lambda m: (m["position"] is None, m["position"] or 0, m["title"].lower()))
        # Only the main line is numbered: a remake shares its original's
        # position on purpose, and a spin-off sits outside the numbering.
        main = [m for m in members if not m["variant"]]
        positions = [m["position"] for m in main if m["position"] is not None]
        duplicates = sorted({p for p in positions if positions.count(p) > 1})
        gaps = sorted(set(range(1, max(positions) + 1)) - set(positions)) if positions else []
        rows.append(
            {
                "name": name,
                "anchor": series_anchor(name),
                "has_entry": meta is not None,
                "series_type": (meta or {}).get("series_type") or "",
                "genre": (meta or {}).get("genre") or [],
                "franchise": (meta or {}).get("franchise") or "",
                "min_age": (meta or {}).get("min_age"),
                "suggested": None if meta is not None else suggest_series_metadata(
                    [overrides[m["entry_id"]] for m in members]
                ),
                "members": members,
                "duplicate_positions": duplicates,
                "unpositioned": sum(1 for m in members if m["position"] is None and m["variant"] != "spin_off"),
                "gaps": gaps,
            }
        )
    return rows


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
    (GENRE_VALUES/FRANCHISE_VALUES/SEASONAL_VALUES/AWARD_VALUES),
    plus - for the three slug-based lists, not `award` - a matching
    "<prefix>_<slug>" translation key in both app/i18n.py language blocks.
    Without the i18n step, a new genre/franchise/seasonal slug would
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
