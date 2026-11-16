"""
Manual per-item metadata overrides, keyed by catalog entry id.

For 'channel'/'playlist' sources that's a YouTube video id (one entry per
video). For 'album' sources it's the playlist/album id instead, since an
album collapses down to a single catalog entry for the whole audiobook
(see build_album_entry() in refresh.py) - not one entry per chapter.

The YouTube Data API gives us a raw video/album description, but it's never
used - `description` here is entirely override-only too, same as the other
eight fields below. It has no concept of series, episode number, genre,
franchise, age group, the *source* material's original release year,
seasonal relevance, or awards either, so all nine fields have to be curated
by hand here. refresh.py applies these on every run (merged in after the
API data), so they're safe from being wiped out by a re-sync and stay
version-controlled like the rest of the curation.

**`genre`/`franchise`/`min_age` are per-item fields here, EXCEPT for
an item belonging to a series with a `SERIES_OVERRIDES` entry** (episodic,
sequel, or untyped - see `series_type` below and `SERIES_OVERRIDES`
further down) - for those, the three fields move to a single shared entry
in `SERIES_OVERRIDES`, keyed by the series name, and are simply omitted
from every member's own `ITEM_OVERRIDES` entry. This exists because a
series is expected to agree on all three across every member anyway (the
series consistency check below already assumed this and just warned when
it didn't) - retyping the same genre/franchise/min_age on every entry was
pure duplication and a recurring source of typos (this codebase's own
Bibi Blocksberg entries once disagreed on `min_age` between two episodes
before this change, and several film series - Der König der Löwen, Peter
Pan, Michel aus Lönneberga - did too before it was extended beyond
episodic series). `series`/
`position_in_series`/`description`/`source_release_year`/`seasonal`/
`awards` stay per-item regardless of `series_type` - only the three fields
above move.

For every genuinely new item, refresh.py also asks Claude for best-effort
suggestions for eight of these nine fields - everything except `awards` (see
below) - in one combined call, to keep token spend down (see
generate_metadata_suggestions() in refresh.py), and writes them to
data/claude_suggestions.json for you to review by hand. That file is NEVER
read back into the catalog - it's a staging area, not a data source.
Nothing Claude proposes reaches the catalog on its own, `description`
included - `seasonal` too, even though it's subjective/generative
rather than a factual claim; every suggested field goes through the same
human-review gate with no exceptions. If you agree with a suggestion, copy
it into an entry here yourself. ITEM_OVERRIDES here is always the only
thing that actually reaches the catalog.

All fields are optional - omit whatever you don't know. All of them are
override-only with NO fallback to any API value:

  - `description`: a short, spoiler-light one- or two-sentence description
    of the story, in the item's own language. This is the exact same text
    Claude suggests (see above) - there is no separate auto-generation path
    that writes it for you; an item with no `description` override just has
    no description shown, until you add one.
  - `genre`: a list of ONE OR MORE values from this fixed list (an item can
    carry more than one thematic tag, e.g. `["adventure", "family"]` -
    filtering matches if ANY selected genre is present):
        adventure, fairy_tale, family, fantasy, mystery, educational
    Always a list, even for a single tag (`["adventure"]`, not
    `"adventure"`) - `[]`/omitted means no genre set, same "no catch-all
    value" convention as every other unset field in this file. **Omit on an
    item whose series has a `SERIES_OVERRIDES` entry** - set it once
    there instead (see below).
  - `franchise`: IP/brand grouping - NOT genre, NOT publisher. One value
    from this fixed list, or omit/None for a standalone (non-franchise)
    title:
        disney, pixar, dreamworks, marvel, star_wars, bibi_blocksberg,
        benjamin_bluemchen, die_drei_fragezeichen, tkkg
    (refresh.py logs a warning, but doesn't fail the sync, if a genre or
    franchise value isn't in its fixed list - see GENRE_VALUES/
    FRANCHISE_VALUES in refresh.py.) **Omit on an item whose series has a
    `SERIES_OVERRIDES` entry** - set it once there instead.
  - `min_age`: the precise minimum age from the publisher/retailer, as an
    int (e.g. 4). This is the only age input - `age_tag` is NOT set
    directly; refresh.py derives it from `min_age` via a fixed bracket
    lookup (`derive_age_tag()`/`AGE_BRACKETS` in refresh.py):
        0_3      toddlers, very short attention span, sound/music-driven
        3_5      kindergarten age, matches most "ab 3/4/5" publisher labels
        6_8      early readers, most Disney Hoerspiele land here
        9_11     matches Deutscher Kinderhoerbuchpreis BEO Kategorie II
        12_plus  matches BEO Kategorie III, older/literary content
    Single-select by design: one min_age maps to exactly one bracket, so
    there's no overlapping-bracket filter UI to reconcile. If different
    editions/sources disagree on the minimum age for the same title,
    resolve that here (not in refresh.py) by using the LOWER of the two
    conflicting values. Leave `min_age` unset for "no age restriction"
    rather than a catch-all value - the item then shows under "Alle" in
    the age filter, same as before. **Omit on an item whose series has a
    `SERIES_OVERRIDES` entry** - set it once there instead (same
    lower-of-the-two tie-break rule applies there if members disagree).
  - `source_release_year`: the year the SOURCE film or book was originally
    released - e.g. 1994 for a "The Lion King" audiobook - NOT the
    audiobook production's own release/upload date. The audiobook's own
    date is often ambiguous (the same title can show several different
    years across editions/reissues/platforms), while the source material's
    release year is a single stable, verifiable fact. Year only (an int),
    not a full date. Stays per-item even for a series' members -
    unlike genre/franchise/min_age, an episode's own release year is
    never expected to be shared across the series.
  - `series`, `position_in_series`: e.g. "Die drei ???" / 78 for episode 78
    of that series. `series_type` used to be a third per-item field here -
    it's now series-level only, see `SERIES_OVERRIDES` below.
  - `variant`: how an item relates to its series' MAIN LINE - omit for a
    main-line item (the common case), else ONE value from this fixed list:
        remake    a new version of an existing part (e.g. Arielle 2023 ->
                  Arielle 1989). Give it the SAME `position_in_series` as
                  the part it remakes; the site shows a "Neuverfilmung"
                  badge with an "Original: ..." link to that part.
        spin_off  a prequel or side story outside the numbering (e.g.
                  Mufasa, Tinker Bell, Arielle - Wie alles begann). Needs
                  no position; the site shows a "Spin-off" badge.
    Only main-line items get "Teil N von M" badges and davor:/danach: links
    in a `sequel` series, and only they count toward M; the duplicate-
    position check ignores variants. Manual curation only - never inferred
    from a shared title or position.
  - `seasonal`: ONE value from this fixed list, or omit/None for the
    (expected-to-be-majority) non-seasonal case - don't force a value just
    because a title is loosely festive:
        winter, christmas, halloween, easter, summer, birthday
  - `awards`: a list of `{"name": ..., "category": ..., "year": ...}` dicts
    for real awards this specific title has won - `category`/`year` are
    optional per entry, `name` is required. Unlike every other field here,
    this is entirely hand-curated - Claude is NEVER asked to suggest it (it
    used to verify candidates with a web search tool, but that was removed:
    the searches were expensive, and this catalog's award data is meant to
    be maintained fully manually anyway, so there's no reason to pay for an
    LLM's best-effort guess at a factual claim it can't verify without a
    tool). Add awards here only from what you've verified yourself. `name`
    is checked against `AWARD_VALUES` in refresh.py (a starter list, not a
    claim of completeness - extend it by hand as you curate more real
    awards, e.g. via the admin tool's Values screen); an unrecognized name
    logs a warning but doesn't fail the sync, same treatment as genre/
    franchise. Omit the field entirely (not `[]`) for "never checked" -
    `[]` in refresh.py's default just means "no awards found so far".

`SERIES_OVERRIDES` (a `dict[str, dict]`, defined further down in this file
right before ITEM_OVERRIDES) is the shared home for `series_type`/`genre`/
`franchise`/`min_age` for a whole series - keyed by the series
NAME (not an entry id, the only place in this codebase a dict is keyed by
free text rather than a YouTube/entry id), e.g.:
    SERIES_OVERRIDES = {
        "Bibi Blocksberg": {
            "series_type": "episodic",
            "genre": ["fantasy"],
            "franchise": "",
            "min_age": 4,
        },
    }
Every entry's `genre`/`franchise`/`min_age` take effect for every item
sharing that `series` name, whatever its `series_type` (their own
`ITEM_OVERRIDES` entries should omit those three fields - see each field's
bullet above). `series_type` only decides how the site DISPLAYS the series
and is exactly ONE value from this fixed list, or omitted:
    episodic, sequel
MANUAL curation only - NEVER auto-inferred from how many entries share a
`series` name (a trilogy is 3 "sequel" films; a 3-part miniseries is
"episodic" - count alone can't tell them apart). `episodic` (Bibi
Blocksberg, TKKG, Die drei ??? - a long-running series where each entry
stands alone) collapses the series into one card on the site with a
`/series/<slug>` episode listing. `sequel` (Toy Story 1 -> 5, Der König der
Löwen 1 -> 3 - direct film sequels/numbered installments) keeps every film
as its own individual card with a "Teil N von M" badge and davor:/danach:
cross-links instead. An entry with no `series_type` (e.g. a series with
only one item in the catalog so far, where a "Teil 2 von 1" badge would
be nonsense) only centralizes the metadata and displays plain cards -
filterable by "Reihe", no collapsing, no badge. A series with no
`SERIES_OVERRIDES` entry at all keeps all three fields per-item.

Series consistency checks: every entry sharing the same `series` name
(across every source, not just one - a series could in principle span more
than one) is compared against the others for two likely mistakes, warned
about but never a hard failure:
  - entries in the same series disagreeing on `genre`/`franchise`/
    `seasonal` - a real series is usually consistent on all three, so a
    mismatch is more often a typo or a forgotten field in one entry than a
    deliberate choice. Fix it by aligning the odd one out, or ignore the
    warning if the disagreement really is intentional (some Disney series
    do shift genre between installments). For a series with a
    `SERIES_OVERRIDES` entry this can only actually fire for `seasonal`
    now - `genre`/`franchise` are meant to be omitted per-item once
    `SERIES_OVERRIDES` covers them, so there's nothing left on the item
    entries to disagree about;
    if this warning still fires for those two on a series you've already
    migrated to `SERIES_OVERRIDES`, it means some episodes still have
    stale per-item values worth cleaning up.
  - two entries in the same series claiming the same `position_in_series` -
    almost always a copy-paste mistake (e.g. forgetting to bump the number
    when adding a new episode's override block).
These warnings only ever read what's already in ITEM_OVERRIDES - they never
change what gets written, same as the genre/franchise/seasonal/award
vocabulary warnings above. Surfaced in two places: `--sync` runs it against
`storytimefinder.db` post-sync and logs findings to the console
(`_check_series_consistency()` in refresh.py); the admin tool's Suggestions
screen runs the same check directly against this file
(`check_overrides_series_consistency()`) and shows it right in the browser,
so you see it as you edit, before ever syncing.

Example:
    SERIES_OVERRIDES = {
        "Die drei ???": {
            "series_type": "episodic",
            "genre": ["mystery"],
            "franchise": "die_drei_fragezeichen",
            "min_age": 8,
        },
    }

    ITEM_OVERRIDES = {
        "dQw4w9WgXcQ": {
            # genre/franchise/min_age all come from SERIES_OVERRIDES
            # above instead - omitted here on purpose, not forgotten.
            "description": "Episode 78 der drei Detektive: ein spurloses Verschwinden im Nebel.",
            "series": "Die drei ???",
            "position_in_series": 78,
            "source_release_year": 1999,
            "awards": [
                {"name": "Deutscher Hörbuchpreis", "category": "Bestes Kinderhörbuch", "year": 2026},
            ],
        },
        "OLAK5uy_mSqQ0DFEOq4ehi5QCmGcMbse1XPGrH9Jg": {  # an 'album' source, not part of a series
            "description": "Ein Clownfisch sucht seinen vermissten Sohn und erlebt dabei ein großes Abenteuer im Meer.",
            "genre": ["adventure"],
            "franchise": "disney",
            "source_release_year": 2003,
        },
    }
"""

