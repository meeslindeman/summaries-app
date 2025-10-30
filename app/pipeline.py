from typing import List, Dict, Any
from datetime import datetime, timezone
from app import fetch, filters, db
from app.summarizer import summarize_article

from urllib.parse import urlsplit
from email.utils import parsedate_to_datetime

def _has_hash(content_hash: str) -> bool:
    """Check if we already stored an item with this content hash."""
    conn = db.connect()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM summaries WHERE content_hash=?", (content_hash,))
    row = cur.fetchone()
    conn.close()
    return bool(row)

def _normalize_published(s: str | None) -> str:
    if not s:
        return ""
    # try RFC822 via email.utils
    try:
        dt = parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        pass
    # try plain ISO
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return ""
    
def _format_date_eu(iso_ts: str | None) -> str:
    if not iso_ts:
        return ""
    try:
        dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        return dt.strftime("%d-%m-%Y")  # EU day-month-year
    except Exception:
        return ""

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
    started_at = datetime.now(timezone.utc).isoformat()

    seen = summarized = cached = skipped = errors = 0

    for feed_url in feeds:
        entries = fetch.get_feed_entries(feed_url, limit=per_feed)
        for e in entries:
            url = e["url"]
            title = e["title"]
            published_at = e["published_at"]
            domain = urlsplit(url).netloc or ""
            norm_pub = _normalize_published(published_at)
            source = (e.get("feed_title") or domain)

            if not url:
                continue

            # URL-level cache
            if db.has_url(url):
                cached += 1
                continue

            # Fetch and extract text
            text = fetch.extract_main_text(url)
            image_url = e.get("image_url") or fetch.get_best_image(url, e)
            if not image_url:
                image_url = "/static/no-image.jpg"
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
                    data["image_url"] = image_url
                    data["domain"] = domain
                    data["source"] = source
                    if norm_pub:
                        data["published_at"] = norm_pub
                        data["published_date"] = _format_date_eu(norm_pub)
                    else:
                        # fall back to created_at date later when reading if you want
                        data["published_date"] = ""
                    db.insert_summary(data, content_hash, norm_pub or published_at)
                    summarized += 1
            except Exception:
                errors += 1

            seen += 1
            fetch.polite_delay(0.3)
        
    result = {
        "seen": seen,
        "summarized": summarized,
        "cached": cached,
        "skipped": skipped,
        "errors": errors,
    }
    finished_at = datetime.now(timezone.utc).isoformat()
    db.record_run(result, started_at, finished_at)   
    return result
