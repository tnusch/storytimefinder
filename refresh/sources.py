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
    {
        "type": "album",
        "youtube_id": "OLAK5uy_mk1rApVK6CxC1T7JfYx53jaJE0BtApAaE",
        "label": "Toy Story 4",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_kmLVCReazoOwmF9XVVvgYXJ1RdOPzZFa0",
        "label": "Cars 2",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_l7ClnZldSsZzHDTXeJcysmnEZEG-eX-8s",
        "label": "Coco",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_nf9pDKOq0IVh-loWWSF6v2VLm-VJZAokE",
        "label": "Soul",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_k8ZIXUjGwX8GXZu4RfHEOSLYlByrxTPPQ",
        "label": "Die Monster AG",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_nnhLzV862YYp4wwic75VSXQJWCvxYr0DQ",
        "label": "Die Unglaublichen - The Incredibles",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_m3oJuBguPxtknzSnqvQSMGWn6ICf6BPWE",
        "label": "Rot",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_lzZjFEUpcdHvCgOVFvkFxuQyprGBHRF-4",
        "label": "Lightyear",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_k4GclUyGqUTnFHmSAFXgcXLUhJGu_Dg4A",
        "label": "Cap und Capper",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_nmCLOP7hjBJtEVIMEvi0uOwH1RaakvUo8",
        "label": "Ein Königreich für ein Lama",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_nvAPM1KYwDmyVcBJkDzeCvushOyCzeY1M",
        "label": "Bärenbrüder",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_nZhJ91S_mNEFmyFMvV-N8bY3mhxq2e8-U",
        "label": "Tierisch Wild",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_mCUNR-Av0GzcrZ9vfuaOIIMlNVBg-95Q8",
        "label": "Encanto",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_mWaaL1fk_QUpmiBrEtFRf7UFhdvEO6G2g",
        "label": "Strange World",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_n0HRLnDJ5o7q1VeH0WrzXAflNYGbFgZPs",
        "label": "Tinker Bell - Ein Sommer voller Abenteuer",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_nIlfMQgrwbOxbgSPRIixxI3qt1_D4bilM",
        "label": "Die Eiskönigin: Olaf taut auf",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_nQbGAQTtMuyp_n7rO7Xz6B-Re4agRiso4",
        "label": "Kung Fu Panda 3",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_lqa1SNw9mLihZLbNKqzV7EHhwcC45smGk",
        "label": "Alice im Wunderland - Hinter den Spiegeln",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_mUJXtJvaGm1o19boWNKPn9zU-am8OXRXQ",
        "label": "Das Dschungelbuch",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_loAK3fXOH3uOo3T00so5cPnGsYsspZpEQ",
        "label": "Dumbo",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_k8Rx3UELXDLdeVWfA9tFflFBXDMFWxtHs",
        "label": "Tarzan",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_ke-thGtflnODrBMuezYbYpy8QSpbdP1Oc",
        "label": "Kung Fu Panda 2",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_mF7TtT8TcZBNPj2wNOsygEGUxPB9fhJRc",
        "label": "Mulan",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_koI0XDzfqYw2soOwJEqtP1FyiAJP_ebuU",
        "label": "Luca",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_mlBwAOSeO8VJhCoRM4guDX6imu4giVs8k",
        "label": "Das grosse Krabbeln",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_mUJXtJvaGm1o19boWNKPn9zU-am8OXRXQ",
        "label": "Das Dschungelbuch",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_n2rqUY97UHsO4XcWOTzPbb4bvFl_NhBQg",
        "label": "101 Dalmatiner",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_loAK3fXOH3uOo3T00so5cPnGsYsspZpEQ",
        "label": "Dumbo",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_k3wcD9oqepKNt2J1ZBbPuAzSwVDRx_3Gg",
        "label": "A Toy Story: Alles hört auf kein Kommando",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_nOc6WKydiRIxbcQOfc-RzJWcj2ueAJpQY",
        "label": "Phineas und Ferb der Film: Candace gegen das Universum",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_muFPBJI4TLYs5fNENHVPal57RJqqrkZ0w",
        "label": "Toy Story 5",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_lm8n1UHMVHPKySZ-dRFs_aTYl9x_lAPDI",
        "label": "Der Nussknacker und die vier Reiche",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_nJRQQEIIqbhr4kzAJBvDOQLP35g6bNCQM",
        "label": "Onward: Keine halben Sachen",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_kHFZCUQ8uAA03ClwqmaJyGOmUuEDJmFws",
        "label": "Mickey's Weihnachts-Erzählung",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_mM5uoTUzZCg1mBg1zoiNplSA6kRdlGEaw",
        "label": "Der einzig wahre Ivan",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_kUz3yb-KbwBsK2pslAd08fwHVPsAdfjNg",
        "label": "Wall-E - Der Letzte räumt die Erde auf",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_mKQtP61sPR5npHu7DZtrVFhAQdQo9V-I8",
        "label": "Susi und Strolch 2: Kleine Strolche - Großes Abenteuer",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_mLkUymz-JBD0gR3Cl9KcbaDmajDq_tETs",
        "label": "Frankenweenie",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_k2zoA9rd9BfKTseNVJBvIif9avP46xFws",
        "label": "Die Schöne und das Biest - Weihnachtszauber",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_neRq_XHTqVD1AWQcTs8E7FQL08KB8sOr4",
        "label": "Flora & Ulysses",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_ly--6KeCsZMRhG4nTI6uXdIbFEwkaJgo0",
        "label": "Fantasia",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_kOGO310iCRP9ATXkZav6dptn8EDHe38ho",
        "label": "Madagascar 2",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_npX4I2rAwUnbX39bRnWaHy7jrGcKX8LSA",
        "label": "Planes 2 - Immer im Einsatz",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_neBCIjeNGVDNWSnBkoE4a0oEydUFyRH8U",
        "label": "The Jungle Book",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_lO86h88tvQMYISO9_3k3r7YKYK1pHhwxE",
        "label": "Die Unglaublichen 2",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_kYcYRfvNlZbJJd16ilNswjluxiSvnybuM",
        "label": "Cars",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_k0su_4jE-pvnaRx3DR_uzgqvnzVHqHO_k",
        "label": "Dumbo",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_mRKkcj-jZYsoxx6zexSQUI0UZSbKFvmpE",
        "label": "Triff die Robinsons",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_kQ3XTPCT37ZXx2lumLYJ6DKbFwChnkXYs",
        "label": "Bolt - Ein Hund für alle Fälle",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_lkxg2x89y5vfi44HpB_fRY77dHQ8Di7gc",
        "label": "Winnie Puuh - Lustige Jahreszeiten im Hundertmorgenwald",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_nxACHw7AuDsAjktLAmdJrbI1Ortwse45w",
        "label": "Mickys total verrücktes Fußballspiel",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_mjxN270TdL5rlzL-7Opa2YRiBetDBTwAs",
        "label": "Tim Burton's Nightmare Before Christmas",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_nWV9JLxDYVffi_Y3z6dWybb7awjLeRvkw",
        "label": "Maleficent: Mächte der Finsternis",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_ks8WMkyqJOBbpzjTbAiouujODFK5GO_zA",
        "label": "Tiggers großes Abenteuer mit Winnie Puuh und seinen Freunden",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_kRMBgAEPpzLpCzNhW1ErpslqDegTTTDTA",
        "label": "Himmel und Huhn",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_kundgUTfQdcOpKXKaj6VVik5VxrVXv8qw",
        "label": "Die Kühe sind los",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_kK8J9XSQLPWmc5hItx9qU9ybeMTvuoPlM",
        "label": "Merida - Legende der Highlands",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_mTpfKq3DfbaaGH8hZxbR-5_wtmwggfjF8",
        "label": "Heffalump - Ein neuer Freund für Winnie Puuh",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_k1jgDzLL5A_fwHbvbDv3ZoghjzX7_eJW8",
        "label": "Arielle, die Meerjungfrau - Wie alles begann",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_kloVPhJNdAVWUVn_1CCAeEouwp4UjICTw",
        "label": "Elliot, der Drache",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_leU1mji7v0fy9yN2_zCsV9AmCJdGd5vWs",
        "label": "Dornröschen",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_kV11E1FyEC12rrZSiP1wtUxU3TT5c-MOw",
        "label": "Toy Story 3",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_ngoV8tTYHGlQlh8x0YOYlFd-O8YaIlJG0",
        "label": "Baymax - Riesiges Robowabohu",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_m_hm-SUaGplqMI8ht6iZeN7Js5r_cB-rk",
        "label": "Alles steht Kopf 2",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_mDRgeNmjkLEFg78lW_cGP8klR11L6d-0Y",
        "label": "Tarzan 2",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_m9K0ZDoAwreKv2zfLLzNsAbEvNcN_TOSI",
        "label": "Tinker Bell und die Piratenfee",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_ncTsRBl3ihS8xc2fXuo2lPv04dO1f6KC0",
        "label": "Hoppers",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_mIc-VWkQW1EornvdVdv8CIFfq5OOnloAE",
        "label": "Cinderella",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_n7GLXBULfc3ScSzTSQeallIozR5ba4a6M",
        "label": "Die Eiskönigin - Völlig Unverfroren",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_k1hbEIDe47tFGg80KxSPrzJUB-Yt1lyyc",
        "label": "Cinderella 2 - Träume werden wahr",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_n2-ZUhnXeGYmaywf4AcpFudjR10JsbrQo",
        "label": "Elio",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_nUcVxlUReyhD771ST9B_53UHaPgNNGRpk",
        "label": "Arielle, die Meerjungfrau",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_mNqk3ri39BDq8HqCdr6vftp0EJ04JRp7g",
        "label": "Der Glöckner von Notre Dame",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_kKXhJ6GTzojNC72P50parWidxdJ1-EbRI",
        "label": "Arielle, die Meerjungfrau 2 - Sehnsucht nach dem Meer",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_lqHhBfvgUONgvYU_GOw0L_LIsPd5IXNxU",
        "label": "Cars 3 - Evolution",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_lEAY5We7uhhjeCuw89LgsAc9i0qTk8NLc",
        "label": "Cinderella",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_nsb0OsuUyDuhKW52EFCLTMv0-vMJ0zBzY",
        "label": "Robin Hood",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_kIOCOVKQ1hymSZYSZitxAnc1LBtGQYobI",
        "label": "Winnie Puuh - Der Film",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_mBZHU-r4X89vIltngewixsIqZhtpZO-zo",
        "label": "Winnie Puuh auf Großer Reise",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_mzo5-o7iRgmG9YJVZFY4n8VhDmYl4oAjQ",
        "label": "Die Monster Uni",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_k1NtuVYsO5k0pEW4qvx9DYL7ZiJHJ95S0",
        "label": "Hotel Transsilvanien",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_lGV65AB3Czwmze7vTqqSZsykA6kOGAMsU",
        "label": "Ferkels Grosses Abenteuer",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_mciDVsg3oLjYKBHtNlF2rSUpzlLjep84o",
        "label": "Pinocchio",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_nTgjFjpGwgBQV2WCq7Ekshyy0hngwi_lg",
        "label": "Planes",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_nlEen2psNk1p9LJdZYO5gm2YKUR4aXjGA",
        "label": "Bernard & Bianca - Die Mäusepolizei",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_ms8Lnv1d7nIyy2coHVKSSddjP5sdTp9Pg",
        "label": "Alice im Wunderland",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_kccPvfF199D-xEUPPp_9ge7FqbtuapX4c",
        "label": "Bambi 2 - Der Herr der Wälder",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_ntT0Ve6F3NTuC3KRTgr1O_f44fnPpKBfQ",
        "label": "Die Schöne und das Biest",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_mRA_lATsy2YhZrrOCkTYMVQ9mBtJSwQYU",
        "label": "Sing",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_kwrZs3W4PNH-aJRUvkOoafbOS_J9zJ7Oo",
        "label": "Aladdin",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_nc0WkNNelHnxEg2CWgqoOZxxRxguq6V78",
        "label": "Die Eiskönigin 2",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_kg0qHwby8-YPdDmP6iH5zfEOj8wsfZOb4",
        "label": "Die Schöne und das Biest",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_lsM_ClEpmS1qqkXy95F_RTdbkZIyvoQ5I",
        "label": "Arielle, die Meerjungfrau",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_mDiC8M2jC1ME7qdPJIg4exPLO4EseVCQc",
        "label": "Raya und der letzte Drache",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_kAi57TwgXP3WVsHzZA1jz8A_NWGWPP3vM",
        "label": "Lilo & Stitch",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_lEqQksSC8weTFhGAnsA35Z63nTbnOuz5A",
        "label": "Lilo & Stitch",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_nzOzTv6DtDwjF-fnRt5K_xSR1u4d1KWcI",
        "label": "Aladdin",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_lvpbmPh_EH97rOu6rYGC-4mGVtaisBILM",
        "label": "Bärenbrüder 2",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_n-nP-qclR2U3yjcdZ-pvwwoecfo9OGw5A",
        "label": "Ralph reichts",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_l2vxY1WGKjDMX16cSsSDCbHmEvLnClm2M",
        "label": "Schneewittchen und die sieben Zwerge",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_lvH5U1ug8PcYe-QvcLqbTdtx3N30W6M8c",
        "label": "Bambi",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_mBHMZ1XX4yUic_FiPIypUCbKt-H5bWJxI",
        "label": "Hercules",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_nymLr2m79sxm1PiRL15od7M6KP7-v8RjM",
        "label": "Tinker Bell",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_lNX0rUnIGzy7-JFvKbs0oSxpAzRCPRed8",
        "label": "Wish",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_muL8Aszjs2LS1rVQKJiwIJJX7DD1wBMHo",
        "label": "Tinker Bell - Die Suche nach dem verlorenen Schatz",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_nyEgHwTQFtmweDI4mDC-ID0nCH_Tz33PM",
        "label": "Chaos im Netz",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_lUDeeTyS6wmAkZhng8HTRfU6UGoCyyeos",
        "label": "Aristocats",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_k_xP81n2cp-CAuB8a65pUed-5h4Ixmp44",
        "label": "Rapunzel - Neu Verföhnt",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_kUG2V3s93Gvc4JFFHZpdGhEK5FkNvdJs0",
        "label": "Der Schatzplanet",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_mDRgeNmjkLEFg78lW_cGP8klR11L6d-0Y",
        "label": "Tarzan 2",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_laDw1u6K1Y8EKAIzNmwF-43MveI_b8CmY",
        "label": "Tarzan",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_mYT2vME3GNSy2akeG5jc9rA74RR-OduYk",
        "label": "Atlantis - Das Geheimnis der verlorenen Stadt",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_k7tY3kG6h6qrg48K4bXmLO0QwGQ84hees",
        "label": "Susi und Strolch",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_kw0MiYKPgMzBzH1tAu11nE6Lc4rxh2Wsk",
        "label": "Oben",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_mIHDTjeetGqr7X1LLJrNQdhLAiHO6bVbA",
        "label": "Ratatouille",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_mCUNR-Av0GzcrZ9vfuaOIIMlNVBg-95Q8",
        "label": "Encanto",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_nuI_CulUwubWa7-lWQql_yH_HG0D7iXPc",
        "label": "Elemental",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_lCgHBJzv-CF-T6PoTuphles7HQtVvqFbk",
        "label": "Toy Story",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_lQOL4rgUSsbYG3I9Z1MLN9BdaFXQHFPAE",
        "label": "Pocahontas",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_kNTbcVMS1WuJM23pQQcX4xADhDgfgdE30",
        "label": "Alles steht Kopf",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_kB4Blrc0yyraIEdfY1FlprO6w_yOzrhks",
        "label": "Mulan",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_kbbd0cygGfWMW8OM_IxE4YJ6lD1Hnlfgo",
        "label": "Zoomania 2",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_m8WNpYCFjKdk-ddt7gKQNLmY---s83epc",
        "label": "Zoomania",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_m5np3cQD6JI4qqyaKPFkyYJacjmepggw0",
        "label": "Pettersson und Findus",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_lAEv53WjTcYdbezfmqvoRbp0rxbCTTWSk",
        "label": "Kung Fu Panda",
        "language": "de",
        "active": True,
    },

    {
        "type": "album",
        "youtube_id": "OLAK5uy_nT1mL8aZvxqfIRFN9L8FgIzfvk6HUkd0I",
        "label": "Madagascar",
        "language": "de",
        "active": True,
    },

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
        "label": "Der König der Löwen",
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
        "label": "Peter Pan & Wendy",
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
