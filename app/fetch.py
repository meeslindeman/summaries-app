import time
import requests
import feedparser
import trafilatura
from app.config import settings

HEADERS = {"User-Agent": settings.user_agent}

def get_feed_entries(feed_url: str, limit: int = 10):
    """Return a list of (url, title, published_at) from an RSS/Atom feed."""
    parsed = feedparser.parse(feed_url)
    out = []
    for e in parsed.entries[:limit]:
        out.append({
            "url": e.get("link") or "",
            "title": e.get("title") or "(no title)",
            "published_at": e.get("published") or e.get("updated") or ""
        })
    return out

def fetch_html(url: str) -> str:
    """Download raw HTML with requests (timeout + headers)."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=settings.request_timeout_s)
        if r.status_code != 200:
            return ""
        return r.text
    except Exception:
        return ""

def extract_main_text(url: str) -> str:
    """Use trafilatura to extract readable text."""
    html = trafilatura.fetch_url(url, no_ssl=True)
    if not html:
        # fallback to requests if direct fetch fails
        html = fetch_html(url)
    if not html:
        return ""
    text = trafilatura.extract(
        html,
        include_comments=False,
        include_images=False,
        include_tables=False,
        favor_precision=True,
    )
    return text or ""

def polite_delay(seconds: float = 0.3):
    """Small pause to avoid hammering sites."""
    time.sleep(seconds)
