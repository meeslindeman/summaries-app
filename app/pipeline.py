from typing import List, Dict, Any
from datetime import datetime, timezone
from urllib.parse import urlsplit
from email.utils import parsedate_to_datetime

from app import fetch, filters, db
from app.summarizer import summarize_article
from app.util import load_lines

PLACEHOLDER_IMAGE = "/static/no-image.jpg"

def _has_hash(content_hash: str) -> bool:
    """Return True if this content hash already exists in the DB."""
    conn = db.connect()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM summaries WHERE content_hash=?", (content_hash,))
    found = cur.fetchone()
    conn.close()
    return bool(found)

def _normalize_published(s: str | None) -> str:
    if not s:
        return ""
    try:
        dt = parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        pass
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
        return dt.strftime("%d-%m-%Y")
    except Exception:
        return ""

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def run_once(
    feeds: List[str],
    includes: List[str] | None = None,   # kept for compatibility; can be removed later
    excludes: List[str] | None = None,
    per_feed: int = 5,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Process all feeds once.
    Returns counters and URL details: seen, summarized, cached, skipped, errors, details.
    """
    db.init_db()
    started_at = _now_iso()

    # (re)load filter rules every run so edits take effect without restart
    inc_lines = load_lines("data/include.txt")
    exc_lines = load_lines("data/exclude.txt")
    rules = filters.compile_rules(inc_lines, exc_lines)

    seen = summarized = cached = skipped = errors = 0
    details = {"summarized": [], "cached": [], "skipped": [], "errors": []}

    for feed_url in feeds:
        entries = fetch.get_feed_entries(feed_url, limit=per_feed)
        for e in entries:
            url = e.get("url") or ""
            title = e.get("title") or ""
            published_at = e.get("published_at") or ""
            if not url:
                continue

            seen += 1  # count every entry we examine

            domain = urlsplit(url).netloc or ""
            norm_pub = _normalize_published(published_at)
            source = (e.get("feed_title") or domain)

            # URL-level cache
            if db.has_url(url):
                cached += 1
                details["cached"].append(url)
                continue

            # Fetch & extract main text (robots + rate limiting handled in fetch)
            text = fetch.extract_main_text(url) or ""

            # Keyword / site rules (title + body)
            if not filters.should_keep(url, title, text, rules):
                skipped += 1
                details["skipped"].append(url)
                continue

            # Choose image (feed hint, best guess, placeholder)
            image_url = e.get("image_url") or fetch.get_best_image(url, e) or PLACEHOLDER_IMAGE

            # Hash-level cache (avoid dup content across different URLs)
            content_hash = filters.sha1((text or "")[:2000] or url)
            if _has_hash(content_hash):
                cached += 1
                details["cached"].append(url)
                continue

            try:
                if dry_run:
                    summarized += 1
                    details["summarized"].append(url)
                else:
                    data = summarize_article(url, title, text)
                    data["image_url"] = image_url
                    data["domain"] = domain
                    data["source"] = source

                    if norm_pub:
                        data["published_at"] = norm_pub
                        data["published_date"] = _format_date_eu(norm_pub)
                        created_ts = norm_pub
                    else:
                        # fallback to "now" for both created_at and display date
                        today_iso = _now_iso()
                        data["published_date"] = _format_date_eu(today_iso)
                        created_ts = published_at or today_iso

                    db.insert_summary(data, content_hash, created_ts)
                    summarized += 1
                    details["summarized"].append(url)

            except Exception as ex:
                errors += 1
                details["errors"].append(url)
                # optional: print or log
                # print(f"Summarize error for {url}: {type(ex).__name__} {ex}")

            # be polite between entries
            fetch.polite_delay(0.3)

    result = {
        "seen": seen,
        "summarized": summarized,
        "cached": cached,
        "skipped": skipped,
        "errors": errors,
        "details": details,
    }
    finished_at = _now_iso()
    db.record_run(result, started_at, finished_at)
    return result