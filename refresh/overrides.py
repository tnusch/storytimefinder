"""
Manual per-item metadata overrides, keyed by catalog entry id.

For 'channel'/'playlist' sources that's a YouTube video id (one entry per
video). For 'album' sources it's the playlist/album id instead, since an
album collapses down to a single catalog entry for the whole audiobook
(see build_album_entry() in refresh.py) - not one entry per chapter.

The YouTube Data API gives us a raw video/album description, but it's never
used - `description` here is entirely override-only too, same as the other
nine fields below. It has no concept of series, episode number, genre,
franchise, age group, the *source* material's original release year, mood,
seasonal relevance, or awards either, so all ten fields have to be curated
by hand here. refresh.py applies these on every run (merged in after the
API data), so they're safe from being wiped out by a re-sync and stay
version-controlled like the rest of the curation.

**`genre`/`franchise`/`mood`/`min_age` are per-item fields here, EXCEPT for
an item belonging to an `episodic` series** (see `series_type` below and
`SERIES_OVERRIDES` further down) - for those, the four fields move to a
single shared entry in `SERIES_OVERRIDES`, keyed by the series name, and
are simply omitted from every episode's own `ITEM_OVERRIDES` entry. This
exists because a real episodic series (Bibi Blocksberg, TKKG, ...) is
expected to agree on all four across every episode anyway (the series
consistency check below already assumed this and just warned when it
didn't) - retyping the same genre/franchise/mood/min_age on 20+ episode
entries was pure duplication and a recurring source of typos (this
codebase's own Bibi Blocksberg entries once disagreed on both `min_age`
and `mood` between two episodes before this change). `series`/
`position_in_series`/`description`/`source_release_year`/`seasonal`/
`awards` stay per-item regardless of `series_type` - only the four fields
above move.

For every genuinely new item, refresh.py also asks Claude for best-effort
suggestions for nine of these ten fields - everything except `awards` (see
below) - in one combined call, to keep token spend down (see
generate_metadata_suggestions() in refresh.py), and writes them to
data/claude_suggestions.json for you to review by hand. That file is NEVER
read back into the catalog - it's a staging area, not a data source.
Nothing Claude proposes reaches the catalog on its own, `description`
included - `mood`/`seasonal` too, even though they're subjective/generative
rather than factual claims; every suggested field goes through the same
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
  - `genre`: exactly ONE value from this fixed list (not a list/multi-select):
        fairy_tale, adventure, mystery, fantasy, educational, bedtime_story,
        classic, comedy
    **Omit on an item belonging to an `episodic` series** - set it once in
    `SERIES_OVERRIDES` instead (see below).
  - `franchise`: IP/brand grouping - NOT genre, NOT publisher. One value
    from this fixed list, or omit/None for a standalone (non-franchise)
    title:
        disney, pixar, dreamworks, marvel, star_wars, bibi_blocksberg,
        benjamin_bluemchen, die_drei_fragezeichen, tkkg
    (refresh.py logs a warning, but doesn't fail the sync, if a genre or
    franchise value isn't in its fixed list - see GENRE_VALUES/
    FRANCHISE_VALUES in refresh.py.) **Omit on an item belonging to an
    `episodic` series** - set it once in `SERIES_OVERRIDES` instead.
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
    the age filter, same as before. **Omit on an item belonging to an
    `episodic` series** - set it once in `SERIES_OVERRIDES` instead (same
    lower-of-the-two tie-break rule applies there if episodes disagree).
  - `source_release_year`: the year the SOURCE film or book was originally
    released - e.g. 1994 for a "The Lion King" audiobook - NOT the
    audiobook production's own release/upload date. The audiobook's own
    date is often ambiguous (the same title can show several different
    years across editions/reissues/platforms), while the source material's
    release year is a single stable, verifiable fact. Year only (an int),
    not a full date. Stays per-item even for an episodic series' episodes -
    unlike genre/franchise/mood/min_age, an episode's own release year is
    never expected to be shared across the series.
  - `series`, `position_in_series`: e.g. "Die drei ???" / 78 for episode 78
    of that series. `series_type` used to be a third per-item field here -
    it's now series-level only, see `SERIES_OVERRIDES` below.
  - `mood`: exactly ONE value from this fixed list (not a list/multi-select),
    a subjective read of the story's overall tone - a creative judgment
    call, not a factual claim, but still gated behind the same human-review
    step as every other field:
        calm, funny, spooky, adventurous, heartwarming, exciting, silly, gentle
    **Omit on an item belonging to an `episodic` series** - set it once in
    `SERIES_OVERRIDES` instead.
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
`franchise`/`mood`/`min_age` for an EPISODIC series - keyed by the series
NAME (not an entry id, the only place in this codebase a dict is keyed by
free text rather than a YouTube/entry id), e.g.:
    SERIES_OVERRIDES = {
        "Bibi Blocksberg": {
            "series_type": "episodic",
            "genre": "fantasy",
            "franchise": "bibi_blocksberg",
            "mood": "funny",
            "min_age": 4,
        },
    }
`series_type` is exactly ONE value from this fixed list:
    episodic, sequel
MANUAL curation only - NEVER auto-inferred from how many entries share a
`series` name (a trilogy is 3 "sequel" films; a 3-part miniseries is
"episodic" - count alone can't tell them apart). `episodic` (Bibi
Blocksberg, TKKG, Die drei ??? - a long-running series where each entry
stands alone) collapses the series into one card on the site with a
`/series/<slug>` episode listing, and is what makes this entry's
`genre`/`franchise`/`mood`/`min_age` take effect for every item sharing
that `series` name (their own `ITEM_OVERRIDES` entries should omit those
four fields - see each field's bullet above). `sequel` (Findet Nemo ->
Findet Dorie, Der König der Löwen 1 -> 2 - a small cluster of direct film
sequels) keeps every film as its own individual card with a "Teil N von M"
badge and davor:/danach: cross-links instead - `genre`/`franchise`/`mood`/
`min_age` are NOT centralized for a `sequel` series (each film keeps its
own values in `ITEM_OVERRIDES`, same as a standalone title), since a
`SERIES_OVERRIDES` entry only ever redirects those four fields when
`series_type == "episodic"`. A series with no `SERIES_OVERRIDES` entry at
all (the common case for most `series` values today) behaves exactly like
it did before this field existed - filterable by "Reihe", no collapsing,
no badge.

Series consistency checks: every entry sharing the same `series` name
(across every source, not just one - a series could in principle span more
than one) is compared against the others for two likely mistakes, warned
about but never a hard failure:
  - entries in the same series disagreeing on `genre`/`franchise`/`mood`/
    `seasonal` - a real series is usually consistent on all four, so a
    mismatch is more often a typo or a forgotten field in one entry than a
    deliberate choice. Fix it by aligning the odd one out, or ignore the
    warning if the disagreement really is intentional (some Disney series
    do shift genre/mood between installments). For an `episodic` series
    this can only actually fire for `seasonal` now - `genre`/`franchise`/
    `mood` are meant to be omitted per-item once `SERIES_OVERRIDES` covers
    them, so there's nothing left on the item entries to disagree about;
    if this warning still fires for those three on a series you've already
    migrated to `SERIES_OVERRIDES`, it means some episodes still have
    stale per-item values worth cleaning up.
  - two entries in the same series claiming the same `position_in_series` -
    almost always a copy-paste mistake (e.g. forgetting to bump the number
    when adding a new episode's override block).
These warnings only ever read what's already in ITEM_OVERRIDES - they never
change what gets written, same as the genre/franchise/mood/seasonal/award
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
            "genre": "mystery",
            "franchise": "die_drei_fragezeichen",
            "mood": "spooky",
            "min_age": 8,
        },
    }

    ITEM_OVERRIDES = {
        "dQw4w9WgXcQ": {
            # genre/franchise/mood/min_age all come from SERIES_OVERRIDES
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
            "genre": "adventure",
            "franchise": "disney",
            "source_release_year": 2003,
            "mood": "heartwarming",
        },
    }
"""

