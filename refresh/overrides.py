"""
Manual per-item metadata overrides, keyed by catalog entry id.

For 'channel'/'playlist' sources that's a YouTube video id (one entry per
video). For 'album' sources it's the playlist/album id instead, since an
album collapses down to a single catalog entry for the whole audiobook
(see build_album_entry() in refresh.py) - not one entry per chapter.

The YouTube Data API gives us a raw video/album description, but it's never
used - `description` here is entirely override-only too, same as the other
six fields below. It has no concept of series, episode number, genre,
franchise, age group, or the *source* material's original release year
either, so all seven fields have to be curated by hand here. refresh.py
applies these on every run (merged in after the API data), so they're safe
from being wiped out by a re-sync and stay version-controlled like the rest
of the curation.

For every genuinely new item, refresh.py also asks Claude for best-effort
suggestions for all seven of these fields (one combined call, to keep token
spend down - see generate_metadata_suggestions() in refresh.py) and writes
them to data/claude_suggestions.json for you to review by hand. That file
is NEVER read back into the catalog - it's a staging area, not a data
source. Nothing Claude proposes reaches the catalog on its own, `description`
included; if you agree with a suggestion, copy it into an entry here
yourself. ITEM_OVERRIDES here is always the only thing that actually
reaches the catalog.

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
        },
        "OLAK5uy_mSqQ0DFEOq4ehi5QCmGcMbse1XPGrH9Jg": {  # an 'album' source
            "description": "Ein Clownfisch sucht seinen vermissten Sohn und erlebt dabei ein großes Abenteuer im Meer.",
            "genre": "adventure",
            "franchise": "disney",
            "source_release_year": 2003,
        },
    }
"""

