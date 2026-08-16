"""
Seed list of curated YouTube sources for the refresh pipeline.

Each entry becomes a row in the `sources` table (see refresh.py). `type`
determines which YouTube Data API call is used to enumerate items:

  - "channel":  resolved to the channel's uploads playlist, then walked with
                playlistItems.list (cheap on quota)
  - "playlist": walked directly with playlistItems.list
  - "album":    a YouTube Music album/playlist id, walked the same way as
                "playlist" - kept as a separate type only for curation
                bookkeeping (so you can tell "official album" apart from
                "someone's playlist" later)

IMPORTANT: the youtube_id values below are PLACEHOLDERS. Replace each one
with a real channel ID (starts with "UC...", found via a channel's page
source or https://commentpicker.com/youtube-channel-id.php) or playlist ID
(starts with "PL..." or "OLAK5uy_...") before running refresh.py for real.
Nothing in this file has been verified against the live YouTube Data API -
treat it as a starting skeleton for curation, not a finished catalog.
"""

SOURCES = [
    {
        "type": "channel",
        "youtube_id": "UC_REPLACE_WITH_REAL_CHANNEL_ID",
        "label": "Hörspiele für Kinder (placeholder)",
        "language": "de",
        "category": "hoerspiel",
        "age_tag": "3-6",
        "active": False,
    },
    {
        "type": "channel",
        "youtube_id": "UC_REPLACE_WITH_REAL_CHANNEL_ID",
        "label": "Disney Hörspiele (placeholder)",
        "language": "de",
        "category": "disney",
        "age_tag": "all",
        "active": False,
    },
    {
        "type": "playlist",
        "youtube_id": "PL_REPLACE_WITH_REAL_PLAYLIST_ID",
        "label": "Klassiker Hörspiele (placeholder)",
        "language": "de",
        "category": "classic",
        "age_tag": "6-10",
        "active": False,
    },
]