# Series-level metadata for episodic series - see the docstring above for
# the full field-by-field spec. Keyed by series NAME, not an entry id.
SERIES_OVERRIDES: dict[str, dict] = {
    "Bibi Blocksberg": {
        "series_type": "episodic",
        "genre": "fantasy",
        "franchise": "bibi_blocksberg",
        # The two episodes below disagreed on mood ("funny" vs
        # "adventurous") before this field moved here - picked "funny" as
        # the series-wide value; revisit if a better single read of the
        # series' overall tone comes up.
        "mood": "funny",
        # The two episodes below disagreed on min_age (5 vs 4) before this
        # field moved here - used the lower of the two, per the same
        # tie-break rule min_age's own docstring bullet already documents.
        "min_age": 4,
    },
}

ITEM_OVERRIDES: dict[str, dict] = {
    "OLAK5uy_l-P6wjCCtVMqwx7s8rAgS4nGGjZra-reE": {
        "description": "Ein kleines Waldtier trifft auf ein furchteinflößendes Wesen und entdeckt dabei seine eigene Cleverness.",
        "genre": "adventure",
        "min_age": 3,
        "source_release_year": 2009,
        "mood": "heartwarming",
    },

    "OLAK5uy_kSX5rN90rg1Usa39MZdURHzLxmvEuS17A": {
        "description": "Ein schlitzohriger Bauernjunge im alten Schweden sorgt mit seinen Streichen ständig für Chaos, hat dabei aber ein gutes Herz.",
        "series": "Michel aus Lönneberga",
        "genre": "classic",
        "min_age": 4,
        "source_release_year": 1971,
        "mood": "gentle",
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
        "genre": "comedy",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2006,
        "mood": "heartwarming",
    },

    "OLAK5uy_nUcVxlUReyhD771ST9B_53UHaPgNNGRpk": {
        "description": "Eine wissbegierige Prinzessin der Meere verliebt sich in die Welt über der Wasseroberfläche und wagt einen folgenschweren Tausch.",
        "series": "Arielle",
        "genre": "fairy_tale",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2023,
        "mood": "adventurous",
    },

    "OLAK5uy_nOc6WKydiRIxbcQOfc-RzJWcj2ueAJpQY": {
        "description": "Zwei erfinderische Stiefbrüder müssen ihre große Schwester retten, die von Außerirdischen in eine andere Galaxie entführt wurde.",
        "genre": "adventure",
        "franchise": "disney",
        "min_age": 6,
        "source_release_year": 2020,
        "mood": "adventurous",
    },

    "OLAK5uy_n0HRLnDJ5o7q1VeH0WrzXAflNYGbFgZPs": {
        "description": "Eine kleine Fee gerät versehentlich in die Menschenwelt und muss mit neuen Freunden einen Weg zurück in ihre Heimat finden.",
        "series": "Peter Pan",
        "genre": "fairy_tale",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2010,
        "mood": "adventurous",
        "seasonal": "summer",
    },

    "OLAK5uy_mzo5-o7iRgmG9YJVZFY4n8VhDmYl4oAjQ": {
        "description": "Zwei ungleiche und anfangs verfeindete Studierende an einer Schule für furchteinflößende Wesen lernen, echte Freunde zu werden.",
        "series": "Die Monster AG",
        "position_in_series": 2,
        "genre": "comedy",
        "franchise": "pixar",
        "min_age": 4,
        "source_release_year": 2013,
        "mood": "funny",
    },

    "OLAK5uy_muL8Aszjs2LS1rVQKJiwIJJX7DD1wBMHo": {
        "description": "Eine kleine Fee reist gefährlich weit, um ein magisches Objekt zu bergen, das die Jahreszeiten ihrer Heimat bedroht.",
        "series": "Peter Pan",
        "genre": "fairy_tale",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2009,
        "mood": "adventurous",
    },

    "OLAK5uy_mKQtP61sPR5npHu7DZtrVFhAQdQo9V-I8": {
        "description": "Ein junger Hund, hin- und hergerissen zwischen Zuhause und Freiheit, erlebt auf der Straße ein gefährliches Abenteuer.",
        "series": "Susi und Strolch",
        "position_in_series": 2,
        "genre": "adventure",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2001,
        "mood": "heartwarming",
    },

    "OLAK5uy_mBZHU-r4X89vIltngewixsIqZhtpZO-zo": {
        "description": "Als ein kleines Waldtier plötzlich verschwunden scheint, begeben sich seine Freunde auf eine abenteuerliche Suche nach ihm.",
        "series": "Winnie Puuh",
        "genre": "adventure",
        "franchise": "disney",
        "min_age": 3,
        "source_release_year": 1997,
        "mood": "adventurous",
    },

    "OLAK5uy_lsM_ClEpmS1qqkXy95F_RTdbkZIyvoQ5I": {
        "description": "Eine neugierige Meeresprinzessin sehnt sich nach dem Leben an Land und geht dafür einen riskanten Handel mit dunklen Mächten ein.",
        "series": "Arielle",
        "position_in_series": 1,
        "genre": "fairy_tale",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 1989,
        "mood": "adventurous",
    },

    "OLAK5uy_lm8n1UHMVHPKySZ-dRFs_aTYl9x_lAPDI": {
        "description": "Ein Mädchen erhält einen geheimnisvollen Schlüssel und reist durch vier magische Reiche auf der Suche nach ihrer Vergangenheit.",
        "genre": "fairy_tale",
        "franchise": "disney",
        "min_age": 5,
        "source_release_year": 2018,
        "mood": "adventurous",
        "seasonal": "christmas",
    },

    "OLAK5uy_lkxg2x89y5vfi44HpB_fRY77dHQ8Di7gc": {
        "description": "Eine Gruppe von Waldfreunden erlebt die wechselnden Jahreszeiten und meistert dabei herzerwärmende Alltagsabenteuer.",
        "series": "Winnie Puuh",
        "genre": "adventure",
        "franchise": "disney",
        "min_age": 3,
        "source_release_year": 1999,
        "mood": "adventurous",
    },

    "OLAK5uy_lGV65AB3Czwmze7vTqqSZsykA6kOGAMsU": {
        "description": "Ein kleines, ängstliches Waldtier fühlt sich von seinen Freunden übersehen und beweist bei einem Abenteuer unerwarteten Mut.",
        "series": "Winnie Puuh",
        "genre": "adventure",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2003,
        "mood": "adventurous",
    },

    "OLAK5uy_ks8WMkyqJOBbpzjTbAiouujODFK5GO_zA": {
        "description": "Ein hüpffreudiges Tier sucht nach Artgenossen und entdeckt dabei, dass wahre Familie auch aus Freunden bestehen kann.",
        "series": "Winnie Puuh",
        "genre": "adventure",
        "franchise": "disney",
        "min_age": 3,
        "source_release_year": 2000,
        "mood": "adventurous",
    },

    "OLAK5uy_kloVPhJNdAVWUVn_1CCAeEouwp4UjICTw": {
        "description": "Ein Waisenjunge im Wald freundet sich mit einem unsichtbaren Fabelwesen an, das ihn beschützt und Erwachsene misstrauisch macht.",
        "genre": "fantasy",
        "min_age": 4,
        "source_release_year": 2016,
        "mood": "adventurous",
    },

    "OLAK5uy_kUz3yb-KbwBsK2pslAd08fwHVPsAdfjNg": {
        "description": "Ein einsamer Aufräumroboter auf verlassener Erde findet durch den Besuch eines anderen Roboters Hoffnung und Zuneigung.",
        "genre": "adventure",
        "franchise": "pixar",
        "min_age": 4,
        "source_release_year": 2008,
        "mood": "heartwarming",
    },

    "OLAK5uy_kKXhJ6GTzojNC72P50parWidxdJ1-EbRI": {
        "description": "Trotz eines Verbots fühlt sich die Tochter eines ungewöhnlichen Paares zum Meer und seinen Geheimnissen hingezogen.",
        "series": "Arielle",
        "position_in_series": 2,
        "genre": "fairy_tale",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2000,
        "mood": "adventurous",
    },

    "OLAK5uy_k1jgDzLL5A_fwHbvbDv3ZoghjzX7_eJW8": {
        "description": "Bevor Gesang im Unterwasserreich verboten wird, entdeckt eine junge Prinzessin ihre Liebe zur Musik und zur Welt über den Wellen.",
        "series": "Arielle",
        "genre": "fairy_tale",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2008,
        "mood": "adventurous",
    },

    "OLAK5uy_nsb0OsuUyDuhKW52EFCLTMv0-vMJ0zBzY": {
        "description": "Ein Held kämpft gegen Ungerechtigkeit und hilft den Bedürftigen, indem er sich gegen tyrannische Machthaber aufbegehrt.",
        "genre": "adventure",
        "franchise": "disney",
        "source_release_year": 1973,
        "mood": "adventurous",
        "min_age": 4,
    },

    "OLAK5uy_nzOzTv6DtDwjF-fnRt5K_xSR1u4d1KWcI": {
        "description": "Ein junger Mann mit bescheidenen Anfängen entdeckt eine magische Lampe und versucht, sein Leben zu verändern und die Liebe einer Prinzessin zu gewinnen.",
        "genre": "fairy_tale",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2019,
        "mood": "adventurous",
    },

    "OLAK5uy_ms8Lnv1d7nIyy2coHVKSSddjP5sdTp9Pg": {
        "description": "Ein Mädchen folgt einem weißen Kaninchen in eine fantastische Welt voller surrealer Abenteuer und merkwürdiger Begegnungen.",
        "genre": "fantasy",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2010,
        "mood": "adventurous",
    },

    "OLAK5uy_nlEen2psNk1p9LJdZYO5gm2YKUR4aXjGA": {
        "description": "Zwei Mäuse arbeiten als Polizisten und lösen Fälle, um Gerechtigkeit herzustellen und ihre Gemeinschaft zu schützen.",
        "genre": "adventure",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 1977,
        "mood": "adventurous",
    },

    "OLAK5uy_mciDVsg3oLjYKBHtNlF2rSUpzlLjep84o": {
        "description": "Ein Junge aus Holz erlebt Abenteuer und lernt, sich richtig zu verhalten.",
        "genre": "fairy_tale",
        "min_age": 4,
        "source_release_year": 1940,
        "mood": "heartwarming",
    },

    "OLAK5uy_mTpfKq3DfbaaGH8hZxbR-5_wtmwggfjF8": {
        "description": "Ein neues freundliches Wesen kommt in den Wald und freundet sich mit den bekannten Bewohnern an.",
        "genre": "fairy_tale",
        "franchise": "disney",
        "min_age": 3,
        "source_release_year": 2005,
        "mood": "heartwarming",
    },

    "OLAK5uy_m9K0ZDoAwreKv2zfLLzNsAbEvNcN_TOSI": {
        "description": "Eine Fee muss sich einer Piratin entgegenstellen und ein großes Abenteuer bestehen.",
        "genre": "fairy_tale",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2014,
        "mood": "adventurous",
    },

    "OLAK5uy_npX4I2rAwUnbX39bRnWaHy7jrGcKX8LSA": {
        "description": "Ein Hubschrauber und seine Freunde arbeiten zusammen, um Rettungseinsätze durchzuführen und Menschen in Not zu helfen.",
        "series": "Planes",
        "position_in_series": 2,
        "genre": "adventure",
        "franchise": "pixar",
        "min_age": 4,
        "source_release_year": 2014,
        "mood": "adventurous",
    },

    "OLAK5uy_mM5uoTUzZCg1mBg1zoiNplSA6kRdlGEaw": {
        "description": "Ein Gorilla in einem Zirkus träumt von Freiheit und findet unerwartete Freundschaft in seiner Gefangenschaft.",
        "genre": "fantasy",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2020,
        "mood": "heartwarming",
    },

    "OLAK5uy_nvAPM1KYwDmyVcBJkDzeCvushOyCzeY1M": {
        "description": "Zwei Brüder kämpfen gemeinsam gegen Widrigkeiten und erleben abenteuerliche Herausforderungen in der Wildnis.",
        "series": "Bärenbrüder",
        "position_in_series": 1,
        "genre": "adventure",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2003,
        "mood": "adventurous",
    },

    "OLAK5uy_nuI_CulUwubWa7-lWQql_yH_HG0D7iXPc": {
        "description": "Zwei Freunde entdecken eine magische Welt, in der die Elemente Feuer und Wasser in Konflikt geraten.",
        "genre": "fantasy",
        "franchise": "pixar",
        "min_age": 6,
        "source_release_year": 2023,
        "mood": "adventurous",
    },

    "OLAK5uy_nnhLzV862YYp4wwic75VSXQJWCvxYr0DQ": {
        "description": "Eine Familie mit Superkräften muss sich aus dem Ruhestand zurückmelden, um die Welt zu retten.",
        "series": "Die Unglaublichen",
        "position_in_series": 1,
        "genre": "adventure",
        "franchise": "pixar",
        "min_age": 5,
        "source_release_year": 2004,
        "mood": "exciting",
    },

    "OLAK5uy_nmCLOP7hjBJtEVIMEvi0uOwH1RaakvUo8": {
        "description": "Ein Kaiser verliert seine Herrschaft und muss sich in die Wildnis begeben, um seine Macht zurückzugewinnen.",
        "genre": "adventure",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2000,
        "mood": "adventurous",
    },

    "OLAK5uy_ngoV8tTYHGlQlh8x0YOYlFd-O8YaIlJG0": {
        "description": "Ein aufblasbarer Roboter erlebt chaotische und humorvolle Abenteuer voller unerwarteter Wendungen.",
        "genre": "adventure",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2014,
        "mood": "funny",
    },

    "OLAK5uy_nyEgHwTQFtmweDI4mDC-ID0nCH_Tz33PM": {
        "description": "Kinder müssen sich in der digitalen Welt gegen böse Mächte verteidigen und Abenteuer bestehen.",
        "series": "Ralph Reichts",
        "position_in_series": 2,
        "genre": "adventure",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2018,
        "mood": "exciting",
    },

    "OLAK5uy_nf9pDKOq0IVh-loWWSF6v2VLm-VJZAokE": {
        "description": "Eine Seele muss ihre Bestimmung finden und lernt dabei, was es bedeutet, lebendig zu sein.",
        "genre": "fantasy",
        "franchise": "pixar",
        "min_age": 6,
        "source_release_year": 2020,
        "mood": "heartwarming",
    },

    "OLAK5uy_mRA_lATsy2YhZrrOCkTYMVQ9mBtJSwQYU": {
        "description": "Ein Koala träumt davon, einen Gesangswettbewerb zu gewinnen und findet dabei neue Freunde und Mut.",
        "genre": "comedy",
        "franchise": "dreamworks",
        "min_age": 4,
        "source_release_year": 2016,
        "mood": "heartwarming",
    },

    "OLAK5uy_nc0WkNNelHnxEg2CWgqoOZxxRxguq6V78": {
        "description": "Eine Königin muss ein mysteriöses Abenteuer bestehen, um ihr Königreich und ihre Familie zu retten.",
        "series": "Die Eiskönigin",
        "position_in_series": 2,
        "genre": "fantasy",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2019,
        "mood": "heartwarming",
        "seasonal": "winter",
    },

    "OLAK5uy_neBCIjeNGVDNWSnBkoE4a0oEydUFyRH8U": {
        "description": "Ein Junge wächst im Dschungel auf und muss lernen, seinen Platz in der Welt zwischen Natur und Zivilisation zu finden.",
        "series": "Das Dschungelbuch",
        "genre": "adventure",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2016,
        "mood": "adventurous",
    },

    "OLAK5uy_mjxN270TdL5rlzL-7Opa2YRiBetDBTwAs": {
        "description": "Ein Kürbiskopf-König entdeckt die Weihnachtswelt und plant, das Fest auf seine eigene düstere Weise zu übernehmen.",
        "genre": "fantasy",
        "franchise": "disney",
        "min_age": 6,
        "source_release_year": 1993,
        "mood": "spooky",
        "seasonal": "christmas",
    },

    "OLAK5uy_neRq_XHTqVD1AWQcTs8E7FQL08KB8sOr4": {
        "description": "Ein Mädchen rettet einen verletzten Eichhörnchen und erlebt gemeinsam mit ihm magische Abenteuer.",
        "genre": "fantasy",
        "franchise": "disney",
        "min_age": 8,
        "source_release_year": 2021,
        "mood": "heartwarming",
    },

    "OLAK5uy_nJRQQEIIqbhr4kzAJBvDOQLP35g6bNCQM": {
        "description": "Zwei Brüder entdecken einen magischen Weg und müssen sich einer Herausforderung stellen, um ihre Welt zu retten.",
        "genre": "fantasy",
        "franchise": "pixar",
        "min_age": 6,
        "source_release_year": 2020,
        "mood": "adventurous",
    },

    "OLAK5uy_nZhJ91S_mNEFmyFMvV-N8bY3mhxq2e8-U": {
        "description": "Tiere erleben wilde Abenteuer in der Natur und lernen dabei wichtige Lektionen über Freundschaft und Zusammenhalt.",
        "genre": "adventure",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2006,
        "mood": "adventurous",
    },

    "OLAK5uy_m8WNpYCFjKdk-ddt7gKQNLmY---s83epc": {
        "description": "Ein Abenteuer in einer fantastischen Stadt, wo verschiedene Tiere zusammenleben und gemeinsam Herausforderungen meistern.",
        "series": "Zoomania",
        "position_in_series": 1,
        "genre": "adventure",
        "franchise": "disney",
        "min_age": 5,
        "source_release_year": 2016,
        "mood": "adventurous",
    },

    "OLAK5uy_mlBwAOSeO8VJhCoRM4guDX6imu4giVs8k": {
        "description": "Eine Gruppe von Insekten erlebt Abenteuer in ihrer winzigen Welt voller Gefahren und Überraschungen.",
        "genre": "adventure",
        "franchise": "pixar",
        "min_age": 4,
        "source_release_year": 1998,
        "mood": "adventurous",
    },

    "OLAK5uy_n2rqUY97UHsO4XcWOTzPbb4bvFl_NhBQg": {
        "description": "Eine Dalmatinerfamilie muss ihre 99 entführten Welpen vor einem bösen Plan retten.",
        "genre": "adventure",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 1961,
        "mood": "adventurous",
    },

    "OLAK5uy_n7GLXBULfc3ScSzTSQeallIozR5ba4a6M": {
        "description": "Eine Prinzessin mit magischen Kräften muss lernen, ihre Fähigkeiten zu akzeptieren und ihre Schwester zu retten.",
        "series": "Die Eiskönigin",
        "position_in_series": 1,
        "genre": "fantasy",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2013,
        "mood": "heartwarming",
        "seasonal": "winter",
    },

    "OLAK5uy_nWV9JLxDYVffi_Y3z6dWybb7awjLeRvkw": {
        "description": "Eine dunkle Kreatur kämpft gegen ihre böse Vergangenheit und entdeckt unerwartete Verbindungen zu ihrer Welt.",
        "genre": "fantasy",
        "franchise": "disney",
        "min_age": 6,
        "source_release_year": 2014,
        "mood": "spooky",
    },

    "OLAK5uy_ncTsRBl3ihS8xc2fXuo2lPv04dO1f6KC0": {
        "description": "Kleine Hüpfer erleben Abenteuer in ihrer Welt und lernen Lektionen über Freundschaft und Mut.",
        "genre": "adventure",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2026,
        "mood": "adventurous",
    },

    "OLAK5uy_n2-ZUhnXeGYmaywf4AcpFudjR10JsbrQo": {
        "description": "Ein Junge entdeckt seine außergewöhnlichen Fähigkeiten und begibt sich auf eine kosmische Reise der Selbstfindung.",
        "genre": "fantasy",
        "franchise": "pixar",
        "min_age": 6,
        "source_release_year": 2025,
        "mood": "adventurous",
    },

    "OLAK5uy_muFPBJI4TLYs5fNENHVPal57RJqqrkZ0w": {
        "description": "Woody und seine Freunde erleben ein neues Abenteuer, wenn sich ihre Welt unerwartet verändert.",
        "series": "Toy Story",
        "position_in_series": 5,
        "genre": "adventure",
        "franchise": "pixar",
        "min_age": 4,
        "source_release_year": 2025,
        "mood": "adventurous",
    },

    "OLAK5uy_mDiC8M2jC1ME7qdPJIg4exPLO4EseVCQc": {
        "description": "Ein Krieger kämpft gegen eine Bedrohung und sucht nach einem mythischen Wesen, um sein Reich zu retten.",
        "genre": "fantasy",
        "franchise": "disney",
        "min_age": 6,
        "source_release_year": 2021,
        "mood": "adventurous",
    },

    "OLAK5uy_n-nP-qclR2U3yjcdZ-pvwwoecfo9OGw5A": {
        "description": "Ein Kind muss lernen, Probleme durch intelligente Lösungen statt Gewalt zu bewältigen.",
        "series": "Ralph reichts",
        "position_in_series": 1,
        "genre": "educational",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2012,
        "mood": "heartwarming",
    },

    "OLAK5uy_nTgjFjpGwgBQV2WCq7Ekshyy0hngwi_lg": {
        "description": "Ein Flugzeug muss eine wichtige Reise absolvieren und erlebt dabei aufregende Abenteuer in der Luft.",
        "series": "Cars",
        "genre": "adventure",
        "franchise": "pixar",
        "min_age": 4,
        "source_release_year": 2013,
        "mood": "adventurous",
    },

    "OLAK5uy_nQbGAQTtMuyp_n7rO7Xz6B-Re4agRiso4": {
        "description": "Ein Krieger muss seine innere Kraft entdecken und gegen eine dunkle Bedrohung antreten, um sein Volk zu retten.",
        "series": "Kung Fu Panda",
        "position_in_series": 3,
        "genre": "adventure",
        "franchise": "dreamworks",
        "min_age": 5,
        "source_release_year": 2016,
        "mood": "adventurous",
    },

    "OLAK5uy_mk1rApVK6CxC1T7JfYx53jaJE0BtApAaE": {
        "description": "Ein Spielzeug muss sich neuen Herausforderungen stellen und lernt, dass Freundschaft verschiedene Formen annehmen kann.",
        "series": "Toy Story",
        "position_in_series": 4,
        "genre": "adventure",
        "franchise": "pixar",
        "min_age": 4,
        "source_release_year": 2019,
        "mood": "adventurous",
    },

    "OLAK5uy_mYT2vME3GNSy2akeG5jc9rA74RR-OduYk": {
        "description": "Eine Gruppe von Abenteurern erforscht die Ruinen einer legendären versunkenen Zivilisation und enthüllt deren mysteriöse Geheimnisse.",
        "genre": "adventure",
        "franchise": "disney",
        "source_release_year": 2001,
        "mood": "adventurous",
        "min_age": 4,
    },

    "OLAK5uy_mF7TtT8TcZBNPj2wNOsygEGUxPB9fhJRc": {
        "description": "Ein Mädchen verkleidet sich als Soldat, um ihren kranken Vater vor dem Kriegsdienst zu bewahren.",
        "series": "Mulan",
        "genre": "adventure",
        "franchise": "disney",
        "min_age": 5,
        "source_release_year": 2020,
        "mood": "adventurous",
    },

    "OLAK5uy_mLkUymz-JBD0gR3Cl9KcbaDmajDq_tETs": {
        "description": "Ein Junge belebt seinen verstorbenen Hund durch wissenschaftliche Experimente wieder zum Leben.",
        "genre": "fantasy",
        "franchise": "disney",
        "min_age": 6,
        "source_release_year": 2012,
        "mood": "heartwarming",
        "seasonal": "halloween",
    },

    "OLAK5uy_mNqk3ri39BDq8HqCdr6vftp0EJ04JRp7g": {
        "description": "Ein Mensch mit körperlichen Unterschieden findet Zuflucht in einem Turm und entdeckt Freundschaft, Liebe und seinen Platz in der Welt.",
        "genre": "classic",
        "franchise": "disney",
        "min_age": 5,
        "source_release_year": 1996,
        "mood": "heartwarming",
    },

    "OLAK5uy_mIHDTjeetGqr7X1LLJrNQdhLAiHO6bVbA": {
        "description": "Ein Leidenschaftlicher Kampf um Kulinarischen Erfolg in der Küche einer renommierten Gaststätte.",
        "genre": "comedy",
        "franchise": "pixar",
        "min_age": 4,
        "source_release_year": 2007,
        "mood": "heartwarming",
    },

    "OLAK5uy_mIc-VWkQW1EornvdVdv8CIFfq5OOnloAE": {
        "description": "Ein Mädchen überwindet Widrigkeiten und findet durch Mut und Güte sein Glück.",
        "genre": "fairy_tale",
        "min_age": 4,
        "source_release_year": 1950,
        "mood": "heartwarming",
    },

    "OLAK5uy_mUJXtJvaGm1o19boWNKPn9zU-am8OXRXQ": {
        "description": "Ein Junge wächst im Dschungel auf und muss sich gegen Gefahren behaupten, während er seine Identität und seinen Platz in der Welt entdeckt.",
        "series": "Das Dschungelbuch",
        "position_in_series": 1,
        "genre": "adventure",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 1967,
        "mood": "adventurous",
    },

    "OLAK5uy_m_hm-SUaGplqMI8ht6iZeN7Js5r_cB-rk": {
        "description": "Eine Gruppe von Jugendlichen muss sich neuen emotionalen Herausforderungen und inneren Konflikten stellen.",
        "series": "Alles steht Kopf",
        "position_in_series": 2,
        "genre": "comedy",
        "franchise": "pixar",
        "min_age": 6,
        "source_release_year": 2024,
        "mood": "heartwarming",
    },

    "OLAK5uy_mWaaL1fk_QUpmiBrEtFRf7UFhdvEO6G2g": {
        "description": "Kinder erleben mysteriöse und ungewöhnliche Abenteuer in einer rätselhaften Welt voller Geheimnisse.",
        "genre": "adventure",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2022,
        "mood": "adventurous",
    },

    "OLAK5uy_mRKkcj-jZYsoxx6zexSQUI0UZSbKFvmpE": {
        "description": "Eine Familie erlebt Abenteuer auf einer einsamen Insel und muss sich gegen Gefahren behaupten.",
        "genre": "adventure",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2007,
        "mood": "adventurous",
    },

    "OLAK5uy_mDRgeNmjkLEFg78lW_cGP8klR11L6d-0Y": {
        "description": "Ein junger Mensch, aufgewachsen in der Wildnis, muss seine Identität entdecken und seinen Platz zwischen zwei Welten finden.",
        "series": "Tarzan",
        "position_in_series": 2,
        "genre": "adventure",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2005,
        "mood": "adventurous",
    },

    "OLAK5uy_nIlfMQgrwbOxbgSPRIixxI3qt1_D4bilM": {
        "description": "Ein Schneemann erlebt ein Abenteuer und erfährt, was es bedeutet, in der wärmeren Jahreszeit zu bestehen.",
        "series": "Die Eiskönigin",
        "genre": "fantasy",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2017,
        "mood": "heartwarming",
        "seasonal": "winter",
    },

    "OLAK5uy_mCUNR-Av0GzcrZ9vfuaOIIMlNVBg-95Q8": {
        "description": "Eine Familie mit magischen Gaben muss ihre übernatürlichen Kräfte nutzen, um ihre Gemeinde zu retten.",
        "genre": "fantasy",
        "franchise": "disney",
        "min_age": 6,
        "source_release_year": 2021,
        "mood": "heartwarming",
    },

    "OLAK5uy_lzZjFEUpcdHvCgOVFvkFxuQyprGBHRF-4": {
        "description": "Ein Weltraumabenteuer, in dem ein Astronaut versucht, nach Hause zurückzukehren.",
        "series": "Toy Story",
        "genre": "adventure",
        "franchise": "pixar",
        "min_age": 4,
        "source_release_year": 2022,
        "mood": "adventurous",
    },

    "OLAK5uy_m3oJuBguPxtknzSnqvQSMGWn6ICf6BPWE": {
        "description": "Ein Kind entdeckt einen gefährlichen Pilz und muss herausfinden, wie man ihn bekämpft, bevor er alles zerstört.",
        "genre": "adventure",
        "source_release_year": 2022,
        "mood": "spooky",
        "min_age": 5,
    },

    "OLAK5uy_mBHMZ1XX4yUic_FiPIypUCbKt-H5bWJxI": {
        "description": "Ein sterblicher Held muss seine göttlichen Kräfte nutzen, um gegen das Böse zu kämpfen und seinen Platz in der Welt zu finden.",
        "genre": "adventure",
        "franchise": "disney",
        "min_age": 5,
        "source_release_year": 1997,
        "mood": "adventurous",
    },

    "OLAK5uy_nymLr2m79sxm1PiRL15od7M6KP7-v8RjM": {
        "description": "Eine Fee entdeckt ihre magischen Kräfte und findet ihren Platz in einer fantastischen Welt voller Abenteuer.",
        "genre": "fairy_tale",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2008,
        "mood": "adventurous",
    },

    "OLAK5uy_ly--6KeCsZMRhG4nTI6uXdIbFEwkaJgo0": {
        "description": "Ein Orchesterwerk wird zum Leben erweckt, wenn Musik und Animation in einer fantastischen Welt verschmelzen.",
        "genre": "fantasy",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 1940,
        "mood": "adventurous",
    },

    "OLAK5uy_lvpbmPh_EH97rOu6rYGC-4mGVtaisBILM": {
        "description": "Zwei Brüder erleben gemeinsam Abenteuer in der Wildnis und müssen zusammenarbeiten, um Herausforderungen zu meistern.",
        "series": "Bärenbrüder",
        "position_in_series": 2,
        "genre": "adventure",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2006,
        "mood": "adventurous",
    },

    "OLAK5uy_lvH5U1ug8PcYe-QvcLqbTdtx3N30W6M8c": {
        "description": "Ein junges Tier wächst in der Natur auf und erlebt Abenteuer, während es die Welt und sich selbst entdeckt.",
        "series": "Bambi",
        "position_in_series": 1,
        "genre": "classic",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 1942,
        "mood": "heartwarming",
    },

    "OLAK5uy_lqa1SNw9mLihZLbNKqzV7EHhwcC45smGk": {
        "description": "Ein Kind erlebt fantastische Abenteuer in einer Spiegelwelt voller magischer Begegnungen und rätselhafter Wunder.",
        "series": "Alice im Wunderland",
        "genre": "fantasy",
        "franchise": "disney",
        "min_age": 5,
        "source_release_year": 2016,
        "mood": "adventurous",
    },

    "OLAK5uy_leU1mji7v0fy9yN2_zCsV9AmCJdGd5vWs": {
        "description": "Eine Prinzessin verfällt durch einen Fluch in einen magischen Schlaf und kann nur durch wahre Liebe erlöst werden.",
        "genre": "fairy_tale",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 1959,
        "mood": "gentle",
    },

    "OLAK5uy_lqHhBfvgUONgvYU_GOw0L_LIsPd5IXNxU": {
        "description": "Ein alternder Rennwagen muss lernen, sich an neue Zeiten anzupassen und findet dabei neue Ziele jenseits des Sieges.",
        "series": "Cars",
        "position_in_series": 3,
        "genre": "adventure",
        "franchise": "pixar",
        "min_age": 4,
        "source_release_year": 2017,
        "mood": "heartwarming",
    },

    "OLAK5uy_loAK3fXOH3uOo3T00so5cPnGsYsspZpEQ": {
        "description": "Ein junger Elefant mit großen Ohren entdeckt seine außergewöhnliche Fähigkeit und findet seinen Platz in der Welt.",
        "genre": "classic",
        "franchise": "disney",
        "min_age": 3,
        "source_release_year": 1941,
        "mood": "heartwarming",
    },

    "OLAK5uy_laDw1u6K1Y8EKAIzNmwF-43MveI_b8CmY": {
        "description": "Ein Junge wächst im Dschungel auf und muss sich zwischen seiner wilden Heimat und der Zivilisation zurechtfinden.",
        "series": "Tarzan",
        "position_in_series": 1,
        "genre": "adventure",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 1999,
        "mood": "adventurous",
    },

    "OLAK5uy_lUDeeTyS6wmAkZhng8HTRfU6UGoCyyeos": {
        "description": "Eine Katze und ihre Kätzchen werden entführt, aber freundliche Streuner helfen ihnen auf ihrer Reise zurück nach Hause.",
        "genre": "adventure",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 1970,
        "mood": "heartwarming",
    },

    "OLAK5uy_lQOL4rgUSsbYG3I9Z1MLN9BdaFXQHFPAE": {
        "description": "Eine junge Frau überbrückt kulturelle Grenzen und findet ihre eigene Stimme in einer Zeit des Konflikts.",
        "series": "Pocahontas",
        "position_in_series": 1,
        "genre": "adventure",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 1995,
        "mood": "adventurous",
    },

    "OLAK5uy_lEqQksSC8weTFhGAnsA35Z63nTbnOuz5A": {
        "description": "Ein außerirdisches Wesen strandet auf der Erde und freundet sich mit einem einsamen Mädchen an, während es lernt, was Familie bedeutet.",
        "series": "Lilo & Stitch",
        "position_in_series": 1,
        "genre": "adventure",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2002,
        "mood": "heartwarming",
    },

    "OLAK5uy_lO86h88tvQMYISO9_3k3r7YKYK1pHhwxE": {
        "description": "Eine Familie mit Superkräften muss zusammenarbeiten, um die Welt vor einer neuen Bedrohung zu bewahren.",
        "series": "Die Unglaublichen",
        "position_in_series": 2,
        "genre": "adventure",
        "franchise": "pixar",
        "min_age": 5,
        "source_release_year": 2018,
        "mood": "exciting",
    },

    "OLAK5uy_lNX0rUnIGzy7-JFvKbs0oSxpAzRCPRed8": {
        "description": "Ein Kind macht sich auf eine magische Reise, um einen geheimen Wunsch wahr werden zu lassen.",
        "genre": "fantasy",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2023,
        "mood": "heartwarming",
    },

    "OLAK5uy_lEAY5We7uhhjeCuw89LgsAc9i0qTk8NLc": {
        "description": "Ein Mädchen überwindet Widrigkeiten und findet sein Glück durch Mut und Güte.",
        "genre": "fairy_tale",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2015,
        "mood": "heartwarming",
    },

    "OLAK5uy_l7ClnZldSsZzHDTXeJcysmnEZEG-eX-8s": {
        "description": "Ein Junge entdeckt die Welt der Toten und muss seine verstorbene Familie finden.",
        "genre": "fantasy",
        "franchise": "pixar",
        "min_age": 6,
        "source_release_year": 2017,
        "mood": "heartwarming",
    },

    "OLAK5uy_lCgHBJzv-CF-T6PoTuphles7HQtVvqFbk": {
        "description": "Ein Spielzeug muss lernen, dass es nicht das Wichtigste in der Welt eines Kindes ist, wenn ein neues Spielzeug ankommt.",
        "series": "Toy Story",
        "position_in_series": 1,
        "genre": "adventure",
        "franchise": "pixar",
        "min_age": 4,
        "source_release_year": 1995,
        "mood": "adventurous",
    },

    "OLAK5uy_l2vxY1WGKjDMX16cSsSDCbHmEvLnClm2M": {
        "description": "Eine Prinzessin flieht vor einer bösen Königin und findet Zuflucht bei freundlichen Waldwesen.",
        "genre": "fairy_tale",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 1937,
        "mood": "gentle",
    },

    "OLAK5uy_kwrZs3W4PNH-aJRUvkOoafbOS_J9zJ7Oo": {
        "description": "Ein junger Straßendieb findet eine magische Lampe und erhält die Chance, sein Leben völlig zu verändern.",
        "genre": "fairy_tale",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 1992,
        "mood": "adventurous",
    },

    "OLAK5uy_kw0MiYKPgMzBzH1tAu11nE6Lc4rxh2Wsk": {
        "description": "Ein Junge entdeckt eine verborgene Stadt in den Wolken und muss sich gegen dunkle Kräfte behaupten.",
        "genre": "adventure",
        "franchise": "pixar",
        "min_age": 6,
        "source_release_year": 2009,
        "mood": "adventurous",
    },

    "OLAK5uy_kundgUTfQdcOpKXKaj6VVik5VxrVXv8qw": {
        "description": "Bauernhoftiere geraten in chaotische Abenteuer, wenn sie sich selbstständig machen und Unsinn anstellen.",
        "genre": "comedy",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2004,
        "mood": "silly",
    },

    "OLAK5uy_koI0XDzfqYw2soOwJEqtP1FyiAJP_ebuU": {
        "description": "Ein Junge entdeckt ein Geheimnis über seine Herkunft und findet an der Küste unerwartete Freundschaft.",
        "genre": "fantasy",
        "franchise": "pixar",
        "min_age": 5,
        "source_release_year": 2021,
        "mood": "heartwarming",
        "seasonal": "summer",
    },

    "OLAK5uy_kmLVCReazoOwmF9XVVvgYXJ1RdOPzZFa0": {
        "description": "Ein Geheimagent-Auto wird in einen internationalen Spionagefall verwickelt und muss seine Familie schützen.",
        "series": "Cars",
        "position_in_series": 2,
        "genre": "adventure",
        "franchise": "pixar",
        "min_age": 4,
        "source_release_year": 2011,
        "mood": "exciting",
    },

    "OLAK5uy_kg0qHwby8-YPdDmP6iH5zfEOj8wsfZOb4": {
        "description": "Ein junges Mädchen entdeckt die innere Schönheit eines verzauberten Wesens und bricht damit einen bösen Fluch.",
        "series": "Die Schöne und das Biest",
        "genre": "fairy_tale",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2017,
        "mood": "heartwarming",
    },

    "OLAK5uy_ntT0Ve6F3NTuC3KRTgr1O_f44fnPpKBfQ": {
        "description": "Ein Mädchen muss lernen, über Äußerlichkeiten hinauszuschauen und wahre innere Schönheit zu erkennen.",
        "series": "Die Schöne und das Biest",
        "position_in_series": 1,
        "genre": "fairy_tale",
        "min_age": 4,
        "source_release_year": 1991,
        "mood": "heartwarming",
    },

    "OLAK5uy_ke-thGtflnODrBMuezYbYpy8QSpbdP1Oc": {
        "description": "Ein Krieger muss sich seiner Vergangenheit stellen und gegen eine dunkle Bedrohung kämpfen, um sein Volk zu retten.",
        "series": "Kung Fu Panda",
        "position_in_series": 2,
        "genre": "adventure",
        "franchise": "dreamworks",
        "min_age": 5,
        "source_release_year": 2011,
        "mood": "adventurous",
    },

    "OLAK5uy_kccPvfF199D-xEUPPp_9ge7FqbtuapX4c": {
        "description": "Ein junges Tier wächst in der Wildnis auf und muss lernen, sich in seiner Umgebung zurechtzufinden und seine Rolle zu finden.",
        "series": "Bambi",
        "position_in_series": 2,
        "genre": "classic",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2006,
        "mood": "heartwarming",
    },

    "OLAK5uy_kbbd0cygGfWMW8OM_IxE4YJ6lD1Hnlfgo": {
        "description": "Ein Abenteuer im Zoo, in dem Tiere zusammenarbeiten, um ein Geheimnis zu lösen und ihre Gemeinschaft zu schützen.",
        "series": "Zoomania",
        "position_in_series": 2,
        "genre": "adventure",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2025,
        "mood": "adventurous",
    },

    "OLAK5uy_k_xP81n2cp-CAuB8a65pUed-5h4Ixmp44": {
        "description": "Ein Mädchen mit magischen Haaren entdeckt die Welt jenseits seiner Isolation und findet dabei seine wahre Bestimmung.",
        "genre": "fairy_tale",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2010,
        "mood": "adventurous",
    },

    "OLAK5uy_kYcYRfvNlZbJJd16ilNswjluxiSvnybuM": {
        "description": "Ein Auto lernt, dass Freundschaft und Gemeinschaft wichtiger sind als Erfolg und Ruhm.",
        "series": "Cars",
        "position_in_series": 1,
        "genre": "adventure",
        "franchise": "pixar",
        "min_age": 4,
        "source_release_year": 2006,
        "mood": "heartwarming",
    },

    "OLAK5uy_kV11E1FyEC12rrZSiP1wtUxU3TT5c-MOw": {
        "description": "Spielzeuge müssen sich einer neuen Herausforderung stellen, als sie in ein Kindergarten-Abenteuer geraten.",
        "series": "Toy Story",
        "position_in_series": 3,
        "genre": "adventure",
        "franchise": "pixar",
        "min_age": 4,
        "source_release_year": 2010,
        "mood": "adventurous",
    },

    "OLAK5uy_kUG2V3s93Gvc4JFFHZpdGhEK5FkNvdJs0": {
        "description": "Eine Gruppe macht sich auf die Suche nach einem legendären Schatz auf einem geheimnisvollen Planeten.",
        "genre": "adventure",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2002,
        "mood": "adventurous",
    },

    "OLAK5uy_kRMBgAEPpzLpCzNhW1ErpslqDegTTTDTA": {
        "description": "Eine Geschichte über die ungewöhnliche Freundschaft zwischen zwei Charakteren aus unterschiedlichen Welten, die gemeinsam Abenteuer erleben.",
        "genre": "fantasy",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2005,
        "mood": "adventurous",
    },

    "OLAK5uy_kQ3XTPCT37ZXx2lumLYJ6DKbFwChnkXYs": {
        "description": "Ein Superhund-Filmstar muss lernen, dass seine echten Kräfte in Freundschaft und Mut liegen.",
        "genre": "adventure",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2008,
        "mood": "adventurous",
    },

    "OLAK5uy_kOGO310iCRP9ATXkZav6dptn8EDHe38ho": {
        "description": "Eine Gruppe von Tieren muss ihre Heimat verlassen und erlebt aufregende Abenteuer auf ihrer Reise zurück.",
        "series": "Madagascar",
        "position_in_series": 2,
        "genre": "comedy",
        "franchise": "dreamworks",
        "min_age": 4,
        "source_release_year": 2008,
        "mood": "funny",
    },

    "OLAK5uy_kNTbcVMS1WuJM23pQQcX4xADhDgfgdE30": {
        "description": "Eine Geschichte über innere Gefühle und Emotionen, die zum Leben erwachen und gemeinsam Abenteuer erleben.",
        "series": "Alles steht Kopf",
        "position_in_series": 1,
        "genre": "comedy",
        "franchise": "pixar",
        "min_age": 5,
        "source_release_year": 2015,
        "mood": "heartwarming",
    },

    "OLAK5uy_kK8J9XSQLPWmc5hItx9qU9ybeMTvuoPlM": {
        "description": "Ein Mädchen kämpft gegen Tradition und Schicksal, um ihr eigenes Abenteuer zu bestimmen.",
        "series": "Merida",
        "position_in_series": 1,
        "genre": "adventure",
        "franchise": "pixar",
        "min_age": 5,
        "source_release_year": 2012,
        "mood": "adventurous",
    },

    "OLAK5uy_kIOCOVKQ1hymSZYSZitxAnc1LBtGQYobI": {
        "description": "Ein Bär und seine Freunde erleben gemeinsam zauberhafte Abenteuer im Wald voller Freundschaft und Wärme.",
        "genre": "fairy_tale",
        "franchise": "disney",
        "min_age": 3,
        "source_release_year": 2011,
        "mood": "heartwarming",
    },

    "OLAK5uy_kHFZCUQ8uAA03ClwqmaJyGOmUuEDJmFws": {
        "description": "Eine weihnachtliche Geschichte über Großzügigkeit und Zusammensein während der Festzeit.",
        "genre": "fairy_tale",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 1983,
        "mood": "heartwarming",
        "seasonal": "christmas",
    },

    "OLAK5uy_kB4Blrc0yyraIEdfY1FlprO6w_yOzrhks": {
        "description": "Ein Mädchen verkleidet sich als Soldat, um ihren kranken Vater vor dem Militärdienst zu bewahren.",
        "series": "Mulan",
        "position_in_series": 1,
        "genre": "adventure",
        "franchise": "disney",
        "min_age": 5,
        "source_release_year": 1998,
        "mood": "adventurous",
    },

    "OLAK5uy_kAi57TwgXP3WVsHzZA1jz8A_NWGWPP3vM": {
        "description": "Ein außerirdisches Wesen strandet auf der Erde und freundet sich mit einem einsamen Kind an.",
        "series": "Lilo & Stitch",
        "genre": "adventure",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2025,
        "mood": "heartwarming",
    },

    "OLAK5uy_k8ZIXUjGwX8GXZu4RfHEOSLYlByrxTPPQ": {
        "description": "Eine Geschichte über unerwartete Freundschaften zwischen zwei sehr unterschiedlichen Charakteren in einer fantastischen Welt.",
        "series": "Die Monster AG",
        "position_in_series": 1,
        "genre": "comedy",
        "franchise": "pixar",
        "min_age": 4,
        "source_release_year": 2001,
        "mood": "funny",
    },

    "OLAK5uy_k8Rx3UELXDLdeVWfA9tFflFBXDMFWxtHs": {
        "description": "Ein in der Wildnis aufgewachsener Mensch muss sich zwischen seiner Natur und der Zivilisation entscheiden.",
        "series": "Tarzan",
        "genre": "adventure",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2013,
        "mood": "adventurous",
    },

    "OLAK5uy_k7tY3kG6h6qrg48K4bXmLO0QwGQ84hees": {
        "description": "Ein Straßenhund und ein verwöhnter Haushund werden Freunde und erleben gemeinsame Abenteuer in der Stadt.",
        "series": "Susi und Strolch",
        "position_in_series": 1,
        "genre": "adventure",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 1955,
        "mood": "heartwarming",
    },

    "OLAK5uy_k4GclUyGqUTnFHmSAFXgcXLUhJGu_Dg4A": {
        "description": "Ein Straßenkind und ein verwöhnter Haushund werden unerwartete Freunde und erleben gemeinsam Abenteuer.",
        "genre": "adventure",
        "source_release_year": 1981,
        "mood": "heartwarming",
        "min_age": 4,
    },

    "OLAK5uy_k3wcD9oqepKNt2J1ZBbPuAzSwVDRx_3Gg": {
        "description": "Spielzeugen erleben Abenteuer und müssen lernen, zusammenzuarbeiten und Befehle zu befolgen.",
        "series": "Toy Story",
        "genre": "adventure",
        "franchise": "pixar",
        "min_age": 4,
        "source_release_year": 2019,
        "mood": "adventurous",
    },

    "OLAK5uy_k2zoA9rd9BfKTseNVJBvIif9avP46xFws": {
        "description": "Ein verzaubertes Schloss und eine ungewöhnliche Freundschaft während der festlichen Jahreszeit.",
        "series": "Die Schöne und das Biest",
        "position_in_series": 2,
        "genre": "fairy_tale",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 1997,
        "mood": "heartwarming",
        "seasonal": "christmas",
    },

    "OLAK5uy_k1hbEIDe47tFGg80KxSPrzJUB-Yt1lyyc": {
        "description": "Ein Mädchen träumt davon, sein Leben zu verändern und findet dabei wahre Freundschaft und innere Stärke.",
        "series": "Cinderella",
        "position_in_series": 2,
        "genre": "fairy_tale",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2002,
        "mood": "heartwarming",
    },

    "OLAK5uy_k1NtuVYsO5k0pEW4qvx9DYL7ZiJHJ95S0": {
        "description": "Ein Hotelmanager muss seine Unterkunft vor neugierigen Gästen schützen und dabei seine Familie bewahren.",
        "genre": "comedy",
        "source_release_year": 2012,
        "mood": "spooky",
        "seasonal": "halloween",
        "min_age": 6,
    },

    "OLAK5uy_k0su_4jE-pvnaRx3DR_uzgqvnzVHqHO_k": {
        "description": "Ein junger Elefant mit großen Ohren entdeckt seine besonderen Fähigkeiten und findet seinen Platz in der Welt.",
        "genre": "classic",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2019,
        "mood": "heartwarming",
    },

    "OLAK5uy_m5np3cQD6JI4qqyaKPFkyYJacjmepggw0": {
        "description": "Ein alter Mann und sein kluges Haustier erleben zusammen alltägliche Abenteuer voller Wärme und Humor.",
        "series": "Pettersson und Findus",
        "position_in_series": 1,
        "genre": "comedy",
        "min_age": 4,
        "source_release_year": 1999,
        "mood": "heartwarming",
    },

    "OLAK5uy_lAEv53WjTcYdbezfmqvoRbp0rxbCTTWSk": {
        "description": "Ein unwahrscheinlicher Held muss seine innere Kraft entdecken, um sein Dorf vor einer großen Bedrohung zu bewahren.",
        "series": "Kung Fu Panda",
        "position_in_series": 1,
        "genre": "adventure",
        "franchise": "dreamworks",
        "min_age": 5,
        "source_release_year": 2008,
        "mood": "adventurous",
    },

    "OLAK5uy_nT1mL8aZvxqfIRFN9L8FgIzfvk6HUkd0I": {
        "description": "Vier Zootiere landen auf einer exotischen Insel und müssen sich an das Wildleben anpassen.",
        "series": "Madagascar",
        "position_in_series": 1,
        "genre": "comedy",
        "franchise": "dreamworks",
        "min_age": 4,
        "source_release_year": 2005,
        "mood": "funny",
        "seasonal": "summer",
    },

    "OLAK5uy_mSqQ0DFEOq4ehi5QCmGcMbse1XPGrH9Jg": {  # Findet Nemo
        "description": "Ein Fisch macht sich auf eine gefährliche Reise durchs Meer, um seinen vermissten Sohn zu finden.",
    #     "series": None,
    #     "position_in_series": None,
        "genre": "adventure",
        "franchise": "pixar",
        "min_age": 4,
        "source_release_year": 2003,
        "mood": "adventurous",
    },
    "OLAK5uy_kWp4zrOmfr7_cHq_gimr2USOc7LHme7PQ": {  # Findet Dorie
        "description": "Eine blaue Fisch sucht nach ihrer Familie und erlebt dabei ein großes Abenteuer im Meer.",
    #     "series": None,
    #     "position_in_series": None,
        "genre": "adventure",
        "franchise": "pixar",
        "min_age": 4,
        "source_release_year": 2016,
        "mood": "adventurous",
    },
    "OLAK5uy_kCqtsmYi_20kuxHQf8WBmy9L7jhSnhe78": {  # Der König der Löwen (Real-Kinofilm)
        "description": "Ein junger Löwe muss sein Schicksal akzeptieren und seine Heimat vor dunklen Kräften bewahren.",
        "series": "Der König der Löwen",
    #     "position_in_series": None,
        "genre": "adventure",
        "franchise": "disney",
        "min_age": 5,
        "source_release_year": 2019,
        "mood": "adventurous",
    },
    "OLAK5uy_m_ZAOgZp19B5aS8BSI533zAmijpecO9jc": {  # Mufasa: Der König der Löwen
        "description": "Ein verwaistes Löwenjunge trifft einen Prinzen und zusammen erleben sie eine schicksalhafte Reise voller Abenteuer und Gefahr.",
        "series": "Der König der Löwen",
    #     "position_in_series": None,
        "genre": "adventure",
        "franchise": "disney",
        "min_age": 5,
        "source_release_year": 2024,
        "mood": "adventurous",
    },
    "OLAK5uy_k5Z43Vmx4X97Cn_94eb-kYv61EYRvx4e4": {  # Der König der Löwen
        "description": "Ein junger Löwe muss nach tragischen Ereignissen ins Exil fliehen und findet später die Kraft, zu seiner Heimat zurückzukehren.",
        "series": "Der König der Löwen",
        "position_in_series": 1,
        "genre": "adventure",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 1994,
        "mood": "adventurous",
    },
    "OLAK5uy_kUcmQbAHGkB0ML_QLqW85icbTMlbzQ7X8": {  # Der König der Löwen 2 - Simbas Königreich
        "description": "Ein junger Herrscher muss sein Reich verteidigen und seine Verantwortung als Anführer erfüllen.",
        "series": "Der König der Löwen",
        "position_in_series": 2,
        "genre": "adventure",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 1998,
        "mood": "adventurous",
    },
    "OLAK5uy_mUHEROIxVoKVrIDtQ_C1odIq7W7JqxiDs": {  # Der König der Löwen 3 - Hakuna Matata
        "description": "Eine Geschichte über Freundschaft und das Überwinden von Hindernissen in der afrikanischen Savanne.",
        "series": "Der König der Löwen",
        "position_in_series": 3,
        "genre": "adventure",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2004,
        "mood": "funny",
    },
    "OLAK5uy_nMtWXXdz9mDJJzBfIB66BT5ppudiV5eSk": {  # Vaiana
        "description": "Ein junges Mädchen aus einem abgelegenen Inselvolk begibt sich auf eine gefährliche Seereise, um ihr Volk zu retten.",
        "series": "Vaiana",
        "position_in_series": 1,
        "genre": "adventure",
        "franchise": "disney",
        "min_age": 6,
        "source_release_year": 2016,
        "mood": "adventurous",
    },
    "OLAK5uy_mlxW-N-Rs4Ezsg-cML8PncH7s_n4IV1QA": {  # Vaiana 2
        "description": "Eine junge Heldin begibt sich auf eine gefährliche Seereise, um ihr Volk zu retten und ein altes Geheimnis zu enthüllen.",
        "series": "Vaiana",
        "position_in_series": 2,
        "genre": "adventure",
        "franchise": "disney",
        "min_age": 6,
        "source_release_year": 2024,
        "mood": "adventurous",
    },
    "OLAK5uy_m_h-aUU1R1qE6LcDBTEZ3kd1jr-spRZns": {  # Peter Pan
        "description": "Ein Junge, der nicht altert, führt Kinder in ein magisches Land voller Abenteuer und Gefahren.",
        "series": "Peter Pan",
        "position_in_series": 1,
        "genre": "fairy_tale",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 1953,
        "mood": "adventurous",
    },
    "OLAK5uy_nZLW8_8zkzseZZnwEYWYC_x2q9ILwkJH4": {  # Peter Pan 2 - Neue Abenteuer in Nimmer Land
        "description": "Junge Abenteurer erleben magische Herausforderungen in einer fantastischen Welt ohne Altern und kämpfen gegen dunkle Mächte.",
        "series": "Peter Pan",
        "position_in_series": 2,
        "genre": "fairy_tale",
        "franchise": "disney",
        "min_age": 5,
        "source_release_year": 2002,
        "mood": "adventurous",
    },
    "OLAK5uy_mIwvauQpR3lTqtVwm-6a2IsONlCtc08Ps": {  # Peter Pan & Wendy (Real-Film)
        "description": "Ein Junge führt Kinder in ein magisches Land, wo sie Abenteuer erleben und nie erwachsen werden.",
        "series": "Peter Pan",
    #     "position_in_series": None,
        "genre": "fairy_tale",
        "franchise": "disney",
        "min_age": 6,
        "source_release_year": 2023,
        "mood": "adventurous",
    },
    "OLAK5uy_kDNe9h1vmPckr-4AMKagUD6TiYj2LOfb4": {  # Küss den Frosch
        "description": "Ein Mädchen muss einen verwunschenen Prinzen erlösen und lernt dabei wichtige Lektionen über Mut und Freundschaft.",
    #     "series": None,
    #     "position_in_series": None,
        "genre": "fairy_tale",
        "franchise": "disney",
        "min_age": 4,
        "source_release_year": 2009,
        "mood": "adventurous",
    },
    "OLAK5uy_nXayOLN8th_TQrewhWmRfRkZ90weYcWiw": {  # Arlo & Spot
        "description": "Ein ungleiches Duo begibt sich auf eine abenteuerliche Reise durch die Wildnis, um nach Hause zu finden.",
    #     "series": None,
    #     "position_in_series": None,
        "genre": "adventure",
        "franchise": "pixar",
        "min_age": 4,
        "source_release_year": 2015,
        "mood": "heartwarming",
    },
}