# Series-level metadata (episodic, sequel, or untyped) - see the docstring above for
# the full field-by-field spec. Keyed by series NAME, not an entry id.
SERIES_OVERRIDES: dict[str, dict] = {
    "Vom kleinen Waschbären": {
        "genre": ["adventure", "family"],
        "min_age": 3,
    },

    "Woozle Goozle": {
        "genre": ["educational"],
        "min_age": 6,
        "series_type": "episodic",
    },

    "Momo": {
        "genre": ["family", "fantasy"],
        "min_age": 10,
    },

    "Findet Nemo": {
        "genre": ["adventure"],
        "franchise": "pixar",
        "min_age": 4,
    },

    "Dumbo": {
        "genre": ["fairy_tale"],
        "franchise": "disney",
        "min_age": 3,
    },

    "Die Wilden Hühner": {
        "genre": ["family"],
        "min_age": 4,
    },

    "Aladdin": {
        "genre": ["fairy_tale"],
        "franchise": "disney",
        "min_age": 4,
    },

    "Marvels Iron Man und seine fantastischen Freunde": {
        "series_type": "episodic",
        "genre": ["adventure"],
        "franchise": "marvel",
        "min_age": 4,
    },

    "Marvels Spidey und seine Super-Freunde": {
        "series_type": "episodic",
        "genre": ["adventure"],
        "franchise": "marvel",
        "min_age": 4,
    },

    "Bibi Blocksberg": {
        "series_type": "episodic",
        "genre": ["fantasy"],
        "franchise": "",
        # The two episodes below disagreed on min_age (5 vs 4) before this
        # field moved here - used the lower of the two, per the same
        # tie-break rule min_age's own docstring bullet already documents.
        "min_age": 4,
    },

    "Alice im Wunderland": {
        "genre": ["fantasy"],
        "franchise": "disney",
        "min_age": 5,
    },

    # Members disagreed before this entry existed - used the most common
    # value (min_age ties: the lower one): min_age: 6 x1, 5 x1
    "Alles steht Kopf": {
        "series_type": "sequel",
        "genre": ["family"],
        "franchise": "pixar",
        "min_age": 5,
    },

    "Anna und die wilden Tiere": {
        "series_type": "episodic",
        "genre": ["educational", "family"],
        "min_age": 3,
    },

    "Arielle": {
        "series_type": "sequel",
        "genre": ["fairy_tale"],
        "franchise": "disney",
        "min_age": 4,
    },

    "Bambi": {
        "series_type": "sequel",
        "genre": ["fairy_tale"],
        "franchise": "disney",
        "min_age": 4,
    },

    "Bärenbrüder": {
        "series_type": "sequel",
        "genre": ["adventure"],
        "franchise": "disney",
        "min_age": 4,
    },

    "Cars": {
        "series_type": "sequel",
        "genre": ["adventure"],
        "franchise": "pixar",
        "min_age": 4,
    },

    "Cinderella": {
        "genre": ["fairy_tale"],
        "franchise": "disney",
        "min_age": 4,
    },

    "Das Dschungelbuch": {
        "series_type": "sequel",
        "genre": ["adventure"],
        "franchise": "disney",
        "min_age": 4,
    },

    "Das kleine WIR": {
        "genre": ["family"],
        "min_age": 3,
    },

    # Members disagreed before this entry existed - used the most common
    # value (min_age ties: the lower one): min_age: 4 x3, 5 x2
    "Der König der Löwen": {
        "series_type": "sequel",
        "genre": ["adventure"],
        "franchise": "disney",
        "min_age": 4,
    },

    "Die Eiskönigin": {
        "series_type": "sequel",
        "genre": ["fantasy"],
        "franchise": "disney",
        "min_age": 4,
    },

    "Die Monster AG": {
        "series_type": "sequel",
        "genre": ["fantasy"],
        "franchise": "pixar",
        "min_age": 4,
    },

    # Members disagreed before this entry existed - used the most common
    # value (min_age ties: the lower one): franchise: disney x2, None x1
    "Die Schöne und das Biest": {
        "series_type": "sequel",
        "genre": ["fairy_tale"],
        "franchise": "disney",
        "min_age": 4,
    },

    "Die Unglaublichen": {
        "series_type": "sequel",
        "genre": ["adventure"],
        "franchise": "pixar",
        "min_age": 5,
    },

    "Dr. Brumm": {
        "genre": ["family"],
        "min_age": 3,
    },

    "Drachenzähmen leicht gemacht": {
        "series_type": "sequel",
        "genre": ["adventure", "fantasy"],
        "min_age": 4,
    },

    "Fluch der Karibik": {
        "series_type": "sequel",
        "genre": ["adventure", "fantasy"],
        "franchise": "disney",
        "min_age": 7,
    },

    "Jim Knopf": {
        "genre": ["adventure", "fantasy"],
        "min_age": 6,
    },

    "Kung Fu Panda": {
        "series_type": "sequel",
        "genre": ["adventure"],
        "franchise": "dreamworks",
        "min_age": 5,
    },

    "Lieselotte": {
        "genre": ["family"],
        "min_age": 3,
    },

    "Lilo & Stitch": {
        "series_type": "sequel",
        "genre": ["adventure"],
        "franchise": "disney",
        "min_age": 4,
    },

    "Madagascar": {
        "series_type": "sequel",
        "genre": ["adventure"],
        "franchise": "dreamworks",
        "min_age": 4,
    },

    "Merida": {
        "genre": ["adventure"],
        "franchise": "pixar",
        "min_age": 5,
    },

    # Members disagreed before this entry existed - used the most common
    # value (min_age ties: the lower one): min_age: 3 x7, 4 x3
    "Michel aus Lönneberga": {
        "series_type": "episodic",
        "genre": ["family"],
        "min_age": 3,
    },

    "Micky Maus": {
        "genre": ["family"],
        "franchise": "disney",
        "min_age": 4,
    },

    "Minions": {
        "series_type": "sequel",
        "genre": ["adventure", "family"],
        "min_age": 6,
    },

    "Mulan": {
        "series_type": "sequel",
        "genre": ["adventure"],
        "franchise": "disney",
        "min_age": 5,
    },

    "National Geographic Kids": {
        "series_type": "episodic",
        "genre": ["educational"],
        "min_age": 4,
    },

    "Paddington": {
        "series_type": "sequel",
        "genre": ["adventure", "family"],
        "min_age": 6,
    },

    # Members disagreed before this entry existed - used the most common
    # value (min_age ties: the lower one): min_age: 4 x3, 5 x1, 6 x1
    "Peter Pan": {
        "series_type": "sequel",
        "genre": ["fairy_tale"],
        "franchise": "disney",
        "min_age": 4,
    },

    "Pettersson und Findus": {
        "genre": ["family"],
        "min_age": 4,
    },

    "Pippi Langstrumpf": {
        "series_type": "episodic",
        "genre": ["family"],
        "min_age": 4,
    },

    "Planes": {
        "genre": ["adventure"],
        "franchise": "pixar",
        "min_age": 4,
    },

    "Pocahontas": {
        "genre": ["adventure"],
        "franchise": "disney",
        "min_age": 4,
    },

    "Ralph Reichts": {
        "series_type": "sequel",
        "genre": ["adventure"],
        "franchise": "disney",
        "min_age": 4,
    },

    "Shrek": {
        "series_type": "sequel",
        "genre": ["fantasy"],
        "franchise": "dreamworks",
        "min_age": 4,
    },

    # Members disagreed before this entry existed - used the most common
    # value (min_age ties: the lower one): genre: ['family', 'fantasy'] x10, ['adventure', 'fantasy'] x6, ['adventure', 'family'] x3, ['fairy_tale', 'fantasy'] x2, ['educational', 'family', 'fantasy'] x1, ['fairy_tale', 'family'] x1
    "Sofia die Erste": {
        "series_type": "episodic",
        "genre": ["family", "fantasy"],
        "franchise": "disney",
        "min_age": 4,
    },

    "Susi und Strolch": {
        "series_type": "sequel",
        "genre": ["adventure"],
        "franchise": "disney",
        "min_age": 4,
    },

    "Tarzan": {
        "series_type": "sequel",
        "genre": ["adventure"],
        "franchise": "disney",
        "min_age": 4,
    },

    "Toy Story": {
        "series_type": "sequel",
        "genre": ["adventure"],
        "franchise": "pixar",
        "min_age": 4,
    },

    "Vaiana": {
        "series_type": "sequel",
        "genre": ["adventure"],
        "franchise": "disney",
        "min_age": 6,
    },

    "Wendy": {
        "series_type": "sequel",
        "genre": ["adventure", "family"],
        "min_age": 7,
    },

    "Wieso? Weshalb? Warum? ERSTLESER": {
        "series_type": "episodic",
        "genre": ["educational"],
        "min_age": 4,
    },

    # Members disagreed before this entry existed - used the most common
    # value (min_age ties: the lower one): min_age: 3 x3, 4 x1
    "Winnie Puuh": {
        "series_type": "sequel",
        "genre": ["adventure"],
        "franchise": "disney",
        "min_age": 3,
    },

    # Members disagreed before this entry existed - used the most common
    # value (min_age ties: the lower one): min_age: 5 x1, 4 x1
    "Zoomania": {
        "series_type": "sequel",
        "genre": ["adventure"],
        "franchise": "disney",
        "min_age": 4,
    },
}

