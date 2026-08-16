# StorytimeFinder

A free, ad-free, no-account discovery site for curated children's audiobooks
(Hörspiele/Hörbücher) that live on YouTube Music. StorytimeFinder does not
host or stream any audio - it's a search/browse front door that links out to
`music.youtube.com`. The UI is available in German and English.

## How it works

Two separate paths, because the web app runs on Vercel's free tier
(ephemeral, largely read-only filesystem - no reliable SQLite writes there):

- **`refresh/`** - a standalone script, run on a schedule outside of Vercel
  (see the included GitHub Action). It calls the YouTube Data API, curates
  the results against a local SQLite database, and exports the current
  catalog to `data/catalog.json`, which **is** committed to the repo.
- **`app/`** - a read-only Flask app that loads `data/catalog.json` into
  memory and serves search/browse pages. It never touches SQLite or the
  YouTube API at request time, so there's nothing for Vercel's ephemeral
  filesystem to break.

Each listing shows title, thumbnail, and every other metadata field
(category, age group, genre, series/episode, publisher, language, duration,
release year) as a compact chip, plus a short description, always with a
visible YouTube attribution and a link out to play it on YouTube Music. The
whole homepage - live title search as you type, age/series/language
filters, and an "Erweiterte Filter" panel with duration/genre/publisher/
release-decade chips - filters entirely client-side with no page reloads.
A language selector switches the site's own UI text between German and
English (defaulting to the browser's language), independent of the
audiobook-language filter chip. A dark mode toggle is also available, top
right, and remembers your preference.

## Project structure

```
storytimefinder/
├── app/                  # Flask app (read-only, deployed to Vercel)
│   ├── __init__.py       # App factory
│   ├── routes.py         # /, /category/<slug>, /impressum
│   ├── data.py           # Loads catalog.json, search/filter logic
│   ├── i18n.py            # UI translations (de/en) + language resolution
│   ├── templates/
│   └── static/
├── api/
│   └── index.py          # Vercel WSGI entrypoint
├── refresh/
│   ├── refresh.py        # YouTube API -> SQLite -> catalog.json
│   ├── sources.py        # Curated source list (channels/playlists)
│   ├── overrides.py      # Manual per-item metadata (series, genre, ...)
│   └── requirements.txt
├── data/
│   ├── storytimefinder.db  # gitignored, local/refresh-env only
│   └── catalog.json        # committed, what the Flask app reads
├── tests/
│   └── test_data.py
├── .github/workflows/refresh.yml
├── vercel.json
├── requirements.txt        # Flask app deps only
└── requirements-dev.txt    # + pytest
```

## Explicitly out of scope for v1

- User accounts, favorites, personalization
- Streaming/embedding audio directly (link-out only)
- Custom ranking/popularity scoring
