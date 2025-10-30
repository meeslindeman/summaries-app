import time
import socket
import requests
import feedparser
import trafilatura
import urllib.parse as urlparse
import urllib.robotparser as robotparser
from collections import defaultdict
from app.config import settings
from app.logging import setup
from bs4 import BeautifulSoup
import urllib.parse as urlparse

log = setup()

HEADERS = {"User-Agent": settings.user_agent}
TIMEOUT = settings.request_timeout_s
# minimal in-memory rate limit: one hit per domain every 0.5s
_LAST_HIT = defaultdict(float)
_MIN_GAP = 0.5
# robots cache per origin
_ROBOTS = {}

def _origin(url: str) -> str:
    u = urlparse.urlsplit(url)
    return f"{u.scheme}://{u.netloc}"

def _respect_rate_limit(url: str):
    dom = urlparse.urlsplit(url).netloc
    now = time.time()
    gap = now - _LAST_HIT[dom]
    if gap < _MIN_GAP:
        time.sleep(_MIN_GAP - gap)
    _LAST_HIT[dom] = time.time()

def _robots_allowed(url: str) -> bool:
    origin = _origin(url)
    rp = _ROBOTS.get(origin)
    if rp is None:
        rp = robotparser.RobotFileParser()
        robots_url = urlparse.urljoin(origin, "/robots.txt")
        try:
            rp.set_url(robots_url)
            rp.read()
        except Exception:
            # if robots fetch fails, be conservative but allow
            pass
        _ROBOTS[origin] = rp
    try:
        return rp.can_fetch(settings.user_agent, url)
    except Exception:
        return True  # if parser incomplete, default allow
       
def _request(url: str, max_retries: int = 3) -> str:
    backoff = 0.5
    for attempt in range(1, max_retries + 1):
        try:
            _respect_rate_limit(url)
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            if 200 <= r.status_code < 300:
                return r.text
            # 4xx except 429: do not retry
            if 400 <= r.status_code < 500 and r.status_code != 429:
                log.warning("HTTP %s for %s (no retry)", r.status_code, url)
                return ""
            log.warning("HTTP %s for %s (retry %d)", r.status_code, url, attempt)
        except (requests.Timeout, requests.ConnectionError, socket.timeout) as e:
            log.warning("net error %s on %s (retry %d)", type(e).__name__, url, attempt)
        time.sleep(backoff)
        backoff *= 2
    return ""

def _absolutize(base: str, url: str) -> str:
    try:
        return urlparse.urljoin(base, url)
    except Exception:
        return url

def _image_from_feed_entry(e: dict, base_url: str) -> str:
    # media:content / media:thumbnail
    media = e.get("media_content") or []
    if isinstance(media, list) and media:
        u = media[0].get("url")
        if u: return _absolutize(base_url, u)
    thumb = e.get("media_thumbnail") or []
    if isinstance(thumb, list) and thumb:
        u = thumb[0].get("url")
        if u: return _absolutize(base_url, u)
    # <enclosure type="image/*">
    for link in e.get("links", []):
        if link.get("rel") == "enclosure" and str(link.get("type","")).startswith("image/"):
            u = link.get("href")
            if u: return _absolutize(base_url, u)
    # itunes:image or image href
    itunes = e.get("image") or e.get("itunes_image")
    if isinstance(itunes, dict):
        u = itunes.get("href") or itunes.get("url")
        if u: return _absolutize(base_url, u)
    return ""

def _image_from_html(html: str, page_url: str) -> str:
    try:
        soup = BeautifulSoup(html, "html.parser")
        # Prefer og:image then twitter:image then first <img>
        for prop in [
            ('meta', {'property': 'og:image'}, 'content'),
            ('meta', {'name': 'twitter:image'}, 'content'),
        ]:
            tag = soup.find(prop[0], prop[1])
            if tag and tag.get(prop[2]):
                return _absolutize(page_url, tag.get(prop[2]))
        img = soup.find("img")
        if img and img.get("src"):
            return _absolutize(page_url, img.get("src"))
    except Exception:
        pass
    return ""

def get_best_image(url: str, feed_entry: dict | None = None) -> str:
    """Try feed-provided image, else parse page HTML for og:image."""
    base = _origin(url)
    if feed_entry:
        u = _image_from_feed_entry(feed_entry, base)
        if u: return u
    html = fetch_html(url)
    if html:
        u = _image_from_html(html, url)
        if u: return u
    return ""

def get_site_name(url: str, default: str = "") -> str:
    try:
        # Try a quick HTML HEAD/GET for og:site_name
        resp = requests.get(url, timeout=4)
        if resp.ok:
            soup = BeautifulSoup(resp.text, "html.parser")
            meta = soup.find("meta", attrs={"property": "og:site_name"})
            if meta and meta.get("content"):
                return meta["content"].strip()
            # fall back to <title>
            title = soup.find("title")
            if title and title.text:
                # use only the first segment before a dash or bar
                base = title.text.strip().split("–")[0].split("|")[0]
                return base.strip()
    except Exception:
        pass
    # fallback to cleaned domain if all else fails
    from urllib.parse import urlsplit
    host = urlsplit(url).netloc
    host = host.replace("www.", "")
    return default or host.capitalize()

def get_feed_entries(feed_url: str, limit: int = 10):
    parsed = feedparser.parse(feed_url)
    feed_title = (getattr(parsed.feed, "title", None) or "").strip()
    site_name = feed_title or get_site_name(feed_url)
    out = []
    for e in parsed.entries[:limit]:
        url = e.get("link") or ""
        image_url = _image_from_feed_entry(e, base_url=feed_url) if url else ""
        out.append({
            "url": url,
            "title": e.get("title") or "(no title)",
            "published_at": e.get("published") or e.get("updated") or "",
            "image_url": image_url,
            "feed_title": site_name,   
        })
    return out

def fetch_html(url: str) -> str:
    if not _robots_allowed(url):
        log.info("blocked by robots.txt %s", url)
        return ""
    return _request(url)

def extract_main_text(url: str) -> str:
    if not _robots_allowed(url):
        log.info("blocked by robots.txt %s", url)
        return ""
    # try trafilatura direct fetch first
    try:
        _respect_rate_limit(url)
        html = trafilatura.fetch_url(url, no_ssl=True)
    except Exception:
        html = None
    if not html:
        html = fetch_html(url)
    if not html:
        return ""
    try:
        text = trafilatura.extract(
            html,
            include_comments=False,
            include_images=False,
            include_tables=False,
            favor_precision=True,
        )
        return text or ""
    except Exception:
        return ""

def polite_delay(seconds: float = 0.3):
    time.sleep(seconds)


