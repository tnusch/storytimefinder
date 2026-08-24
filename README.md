# StorytimeFinder

A free, ad-free, no-account discovery site for curated children's audiobooks that live on YouTube Music. StorytimeFinder does not
host or stream any audio - it's a search/browse front door that links out to
`music.youtube.com`. The UI is available in German and English.

## Features

- **Find something age-appropriate fast** - filter by age group, series,
  language, genre, franchise, duration, or decade, or just search by title
  as you type. Results update instantly, no page reloads.
- **Know what you're pressing play on** - every title shows a short
  description, age recommendation, series/episode number, and runtime at a
  glance, so you don't have to click through to YouTube just to check if
  something's suitable.
- **One audiobook, one listing** - even when a story is split across dozens
  of YouTube chapters, it shows up as a single entry with its full runtime,
  not a wall of near-identical chapter titles to sift through.
- **German and English**, matching your browser's language by default.
- **Comfortable browsing, day or night**, with a light/dark toggle.
- **Always free, always just a link out** - no accounts, no tracking, no
  ads, no monetization. Every title links straight to YouTube Music to
  actually listen; nothing is hosted or streamed here.

## Project structure

```
storytimefinder/
├── app/                  # Flask app (read-only, deployed to Vercel)
│   ├── __init__.py       # App factory
│   ├── routes.py         # /, /impressum
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

## Stack

| Component               | Technology                                    |
| ------------------------ | ---------------------------------------------- |
| Language                | Python                                        |
| Web app                 | Flask + Jinja2 templates                      |
| Frontend                | Vanilla JS/CSS - no framework, no build step  |
| Catalog metadata source | YouTube Data API v3                           |
| Description generation  | Anthropic Claude API (Haiku 4.5)              |
| Catalog storage         | SQLite (write side), committed JSON (read side) |
| Hosting                 | Vercel (Python/WSGI runtime)                  |
| Scheduled refresh       | GitHub Actions                                |
| Tests                   | pytest                                        |

### Write/read split (CQRS-lite)

StorytimeFinder deliberately splits into a write path and a read path -
"lite" CQRS in that there's no event bus wiring them together, just a
build step - because the web app runs on Vercel's free tier (ephemeral,
largely read-only filesystem - no reliable SQLite writes there):

- **`refresh/`** (command side) - a standalone script, run on a schedule
  outside of Vercel (see the included GitHub Action). It calls the YouTube
  Data API to pull catalog metadata, calls Claude to generate each new
  item's description, curates the results against a local SQLite database
  (the write model), and exports/denormalizes the current catalog into
  `data/catalog.json` - a read model shaped for exactly how the app queries
  it - which **is** committed to the repo.
- **`app/`** (query side) - a read-only Flask app that loads
  `data/catalog.json` into memory and serves search/browse pages. All
  search/filtering runs client-side in the browser. The app never touches
  SQLite or any external API at request time, so there's nothing for
  Vercel's ephemeral filesystem to break - the trade-off is that the site
  is only ever as fresh as the last scheduled refresh, not real-time.

## Contributing

Bug fixes and small, focused improvements are welcome via pull request -
please open an issue first for anything larger so we can agree on the
approach before you put the work in. Before opening a PR:

```bash
pip install -r requirements-dev.txt
pytest
```

Keep changes scoped to the fix/feature at hand, and match the existing code
style (see `CLAUDE.md` for the architectural constraints this project is
built around, if you're using an AI coding assistant).

## Get in touch

Found a bug or have a feature request? [Open an issue on
GitHub](https://github.com/tnusch/storytimefinder/issues).

Know a children's audiobook on YouTube Music that's missing from the
catalog? Use the "Suggest an audiobook" link in the site footer (or [open a
suggestion directly](https://github.com/tnusch/storytimefinder/issues/new?template=audiobook-suggestion.yml))
- suggestions are reviewed and curated by hand, so it can take a little
while to show up.

## License

[MIT](LICENSE)
