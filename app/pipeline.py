from typing import List, Dict, Any
from app import fetch
from app import filters
from app import db
from app.summarizer import summarize_article

def _has_hash(content_hash: str) -> bool:
    """Check if we already stored an item with this content hash."""
    conn = db.connect()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM summaries WHERE content_hash=?", (content_hash,))
    row = cur.fetchone()
    conn.close()
    return bool(row)

def run_once(
    feeds: List[str],
    includes: List[str] | None = None,
    excludes: List[str] | None = None,
    per_feed: int = 5,
    dry_run: bool = False,
) -> Dict[str, int]:
    """
    Process all feeds once.
    Returns counters: seen, summarized, cached, skipped, errors.
    """
    includes = includes or []
    excludes = excludes or []
    db.init_db()

    seen = summarized = cached = skipped = errors = 0

    for feed_url in feeds:
        entries = fetch.get_feed_entries(feed_url, limit=per_feed)
        for e in entries:
            url = e["url"]
            title = e["title"]
            published_at = e["published_at"]

            if not url:
                continue

            # URL-level cache
            if db.has_url(url):
                cached += 1
                continue

            # Fetch and extract text
            text = fetch.extract_main_text(url)
            combined = f"{title}\n{text}"

            # Keyword filter
            if filters.match_keywords(combined, includes, excludes) is False:
                skipped += 1
                continue

            # Hash-level cache
            content_hash = filters.sha1((text or "")[:2000] or url)
            if _has_hash(content_hash):
                cached += 1
                continue

            try:
                if dry_run:
                    summarized += 1
                else:
                    data = summarize_article(url, title, text)
                    db.insert_summary(data, content_hash, published_at)
                    summarized += 1
            except Exception:
                errors += 1

            seen += 1
            fetch.polite_delay(0.3)

    return {
        "seen": seen,
        "summarized": summarized,
        "cached": cached,
        "skipped": skipped,
        "errors": errors,
    }
