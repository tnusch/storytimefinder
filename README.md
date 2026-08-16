# StorytimeFinder

A free, ad-free, no-account discovery site for curated children's audiobooks
(Hörspiele/Hörbücher) that live on YouTube Music. StorytimeFinder does not
host or stream any audio - it's a search/browse front door that links out to
`music.youtube.com`.

## How it's built

Two separate paths, because the web app runs on Vercel's free tier
(ephemeral, largely read-only filesystem - no reliable SQLite writes there):

- **`refresh/`** - a standalone script you run yourself (locally, via cron,
  or via the included GitHub Action). It calls the YouTube Data API, upserts
  into a local SQLite file (`data/storytimefinder.db`, gitignored), and
  exports the current catalog to `data/catalog.json`, which **is** committed.
- **`app/`** - a read-only Flask app that loads `data/catalog.json` into
  memory and serves search/browse pages. It never touches SQLite or the
  YouTube API at request time.

## Local setup

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements-dev.txt
flask --app app run --debug
```

Visit http://127.0.0.1:5000. It'll serve whatever is currently in
`data/catalog.json` - the repo ships with a handful of **sample/placeholder
items** (titles prefixed `[Beispiel]`, fake video IDs) so the UI is visibly
exercisable before you've run a real refresh. Replace them by running the
refresh job (below) with real sources.

Run tests:

```bash
pytest
```

## Running the refresh job

1. Get a YouTube Data API v3 key: https://console.cloud.google.com/apis/credentials
   (enable "YouTube Data API v3" on the project first).
2. Copy `.env.example` to `.env` and fill in `YOUTUBE_API_KEY`.
3. **Edit `refresh/sources.py`** - the shipped entries are placeholders with
   fake IDs and `active: False`. Replace `youtube_id` with real channel IDs
   (`UC...`) or playlist IDs (`PL...`/`OLAK5uy_...`), set `active: True`, and
   fill in real category/age/language tags. This file is the curated seed
   list - nothing in the app auto-discovers content.
4. Install refresh deps and run:

   ```bash
   pip install -r refresh/requirements.txt
   python refresh/refresh.py
   ```

This upserts `data/storytimefinder.db` and rewrites `data/catalog.json`.
Commit the updated `catalog.json` (not the `.db` file - it's gitignored) so
the next deploy picks it up.

### YouTube API compliance

The refresh job is designed around YouTube API Developer Policies:

- Only `snippet` (title, thumbnail) and `contentDetails` (duration) are
  fetched and stored - no view/like/subscriber counts, so there's nothing
  that needs re-verification within 30 days.
- No derived popularity/ranking score is ever computed.
- Every run fully re-syncs each active source and deletes items no longer
  returned (deleted/private videos), so `catalog.json` always reflects
  current state.
- Run it at least every 30 days - the included GitHub Action runs weekly.

## Scheduled refresh (GitHub Actions)

`.github/workflows/refresh.yml` runs the refresh job every Monday and
commits the updated `catalog.json` back to the repo. Set these repo secrets:

- `YOUTUBE_API_KEY` - required.
- `VERCEL_DEPLOY_HOOK_URL` - optional; if set, the workflow POSTs to it after
  committing so Vercel redeploys immediately instead of waiting for its own
  polling/webhook.

The workflow needs `contents: write` (already set) so it can push the commit -
that's the default `GITHUB_TOKEN` permission model, no extra PAT needed.

## Deploying to Vercel

1. Push this repo to GitHub.
2. Import it in Vercel. `vercel.json` routes all requests to
   `api/index.py`, which imports the Flask `app` object - Vercel's Python
   runtime auto-detects the WSGI callable.
3. No environment variables are needed for the web app itself - it only
   reads the committed `data/catalog.json`.
4. Every push to the deployed branch (including the weekly refresh commit)
   triggers a redeploy, so the live site picks up new data automatically.

## Before going live

- **`app/templates/impressum.html`** has placeholder name/address/contact
  fields (marked with a `TODO` comment). A German Impressum legally requires
  real information - fill these in before making the site public.
- **`refresh/sources.py`** ships with placeholder, inactive sources - the
  real curated source list needs to be added.
- The YouTube attribution badge in the footer/cards is a simplified
  text+color mark, not the official brand asset from YouTube's brand
  resources page - swap in the official logo if you want to be fully
  strict about branding guidelines.

## Project structure

```
storytimefinder/
├── app/                  # Flask app (read-only, deployed to Vercel)
│   ├── __init__.py       # App factory
│   ├── routes.py         # /, /search, /category/<slug>, /impressum
│   ├── data.py           # Loads catalog.json, search/filter logic
│   ├── templates/
│   └── static/
├── api/
│   └── index.py          # Vercel WSGI entrypoint
├── refresh/
│   ├── refresh.py        # YouTube API -> SQLite -> catalog.json
│   ├── sources.py         # Curated seed list (edit this)
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
- Non-German content (the `language` field supports it later; no UI for it yet)
- Custom ranking/popularity scoring
