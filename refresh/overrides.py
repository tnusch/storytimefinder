"""
Manual per-item metadata overrides, keyed by YouTube video id.

The YouTube Data API only gives us title, thumbnail, duration, description,
publish date, and channel name. It has no concept of series, episode
number, or genre, so those fields have to be curated by hand here.
refresh.py applies these on every run (merged in after the API data), so
they're safe from being wiped out by a re-sync and stay version-controlled
like the rest of the curation.

All fields are optional - omit whatever you don't know. `publisher` is
also accepted here to override the raw YouTube channel name with a cleaner
label (e.g. "Universal Music" instead of "UniversalMusicKidsDE - Topic").

Example:
    ITEM_OVERRIDES = {
        "dQw4w9WgXcQ": {
            "series": "Die drei ???",
            "position_in_series": 78,
            "genre": "Krimi",
            "publisher": "Europa",
        },
    }
"""

ITEM_OVERRIDES: dict[str, dict] = {}
