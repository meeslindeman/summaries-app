import argparse
import os
from typing import List
from app.pipeline import run_once

from app.logging import setup
log = setup()

DEF_FEEDS = "data/feeds.txt"
DEF_INCLUDE = "data/include.txt"
DEF_EXCLUDE = "data/exclude.txt"

def load_lines(path: str) -> List[str]:
    if not path or not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [ln.strip() for ln in f if ln.strip() and not ln.strip().startswith("#")]

def main():
    log.info("Starting ingest")

    ap = argparse.ArgumentParser(description="Ingest feeds, summarize, and cache results.")
    ap.add_argument("--feeds", default=DEF_FEEDS, help="Path to feeds list")
    ap.add_argument("--include", default=DEF_INCLUDE, help="Path to include keywords list")
    ap.add_argument("--exclude", default=DEF_EXCLUDE, help="Path to exclude keywords list")
    ap.add_argument("--per-feed", type=int, default=5, help="Max items per feed")
    ap.add_argument("--dry-run", action="store_true", help="Do everything except call the LLM and write")
    args = ap.parse_args()

    feeds = load_lines(args.feeds)
    inc = load_lines(args.include)
    exc = load_lines(args.exclude)
    if not feeds:
        raise SystemExit(f"No feeds found at {args.feeds}. Add URLs, one per line.")

    stats = run_once(
        feeds=feeds,
        includes=inc,
        excludes=exc,
        per_feed=args.per_feed,
        dry_run=args.dry_run,
    )

    log.info("Done %s", stats)

if __name__ == "__main__":
    main()
