"""
One-off helper: scaffold commented-out ITEM_OVERRIDES stub entries in
overrides.py for every 'album' source in sources.py that doesn't have one
yet.

Only 'album' sources are stubbed, since for those the source's own
youtube_id IS the catalog item's id - build_album_entry() (see refresh.py)
collapses the whole album down to one item keyed by the playlist id.
'channel'/'playlist' sources produce one item per video, and their video
ids aren't known ahead of time without a real sync, so they're skipped
here - add those overrides by hand using the ids already synced into
storytimefinder.db/catalog.json.

This never touches sources.py, SQLite, or any API - it only reads SOURCES
and rewrites overrides.py, inserting commented stub blocks right after the
`ITEM_OVERRIDES = {` line without disturbing anything already there.
Re-running it is safe: a source already has a real entry or a stub (its
youtube_id string appears anywhere in the file) is left untouched.

Usage:
    python refresh/generate_overrides_stubs.py            # write stubs into overrides.py
    python refresh/generate_overrides_stubs.py --dry-run  # preview only, don't write
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import SOURCES  # noqa: E402

OVERRIDES_PATH = Path(__file__).resolve().parent / "overrides.py"
DICT_ANCHOR_RE = re.compile(r"(ITEM_OVERRIDES: dict\[str, dict\] = \{)")

# Full override schema - see overrides.py's own docstring for what each field
# does and whether it falls back to an API value when left unset.
OVERRIDE_FIELDS = (
    "description",
    "series",
    "position_in_series",
    "series_type",
    "genre",
    "franchise",
    "min_age",
    "source_release_year",
    "mood",
    "seasonal",
    "awards",
)


def build_stub(youtube_id: str, label: str) -> str:
    lines = [f'    # "{youtube_id}": {{  # {label}']
    lines += [f'    #     "{field}": None,' for field in OVERRIDE_FIELDS]
    lines.append("    # },")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the stub entries that would be added without writing overrides.py.",
    )
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # readable umlauts on Windows consoles

    content = OVERRIDES_PATH.read_text(encoding="utf-8")
    anchor_match = DICT_ANCHOR_RE.search(content)
    if not anchor_match:
        print(
            "Could not find 'ITEM_OVERRIDES: dict[str, dict] = {' in overrides.py - aborting.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Only scan the dict's own body for existing/stubbed ids - not the whole
    # file, since the module docstring's illustrative example above the dict
    # may itself contain a real youtube_id and would otherwise false-positive.
    body = content[anchor_match.end():]

    album_sources = [src for src in SOURCES if src.get("type") == "album"]
    non_album_count = len(SOURCES) - len(album_sources)
    to_add = [src for src in album_sources if src["youtube_id"] not in body]

    if not to_add:
        print("Nothing to add - every album source already has an entry (or a stub) in overrides.py.")
        if non_album_count:
            print(f"({non_album_count} non-'album' source(s) skipped - see the module docstring.)")
        return

    block = "\n".join(build_stub(src["youtube_id"], src["label"]) for src in to_add) + "\n"
    new_content = content[: anchor_match.end()] + "\n" + block + body

    verb = "Would add" if args.dry_run else "Adding"
    plural = "y" if len(to_add) == 1 else "ies"
    print(f"{verb} {len(to_add)} stub entr{plural} to overrides.py:")
    for src in to_add:
        print(f"  + {src['label']} ({src['youtube_id']})")

    skipped = len(album_sources) - len(to_add)
    if skipped:
        print(f"Skipped {skipped} already present in overrides.py.")
    if non_album_count:
        print(f"Skipped {non_album_count} non-'album' source(s) - see the module docstring.")

    if args.dry_run:
        return

    OVERRIDES_PATH.write_text(new_content, encoding="utf-8")
    print(f"\nWrote {OVERRIDES_PATH}")


if __name__ == "__main__":
    main()
