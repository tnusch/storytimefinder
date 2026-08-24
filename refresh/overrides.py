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
  - `franchise`: IP/brand grouping - NOT genre, NOT publisher. One value
    from this fixed list, or omit/None for a standalone (non-franchise)
    title:
        disney, pixar, dreamworks, marvel, star_wars, bibi_blocksberg,
        benjamin_bluemchen, die_drei_fragezeichen, tkkg
    (refresh.py logs a warning, but doesn't fail the sync, if a genre or
    franchise value isn't in its fixed list - see GENRE_VALUES/
    FRANCHISE_VALUES in refresh.py.)
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
    the age filter, same as before.
  - `source_release_year`: the year the SOURCE film or book was originally
    released - e.g. 1994 for a "The Lion King" audiobook - NOT the
    audiobook production's own release/upload date. The audiobook's own
    date is often ambiguous (the same title can show several different
    years across editions/reissues/platforms), while the source material's
    release year is a single stable, verifiable fact. Year only (an int),
    not a full date.
  - `series`, `position_in_series`: e.g. "Die drei ???" / 78 for episode 78
    of that series.
  - `mood`: exactly ONE value from this fixed list (not a list/multi-select),
    a subjective read of the story's overall tone - a creative judgment
    call, not a factual claim, but still gated behind the same human-review
    step as every other field:
        calm, funny, spooky, adventurous, heartwarming, exciting, silly, gentle
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

Series consistency checks: every entry sharing the same `series` name
(across every source, not just one - a series could in principle span more
than one) is compared against the others for two likely mistakes, warned
about but never a hard failure:
  - entries in the same series disagreeing on `genre`/`franchise`/`mood`/
    `seasonal` - a real series is usually consistent on all four, so a
    mismatch is more often a typo or a forgotten field in one entry than a
    deliberate choice. Fix it by aligning the odd one out, or ignore the
    warning if the disagreement really is intentional (some Disney series
    do shift genre/mood between installments).
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
    ITEM_OVERRIDES = {
        "dQw4w9WgXcQ": {
            "description": "Episode 78 der drei Detektive: ein spurloses Verschwinden im Nebel.",
            "series": "Die drei ???",
            "position_in_series": 78,
            "genre": "mystery",
            "franchise": "die_drei_fragezeichen",
            "min_age": 8,
            "source_release_year": 1999,
            "mood": "spooky",
            "awards": [
                {"name": "Deutscher Hörbuchpreis", "category": "Bestes Kinderhörbuch", "year": 2026},
            ],
        },
        "OLAK5uy_mSqQ0DFEOq4ehi5QCmGcMbse1XPGrH9Jg": {  # an 'album' source
            "description": "Ein Clownfisch sucht seinen vermissten Sohn und erlebt dabei ein großes Abenteuer im Meer.",
            "genre": "adventure",
            "franchise": "disney",
            "source_release_year": 2003,
            "mood": "heartwarming",
        },
    }
"""

ITEM_OVERRIDES: dict[str, dict] = {
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