ITEM_OVERRIDES: dict[str, dict] = {
    "OLAK5uy_nq01DAF8UIqd0DwFcoxsaDpg4h8PtPTrE": {
        "description": "Ein kleiner Waldbewohner trainiert für einen Sprungwettbewerb und hilft trotz eigener Enttäuschung einem Freund.",
        "series": "Vom kleinen Waschbären",
        "position_in_series": 3,
        "source_release_year": 2021,
    },

    "OLAK5uy_nCWBT4bA-q87liqUOENx23lPwvPgcbsGQ": {
        "description": "Ein Spielzeug wird entführt und droht, für immer in einer Vitrine zu landen – seine Freunde starten eine Rettungsmission.",
        "series": "Toy Story",
        "position_in_series": 2,
        "source_release_year": 1999,
    },

    "OLAK5uy_mjxCxdV6s25c7zdhmQVBuYQKSTquPNXXg": {
        "description": "Ein tollpatschiger kleiner Waldbewohner fühlt sich wertlos, bis ihm ein weiser Beschützer seine besondere Gabe zeigt.",
        "series": "Vom kleinen Waschbären",
        "position_in_series": 1,
        "source_release_year": 2018,
    },

    "OLAK5uy_kpvpzW_UgVGOGWo_mXaVT5mANQjn3ImoE": {
        "description": "Ein kleiner Waldbewohner überwindet seine Angst vor einem dunklen Wald, um einem verirrten Tierkind zu helfen.",
        "series": "Vom kleinen Waschbären",
        "position_in_series": 2,
        "source_release_year": 2020,
    },

    "OLAK5uy_nKlD7cYYo8KyInjqQBpomB2CN4dUCSMdQ": {
        "series": "Woozle Goozle",
        "description": "Eine verrückte Aufräum-Erfindung sortiert eine Wohnung komplett falsch und sorgt für heillose Unordnung.",
        "source_release_year": 2023,
    },

    "OLAK5uy_mevSprrlnuRBvRFA1Uea9OStKs-Q5m0ns": {
        "series": "Woozle Goozle",
        "description": "Ein chaotischer, zaubernder Erfinder zieht bei einem Moderator ein und stellt dessen Alltag auf den Kopf.",
        "source_release_year": 2023,
    },

    "OLAK5uy_mFc2YnxX8zB1ouLPkg7-OmMR0u-RkM96E": {
        "series": "Woozle Goozle",
        "description": "Eine Erfindung gegen zu viel Müll zeigt kindgerecht, wie jeder Einzelne die Umwelt schützen kann.",
        "source_release_year": 2013,
    },

    "OLAK5uy_lnLOLZ3J_uDb7VbbgnDGFn9rMbm7LgMpA": {
        "series": "Woozle Goozle",
        "description": "Eine verrückte Erfindung schickt die Handlung ins Weltall und erklärt kindgerecht, wie Raketen fliegen.",
        "source_release_year": 2013,
    },

    "OLAK5uy_meWNxB9thLqeRT9V4RbA5L8p4NARi2hFE": {
        "series": "Woozle Goozle",
        "description": "Eine Zeitreise in eine Pyramide erweckt versehentlich einen jahrtausendealten Geist, der gebändigt werden muss.",
        "source_release_year": 2013,
    },

    "OLAK5uy_k9c8uu09srJKPjTzfCYvrvRv13e25pPt8": {
        "series": "Woozle Goozle",
        "description": "Eine Zeitreise beschwört versehentlich einen echten Dinosaurier ins Studio, den es wieder loszuwerden gilt.",
        "source_release_year": 2013,
    },

    "OLAK5uy_lC5tPsq9j9nSwnGryjSRnbxejSZ9PkPZU": {
        "series": "Woozle Goozle",
        "description": "Eine Erfindung führt in heißen Sand und erklärt kindgerecht, wie Tiere und Pflanzen in der Wüste überleben.",
        "source_release_year": 2013,
    },

    "OLAK5uy_nS7sTCy2vEvzEVXoHAvs-YL38vrTDl7W4": {
        "series": "Woozle Goozle",
        "description": "Eine misslungene Erfindung sorgt für spannende Fakten darüber, wie wilde Jäger in der Natur überleben.",
        "source_release_year": 2013,
    },

    "OLAK5uy_l4XO4NTh3dMZBcWhBODAe-untZECmit3o": {
        "series": "Woozle Goozle",
        "description": "Eine chaotische Erfindung macht die unsichtbare Luft um uns herum kindgerecht erlebbar und erklärbar.",
        "source_release_year": 2013,
    },

    "OLAK5uy_nFNmIE5tMHRgeno4JUYCZLsyf7AzYG-wY": {
        "series": "Woozle Goozle",
        "description": "Eine missglückte Erfindung führt zu spannenden Fakten darüber, wie Haie leben und jagen.",
        "source_release_year": 2013,
    },

    "OLAK5uy_kw-kphVJT-Dex1pVXSajrkrUi6X3w5gQc": {
        "series": "Woozle Goozle",
        "description": "Eine missglückte Erfindung erklärt kindgerecht, wie unsere Augen funktionieren und wir die Welt wahrnehmen.",
        "source_release_year": 2013,
    },

    "OLAK5uy_k0FC1tqzbUMF0Lh2ia8di5ocbCK1SStbI": {
        "series": "Woozle Goozle",
        "description": "Eine schlaflose Erfindungsnacht erklärt kindgerecht, warum Schlaf so wichtig ist und was dabei im Körper passiert.",
        "source_release_year": 2013,
    },

    "OLAK5uy_mP62jcOCIhzRKePsZBBxLALt7K7sHF6zw": {
        "series": "Woozle Goozle",
        "description": "Eine Erfindung schickt die Handlung Richtung Weltall und erklärt kindgerecht, warum der Mond sein Gesicht ändert.",
        "source_release_year": 2013,
    },

    "OLAK5uy_mk0nnDSsTDf4U4gNUUqqzISNhoJ6O76LE": {
        "series": "Woozle Goozle",
        "description": "Eine Erfindung führt tief unter die Erde und erklärt kindgerecht, wie Höhlen entstehen und wer dort lebt.",
        "source_release_year": 2013,
    },

    "OLAK5uy_mfbbqV4YMLsu3bxzyLcAP-aAPZr0ZDEHE": {
        "series": "Woozle Goozle",
        "description": "Zwischen schaurigen Experimenten wird kindgerecht erklärt, warum uns manche Dinge eine Gänsehaut bereiten.",
        "source_release_year": 2013,
    },

    "OLAK5uy_nlAUFhCAIR-l1PyTTpETlDpU8k-kcbi4k": {
        "series": "Woozle Goozle",
        "description": "Eine misslungene Erfindung zeigt kindgerecht, wie aus einfachem Sand durch Hitze funkelndes Glas entsteht.",
        "source_release_year": 2013,
    },

    "OLAK5uy_k6CFmTjSs_dOfvFNp2RPZLZIZziTEN0xo": {
        "series": "Woozle Goozle",
        "description": "Ein Erfindungsunfall bringt kindgerecht näher, wie Strom entsteht und wofür man ihn überall braucht.",
        "source_release_year": 2013,
    },

    "OLAK5uy_mpnbjEDw3z31tO0i0qWH1mG5VfBu6pT-w": {
        "series": "Woozle Goozle",
        "description": "Eine schiefgelaufene Erfindung erklärt kindgerecht, wie ein Fahrrad funktioniert und sicher genutzt wird.",
        "source_release_year": 2013,
    },

    "OLAK5uy_kAKPndRKv5i5ye3OQj6v4FbAP2QCVSIdg": {
        "series": "Sofia die Erste",
        "description": "Bei einem Fest unter lauter Prinzen und einer ersten Übernachtungsparty muss sich ein Mädchen in ihrer neuen Rolle beweisen.",
        "position_in_series": 1,
        "source_release_year": 2013,
    },

    "OLAK5uy_lsprJDxiy7VybynYIzHqFXCve4R9EAPfo": {
        "series": "Sofia die Erste",
        "description": "Eine neue Zauberschule in einem fernen Königreich empfängt ihre ersten Schüler und steckt voller unentdeckter Magie.",
        "position_in_series": 1,
        "source_release_year": 2026,
        "variant": "remake",
    },

    "OLAK5uy_lug6b7z2iyGn_54YVJ6zwr12VQTMcdG9I": {
        "series": "Sofia die Erste",
        "description": "Eine Prinzessin wird zur Lehrlingszauberin ernannt, während ein kleines Missgeschick für großes königliches Chaos sorgt.",
        "position_in_series": 2,
        "source_release_year": 2013,
    },

    "OLAK5uy_l8iQUtEpebR5iYCaBFfKpkUqf78mNgZwY": {
        "series": "Sofia die Erste",
        "description": "Beim Zauberunterricht und einer schwungvollen Tanztruppe steckt so manches Missgeschick noch volle Magie.",
        "position_in_series": 2,
        "source_release_year": 2026,
        "variant": "remake",
    },

    "OLAK5uy_nBltjiSPG-kakIW3xXrvINU13Bc16CbGk": {
        "series": "Sofia die Erste",
        "description": "Ein musikalisches Trollfest und die Begegnung mit einer schüchternen Prinzessin bringen neue Freundschaften und viel Mut.",
        "position_in_series": 3,
        "source_release_year": 2013,
    },

    "OLAK5uy_mv4gAAP6Odi6_uTTazXSNDl-3liITyWC4": {
        "series": "Sofia die Erste",
        "description": "Eine Begegnung mit dem Volk der Meerjungfrauen führt zum Bau eines schwimmenden Palastes und einer wichtigen Freundschaft.",
        "position_in_series": 4,
        "source_release_year": 2013,
    },

    "OLAK5uy_mQqVhss7QvBmRIhWUw10F3OUADYC0ihks": {
        "series": "Sofia die Erste",
        "description": "Eine Reise in ein fernes Wüstenreich und ein Haustier-Wettbewerb stellen eine junge Prinzessin vor neue Herausforderungen.",
        "position_in_series": 5,
        "source_release_year": 2013,
    },

    "OLAK5uy_nljg55LpPMXqCJBzVdehVg_uJdQ1zJoPk": {
        "series": "Sofia die Erste",
        "description": "Ein fröhliches Familienfest und eine knifflige Prüfung, die wahre königliche Tugenden auf die Probe stellt, stehen im Mittelpunkt.",
        "position_in_series": 6,
        "source_release_year": 2013,
        "seasonal": "winter",
    },

    "OLAK5uy_nrt0UCAnDjETpOUk3m09vXx6oXFB2EJww": {
        "series": "Sofia die Erste",
        "description": "Eine strenge neue Lehrerin sorgt für Unruhe, während ein Zauber ein Mädchen auf Schmetterlingsgröße schrumpfen lässt.",
        "position_in_series": 7,
        "source_release_year": 2013,
    },

    "OLAK5uy_lTvsmqnsMt_A3LVadVOtBCYdYwBft2laM": {
        "series": "Sofia die Erste",
        "description": "Eine eifersüchtige junge Zauberin belegt eine Prinzessin mit einem Fluch, den diese gemeinsam mit ihren Freunden brechen muss.",
        "position_in_series": 8,
        "source_release_year": 2014,
    },

    "OLAK5uy_kJtpRjSCQYRBHzGcuFWeZXvYVcSdwExU0": {
        "series": "Sofia die Erste",
        "description": "Ein verzaubertes Festessen gerät aus den Fugen, während ein spannendes Flugrennen um eine besondere Krone entbrennt.",
        "position_in_series": 9,
        "source_release_year": 2014,
    },

    "OLAK5uy_nPXV9opit7OoyvSLOZky30FrLpcxBf87s": {
        "series": "Sofia die Erste",
        "description": "Ein magischer Brunnen erfüllt Wünsche auf überraschende Weise, und eine Höhlenexpedition verlangt Mut und Teamgeist.",
        "position_in_series": 10,
        "source_release_year": 2014,
    },

    "OLAK5uy_n6xgrygYLw9Tcy_Vqp1JZe1YjoMoYcoXk": {
        "series": "Sofia die Erste",
        "description": "Eine herzliche Geschenkidee im Winter und die aufgeregte Suche nach einem vermissten geflügelten Pferd bewegen die Freunde.",
        "position_in_series": 11,
        "source_release_year": 2014,
        "seasonal": "winter",
    },

    "OLAK5uy_m0hPKy1P9QE2y4thZYMeKW1iadAuFqLqQ": {
        "series": "Sofia die Erste",
        "description": "Ein frisch befreiter Flaschengeist sorgt mit seinen Wünschen für Chaos, während hilfsbedürftige Fabelwesen Unterstützung brauchen.",
        "position_in_series": 12,
        "source_release_year": 2015,
    },

    "OLAK5uy_nsBJzhXHfYJRL5b7ePWT8USaWr8pyBsA0": {
        "series": "Sofia die Erste",
        "description": "Eine magische Bibliothek entführt in alte Legenden, darunter die Geschichte einer mürrischen Hexerei-Lehrerin.",
        "position_in_series": 13,
        "source_release_year": 2015,
    },

    "OLAK5uy_lbf91eQEV3A3nORpohOSLq7Azpkw6TpQE": {
        "series": "Sofia die Erste",
        "description": "Eine feierliche Hexenzeremonie und ein farbenfrohes Drachenfest sorgen für aufregende Tage voller Magie und Tradition.",
        "position_in_series": 14,
        "source_release_year": 2016,
    },

    "OLAK5uy_mfop4nUZTa3yXn_jSyktOg_ICrAp6T4fM": {
        "series": "Sofia die Erste",
        "description": "Eine Verwechslung zwischen zwei ähnlichen Häschen und ein stürmisches Abenteuer stellen die Freunde vor kuriose Prüfungen.",
        "position_in_series": 15,
        "source_release_year": 2015,
    },

    "OLAK5uy_lxdgvEfuiIPgRmECUgmmb9kTEmux6AQwY": {
        "series": "Sofia die Erste",
        "description": "Die wahre Kraft eines magischen Amuletts kommt bei einem großen Treffen mächtiger Zauberer ans Licht.",
        "position_in_series": 16,
        "source_release_year": 2017,
    },

    "OLAK5uy_lpiIii1iLyhhFL7Wy6C8vHbTTC8whLSJM": {
        "series": "Sofia die Erste",
        "description": "Zwei Bibliotheksgeschichten erwecken die Legenden eines tapferen Ritters und einer ewigen Flamme zum Leben.",
        "position_in_series": 17,
        "source_release_year": 2016,
    },

    "OLAK5uy_nVUTWZvOA-dqFFi1d3hV92bVEabd_2ynE": {
        "series": "Sofia die Erste",
        "description": "Ein Open-Air-Feriencamp und ein chaotischer königlicher Urlaub bringen eine Familie auf unerwartete Abenteuer.",
        "position_in_series": 18,
        "source_release_year": 2016,
    },

    "OLAK5uy_llnq4P2pxrf1zc_vdTBvLz-ez_WnVfuww": {
        "series": "Sofia die Erste",
        "description": "Eine Reise zu geheimnisvollen, magischen Inseln eröffnet eine völlig neue Welt voller Legenden und Verantwortung.",
        "position_in_series": 19,
        "source_release_year": 2017,
    },

    "OLAK5uy_k4XygqSrQHNwhprBGCpc56lm9elFk-mnw": {
        "series": "Sofia die Erste",
        "description": "Auf den geheimnisvollen Inseln warten weitere Abenteuer, bei denen Mut und Freundschaft über Legenden entscheiden.",
        "position_in_series": 20,
        "source_release_year": 2017,
    },

    "OLAK5uy_mlk7hz4fh71O1wdELogfNrOF4GDTTXHHU": {
        "series": "Sofia die Erste",
        "description": "Ein Mädchen wird über Nacht zur Prinzessin und muss sich in ihrer neuen königlichen Familie und deren Welt erst zurechtfinden.",
        "source_release_year": 2012,
    },

    "OLAK5uy_mq9EeCSkGMZo4Yd57MTMfeRbTbo-Vz5Ig": {
        "description": "Um den Hof der Großmutter zu retten, trainiert ein Mädchen mit einem verängstigten Turnierpferd für einen wichtigen Wettkampf.",
        "series": "Wendy",
        "position_in_series": 2,
        "source_release_year": 2018,
    },

    "OLAK5uy_mZyuypM6NnuR7S94P0ILBiILhZb1zpfmw": {
        "description": "Ein höflicher Bär aus einem fernen Land sucht in einer belebten Stadt ein neues Zuhause und findet eine warmherzige Familie.",
        "series": "Paddington",
        "position_in_series": 1,
        "source_release_year": 2014,
    },

    "OLAK5uy_mRKqn604hzD9BAuYk2pSlsPZkuk1S1Jac": {
        "description": "Ein junger Mann sucht nach einem legendären Dreizack, während ein untoter Rachegeist aus der Geisterwelt zurückkehrt.",
        "series": "Fluch der Karibik",
        "position_in_series": 5,
        "source_release_year": 2017,
    },

    "OLAK5uy_mL8XIakMMGbRpzYl0N-AP-MIUMNITYX1U": {
        "description": "Ein obdachloses Mädchen mit besonderer Gabe fürs Zuhören stellt sich grauen Männern entgegen, die Menschen die Zeit stehlen.",
        "source_release_year": 1973,
        "series": "Momo",
    },

    "OLAK5uy_mKGgQ71T2VGF0rcXlUGcGsvSEPR0JYhjw": {
        "description": "Ein listiger Pirat gerät auf der Suche nach einer sagenhaften Quelle der Jugend in die Fänge eines gefürchteten Freibeuters.",
        "series": "Fluch der Karibik",
        "position_in_series": 4,
        "source_release_year": 2011,
    },

    "OLAK5uy_mIHPHb9OHta6RPjd3vZR2gKpkLgQkRNzE": {
        "description": "Ein ehrenhafter Pirat verbündet sich mit ungewöhnlichen Gefährten, um ein verfluchtes Schiff und seine untote Crew zu stoppen.",
        "series": "Fluch der Karibik",
        "position_in_series": 1,
        "source_release_year": 2003,
    },

    "OLAK5uy_nXC4mIAq9Sj5bpJzmXSECKqR7YazNv1pQ": {
        "description": "Ein kleiner gelber Helfer will unbedingt einer berüchtigten Bande angehören und gerät dabei in ein großes Abenteuer.",
        "series": "Minions",
        "position_in_series": 2,
        "source_release_year": 2022,
    },

    "OLAK5uy_my-pnR6u4KmFr-2cAIyyTnfMk3o9QHBzM": {
        "description": "Zwei kurze Wissensgeschichten erklären, wie ein Alligator mit seinen Zähnen Beute packt und wie Delfine unter Wasser atmen.",
        "series": "Anna und die wilden Tiere",
        "position_in_series": 2,
        "source_release_year": 2014,
    },

    "OLAK5uy_mT2UX0HWg_1S5tn-0MG3dAWyDGGpOey2Q": {
        "description": "Zwei kurze Wissensgeschichten zeigen, wie ein ausgebildeter Greifvogel jagt und wie ein Wildpferd in freier Natur lebt.",
        "series": "Anna und die wilden Tiere",
        "position_in_series": 1,
        "source_release_year": 2014,
    },

    "OLAK5uy_mHtO9kOClycCW1UkRokDP_sZ6yuc2_YSM": {
        "description": "Mehrere Verbündete und Rivalen reisen an den Rand der Welt, um einen gefangenen Freund aus einer anderen Dimension zu retten.",
        "series": "Fluch der Karibik",
        "position_in_series": 3,
        "source_release_year": 2007,
    },

    "OLAK5uy_lybh9C2bHKFrnj6fEAq9kU_kJPIgCZKXc": {
        "description": "Ein Findelkind und sein Freund verlassen mit einer sprechenden Lokomotive ihre Heimatinsel und geraten in ein fantastisches Reich.",
        "series": "Jim Knopf",
        "position_in_series": 1,
        "source_release_year": 1960,
    },

    "OLAK5uy_lbROi7OjKXwQxch1kN21HaP3eQHOeMjAM": {
        "description": "Kleine gelbe Helfer suchen über Jahrzehnte nach dem passenden furchteinflößenden Herrscher, dem sie treu dienen können.",
        "series": "Minions",
        "position_in_series": 1,
        "source_release_year": 2015,
    },

    "OLAK5uy_lAHSAzFZyP9SPNLxVEhJJO01k8TMPNv-E": {
        "description": "Ein Pirat muss eine alte Schuld bei einem furchteinflößenden Herrscher der Meere begleichen, bevor seine Seele verloren ist.",
        "series": "Fluch der Karibik",
        "position_in_series": 2,
        "source_release_year": 2006,
    },

    "OLAK5uy_kp_48MvIdf0CIOQxb2AdhGM5eDR0lqSW0": {
        "description": "Ein höflicher Bär möchte ein besonderes Geschenk besorgen, wird fälschlich verdächtigt und muss seine Unschuld beweisen.",
        "series": "Paddington",
        "position_in_series": 2,
        "source_release_year": 2017,
    },

    "OLAK5uy_kkjjRgEkLkOx0fcpHfYdtvXwIMZhsJOAA": {
        "description": "Ein Mädchen mit Angst vor Pferden schließt auf dem Hof der Großmutter Freundschaft mit einem geretteten Zirkuspferd.",
        "series": "Wendy",
        "position_in_series": 1,
        "source_release_year": 2017,
    },

    "OLAK5uy_kXXiCH2EvFSH5mkuKU5178pgs6qPtVcDk": {
        "description": "Ein obdachloses Mädchen mit besonderer Gabe fürs Zuhören stellt sich grauen Männern entgegen, die Menschen die Zeit stehlen.",
        "source_release_year": 2025,
        "series": "Momo",
        "variant": "remake",
    },

    "OLAK5uy_kSXJbi_AM-BZOZGnNwgSRlAdIoXryVSN8": {
        "description": "In einer Silvesternacht wetteifern zwei boshafte Verwandte und zwei tierische Verbündete per Zaubertrank um das Weltschicksal.",
        "genre": ["adventure", "fantasy"],
        "min_age": 10,
        "source_release_year": 1989,
        "seasonal": "winter",
    },

    "OLAK5uy_mxe83gXRcV-vpR7KXHM_SbLW6hgzAw5eg": {
        "description": "Nach einem seiner Streiche muss ein einfallsreicher Bauernjunge zur Strafe geduldig kleine Schnitzfiguren anfertigen.",
        "series": "Michel aus Lönneberga",
        "source_release_year": 2006,
    },

    "OLAK5uy_mwEsI9hkHG6ZqR2xj2CrhRFZpuFqwWpbs": {
        "description": "Mehrere kurze Geschichten erzählen von den Streichen eines einfallsreichen Jungen auf einem alten schwedischen Bauernhof.",
        "series": "Michel aus Lönneberga",
        "source_release_year": 2006,
    },

    "OLAK5uy_mgZx2NeY8E2oDeS0foWwg9-kdhvI5aMEk": {
        "description": "Ein einfallsreicher Junge beschließt, sein Leben besonders lustig zu gestalten, und sorgt damit prompt für neue Verwicklungen.",
        "series": "Michel aus Lönneberga",
        "source_release_year": 2022,
    },

    "OLAK5uy_mcXFSFjoT4GZOScOR06oBQG5Sm6sqDYpM": {
        "description": "Ein gut gemeinter, aber improvisierter Versuch, einem schmerzenden Zahn Abhilfe zu verschaffen, gerät gründlich aus den Fugen.",
        "series": "Michel aus Lönneberga",
        "source_release_year": 2023,
    },

    "OLAK5uy_llBB5F09mR-y59xOqfXtfxSUZudMv-JGg": {
        "description": "Ein gutmütiger, aber tollpatschiger Junge sorgt mit seinen wohlgemeinten Einfällen auf dem Hof für herrliches Chaos.",
        "series": "Michel aus Lönneberga",
        "source_release_year": 2006,
    },

    "OLAK5uy_lV7PzLThlgVveps5dBBB5qerDijjowsf8": {
        "description": "Ein gutgemeinter Aufräum-Eifer sorgt dafür, dass auf dem heimischen Hof am Ende mehr Chaos herrscht als vorher.",
        "genre": ["family"],
        "min_age": 3,
        "source_release_year": 2022,
        "series": "Michel aus Lönneberga",
    },

    "OLAK5uy_lCSZHmbFIwd-aqQxqpg_5ka6NxrDQze44": {
        "description": "Ein Junge erreicht nach zahllosen kleinen Streichen einen besonderen Meilenstein beim Schnitzen hölzerner Figuren.",
        "genre": ["family"],
        "source_release_year": 2022,
        "min_age": 3,
        "series": "Michel aus Lönneberga",
    },

    "OLAK5uy_kpve6O1MFeJC2innaukfOraWOEHyomjHE": {
        "description": "Ein kleiner Schabernack endet damit, dass ein Junge mit dem Kopf in einer Schüssel feststeckt und alle in Aufregung versetzt.",
        "series": "Michel aus Lönneberga",
        "source_release_year": 2022,
    },

    "OLAK5uy_kd0_YxNi0eb3vdTqZi6QmNDSDtwlAFnzE": {
        "description": "Mitten in einer gefährlichen Situation beweist ein kleiner Schlingel unerwarteten Mut und rettet damit den Tag.",
        "series": "Michel aus Lönneberga",
        "source_release_year": 2023,
    },

    "OLAK5uy_nY3qxurbWZa4pzbm8JA3MMsioemOZSVT0": {
        "description": "Ein außergewöhnlich starkes, freies Mädchen lebt ganz ohne Erwachsene und stellt mit Witz alle Regeln auf den Kopf.",
        "series": "Pippi Langstrumpf",
        "position_in_series": 1,
        "source_release_year": 1969,
    },

    "OLAK5uy_nHgfEWQDvuyKHUT0kvzngSzSUSjllsTKg": {
        "description": "Ein enttäuschter Ogre schließt einen fatalen Handel und muss in einer veränderten Welt seinen Platz zurückerobern.",
        "series": "Shrek",
        "position_in_series": 4,
        "source_release_year": 2010,
    },

    "OLAK5uy_nDascpKMwl-XKJgHvO7JRsOsyifohwdek": {
        "description": "Ein ungewöhnlich starkes Mädchen segelt über den Ozean, um auf einer fernen Insel ihrem Vater wiederzubegegnen.",
        "series": "Pippi Langstrumpf",
        "source_release_year": 1970,
    },

    "OLAK5uy_n3Ek0cI8PqEMMGp3cL3U6voDqM9A6MZ30": {
        "description": "Ein mürrischer Ogre muss eine verzauberte Prinzessin retten, um sein geliebtes Sumpfgrundstück zurückzubekommen.",
        "series": "Shrek",
        "source_release_year": 2001,
        "position_in_series": 1,
    },

    "OLAK5uy_mkvpySvpPKL798u7sVB9QOjUktXNf9ujE": {
        "description": "Mehrere stimmungsvolle Geschichten erzählen von Vorfreude, Bräuchen und kleinen Wundern rund um die Weihnachtszeit.",
        "series": "Pippi Langstrumpf",
        "source_release_year": 2023,
    },

    "OLAK5uy_mQFbkCAfkXkVlkb-f2jCISNXOgaBul4YU": {
        "description": "Ein frisch verheirateter Ogre besucht die Schwiegereltern und gerät dabei in einen verhängnisvollen Zaubertrank-Plan.",
        "series": "Shrek",
        "position_in_series": 2,
        "source_release_year": 2004,
    },

    "OLAK5uy_lpeOSlCQ8RBlILpLlDR3Dz-uJLJtuSZpw": {
        "description": "Nach einem seiner Streiche muss ein einfallsreicher Bauernjunge zur Strafe geduldig kleine Schnitzfiguren anfertigen.",
        "series": "Michel aus Lönneberga",
        "position_in_series": 2,
        "source_release_year": 1972,
    },

    "OLAK5uy_lmOJ1gTwh30H-TrvMDMoJ0Be9tRO0qoN8": {
        "description": "Ein gutmütiger, aber tollpatschiger Junge sorgt mit seinen wohlgemeinten Einfällen auf dem Hof für herrliches Chaos.",
        "series": "Michel aus Lönneberga",
        "position_in_series": 3,
        "source_release_year": 1973,
    },

    "OLAK5uy_lhfkB_yItthzO_C1F_dYkObZgVH_O1vyU": {
        "description": "Ein freches, überstarkes Mädchen bringt mit seinen ungewöhnlichen Ideen Schule und feine Gesellschaft durcheinander.",
        "series": "Pippi Langstrumpf",
        "source_release_year": 1970,
    },

    "OLAK5uy_lfvKt1ir8O7DL8jyN5QAHtlwLdC1bcl4w": {
        "description": "Eine Mädchenclique gründet ihre eigene Geheimbande und legt sich dabei mit einer rivalisierenden Jungsbande an.",
        "source_release_year": 1998,
        "series": "Die Wilden Hühner",
    },

    "OLAK5uy_lVVg83AXD4QkbSCAhKDZA5q2EvVHIm9SU": {
        "description": "Eine eingeschworene Mädchenclique meistert gemeinsam neue Herausforderungen und hält trotz mancher Streitereien zusammen.",
        "source_release_year": 2006,
        "series": "Die Wilden Hühner",
    },

    "OLAK5uy_kxipbeZe4CHEDGG1IBNMOE1q3BGCBgFrc": {
        "description": "Ausgebrochene Zootiere schließen sich einem Wanderzirkus an, um quer durch Europa nach Hause zu gelangen.",
        "series": "Madagascar",
        "position_in_series": 3,
        "source_release_year": 2012,
    },

    "OLAK5uy_kmiqlQPkr6sSI4PRvR3CjCdbFqPomUAbY": {
        "description": "Ein widerwilliger Thronerbe sucht auf einem chaotischen Roadtrip einen Ersatz, während zu Hause eine Rebellion droht.",
        "series": "Shrek",
        "position_in_series": 3,
        "source_release_year": 2007,
    },

    "OLAK5uy_kbJDfgokRifVHGPKcvNyBaYZqBIz7U03c": {
        "description": "Mehrere warmherzige Geschichten begleiten Kinder durch die aufregende Zeit rund um ihren ersten Schultag.",
        "series": "Pippi Langstrumpf",
        "source_release_year": 2013,
    },

    "OLAK5uy_kavr8OpgdL8Qtw2ub1MVC8b0vH80vwwHI": {
        "series": "Pippi Langstrumpf",
        "source_release_year": 1969,
        "description": "Ein ungewöhnlich starkes Mädchen gerät mit seinen Freunden in ein Abenteuer rund um Schmuggler und eine alte Schatzkarte.",
    },

    "OLAK5uy_kOc5vs0YA5NABjQPNRHBOcLfqszgQVc7M": {
        "description": "Ein Team schlagfertiger Pinguine muss einen finsteren Tintenfisch aufhalten, der niedliche Tiere in Monster verwandeln will.",
        "series": "Madagascar",
        "source_release_year": 2014,
        "variant": "spin_off",
    },

    "OLAK5uy_k-aHXnvyhnC0p4MNew35XinqIbS5Jvu6A": {
        "description": "Ein einsamer Junge taucht durch ein magisches Buch in ein Fantasiereich ein, das er vor dem drohenden Verschwinden retten muss.",
        "genre": ["fantasy"],
        "min_age": 6,
        "source_release_year": 1984,
    },

    "OLAK5uy_mL2Ydsjrz__6YtptLzkVTGpN0z5ZJ3LLo": {
        "description": "Ein Sachbuch erklärt kindgerecht den Aufbau unseres Planeten und seine unterschiedlichen Lebensräume.",
        "series": "Wieso? Weshalb? Warum? ERSTLESER",
        "source_release_year": 2022,
    },

    "OLAK5uy_mbB340T6ZWP1Ye3KeWjC4ytHkuiDvkaSU": {
        "description": "Ein Sachbuch erklärt kindgerecht, warum unsere Umwelt geschützt werden muss und wie jeder helfen kann.",
        "series": "Wieso? Weshalb? Warum? ERSTLESER",
        "source_release_year": 2024,
    },

    "OLAK5uy_n4vQH1g4_Qk9Ij7Sn4zD3eAwVDKKjdOS8": {
        "description": "Ein Sachbuch stellt eines der größten Landtiere der Welt vor und erklärt sein Leben in freier Wildbahn.",
        "series": "National Geographic Kids",
        "source_release_year": 2025,
    },

    "OLAK5uy_nGenFwsRj9UiyyW_JeToWUcO0etjOh4Ew": {
        "description": "Ein Sachbuch erklärt kindgerecht Planeten, Sterne und wie Menschen den Weltraum erforschen.",
        "series": "Wieso? Weshalb? Warum? ERSTLESER",
        "source_release_year": 2021,
    },

    "OLAK5uy_nAlhlyxHDGjVpvRs-W4LM8j50-F2xAdgc": {
        "description": "Ein Sachbuch stellt Tiere vor, die mit Gift, Kraft oder scharfen Zähnen zu den gefährlichsten der Welt zählen.",
        "series": "Wieso? Weshalb? Warum? ERSTLESER",
        "source_release_year": 2025,
    },

    "OLAK5uy_ns497l-VGiCDHY8isQtKoh4o0ZI4sJD8g": {
        "description": "Ein Sachbuch erklärt kindgerecht Regeln, Technik und Geschichte des beliebtesten Mannschaftssports der Welt.",
        "series": "Wieso? Weshalb? Warum? ERSTLESER",
        "source_release_year": 2022,
    },

    "OLAK5uy_ndeAfpo0H_mtFpkFOFbP0eEWgjh_B_Yhc": {
        "description": "Ein Sachbuch erklärt kindgerecht, wie Pflanzen, Tiere und Jahreszeiten in der Natur zusammenhängen.",
        "series": "Wieso? Weshalb? Warum? ERSTLESER",
        "source_release_year": 2023,
    },

    "OLAK5uy_na3dYToTEBsVvR33aA_z95Sr3pvtfYkdA": {
        "description": "Ein Sachbuch erklärt kindgerecht, wie man verschiedene Haustiere richtig versorgt und glücklich macht.",
        "series": "Wieso? Weshalb? Warum? ERSTLESER",
        "source_release_year": 2023,
    },

    "OLAK5uy_nMxG6i6DEkViOWjdGLAYngZopGWJRcT1E": {
        "description": "Ein Sachbuch stellt beeindruckende Meeresbewohner vor und erklärt ihr Leben in den Ozeanen der Welt.",
        "series": "Wieso? Weshalb? Warum? ERSTLESER",
        "source_release_year": 2021,
    },

    "OLAK5uy_nH3xWRvDFx8sDNPhnGHy2-iMd7Dublbgc": {
        "description": "Ein Sachbuch stellt urzeitliche Riesenechsen vor und erklärt, wie sie lebten und warum sie ausstarben.",
        "series": "Wieso? Weshalb? Warum? ERSTLESER",
        "source_release_year": 2021,
    },

    "OLAK5uy_m1vGyI1cCVDDIrlQ3E1aE2nf_YHp8fznM": {
        "series": "National Geographic Kids",
        "source_release_year": 2025,
        "description": "Ein Sachbuch entführt in einen artenreichen Regenwald voller ungewöhnlicher Pflanzen und Tiere.",
    },

    "OLAK5uy_lf8B7Rto_FygtNXHgTIdYBMSjvxxQyG6U": {
        "description": "Ein Sachbuch erklärt kindgerecht, wie Vulkane entstehen, ausbrechen und die Landschaft verändern.",
        "series": "Wieso? Weshalb? Warum? ERSTLESER",
        "source_release_year": 2021,
    },

    "OLAK5uy_lKbxnL7WVRObRcYz5Tp2fa32E0HX-4Esg": {
        "description": "Ein Sachbuch erklärt kindgerecht, wie Roboter funktionieren und wofür Menschen sie heute einsetzen.",
        "series": "Wieso? Weshalb? Warum? ERSTLESER",
        "source_release_year": 2024,
    },

    "OLAK5uy_lAqv091MpJfrFD0SEzyVcEGfLNBgK08IA": {
        "description": "Ein Sachbuch erklärt kindgerecht, wie der eigene Körper aufgebaut ist und wie seine Organe zusammenarbeiten.",
        "series": "Wieso? Weshalb? Warum? ERSTLESER",
        "source_release_year": 2025,
    },

    "OLAK5uy_kitKFs_XpbGaVTHs9ZRGYY3trDOOzNmEc": {
        "description": "Ein Sachbuch erklärt kindgerecht, wie Pferde leben, sich verhalten und richtig gepflegt werden.",
        "series": "Wieso? Weshalb? Warum? ERSTLESER",
        "source_release_year": 2022,
    },

    "OLAK5uy_kY0Cy58kGjyp9Ov0JEl5v9gqK4YIPpNkU": {
        "description": "Ein Sachbuch nimmt junge Leser mit auf eine Entdeckungstour durch das Ökosystem eines dichten Waldes.",
        "series": "Wieso? Weshalb? Warum? ERSTLESER",
        "source_release_year": 2026,
    },

    "OLAK5uy_kZBkWFFqzaqgwwZGF1AwSUGL_wHIG9v-Q": {
        "description": "Ein Sachbuch nimmt junge Leser mit auf eine Zeitreise zu Pyramiden, Pharaonen und dem Alltag einer alten Hochkultur.",
        "series": "Wieso? Weshalb? Warum? ERSTLESER",
        "source_release_year": 2023,
    },

    "OLAK5uy_kGp0YUtjUPAWWvwOEIeqsY-71h68udgdk": {
        "series": "Wieso? Weshalb? Warum? ERSTLESER",
        "description": "Ein Sachbuch erklärt kindgerecht, wie Ermittler Spuren lesen, Rätsel lösen und knifflige Fälle aufklären.",
        "source_release_year": 2023,
    },

    "OLAK5uy_nYGcJxw7VmlWg5YIB8mn3wLi_TUMvx1go": {
        "description": "Immer mehr Tiere ziehen nacheinander in ein Zuhause ein, bis sich zeigt, dass für alle gemeinsam noch genug Platz ist.",
        "min_age": 3,
        "source_release_year": 2012,
        "genre": ["family"],
    },

    "OLAK5uy_mSgdpKUe0h-7BG-u6A3bxDJnnahf5apAU": {
        "description": "Eine kleine Schnecke sehnt sich nach der weiten Welt und erlebt an der Seite eines riesigen Wals ein großes Abenteuer.",
        "genre": ["adventure"],
        "min_age": 3,
        "source_release_year": 2019,
    },

    "OLAK5uy_lXtRqpjY4FVX1IWO-jJTZF2L5uAnEYd5I": {
        "description": "Eine kleine, astähnliche Figur wird von ihrer Familie getrennt und kämpft sich durch Abenteuer rechtzeitig nach Hause zurück.",
        "genre": ["adventure"],
        "min_age": 3,
        "source_release_year": 2015,
    },

    "OLAK5uy_njo7N9q9TTp_plvqgqlGZJ9dAt5pD2vaU": {
        "series": "Das kleine WIR",
        "description": "Ein Gefühl der Verbundenheit zeigt, wie Familienalltag zu Hause auch in schwierigen Momenten Halt geben kann.",
        "source_release_year": 2020,
    },

    "OLAK5uy_mcglAHuM_7wXMvyLeVkS-mMUFYtp2wZuw": {
        "series": "Lieselotte",
        "description": "Eine eigenwillige Kuh hat einfach keine Lust mitzumachen und sorgt mit ihrer Sturheit für einige komische Verwicklungen.",
        "source_release_year": 2023,
    },

    "OLAK5uy_mBrrC_wKDcojNm8UGmx5QC5TWfi6oYY9A": {
        "series": "Lieselotte",
        "description": "Als ein frisch gebackener Kuchen spurlos verschwindet, ermittelt eine neugierige Kuh und deckt am Ende die Wahrheit auf.",
        "source_release_year": 2017,
    },

    "OLAK5uy_m2D0-24hp4udry6-8DgRBlx8EGaXvDzMY": {
        "series": "Dr. Brumm",
        "description": "Ein liebenswert tollpatschiger Bär erlebt weihnachtliche Missverständnisse und muss so manches erst auf seine Weise verstehen.",
        "source_release_year": 2014,
    },

    "OLAK5uy_lp-y5mAS6_UXrwUqn_y1okDAmBKULcOd8": {
        "series": "Drachenzähmen leicht gemacht",
        "description": "Ein junger Wikinger freundet sich entgegen aller Tradition mit einem gefürchteten Flugtier an und verändert damit sein Dorf.",
        "position_in_series": 1,
        "source_release_year": 2010,
    },

    "OLAK5uy_ldSjD9xoq9WWIMfZyFLzaQGuCKxoHAwY0": {
        "series": "Das kleine WIR",
        "description": "Ein Gefühl der Verbundenheit hilft einem Kind, mit den Veränderungen einer Trennung der Eltern zurechtzukommen.",
        "source_release_year": 2025,
    },

    "OLAK5uy_lcSwJzlfKp0lzirfI3KVR6_djT9exCRHc": {
        "series": "Das kleine WIR",
        "description": "Ein besonderes Gefühl der Verbundenheit zeigt Kindern, dass sie nie ganz allein sind, wenn sie mit anderen zusammen sind.",
        "source_release_year": 2016,
    },

    "OLAK5uy_l_uxeaBeYTHp7YfR_Ysla5Iy3AgFRmczA": {
        "series": "Drachenzähmen leicht gemacht",
        "description": "Jahre später entdeckt der junge Wikinger eine verborgene Welt und muss sein Dorf vor einer neuen dunklen Bedrohung schützen.",
        "position_in_series": 2,
        "source_release_year": 2014,
    },

    "OLAK5uy_lWFk46tu1C5PqYTqem3qmIIGa9DSH-DB4": {
        "series": "Das kleine WIR",
        "description": "Bei einer Geburtstagsfeier zeigt sich, wie ein Gefühl der Verbundenheit große und kleine Momente gemeinsam schöner macht.",
        "source_release_year": 2026,
    },

    "OLAK5uy_lO-HNfBu8cHuq2tq_lVcq4ukQpTwODSSg": {
        "series": "Das kleine WIR",
        "description": "Ein Gefühl der Verbundenheit begleitet ein Kind durch aufregende und manchmal unsichere Momente im Kindergartenalltag.",
        "source_release_year": 2021,
    },

    "OLAK5uy_l1jyFg5fuLBZnZR83ExwIVkHEXECt0_60": {
        "series": "Lieselotte",
        "description": "Eine eigensinnige Kuh sucht sich einen ganz eigenen Rückzugsort, nur für sich allein, fernab vom Trubel des Hofes.",
        "source_release_year": 2019,
    },

    "OLAK5uy_kr--flk-x2tuXSt0QFHKjz8aWxfHTtQlY": {
        "series": "Dr. Brumm",
        "description": "Ein tollpatschiger Bär trifft auf ein riesiges, urzeitlich anmutendes Wesen und erlebt dabei weitere kleine Alltagsabenteuer.",
        "source_release_year": 2018,
    },

    "OLAK5uy_kmeBWumod9y-EgU57lPSrKRqnEIrodndE": {
        "series": "Drachenzähmen leicht gemacht",
        "description": "Ein junger Wikinger freundet sich entgegen aller Tradition mit einem gefürchteten Flugtier an und verändert damit sein Dorf.",
        "position_in_series": 1,
        "source_release_year": 2025,
        "variant": "remake",
    },

    "OLAK5uy_kPaXIwzMyooY-lYyKWHI420DYd5ltqY8w": {
        "series": "Lieselotte",
        "description": "Eine liebenswert tollpatschige Kuh erlebt in mehreren kurzen Geschichten allerlei witzige Alltagsabenteuer auf dem Bauernhof.",
        "source_release_year": 2015,
    },

    "OLAK5uy_kWp1nCuNE9r5z_e03Id1N-3Cu55Z2WxUI": {
        "series": "Drachenzähmen leicht gemacht",
        "description": "Eine geheime Welt zwingt einen jungen Anführer, sich zwischen zwei Leben und einem schmerzhaften Abschied zu entscheiden.",
        "position_in_series": 3,
        "source_release_year": 2019,
    },

    "OLAK5uy_kCinBaMQHLf2sGZzDuJ5IMYwN6RlHyBQI": {
        "series": "Drachenzähmen leicht gemacht",
        "description": "Eine Rückblende erzählt, wie sich Menschen und geflügelte Fabelwesen einst bekämpften, bevor eine Freundschaft alles veränderte.",
        "source_release_year": 2019,
        "variant": "spin_off",
    },

    "OLAK5uy_ni1m5jqeaPnKx5RWjvTrPwAKqURbHTGGI": {
        "description": "Ein gestohlener Edelstein verwandelt Freund und Feind in Dinosaurier, später steht sogar ein Mondflug an.",
        "series": "Marvels Spidey und seine Super-Freunde",
        "position_in_series": 16,
        "source_release_year": 2021,
    },

    "OLAK5uy_ndgBGwUTo-lqxlp4IIq9oUdFyU63Hv1EQ": {
        "description": "Ein misslungener Schrumpfstrahl lässt einen kleinen Störenfried immer größer werden, dazu kommt ein Osterabenteuer.",
        "series": "Marvels Spidey und seine Super-Freunde",
        "position_in_series": 10,
        "source_release_year": 2021,
    },

    "OLAK5uy_nY4HxEvVh41vD6DxCCD-Z2i2FFBkx8aVE": {
        "description": "Ein geheimnisvoller Kristall, ein angebliches Filmmonster und ungewollte Superkräfte stellen ein Heldenteam vor Rätsel.",
        "series": "Marvels Spidey und seine Super-Freunde",
        "position_in_series": 11,
        "source_release_year": 2021,
    },

    "OLAK5uy_nX2epgcbsva26DJL8cMu5NsXzHruLf2dU": {
        "description": "Zu viel Spaß im Vergnügungspark, ein gestohlenes Vogelei und ein geklauter Riesenmagnet halten ein Heldenteam auf Trab.",
        "series": "Marvels Spidey und seine Super-Freunde",
        "position_in_series": 15,
        "source_release_year": 2021,
    },

    "OLAK5uy_nJbbhBPjIUOnM_yHX6kY3tzsdG5uWePc4": {
        "description": "Ein Team gepanzerter junger Helden will einen entspannten Ausflug machen, muss aber Roboter-Schurken aufhalten.",
        "series": "Marvels Iron Man und seine fantastischen Freunde",
        "position_in_series": 1,
        "source_release_year": 2025,
    },

    "OLAK5uy_nIZ-f_K-BjrFVZ7vEk3g3LyNahsSe5owI": {
        "description": "Ferngesteuerte Schneemänner, ein verdorbenes Fest und ein listiges Eichhörnchen bringen selbst starke Helden ins Schwitzen.",
        "series": "Marvels Spidey und seine Super-Freunde",
        "position_in_series": 8,
        "source_release_year": 2021,
    },

    "OLAK5uy_mvvU_2ODkoKDuoM6PafITo48wyMrWwszM": {
        "description": "An Halloween bedrohen ein Museumsdieb und ferngesteuerte Vogelscheuchen ein Fest, später fallen Wasser und Strom der Stadt aus.",
        "series": "Marvels Spidey und seine Super-Freunde",
        "position_in_series": 14,
        "source_release_year": 2021,
    },

    "OLAK5uy_mvaFjVIV7l_zOgZ_64ra0iihxzgW1XSP8": {
        "description": "Als ein Schurke zu Weihnachten alle Geschenke stiehlt, muss ein Team gepanzerter Freunde das Fest gemeinsam retten.",
        "series": "Marvels Iron Man und seine fantastischen Freunde",
        "position_in_series": 3,
        "source_release_year": 2025,
    },

    "OLAK5uy_muLJTaMxs6MEsxrZ6VJvW6jOOrnloU66g": {
        "description": "Ein Turm wird gekapert, ein starker Verbündeter ausgetrickst und ein wichtiges Werkzeug bedroht, während ein Kampfroboter wütet.",
        "series": "Marvels Spidey und seine Super-Freunde",
        "position_in_series": 19,
        "source_release_year": 2021,
    },

    "OLAK5uy_mt4TC0DEyjXo3dJSStdrofG5ayORcAvds": {
        "description": "Ein verzauberter Haustier-Riese, hypnotisierte Parkbesucher und abgerichtete Tauben sorgen für turbulentes Sommerchaos.",
        "series": "Marvels Spidey und seine Super-Freunde",
        "position_in_series": 4,
        "source_release_year": 2021,
    },

    "OLAK5uy_mm4zg2uv8P3vjUA47E193NFSMslUIEjH0": {
        "description": "Von einem bedrohten Erntedankfest bis zur Suche nach einem Seeungeheuer erlebt ein Heldenteam Abenteuer durchs ganze Jahr.",
        "series": "Marvels Spidey und seine Super-Freunde",
        "position_in_series": 13,
        "source_release_year": 2021,
    },

    "OLAK5uy_mi7X68Tf4KxpRiRminYdsVlZOMXFnD_mE": {
        "description": "Zwei Schurken stören abwechselnd ein Rennen und streiten um einen Riesenroboter, bis dem Team die eigenen Kräfte geraubt werden.",
        "series": "Marvels Spidey und seine Super-Freunde",
        "position_in_series": 18,
        "source_release_year": 2021,
    },

    "OLAK5uy_maiJt1sIyuCSufGA87P44YHIqPLzxfx58": {
        "description": "Zwei Freunde kleben aneinander fest, ein Schurke friert im Pool ein, und eine Ehrenparade für das Team gerät aus den Fugen.",
        "series": "Marvels Spidey und seine Super-Freunde",
        "position_in_series": 12,
        "source_release_year": 2021,
    },

    "OLAK5uy_mNkVu8OS4H6AYbj18LmuGQpKwfTrqWy3o": {
        "description": "Drei junge Helden mit Verwandlungskräften lernen, dass Teamarbeit gegen Schurkenpläne mehr bringt als Alleingänge.",
        "series": "Marvels Spidey und seine Super-Freunde",
        "position_in_series": 1,
        "source_release_year": 2021,
    },

    "OLAK5uy_mLxxPGkXvLgED7wYJOwEp8DUSzVOOQtU0": {
        "description": "Ein wildes Rieseninsekt, ein Lachgas-Diebstahl und ein fallenreicher Freizeitpark bringen ein Heldenteam in Bedrängnis.",
        "series": "Marvels Spidey und seine Super-Freunde",
        "position_in_series": 2,
        "source_release_year": 2021,
    },

    "OLAK5uy_mKBoE4bMdsTsmDGfFYZCGazSDX3wSRDg8": {
        "description": "Ein Schurke will sich mit geborgter Technik zum größeren Verbrecher aufrüsten, ein anderer sabotiert eine Halloweenparade.",
        "series": "Marvels Spidey und seine Super-Freunde",
        "position_in_series": 7,
        "source_release_year": 2021,
    },

    "OLAK5uy_m85jEkTItv0lodkpl6D7Uluq18zugoXE0": {
        "description": "Eine Riesenechse will einen Turm übernehmen, Tiere geraten auf Diebestour, und eine wichtige Energiequelle wird gestohlen.",
        "series": "Marvels Spidey und seine Super-Freunde",
        "position_in_series": 22,
        "source_release_year": 2021,
    },

    "OLAK5uy_lllMb08cdtPTyBwr82LsfHZmmuTim6VkI": {
        "description": "Zwei Schurken tun sich erst zusammen und gehen dann getrennte Wege, während eine Dammkatastrophe eine Tierfamilie gefährdet.",
        "series": "Marvels Spidey und seine Super-Freunde",
        "position_in_series": 5,
        "source_release_year": 2021,
    },

    "OLAK5uy_lkguizXTDOCO3tby0LlGLicGkTPEe5Hqg": {
        "description": "Zwei verbündete Schurken planen eine Brückensabotage, einen Piratenschatzraub und eine Parkflutung, die das Team stoppen muss.",
        "series": "Marvels Spidey und seine Super-Freunde",
        "position_in_series": 6,
        "source_release_year": 2021,
    },

    "OLAK5uy_ldyDIX6FAPvbqzEUYfd7sLHA7RzDnYoGQ": {
        "description": "Ein unsichtbar gewordener Schurke stiehlt Bienenvölker, während ein anderer Meeresbewohner und Leguane bedroht.",
        "series": "Marvels Spidey und seine Super-Freunde",
        "position_in_series": 17,
        "source_release_year": 2021,
    },

    "OLAK5uy_lOF25aD6LsH2daD6ntIeMpQIwozMhdfvY": {
        "description": "Wertvolle Schätze und Erfindungen wecken Begehrlichkeiten, sodass ein Heldenteam Museum, Insel und Freunde beschützen muss.",
        "series": "Marvels Spidey und seine Super-Freunde",
        "position_in_series": 9,
        "source_release_year": 2021,
    },

    "OLAK5uy_lOEDZb_zTk1vyUEhW4XzZvyGJvMdXd85A": {
        "description": "Als ein Schurke zu Weihnachten alle Geschenke stiehlt, muss ein Team gepanzerter Freunde das Fest gemeinsam retten.",
        "series": "Marvels Spidey und seine Super-Freunde",
        "position_in_series": 3,
        "source_release_year": 2021,
    },

    "OLAK5uy_l-SqSHZGc9D_PNbGP_r4brLaNqF-FAiWY": {
        "description": "Ein Freizeitpark verliert Strom, ein Konzert wird gestört und verzauberte Piratenhüte sorgen für Ärger, das das Team behebt.",
        "series": "Marvels Spidey und seine Super-Freunde",
        "position_in_series": 20,
        "source_release_year": 2021,
    },

    "OLAK5uy_keBsBPd8TDHN59RDOvIERlT3CQsIAjeXA": {
        "description": "Ein technisches Heldenteam muss gestohlene Erfindungen zurückholen und dabei quirlige Haustiere und listige Schurken bändigen.",
        "series": "Marvels Iron Man und seine fantastischen Freunde",
        "position_in_series": 4,
        "source_release_year": 2025,
    },

    "OLAK5uy_kR_Nvl28OMVtZSWml1nUIPNPalHx-X3wY": {
        "description": "An Halloween verteidigt ein Technik-Heldenteam Süßigkeiten und Kürbisse gegen einen irren Roboter und eine Insektenschurkin.",
        "series": "Marvels Iron Man und seine fantastischen Freunde",
        "position_in_series": 2,
        "source_release_year": 2025,
    },

    "OLAK5uy_kP_Dsbd-F_rpRx0jvMmJZN4kY7WwX8jZA": {
        "description": "Ein tobendes Monster, ein gestohlener Edelstein und entführte Leguane fordern das Team, bis Großmutter zur Rettung eilt.",
        "series": "Marvels Spidey und seine Super-Freunde",
        "position_in_series": 23,
        "source_release_year": 2021,
    },

    "OLAK5uy_kKl4DksXY3PwuKkwPC69Sg9G5ieGYriAU": {
        "description": "Ein Verjüngungsstrahl geht daneben, während ein Heldenteam Schurken bei einer Autoshow und einem Snackklau aufhalten muss.",
        "series": "Marvels Iron Man und seine fantastischen Freunde",
        "position_in_series": 6,
        "source_release_year": 2025,
    },

    "OLAK5uy_kJVI89BcsaAU9uB_t3RdWNoQoD6K9UwC4": {
        "description": "Mit einer neuen fliegenden Drohne ausgestattet, verteidigt ein Heldenteam Stadt und Natur gegen diebische Schurken.",
        "series": "Marvels Iron Man und seine fantastischen Freunde",
        "position_in_series": 5,
        "source_release_year": 2025,
    },

    "OLAK5uy_kGP0rHFspZXCbgDOUNyebn5UYHd7tzonw": {
        "description": "Gestohlene Energie legt die U-Bahn lahm, während eine Schatzsuche und eine übergroße Ameise für zusätzliches Chaos sorgen.",
        "series": "Marvels Spidey und seine Super-Freunde",
        "position_in_series": 21,
        "source_release_year": 2021,
    },

    "OLAK5uy_l-P6wjCCtVMqwx7s8rAgS4nGGjZra-reE": {
        "description": "Ein kleines Waldtier trifft auf ein furchteinfl%F6%DFendes Wesen und entdeckt dabei seine eigene Cleverness.",
        "genre": ["adventure"],
        "min_age": 3,
        "source_release_year": 2009,
    },

    "OLAK5uy_kSX5rN90rg1Usa39MZdURHzLxmvEuS17A": {
        "description": "Ein schlitzohriger Bauernjunge im alten Schweden sorgt mit seinen Streichen ständig für Chaos, hat dabei aber ein gutes Herz.",
        "series": "Michel aus Lönneberga",
        "source_release_year": 1971,
        "position_in_series": 1,
    },

    "OLAK5uy_lhF7sdKpO1AJf3tkSj0ALVsAokKjRHavs": {
        "series": "Bibi Blocksberg",
        "position_in_series": 2,
        "source_release_year": 1980,
        "description": "Eine kleine Hexe setzt in der Schule heimlich ihre Zauberkräfte ein und sorgt damit für jede Menge turbulente Verwicklungen.",
    },

    "OLAK5uy_kzVrxJgnruXuKhiBk8bc_cqqVUVEtL6-I": {
        "description": "Kinder entdecken, dass übernatürliche Wesen real existieren und müssen sich deren Herausforderungen stellen.",
        "series": "Bibi Blocksberg",
        "position_in_series": 1,
        "source_release_year": 1980,
    },

    "OLAK5uy_nxACHw7AuDsAjktLAmdJrbI1Ortwse45w": {
        "description": "Eine Gruppe tierischer Freunde verwandelt ein harmloses Fußballspiel in ein turbulentes, chaotisches Durcheinander.",
        "series": "Micky Maus",
        "source_release_year": 2006,
    },

    "OLAK5uy_nUcVxlUReyhD771ST9B_53UHaPgNNGRpk": {
        "description": "Eine wissbegierige Prinzessin der Meere verliebt sich in die Welt über der Wasseroberfläche und wagt einen folgenschweren Tausch.",
        "series": "Arielle",
        "source_release_year": 2023,
        "variant": "remake",
        "position_in_series": 1,
    },

    "OLAK5uy_nOc6WKydiRIxbcQOfc-RzJWcj2ueAJpQY": {
        "description": "Zwei erfinderische Stiefbrüder müssen ihre große Schwester retten, die von Außerirdischen in eine andere Galaxie entführt wurde.",
        "genre": ["adventure"],
        "franchise": "disney",
        "min_age": 6,
        "source_release_year": 2020,
    },

    "OLAK5uy_n0HRLnDJ5o7q1VeH0WrzXAflNYGbFgZPs": {
        "description": "Eine kleine Fee gerät versehentlich in die Menschenwelt und muss mit neuen Freunden einen Weg zurück in ihre Heimat finden.",
        "series": "Peter Pan",
        "source_release_year": 2010,
        "seasonal": "summer",
        "variant": "spin_off",
    },

    "OLAK5uy_mzo5-o7iRgmG9YJVZFY4n8VhDmYl4oAjQ": {
        "description": "Zwei ungleiche und anfangs verfeindete Studierende an einer Schule für furchteinflößende Wesen lernen, echte Freunde zu werden.",
        "series": "Die Monster AG",
        "position_in_series": 2,
        "source_release_year": 2013,
    },

    "OLAK5uy_muL8Aszjs2LS1rVQKJiwIJJX7DD1wBMHo": {
        "description": "Eine kleine Fee reist gefährlich weit, um ein magisches Objekt zu bergen, das die Jahreszeiten ihrer Heimat bedroht.",
        "series": "Peter Pan",
        "source_release_year": 2009,
        "variant": "spin_off",
    },

    "OLAK5uy_mKQtP61sPR5npHu7DZtrVFhAQdQo9V-I8": {
        "description": "Ein junger Hund, hin- und hergerissen zwischen Zuhause und Freiheit, erlebt auf der Straße ein gefährliches Abenteuer.",
        "series": "Susi und Strolch",
        "position_in_series": 2,
        "source_release_year": 2001,
    },

    "OLAK5uy_mBZHU-r4X89vIltngewixsIqZhtpZO-zo": {
        "description": "Als ein kleines Waldtier plötzlich verschwunden scheint, begeben sich seine Freunde auf eine abenteuerliche Suche nach ihm.",
        "series": "Winnie Puuh",
        "source_release_year": 1997,
    },

    "OLAK5uy_lsM_ClEpmS1qqkXy95F_RTdbkZIyvoQ5I": {
        "description": "Eine neugierige Meeresprinzessin sehnt sich nach dem Leben an Land und geht dafür einen riskanten Handel mit dunklen Mächten ein.",
        "series": "Arielle",
        "position_in_series": 1,
        "source_release_year": 1989,
    },

    "OLAK5uy_lm8n1UHMVHPKySZ-dRFs_aTYl9x_lAPDI": {
        "description": "Ein Mädchen erhält einen geheimnisvollen Schlüssel und reist durch vier magische Reiche auf der Suche nach ihrer Vergangenheit.",
        "genre": ["fairy_tale"],
        "franchise": "disney",
        "min_age": 5,
        "source_release_year": 2018,
        "seasonal": "christmas",
    },

    "OLAK5uy_lkxg2x89y5vfi44HpB_fRY77dHQ8Di7gc": {
        "description": "Eine Gruppe von Waldfreunden erlebt die wechselnden Jahreszeiten und meistert dabei herzerwärmende Alltagsabenteuer.",
        "series": "Winnie Puuh",
        "source_release_year": 1999,
    },

    "OLAK5uy_lGV65AB3Czwmze7vTqqSZsykA6kOGAMsU": {
        "description": "Ein kleines, ängstliches Waldtier fühlt sich von seinen Freunden übersehen und beweist bei einem Abenteuer unerwarteten Mut.",
        "series": "Winnie Puuh",
        "source_release_year": 2003,
    },

    "OLAK5uy_ks8WMkyqJOBbpzjTbAiouujODFK5GO_zA": {
        "description": "Ein hüpffreudiges Tier sucht nach Artgenossen und entdeckt dabei, dass wahre Familie auch aus Freunden bestehen kann.",
        "series": "Winnie Puuh",
        "source_release_year": 2000,
    },

    "OLAK5uy_kloVPhJNdAVWUVn_1CCAeEouwp4UjICTw": {
        "description": "Ein Waisenjunge im Wald freundet sich mit einem unsichtbaren Fabelwesen an, das ihn beschützt und Erwachsene misstrauisch macht.",
        "genre": ["fantasy"],
        "min_age": 4,
        "source_release_year": 2016,
    },

    "OLAK5uy_kUz3yb-KbwBsK2pslAd08fwHVPsAdfjNg": {
        "description": "Ein einsamer Aufräumroboter auf verlassener Erde findet durch den Besuch eines anderen Roboters Hoffnung und Zuneigung.",
        "genre": ["adventure"],
        "franchise": "pixar",
        "min_age": 4,
        "source_release_year": 2008,
    },

    "OLAK5uy_kKXhJ6GTzojNC72P50parWidxdJ1-EbRI": {
        "description": "Trotz eines Verbots fühlt sich die Tochter eines ungewöhnlichen Paares zum Meer und seinen Geheimnissen hingezogen.",
        "series": "Arielle",
        "position_in_series": 2,
        "source_release_year": 2000,
    },

    "OLAK5uy_k1jgDzLL5A_fwHbvbDv3ZoghjzX7_eJW8": {
        "description": "Bevor Gesang im Unterwasserreich verboten wird, entdeckt eine junge Prinzessin ihre Liebe zur Musik und zur Welt über den Wellen.",
        "series": "Arielle",
        "source_release_year": 2008,
        "variant": "spin_off",
    },

    "OLAK5uy_nsb0OsuUyDuhKW52EFCLTMv0-vMJ0zBzY": {
        "description": "Ein Held kämpft gegen Ungerechtigkeit und hilft den Bedürftigen, indem er sich gegen tyrannische Machthaber aufbegehrt.",
        "genre": ["adventure"],
        "franchise": "disney",
        "source_release_year": 1973,
        "min_age": 4,
    },

    "OLAK5uy_nzOzTv6DtDwjF-fnRt5K_xSR1u4d1KWcI": {
        "description": "Ein junger Mann mit bescheidenen Anfängen entdeckt eine magische Lampe und versucht, sein Leben zu verändern und die Liebe einer Prinzessin zu gewinnen.",
        "source_release_year": 2019,
        "series": "Aladdin",
        "variant": "remake",
    },

    "OLAK5uy_ms8Lnv1d7nIyy2coHVKSSddjP5sdTp9Pg": {
        "description": "Ein Mädchen folgt einem weißen Kaninchen in eine fantastische Welt voller surrealer Abenteuer und merkwürdiger Begegnungen.",
        "genre": ["fantasy"],
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2010,
        "series": "Alice im Wunderland",
    },

    "OLAK5uy_nlEen2psNk1p9LJdZYO5gm2YKUR4aXjGA": {
        "description": "Zwei Mäuse arbeiten als Polizisten und lösen Fälle, um Gerechtigkeit herzustellen und ihre Gemeinschaft zu schützen.",
        "genre": ["adventure"],
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 1977,
    },

    "OLAK5uy_mciDVsg3oLjYKBHtNlF2rSUpzlLjep84o": {
        "description": "Ein Junge aus Holz erlebt Abenteuer und lernt, sich richtig zu verhalten.",
        "genre": ["fairy_tale"],
        "min_age": 4,
        "source_release_year": 1940,
    },

    "OLAK5uy_mTpfKq3DfbaaGH8hZxbR-5_wtmwggfjF8": {
        "description": "Ein neues freundliches Wesen kommt in den Wald und freundet sich mit den bekannten Bewohnern an.",
        "genre": ["fairy_tale"],
        "franchise": "disney",
        "min_age": 3,
        "source_release_year": 2005,
    },

    "OLAK5uy_m9K0ZDoAwreKv2zfLLzNsAbEvNcN_TOSI": {
        "description": "Eine Fee muss sich einer Piratin entgegenstellen und ein großes Abenteuer bestehen.",
        "genre": ["fairy_tale"],
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2014,
        "series": "Peter Pan",
        "variant": "spin_off",
    },

    "OLAK5uy_npX4I2rAwUnbX39bRnWaHy7jrGcKX8LSA": {
        "description": "Ein Hubschrauber und seine Freunde arbeiten zusammen, um Rettungseinsätze durchzuführen und Menschen in Not zu helfen.",
        "series": "Cars",
        "position_in_series": 2,
        "source_release_year": 2014,
        "variant": "spin_off",
    },

    "OLAK5uy_mM5uoTUzZCg1mBg1zoiNplSA6kRdlGEaw": {
        "description": "Ein Gorilla in einem Zirkus träumt von Freiheit und findet unerwartete Freundschaft in seiner Gefangenschaft.",
        "genre": ["fantasy"],
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2020,
    },

    "OLAK5uy_nvAPM1KYwDmyVcBJkDzeCvushOyCzeY1M": {
        "description": "Zwei Brüder kämpfen gemeinsam gegen Widrigkeiten und erleben abenteuerliche Herausforderungen in der Wildnis.",
        "series": "Bärenbrüder",
        "position_in_series": 1,
        "source_release_year": 2003,
    },

    "OLAK5uy_nuI_CulUwubWa7-lWQql_yH_HG0D7iXPc": {
        "description": "Zwei Freunde entdecken eine magische Welt, in der die Elemente Feuer und Wasser in Konflikt geraten.",
        "genre": ["fantasy"],
        "franchise": "pixar",
        "min_age": 6,
        "source_release_year": 2023,
    },

    "OLAK5uy_nnhLzV862YYp4wwic75VSXQJWCvxYr0DQ": {
        "description": "Eine Familie mit Superkräften muss sich aus dem Ruhestand zurückmelden, um die Welt zu retten.",
        "series": "Die Unglaublichen",
        "position_in_series": 1,
        "source_release_year": 2004,
    },

    "OLAK5uy_nmCLOP7hjBJtEVIMEvi0uOwH1RaakvUo8": {
        "description": "Ein Kaiser verliert seine Herrschaft und muss sich in die Wildnis begeben, um seine Macht zurückzugewinnen.",
        "genre": ["adventure"],
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2000,
    },

    "OLAK5uy_ngoV8tTYHGlQlh8x0YOYlFd-O8YaIlJG0": {
        "description": "Ein aufblasbarer Roboter erlebt chaotische und humorvolle Abenteuer voller unerwarteter Wendungen.",
        "genre": ["adventure"],
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2014,
    },

    "OLAK5uy_nyEgHwTQFtmweDI4mDC-ID0nCH_Tz33PM": {
        "description": "Kinder müssen sich in der digitalen Welt gegen böse Mächte verteidigen und Abenteuer bestehen.",
        "series": "Ralph Reichts",
        "position_in_series": 2,
        "source_release_year": 2018,
    },

    "OLAK5uy_nf9pDKOq0IVh-loWWSF6v2VLm-VJZAokE": {
        "description": "Eine Seele muss ihre Bestimmung finden und lernt dabei, was es bedeutet, lebendig zu sein.",
        "genre": ["fantasy"],
        "franchise": "pixar",
        "min_age": 6,
        "source_release_year": 2020,
    },

    "OLAK5uy_mRA_lATsy2YhZrrOCkTYMVQ9mBtJSwQYU": {
        "description": "Ein Koala träumt davon, einen Gesangswettbewerb zu gewinnen und findet dabei neue Freunde und Mut.",
        "genre": ["family"],
        "franchise": "dreamworks",
        "min_age": 4,
        "source_release_year": 2016,
    },

    "OLAK5uy_nc0WkNNelHnxEg2CWgqoOZxxRxguq6V78": {
        "description": "Eine Königin muss ein mysteriöses Abenteuer bestehen, um ihr Königreich und ihre Familie zu retten.",
        "series": "Die Eiskönigin",
        "position_in_series": 2,
        "source_release_year": 2019,
        "seasonal": "winter",
    },

    "OLAK5uy_neBCIjeNGVDNWSnBkoE4a0oEydUFyRH8U": {
        "description": "Ein Junge wächst im Dschungel auf und muss lernen, seinen Platz in der Welt zwischen Natur und Zivilisation zu finden.",
        "series": "Das Dschungelbuch",
        "source_release_year": 2016,
        "variant": "remake",
        "position_in_series": 1,
    },

    "OLAK5uy_mjxN270TdL5rlzL-7Opa2YRiBetDBTwAs": {
        "description": "Ein Kürbiskopf-König entdeckt die Weihnachtswelt und plant, das Fest auf seine eigene düstere Weise zu übernehmen.",
        "genre": ["fantasy"],
        "franchise": "disney",
        "min_age": 6,
        "source_release_year": 1993,
        "seasonal": "christmas",
    },

    "OLAK5uy_neRq_XHTqVD1AWQcTs8E7FQL08KB8sOr4": {
        "description": "Ein Mädchen rettet einen verletzten Eichhörnchen und erlebt gemeinsam mit ihm magische Abenteuer.",
        "genre": ["fantasy"],
        "franchise": "disney",
        "min_age": 8,
        "source_release_year": 2021,
    },

    "OLAK5uy_nJRQQEIIqbhr4kzAJBvDOQLP35g6bNCQM": {
        "description": "Zwei Brüder entdecken einen magischen Weg und müssen sich einer Herausforderung stellen, um ihre Welt zu retten.",
        "genre": ["fantasy"],
        "franchise": "pixar",
        "min_age": 6,
        "source_release_year": 2020,
    },

    "OLAK5uy_nZhJ91S_mNEFmyFMvV-N8bY3mhxq2e8-U": {
        "description": "Tiere erleben wilde Abenteuer in der Natur und lernen dabei wichtige Lektionen über Freundschaft und Zusammenhalt.",
        "genre": ["adventure"],
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2006,
    },

    "OLAK5uy_m8WNpYCFjKdk-ddt7gKQNLmY---s83epc": {
        "description": "Ein Abenteuer in einer fantastischen Stadt, wo verschiedene Tiere zusammenleben und gemeinsam Herausforderungen meistern.",
        "series": "Zoomania",
        "position_in_series": 1,
        "source_release_year": 2016,
    },

    "OLAK5uy_mlBwAOSeO8VJhCoRM4guDX6imu4giVs8k": {
        "description": "Eine Gruppe von Insekten erlebt Abenteuer in ihrer winzigen Welt voller Gefahren und Überraschungen.",
        "genre": ["adventure"],
        "franchise": "pixar",
        "min_age": 4,
        "source_release_year": 1998,
    },

    "OLAK5uy_n2rqUY97UHsO4XcWOTzPbb4bvFl_NhBQg": {
        "description": "Eine Dalmatinerfamilie muss ihre 99 entführten Welpen vor einem bösen Plan retten.",
        "genre": ["adventure"],
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 1961,
    },

    "OLAK5uy_n7GLXBULfc3ScSzTSQeallIozR5ba4a6M": {
        "description": "Eine Prinzessin mit magischen Kräften muss lernen, ihre Fähigkeiten zu akzeptieren und ihre Schwester zu retten.",
        "series": "Die Eiskönigin",
        "position_in_series": 1,
        "source_release_year": 2013,
        "seasonal": "winter",
    },

    "OLAK5uy_nWV9JLxDYVffi_Y3z6dWybb7awjLeRvkw": {
        "description": "Eine dunkle Kreatur kämpft gegen ihre böse Vergangenheit und entdeckt unerwartete Verbindungen zu ihrer Welt.",
        "genre": ["fantasy"],
        "franchise": "disney",
        "min_age": 6,
        "source_release_year": 2014,
    },

    "OLAK5uy_ncTsRBl3ihS8xc2fXuo2lPv04dO1f6KC0": {
        "description": "Kleine Hüpfer erleben Abenteuer in ihrer Welt und lernen Lektionen über Freundschaft und Mut.",
        "genre": ["adventure"],
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2026,
    },

    "OLAK5uy_n2-ZUhnXeGYmaywf4AcpFudjR10JsbrQo": {
        "description": "Ein Junge entdeckt seine außergewöhnlichen Fähigkeiten und begibt sich auf eine kosmische Reise der Selbstfindung.",
        "genre": ["fantasy"],
        "franchise": "pixar",
        "min_age": 6,
        "source_release_year": 2025,
    },

    "OLAK5uy_muFPBJI4TLYs5fNENHVPal57RJqqrkZ0w": {
        "description": "Woody und seine Freunde erleben ein neues Abenteuer, wenn sich ihre Welt unerwartet verändert.",
        "series": "Toy Story",
        "position_in_series": 5,
        "source_release_year": 2025,
    },

    "OLAK5uy_mDiC8M2jC1ME7qdPJIg4exPLO4EseVCQc": {
        "description": "Ein Krieger kämpft gegen eine Bedrohung und sucht nach einem mythischen Wesen, um sein Reich zu retten.",
        "genre": ["fantasy"],
        "franchise": "disney",
        "min_age": 6,
        "source_release_year": 2021,
    },

    "OLAK5uy_n-nP-qclR2U3yjcdZ-pvwwoecfo9OGw5A": {
        "description": "Ein Kind muss lernen, Probleme durch intelligente Lösungen statt Gewalt zu bewältigen.",
        "series": "Ralph Reichts",
        "position_in_series": 1,
        "source_release_year": 2012,
    },

    "OLAK5uy_nTgjFjpGwgBQV2WCq7Ekshyy0hngwi_lg": {
        "description": "Ein Flugzeug muss eine wichtige Reise absolvieren und erlebt dabei aufregende Abenteuer in der Luft.",
        "series": "Cars",
        "source_release_year": 2013,
        "variant": "spin_off",
    },

    "OLAK5uy_nQbGAQTtMuyp_n7rO7Xz6B-Re4agRiso4": {
        "description": "Ein Krieger muss seine innere Kraft entdecken und gegen eine dunkle Bedrohung antreten, um sein Volk zu retten.",
        "series": "Kung Fu Panda",
        "position_in_series": 3,
        "source_release_year": 2016,
    },

    "OLAK5uy_mk1rApVK6CxC1T7JfYx53jaJE0BtApAaE": {
        "description": "Ein Spielzeug muss sich neuen Herausforderungen stellen und lernt, dass Freundschaft verschiedene Formen annehmen kann.",
        "series": "Toy Story",
        "position_in_series": 4,
        "source_release_year": 2019,
    },

    "OLAK5uy_mYT2vME3GNSy2akeG5jc9rA74RR-OduYk": {
        "description": "Eine Gruppe von Abenteurern erforscht die Ruinen einer legendären versunkenen Zivilisation und enthüllt deren mysteriöse Geheimnisse.",
        "genre": ["adventure"],
        "franchise": "disney",
        "source_release_year": 2001,
        "min_age": 4,
    },

    "OLAK5uy_mF7TtT8TcZBNPj2wNOsygEGUxPB9fhJRc": {
        "description": "Ein Mädchen verkleidet sich als Soldat, um ihren kranken Vater vor dem Kriegsdienst zu bewahren.",
        "series": "Mulan",
        "source_release_year": 2020,
        "variant": "remake",
        "position_in_series": 1,
    },

    "OLAK5uy_mLkUymz-JBD0gR3Cl9KcbaDmajDq_tETs": {
        "description": "Ein Junge belebt seinen verstorbenen Hund durch wissenschaftliche Experimente wieder zum Leben.",
        "genre": ["fantasy"],
        "franchise": "disney",
        "min_age": 6,
        "source_release_year": 2012,
        "seasonal": "halloween",
    },

    "OLAK5uy_mNqk3ri39BDq8HqCdr6vftp0EJ04JRp7g": {
        "description": "Ein Mensch mit körperlichen Unterschieden findet Zuflucht in einem Turm und entdeckt Freundschaft, Liebe und seinen Platz in der Welt.",
        "genre": ["fairy_tale"],
        "franchise": "disney",
        "min_age": 5,
        "source_release_year": 1996,
    },

    "OLAK5uy_mIHDTjeetGqr7X1LLJrNQdhLAiHO6bVbA": {
        "description": "Ein Leidenschaftlicher Kampf um Kulinarischen Erfolg in der Küche einer renommierten Gaststätte.",
        "genre": ["adventure"],
        "franchise": "pixar",
        "min_age": 4,
        "source_release_year": 2007,
    },

    "OLAK5uy_mIc-VWkQW1EornvdVdv8CIFfq5OOnloAE": {
        "description": "Ein Mädchen überwindet Widrigkeiten und findet durch Mut und Güte sein Glück.",
        "genre": ["fairy_tale"],
        "min_age": 4,
        "source_release_year": 1950,
        "series": "Cinderella",
        "position_in_series": 1,
    },

    "OLAK5uy_mUJXtJvaGm1o19boWNKPn9zU-am8OXRXQ": {
        "description": "Ein Junge wächst im Dschungel auf und muss sich gegen Gefahren behaupten, während er seine Identität und seinen Platz in der Welt entdeckt.",
        "series": "Das Dschungelbuch",
        "position_in_series": 1,
        "source_release_year": 1967,
    },

    "OLAK5uy_m_hm-SUaGplqMI8ht6iZeN7Js5r_cB-rk": {
        "description": "Eine Gruppe von Jugendlichen muss sich neuen emotionalen Herausforderungen und inneren Konflikten stellen.",
        "series": "Alles steht Kopf",
        "position_in_series": 2,
        "source_release_year": 2024,
    },

    "OLAK5uy_mWaaL1fk_QUpmiBrEtFRf7UFhdvEO6G2g": {
        "description": "Kinder erleben mysteriöse und ungewöhnliche Abenteuer in einer rätselhaften Welt voller Geheimnisse.",
        "genre": ["adventure"],
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2022,
    },

    "OLAK5uy_mRKkcj-jZYsoxx6zexSQUI0UZSbKFvmpE": {
        "description": "Eine Familie erlebt Abenteuer auf einer einsamen Insel und muss sich gegen Gefahren behaupten.",
        "genre": ["adventure"],
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2007,
    },

    "OLAK5uy_mDRgeNmjkLEFg78lW_cGP8klR11L6d-0Y": {
        "description": "Ein junger Mensch, aufgewachsen in der Wildnis, muss seine Identität entdecken und seinen Platz zwischen zwei Welten finden.",
        "series": "Tarzan",
        "position_in_series": 2,
        "source_release_year": 2005,
    },

    "OLAK5uy_nIlfMQgrwbOxbgSPRIixxI3qt1_D4bilM": {
        "description": "Ein Schneemann erlebt ein Abenteuer und erfährt, was es bedeutet, in der wärmeren Jahreszeit zu bestehen.",
        "series": "Die Eiskönigin",
        "source_release_year": 2017,
        "seasonal": "winter",
    },

    "OLAK5uy_mCUNR-Av0GzcrZ9vfuaOIIMlNVBg-95Q8": {
        "description": "Eine Familie mit magischen Gaben muss ihre übernatürlichen Kräfte nutzen, um ihre Gemeinde zu retten.",
        "genre": ["fantasy"],
        "franchise": "disney",
        "min_age": 6,
        "source_release_year": 2021,
    },

    "OLAK5uy_lzZjFEUpcdHvCgOVFvkFxuQyprGBHRF-4": {
        "description": "Ein Weltraumabenteuer, in dem ein Astronaut versucht, nach Hause zurückzukehren.",
        "series": "Toy Story",
        "source_release_year": 2022,
        "variant": "spin_off",
    },

    "OLAK5uy_m3oJuBguPxtknzSnqvQSMGWn6ICf6BPWE": {
        "description": "Ein Kind entdeckt einen gefährlichen Pilz und muss herausfinden, wie man ihn bekämpft, bevor er alles zerstört.",
        "genre": ["adventure"],
        "source_release_year": 2022,
        "min_age": 5,
    },

    "OLAK5uy_mBHMZ1XX4yUic_FiPIypUCbKt-H5bWJxI": {
        "description": "Ein sterblicher Held muss seine göttlichen Kräfte nutzen, um gegen das Böse zu kämpfen und seinen Platz in der Welt zu finden.",
        "genre": ["adventure"],
        "franchise": "disney",
        "min_age": 5,
        "source_release_year": 1997,
    },

    "OLAK5uy_nymLr2m79sxm1PiRL15od7M6KP7-v8RjM": {
        "description": "Eine Fee entdeckt ihre magischen Kräfte und findet ihren Platz in einer fantastischen Welt voller Abenteuer.",
        "genre": ["fairy_tale"],
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2008,
        "series": "Peter Pan",
    },

    "OLAK5uy_ly--6KeCsZMRhG4nTI6uXdIbFEwkaJgo0": {
        "description": "Ein Orchesterwerk wird zum Leben erweckt, wenn Musik und Animation in einer fantastischen Welt verschmelzen.",
        "genre": ["fantasy"],
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 1940,
    },

    "OLAK5uy_lvpbmPh_EH97rOu6rYGC-4mGVtaisBILM": {
        "description": "Zwei Brüder erleben gemeinsam Abenteuer in der Wildnis und müssen zusammenarbeiten, um Herausforderungen zu meistern.",
        "series": "Bärenbrüder",
        "position_in_series": 2,
        "source_release_year": 2006,
    },

    "OLAK5uy_lvH5U1ug8PcYe-QvcLqbTdtx3N30W6M8c": {
        "description": "Ein junges Tier wächst in der Natur auf und erlebt Abenteuer, während es die Welt und sich selbst entdeckt.",
        "series": "Bambi",
        "position_in_series": 1,
        "source_release_year": 1942,
    },

    "OLAK5uy_lqa1SNw9mLihZLbNKqzV7EHhwcC45smGk": {
        "description": "Ein Kind erlebt fantastische Abenteuer in einer Spiegelwelt voller magischer Begegnungen und rätselhafter Wunder.",
        "series": "Alice im Wunderland",
        "source_release_year": 2016,
    },

    "OLAK5uy_leU1mji7v0fy9yN2_zCsV9AmCJdGd5vWs": {
        "description": "Eine Prinzessin verfällt durch einen Fluch in einen magischen Schlaf und kann nur durch wahre Liebe erlöst werden.",
        "genre": ["fairy_tale"],
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 1959,
    },

    "OLAK5uy_lqHhBfvgUONgvYU_GOw0L_LIsPd5IXNxU": {
        "description": "Ein alternder Rennwagen muss lernen, sich an neue Zeiten anzupassen und findet dabei neue Ziele jenseits des Sieges.",
        "series": "Cars",
        "position_in_series": 3,
        "source_release_year": 2017,
    },

    "OLAK5uy_loAK3fXOH3uOo3T00so5cPnGsYsspZpEQ": {
        "description": "Ein junger Elefant mit großen Ohren entdeckt seine außergewöhnliche Fähigkeit und findet seinen Platz in der Welt.",
        "source_release_year": 1941,
        "series": "Dumbo",
    },

    "OLAK5uy_laDw1u6K1Y8EKAIzNmwF-43MveI_b8CmY": {
        "description": "Ein Junge wächst im Dschungel auf und muss sich zwischen seiner wilden Heimat und der Zivilisation zurechtfinden.",
        "series": "Tarzan",
        "position_in_series": 1,
        "source_release_year": 1999,
    },

    "OLAK5uy_lUDeeTyS6wmAkZhng8HTRfU6UGoCyyeos": {
        "description": "Eine Katze und ihre Kätzchen werden entführt, aber freundliche Streuner helfen ihnen auf ihrer Reise zurück nach Hause.",
        "genre": ["adventure"],
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 1970,
    },

    "OLAK5uy_lQOL4rgUSsbYG3I9Z1MLN9BdaFXQHFPAE": {
        "description": "Eine junge Frau überbrückt kulturelle Grenzen und findet ihre eigene Stimme in einer Zeit des Konflikts.",
        "series": "Pocahontas",
        "position_in_series": 1,
        "source_release_year": 1995,
    },

    "OLAK5uy_lEqQksSC8weTFhGAnsA35Z63nTbnOuz5A": {
        "description": "Ein außerirdisches Wesen strandet auf der Erde und freundet sich mit einem einsamen Mädchen an, während es lernt, was Familie bedeutet.",
        "series": "Lilo & Stitch",
        "position_in_series": 1,
        "source_release_year": 2002,
    },

    "OLAK5uy_lO86h88tvQMYISO9_3k3r7YKYK1pHhwxE": {
        "description": "Eine Familie mit Superkräften muss zusammenarbeiten, um die Welt vor einer neuen Bedrohung zu bewahren.",
        "series": "Die Unglaublichen",
        "position_in_series": 2,
        "source_release_year": 2018,
    },

    "OLAK5uy_lNX0rUnIGzy7-JFvKbs0oSxpAzRCPRed8": {
        "description": "Ein Kind macht sich auf eine magische Reise, um einen geheimen Wunsch wahr werden zu lassen.",
        "genre": ["fantasy"],
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2023,
    },

    "OLAK5uy_lEAY5We7uhhjeCuw89LgsAc9i0qTk8NLc": {
        "description": "Ein Mädchen überwindet Widrigkeiten und findet sein Glück durch Mut und Güte.",
        "genre": ["fairy_tale"],
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2015,
        "series": "Cinderella",
        "variant": "remake",
    },

    "OLAK5uy_l7ClnZldSsZzHDTXeJcysmnEZEG-eX-8s": {
        "description": "Ein Junge entdeckt die Welt der Toten und muss seine verstorbene Familie finden.",
        "genre": ["fantasy"],
        "franchise": "pixar",
        "min_age": 6,
        "source_release_year": 2017,
    },

    "OLAK5uy_lCgHBJzv-CF-T6PoTuphles7HQtVvqFbk": {
        "description": "Ein Spielzeug muss lernen, dass es nicht das Wichtigste in der Welt eines Kindes ist, wenn ein neues Spielzeug ankommt.",
        "series": "Toy Story",
        "position_in_series": 1,
        "source_release_year": 1995,
    },

    "OLAK5uy_l2vxY1WGKjDMX16cSsSDCbHmEvLnClm2M": {
        "description": "Eine Prinzessin flieht vor einer bösen Königin und findet Zuflucht bei freundlichen Waldwesen.",
        "genre": ["fairy_tale"],
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 1937,
    },

    "OLAK5uy_kwrZs3W4PNH-aJRUvkOoafbOS_J9zJ7Oo": {
        "description": "Ein junger Straßendieb findet eine magische Lampe und erhält die Chance, sein Leben völlig zu verändern.",
        "source_release_year": 1992,
        "series": "Aladdin",
    },

    "OLAK5uy_kw0MiYKPgMzBzH1tAu11nE6Lc4rxh2Wsk": {
        "description": "Ein Junge entdeckt eine verborgene Stadt in den Wolken und muss sich gegen dunkle Kräfte behaupten.",
        "genre": ["adventure"],
        "franchise": "pixar",
        "min_age": 6,
        "source_release_year": 2009,
    },

    "OLAK5uy_kundgUTfQdcOpKXKaj6VVik5VxrVXv8qw": {
        "description": "Bauernhoftiere geraten in chaotische Abenteuer, wenn sie sich selbstständig machen und Unsinn anstellen.",
        "genre": ["adventure"],
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2004,
    },

    "OLAK5uy_koI0XDzfqYw2soOwJEqtP1FyiAJP_ebuU": {
        "description": "Ein Junge entdeckt ein Geheimnis über seine Herkunft und findet an der Küste unerwartete Freundschaft.",
        "genre": ["fantasy"],
        "franchise": "pixar",
        "min_age": 5,
        "source_release_year": 2021,
        "seasonal": "summer",
    },

    "OLAK5uy_kmLVCReazoOwmF9XVVvgYXJ1RdOPzZFa0": {
        "description": "Ein Geheimagent-Auto wird in einen internationalen Spionagefall verwickelt und muss seine Familie schützen.",
        "series": "Cars",
        "position_in_series": 2,
        "source_release_year": 2011,
    },

    "OLAK5uy_kg0qHwby8-YPdDmP6iH5zfEOj8wsfZOb4": {
        "description": "Ein junges Mädchen entdeckt die innere Schönheit eines verzauberten Wesens und bricht damit einen bösen Fluch.",
        "series": "Die Schöne und das Biest",
        "source_release_year": 2017,
        "variant": "remake",
        "position_in_series": 1,
    },

    "OLAK5uy_ntT0Ve6F3NTuC3KRTgr1O_f44fnPpKBfQ": {
        "description": "Ein Mädchen muss lernen, über Äußerlichkeiten hinauszuschauen und wahre innere Schönheit zu erkennen.",
        "series": "Die Schöne und das Biest",
        "position_in_series": 1,
        "source_release_year": 1991,
    },

    "OLAK5uy_ke-thGtflnODrBMuezYbYpy8QSpbdP1Oc": {
        "description": "Ein Krieger muss sich seiner Vergangenheit stellen und gegen eine dunkle Bedrohung kämpfen, um sein Volk zu retten.",
        "series": "Kung Fu Panda",
        "position_in_series": 2,
        "source_release_year": 2011,
    },

    "OLAK5uy_kccPvfF199D-xEUPPp_9ge7FqbtuapX4c": {
        "description": "Ein junges Tier wächst in der Wildnis auf und muss lernen, sich in seiner Umgebung zurechtzufinden und seine Rolle zu finden.",
        "series": "Bambi",
        "position_in_series": 2,
        "source_release_year": 2006,
    },

    "OLAK5uy_kbbd0cygGfWMW8OM_IxE4YJ6lD1Hnlfgo": {
        "description": "Ein Abenteuer im Zoo, in dem Tiere zusammenarbeiten, um ein Geheimnis zu lösen und ihre Gemeinschaft zu schützen.",
        "series": "Zoomania",
        "position_in_series": 2,
        "source_release_year": 2025,
    },

    "OLAK5uy_k_xP81n2cp-CAuB8a65pUed-5h4Ixmp44": {
        "description": "Ein Mädchen mit magischen Haaren entdeckt die Welt jenseits seiner Isolation und findet dabei seine wahre Bestimmung.",
        "genre": ["fairy_tale"],
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2010,
    },

    "OLAK5uy_kYcYRfvNlZbJJd16ilNswjluxiSvnybuM": {
        "description": "Ein Auto lernt, dass Freundschaft und Gemeinschaft wichtiger sind als Erfolg und Ruhm.",
        "series": "Cars",
        "position_in_series": 1,
        "source_release_year": 2006,
    },

    "OLAK5uy_kV11E1FyEC12rrZSiP1wtUxU3TT5c-MOw": {
        "description": "Spielzeuge müssen sich einer neuen Herausforderung stellen, als sie in ein Kindergarten-Abenteuer geraten.",
        "series": "Toy Story",
        "position_in_series": 3,
        "source_release_year": 2010,
    },

    "OLAK5uy_kUG2V3s93Gvc4JFFHZpdGhEK5FkNvdJs0": {
        "description": "Eine Gruppe macht sich auf die Suche nach einem legendären Schatz auf einem geheimnisvollen Planeten.",
        "genre": ["adventure"],
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2002,
    },

    "OLAK5uy_kRMBgAEPpzLpCzNhW1ErpslqDegTTTDTA": {
        "description": "Eine Geschichte über die ungewöhnliche Freundschaft zwischen zwei Charakteren aus unterschiedlichen Welten, die gemeinsam Abenteuer erleben.",
        "genre": ["fantasy"],
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2005,
    },

    "OLAK5uy_kQ3XTPCT37ZXx2lumLYJ6DKbFwChnkXYs": {
        "description": "Ein Superhund-Filmstar muss lernen, dass seine echten Kräfte in Freundschaft und Mut liegen.",
        "genre": ["adventure"],
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2008,
    },

    "OLAK5uy_kOGO310iCRP9ATXkZav6dptn8EDHe38ho": {
        "description": "Eine Gruppe von Tieren muss ihre Heimat verlassen und erlebt aufregende Abenteuer auf ihrer Reise zurück.",
        "series": "Madagascar",
        "position_in_series": 2,
        "source_release_year": 2008,
    },

    "OLAK5uy_kNTbcVMS1WuJM23pQQcX4xADhDgfgdE30": {
        "description": "Eine Geschichte über innere Gefühle und Emotionen, die zum Leben erwachen und gemeinsam Abenteuer erleben.",
        "series": "Alles steht Kopf",
        "position_in_series": 1,
        "source_release_year": 2015,
    },

    "OLAK5uy_kK8J9XSQLPWmc5hItx9qU9ybeMTvuoPlM": {
        "description": "Ein Mädchen kämpft gegen Tradition und Schicksal, um ihr eigenes Abenteuer zu bestimmen.",
        "series": "Merida",
        "position_in_series": 1,
        "source_release_year": 2012,
    },

    "OLAK5uy_kIOCOVKQ1hymSZYSZitxAnc1LBtGQYobI": {
        "description": "Ein Bär und seine Freunde erleben gemeinsam zauberhafte Abenteuer im Wald voller Freundschaft und Wärme.",
        "genre": ["fairy_tale"],
        "franchise": "disney",
        "min_age": 3,
        "source_release_year": 2011,
    },

    "OLAK5uy_kHFZCUQ8uAA03ClwqmaJyGOmUuEDJmFws": {
        "description": "Eine weihnachtliche Geschichte über Großzügigkeit und Zusammensein während der Festzeit.",
        "genre": ["fairy_tale"],
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 1983,
        "seasonal": "christmas",
    },

    "OLAK5uy_kB4Blrc0yyraIEdfY1FlprO6w_yOzrhks": {
        "description": "Ein Mädchen verkleidet sich als Soldat, um ihren kranken Vater vor dem Militärdienst zu bewahren.",
        "series": "Mulan",
        "position_in_series": 1,
        "source_release_year": 1998,
    },

    "OLAK5uy_kAi57TwgXP3WVsHzZA1jz8A_NWGWPP3vM": {
        "description": "Ein außerirdisches Wesen strandet auf der Erde und freundet sich mit einem einsamen Kind an.",
        "series": "Lilo & Stitch",
        "source_release_year": 2025,
        "variant": "remake",
        "position_in_series": 1,
    },

    "OLAK5uy_k8ZIXUjGwX8GXZu4RfHEOSLYlByrxTPPQ": {
        "description": "Eine Geschichte über unerwartete Freundschaften zwischen zwei sehr unterschiedlichen Charakteren in einer fantastischen Welt.",
        "series": "Die Monster AG",
        "position_in_series": 1,
        "source_release_year": 2001,
    },

    "OLAK5uy_k8Rx3UELXDLdeVWfA9tFflFBXDMFWxtHs": {
        "description": "Ein in der Wildnis aufgewachsener Mensch muss sich zwischen seiner Natur und der Zivilisation entscheiden.",
        "series": "Tarzan",
        "source_release_year": 2013,
        "variant": "remake",
        "position_in_series": 1,
    },

    "OLAK5uy_k7tY3kG6h6qrg48K4bXmLO0QwGQ84hees": {
        "description": "Ein Straßenhund und ein verwöhnter Haushund werden Freunde und erleben gemeinsame Abenteuer in der Stadt.",
        "series": "Susi und Strolch",
        "position_in_series": 1,
        "source_release_year": 1955,
    },

    "OLAK5uy_k4GclUyGqUTnFHmSAFXgcXLUhJGu_Dg4A": {
        "description": "Ein Straßenkind und ein verwöhnter Haushund werden unerwartete Freunde und erleben gemeinsam Abenteuer.",
        "genre": ["adventure"],
        "source_release_year": 1981,
        "min_age": 4,
    },

    "OLAK5uy_k3wcD9oqepKNt2J1ZBbPuAzSwVDRx_3Gg": {
        "description": "Spielzeugen erleben Abenteuer und müssen lernen, zusammenzuarbeiten und Befehle zu befolgen.",
        "series": "Toy Story",
        "source_release_year": 2019,
        "position_in_series": 4,
        "variant": "spin_off",
    },

    "OLAK5uy_k2zoA9rd9BfKTseNVJBvIif9avP46xFws": {
        "description": "Ein verzaubertes Schloss und eine ungewöhnliche Freundschaft während der festlichen Jahreszeit.",
        "series": "Die Schöne und das Biest",
        "position_in_series": 2,
        "source_release_year": 1997,
        "seasonal": "christmas",
    },

    "OLAK5uy_k1hbEIDe47tFGg80KxSPrzJUB-Yt1lyyc": {
        "description": "Ein Mädchen träumt davon, sein Leben zu verändern und findet dabei wahre Freundschaft und innere Stärke.",
        "series": "Cinderella",
        "position_in_series": 2,
        "source_release_year": 2002,
    },

    "OLAK5uy_k1NtuVYsO5k0pEW4qvx9DYL7ZiJHJ95S0": {
        "description": "Ein Hotelmanager muss seine Unterkunft vor neugierigen Gästen schützen und dabei seine Familie bewahren.",
        "genre": ["fantasy"],
        "source_release_year": 2012,
        "seasonal": "halloween",
        "min_age": 6,
    },

    "OLAK5uy_k0su_4jE-pvnaRx3DR_uzgqvnzVHqHO_k": {
        "description": "Ein junger Elefant mit großen Ohren entdeckt seine besonderen Fähigkeiten und findet seinen Platz in der Welt.",
        "source_release_year": 2019,
        "series": "Dumbo",
        "variant": "remake",
    },

    "OLAK5uy_m5np3cQD6JI4qqyaKPFkyYJacjmepggw0": {
        "description": "Ein alter Mann und sein kluges Haustier erleben zusammen alltägliche Abenteuer voller Wärme und Humor.",
        "series": "Pettersson und Findus",
        "position_in_series": 1,
        "source_release_year": 1999,
    },

    "OLAK5uy_lAEv53WjTcYdbezfmqvoRbp0rxbCTTWSk": {
        "description": "Ein unwahrscheinlicher Held muss seine innere Kraft entdecken, um sein Dorf vor einer großen Bedrohung zu bewahren.",
        "series": "Kung Fu Panda",
        "position_in_series": 1,
        "source_release_year": 2008,
    },

    "OLAK5uy_nT1mL8aZvxqfIRFN9L8FgIzfvk6HUkd0I": {
        "description": "Vier Zootiere landen auf einer exotischen Insel und müssen sich an das Wildleben anpassen.",
        "series": "Madagascar",
        "position_in_series": 1,
        "source_release_year": 2005,
        "seasonal": "summer",
    },

    "OLAK5uy_mSqQ0DFEOq4ehi5QCmGcMbse1XPGrH9Jg": {  # Findet Nemo
        "description": "Ein Fisch macht sich auf eine gefährliche Reise durchs Meer, um seinen vermissten Sohn zu finden.",
        "series": "Findet Nemo",
        "position_in_series": 1,
        "source_release_year": 2003,
    },
    "OLAK5uy_kWp4zrOmfr7_cHq_gimr2USOc7LHme7PQ": {  # Findet Dorie
        "description": "Eine blaue Fisch sucht nach ihrer Familie und erlebt dabei ein großes Abenteuer im Meer.",
        "series": "Findet Nemo",
        "position_in_series": 2,
        "source_release_year": 2016,
    },
    "OLAK5uy_kCqtsmYi_20kuxHQf8WBmy9L7jhSnhe78": {  # Der König der Löwen (Real-Kinofilm)
        "description": "Ein junger Löwe muss sein Schicksal akzeptieren und seine Heimat vor dunklen Kräften bewahren.",
        "series": "Der König der Löwen",
        "position_in_series": 1,
        "source_release_year": 2019,
        "variant": "remake",
    },
    "OLAK5uy_m_ZAOgZp19B5aS8BSI533zAmijpecO9jc": {  # Mufasa: Der König der Löwen
        "description": "Ein verwaistes Löwenjunge trifft einen Prinzen und zusammen erleben sie eine schicksalhafte Reise voller Abenteuer und Gefahr.",
        "series": "Der König der Löwen",
    #     "position_in_series": None,
        "source_release_year": 2024,
        "variant": "spin_off",
    },
    "OLAK5uy_k5Z43Vmx4X97Cn_94eb-kYv61EYRvx4e4": {  # Der König der Löwen
        "description": "Ein junger Löwe muss nach tragischen Ereignissen ins Exil fliehen und findet später die Kraft, zu seiner Heimat zurückzukehren.",
        "series": "Der König der Löwen",
        "position_in_series": 1,
        "source_release_year": 1994,
    },
    "OLAK5uy_kUcmQbAHGkB0ML_QLqW85icbTMlbzQ7X8": {  # Der König der Löwen 2 - Simbas Königreich
        "description": "Ein junger Herrscher muss sein Reich verteidigen und seine Verantwortung als Anführer erfüllen.",
        "series": "Der König der Löwen",
        "position_in_series": 2,
        "source_release_year": 1998,
    },
    "OLAK5uy_mUHEROIxVoKVrIDtQ_C1odIq7W7JqxiDs": {  # Der König der Löwen 3 - Hakuna Matata
        "description": "Eine Geschichte über Freundschaft und das Überwinden von Hindernissen in der afrikanischen Savanne.",
        "series": "Der König der Löwen",
        "position_in_series": 3,
        "source_release_year": 2004,
    },
    "OLAK5uy_nMtWXXdz9mDJJzBfIB66BT5ppudiV5eSk": {  # Vaiana
        "description": "Ein junges Mädchen aus einem abgelegenen Inselvolk begibt sich auf eine gefährliche Seereise, um ihr Volk zu retten.",
        "series": "Vaiana",
        "position_in_series": 1,
        "source_release_year": 2016,
    },
    "OLAK5uy_mlxW-N-Rs4Ezsg-cML8PncH7s_n4IV1QA": {  # Vaiana 2
        "description": "Eine junge Heldin begibt sich auf eine gefährliche Seereise, um ihr Volk zu retten und ein altes Geheimnis zu enthüllen.",
        "series": "Vaiana",
        "position_in_series": 2,
        "source_release_year": 2024,
    },
    "OLAK5uy_m_h-aUU1R1qE6LcDBTEZ3kd1jr-spRZns": {  # Peter Pan
        "description": "Ein Junge, der nicht altert, führt Kinder in ein magisches Land voller Abenteuer und Gefahren.",
        "series": "Peter Pan",
        "position_in_series": 1,
        "source_release_year": 1953,
    },
    "OLAK5uy_nZLW8_8zkzseZZnwEYWYC_x2q9ILwkJH4": {  # Peter Pan 2 - Neue Abenteuer in Nimmer Land
        "description": "Junge Abenteurer erleben magische Herausforderungen in einer fantastischen Welt ohne Altern und kämpfen gegen dunkle Mächte.",
        "series": "Peter Pan",
        "position_in_series": 2,
        "source_release_year": 2002,
    },
    "OLAK5uy_mIwvauQpR3lTqtVwm-6a2IsONlCtc08Ps": {  # Peter Pan & Wendy (Real-Film)
        "description": "Ein Junge führt Kinder in ein magisches Land, wo sie Abenteuer erleben und nie erwachsen werden.",
        "series": "Peter Pan",
        "position_in_series": 1,
        "source_release_year": 2023,
        "variant": "remake",
    },
    "OLAK5uy_kDNe9h1vmPckr-4AMKagUD6TiYj2LOfb4": {  # Küss den Frosch
        "description": "Ein Mädchen muss einen verwunschenen Prinzen erlösen und lernt dabei wichtige Lektionen über Mut und Freundschaft.",
    #     "series": None,
    #     "position_in_series": None,
        "genre": ["fairy_tale"],
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2009,
    },
    "OLAK5uy_nXayOLN8th_TQrewhWmRfRkZ90weYcWiw": {  # Arlo & Spot
        "description": "Ein ungleiches Duo begibt sich auf eine abenteuerliche Reise durch die Wildnis, um nach Hause zu finden.",
    #     "series": None,
    #     "position_in_series": None,
        "genre": ["adventure"],
        "franchise": "pixar",
        "min_age": 4,
        "source_release_year": 2015,
    },
}
