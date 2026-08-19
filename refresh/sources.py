"""
Seed list of curated YouTube sources for the refresh pipeline.

Each entry becomes a row in the `sources` table (see refresh.py). `type`
determines which YouTube Data API call is used to enumerate items:

  - "channel":  resolved to the channel's uploads playlist, then walked with
                playlistItems.list (cheap on quota) - one catalog item per
                video
  - "playlist": walked directly with playlistItems.list - one catalog item
                per video
  - "album":    a YouTube Music album/playlist id whose tracks are chapters
                of a single audiobook (e.g. "Kapitel 01: ...", "Kapitel
                02: ..."). Unlike "playlist", this collapses down to ONE
                catalog item for the whole album: title/description/
                thumbnail come from the playlist's own metadata (title is
                actually this source's own `label`, see build_album_entry()),
                and duration is the sum of every chapter's duration.

`genre`, `franchise`, `age_tag`, and `source_release_year` are NOT set here -
they're per-item fields curated entirely through `overrides.py` (keyed by
video id, or playlist/album id for an "album" source), since a single
channel/playlist can span more than one genre/franchise/age group, and the
source's original release year has no API equivalent at all. An item with no
matching override entry syncs with all four unset (null) - see overrides.py's
docstring.

IMPORTANT: the youtube_id values below are PLACEHOLDERS. Replace each one
with a real channel ID (starts with "UC...", found via a channel's page
source or https://commentpicker.com/youtube-channel-id.php) or playlist ID
(starts with "PL..." or "OLAK5uy_...") before running refresh.py for real.
Nothing in this file has been verified against the live YouTube Data API -
treat it as a starting skeleton for curation, not a finished catalog.
"""

SOURCES = [
    # {
    #     "type": "channel",
    #     "youtube_id": "UC_REPLACE_WITH_REAL_CHANNEL_ID",
    #     "label": "Hörspiele für Kinder (placeholder)",
    #     "language": "de",
    #     "active": False,
    # },
    # {
    #     "type": "channel",
    #     "youtube_id": "UC_REPLACE_WITH_REAL_CHANNEL_ID",
    #     "label": "Disney Hörspiele (placeholder)",
    #     "language": "de",
    #     "active": False,
    # },
    {
        "type": "album",
        "youtube_id": "OLAK5uy_mSqQ0DFEOq4ehi5QCmGcMbse1XPGrH9Jg",
        "label": "Findet Nemo",
        "language": "de",
        "active": True,
    },
    {
        "type": "album",
        "youtube_id": "OLAK5uy_kWp4zrOmfr7_cHq_gimr2USOc7LHme7PQ",
        "label": "Findet Dorie",
        "language": "de",
        "active": True,
    },
    {
        "type": "album",
        "youtube_id": "OLAK5uy_kCqtsmYi_20kuxHQf8WBmy9L7jhSnhe78",
        "label": "Der König der Löwen (Real-Kinofilm)",
        "language": "de",
        "active": True,
    },
    {
        "type": "album",
        "youtube_id": "OLAK5uy_m_ZAOgZp19B5aS8BSI533zAmijpecO9jc",
        "label": "Mufasa: Der König der Löwen",
        "language": "de",
        "active": True,
    },
    {
        "type": "album",
        "youtube_id": "OLAK5uy_k5Z43Vmx4X97Cn_94eb-kYv61EYRvx4e4",
        "label": "Der König der Löwen",
        "language": "de",
        "active": True,
    },
    {
        "type": "album",
        "youtube_id": "OLAK5uy_kUcmQbAHGkB0ML_QLqW85icbTMlbzQ7X8",
        "label": "Der König der Löwen 2 - Simbas Königreich",
        "language": "de",
        "active": True,
    },
    {
        "type": "album",
        "youtube_id": "OLAK5uy_mUHEROIxVoKVrIDtQ_C1odIq7W7JqxiDs",
        "label": "Der König der Löwen 3 - Hakuna Matata",
        "language": "de",
        "active": True,
    },
    {
        "type": "album",
        "youtube_id": "OLAK5uy_nMtWXXdz9mDJJzBfIB66BT5ppudiV5eSk",
        "label": "Vaiana",
        "language": "de",
        "active": True,
    },
    {
        "type": "album",
        "youtube_id": "OLAK5uy_mlxW-N-Rs4Ezsg-cML8PncH7s_n4IV1QA",
        "label": "Vaiana 2",
        "language": "de",
        "active": True,
    },
    {
        "type": "album",
        "youtube_id": "OLAK5uy_m_h-aUU1R1qE6LcDBTEZ3kd1jr-spRZns",
        "label": "Peter Pan",
        "language": "de",
        "active": True,
    },
    {
        "type": "album",
        "youtube_id": "OLAK5uy_nZLW8_8zkzseZZnwEYWYC_x2q9ILwkJH4",
        "label": "Peter Pan 2 - Neue Abenteuer in Nimmer Land",
        "language": "de",
        "active": True,
    },
    {
        "type": "album",
        "youtube_id": "OLAK5uy_mIwvauQpR3lTqtVwm-6a2IsONlCtc08Ps",
        "label": "Peter Pan & Wendy (Real-Film)",
        "language": "de",
        "active": True,
    },
    {
        "type": "album",
        "youtube_id": "OLAK5uy_kDNe9h1vmPckr-4AMKagUD6TiYj2LOfb4",
        "label": "Küss den Frosch",
        "language": "de",
        "active": True,
    },
    {
        "type": "album",
        "youtube_id": "OLAK5uy_nXayOLN8th_TQrewhWmRfRkZ90weYcWiw",
        "label": "Arlo & Spot",
        "language": "de",
        "active": True,
    },
    # {
    #     "type": "album",
    #     "youtube_id": "URL_URL_URL_URL_URL_URL_",
    #     "label": "TITLE_TITLE_TITLE_TITLE_",
    #     "language": "de",
    #     "active": True,
    # },
    # {
    #     "type": "album",
    #     "youtube_id": "URL_URL_URL_URL_URL_URL_",
    #     "label": "TITLE_TITLE_TITLE_TITLE_",
    #     "language": "de",
    #     "active": True,
    # },
    # {
    #     "type": "album",
    #     "youtube_id": "URL_URL_URL_URL_URL_URL_",
    #     "label": "TITLE_TITLE_TITLE_TITLE_",
    #     "language": "de",
    #     "active": True,
    # },
    # {
    #     "type": "album",
    #     "youtube_id": "URL_URL_URL_URL_URL_URL_",
    #     "label": "TITLE_TITLE_TITLE_TITLE_",
    #     "language": "de",
    #     "active": True,
    # },
    # {
    #     "type": "album",
    #     "youtube_id": "URL_URL_URL_URL_URL_URL_",
    #     "label": "TITLE_TITLE_TITLE_TITLE_",
    #     "language": "de",
    #     "active": True,
    # },
    # {
    #     "type": "album",
    #     "youtube_id": "URL_URL_URL_URL_URL_URL_",
    #     "label": "TITLE_TITLE_TITLE_TITLE_",
    #     "language": "de",
    #     "active": True,
    # },
]