ITEM_OVERRIDES: dict[str, dict] = {
    "OLAK5uy_mSqQ0DFEOq4ehi5QCmGcMbse1XPGrH9Jg": {  # Findet Nemo
        "description": "Ein Clownfisch sucht seinen vermissten Sohn und erlebt dabei ein großes Abenteuer im Meer.",
    #     "series": None,
    #     "position_in_series": None,
    #     "genre": None,
        "franchise": "disney",
    #     "min_age": None,
    #     "source_release_year": None,
    },
    "OLAK5uy_kWp4zrOmfr7_cHq_gimr2USOc7LHme7PQ": {  # Findet Dorie
        "description": "Ein Fisch mit Gedächtnisverlust begibt sich auf eine abenteuerliche Reise, um seine Familie zu finden.",
    #     "series": None,
    #     "position_in_series": None,
    #     "genre": None,
        "franchise": "disney",
    #     "min_age": None,
    #     "source_release_year": None,
    },
    "OLAK5uy_kCqtsmYi_20kuxHQf8WBmy9L7jhSnhe78": {  # Der König der Löwen (Real-Kinofilm)
        "description": "Ein junger Löwe muss sein Schicksal annehmen und sein Königreich zurückgewinnen.",
    #     "series": None,
    #     "position_in_series": None,
    #     "genre": None,
        "franchise": "disney",
    #     "min_age": None,
    #     "source_release_year": None,
    },
    "OLAK5uy_m_ZAOgZp19B5aS8BSI533zAmijpecO9jc": {  # Mufasa: Der König der Löwen
    #     "description": None,
    #     "series": None,
    #     "position_in_series": None,
    #     "genre": None,
        "franchise": "disney",
    #     "min_age": None,
    #     "source_release_year": None,
    },
    "OLAK5uy_k5Z43Vmx4X97Cn_94eb-kYv61EYRvx4e4": {  # Der König der Löwen
        "description": "Ein junger Löwe muss sein Schicksal annehmen und sein Königreich vor dunklen Mächten bewahren.",
    #     "series": None,
    #     "position_in_series": None,
    #     "genre": None,
        "franchise": "disney",
    #     "min_age": None,
    #     "source_release_year": None,
    },
    "OLAK5uy_kUcmQbAHGkB0ML_QLqW85icbTMlbzQ7X8": {  # Der König der Löwen 2 - Simbas Königreich
        "description": "Ein junger Herrscher muss sein Reich verteidigen und seine Verantwortung als Anführer erfüllen.",
    #     "series": None,
    #     "position_in_series": None,
    #     "genre": None,
        "franchise": "disney",
    #     "min_age": None,
    #     "source_release_year": None,
    },
    "OLAK5uy_mUHEROIxVoKVrIDtQ_C1odIq7W7JqxiDs": {  # Der König der Löwen 3 - Hakuna Matata
        "description": "Eine Geschichte über Freundschaft und das Finden des eigenen Weges in der Savanne.",
    #     "series": None,
    #     "position_in_series": None,
    #     "genre": None,
        "franchise": "disney",
    #     "min_age": None,
    #     "source_release_year": None,
    },
    "OLAK5uy_nMtWXXdz9mDJJzBfIB66BT5ppudiV5eSk": {  # Vaiana
        "description": "Eine junge Frau begibt sich auf eine gefährliche Seereise über den Ozean, um ihr Volk zu retten.",
    #     "series": None,
    #     "position_in_series": None,
    #     "genre": None,
        "franchise": "disney",
    #     "min_age": None,
    #     "source_release_year": None,
    },
    "OLAK5uy_mlxW-N-Rs4Ezsg-cML8PncH7s_n4IV1QA": {  # Vaiana 2
        "description": "Eine Heldin begibt sich auf eine gefährliche Seereise, um ihr Volk zu retten und ein altes Geheimnis zu enthüllen.",
    #     "series": None,
    #     "position_in_series": None,
    #     "genre": None,
        "franchise": "disney",
    #     "min_age": None,
    #     "source_release_year": None,
    },
    "OLAK5uy_m_h-aUU1R1qE6LcDBTEZ3kd1jr-spRZns": {  # Peter Pan
        "description": "Ein Junge, der nicht älter wird, führt Kinder in ein magisches Land voller Abenteuer und kämpft gegen böse Mächte.",
    #     "series": None,
    #     "position_in_series": None,
    #     "genre": None,
        "franchise": "disney",
    #     "min_age": None,
    #     "source_release_year": None,
    },
    "OLAK5uy_nZLW8_8zkzseZZnwEYWYC_x2q9ILwkJH4": {  # Peter Pan 2 - Neue Abenteuer in Nimmer Land
        "description": "Junge Abenteurer erkunden eine magische Welt voller Wunder und Gefahren, um ihr Zuhause zu schützen.",
    #     "series": None,
    #     "position_in_series": None,
    #     "genre": None,
        "franchise": "disney",
    #     "min_age": None,
    #     "source_release_year": None,
    },
    "OLAK5uy_mIwvauQpR3lTqtVwm-6a2IsONlCtc08Ps": {  # Peter Pan & Wendy (Real-Film)
        "description": "Ein Junge führt Kinder in ein magisches Land, wo sie Abenteuer erleben und gegen böse Kräfte kämpfen.",
    #     "series": None,
    #     "position_in_series": None,
    #     "genre": None,
        "franchise": "disney",
    #     "min_age": None,
    #     "source_release_year": None,
    },
    "OLAK5uy_kDNe9h1vmPckr-4AMKagUD6TiYj2LOfb4": {  # Küss den Frosch
    #     "description": None,
    #     "series": None,
    #     "position_in_series": None,
    #     "genre": None,
        "franchise": "disney",
    #     "min_age": None,
    #     "source_release_year": None,
    },
    "OLAK5uy_nXayOLN8th_TQrewhWmRfRkZ90weYcWiw": {  # Arlo & Spot
        "description": "Ein junger Dinosaurier und sein menschlicher Freund erleben gemeinsam Abenteuer in einer prähistorischen Welt.",
    #     "series": None,
    #     "position_in_series": None,
    #     "genre": None,
        "franchise": "disney",
    #     "min_age": None,
    #     "source_release_year": None,
    },
}
