from fastapi import FastAPI, Query, Request, Body, Header, HTTPException
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import sqlite3, json
from pathlib import Path
from urllib.parse import urlsplit
from collections import defaultdict

from app.db import init_db, last_run
from app.config import settings
from app.ranker import pick_home_items
from app.util import load_lines
from app.pipeline import run_once
from app.settings import load_settings

import time
_last_refresh_ts = 0

app = FastAPI(title="Summarizer API")

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

def _prettify_domain(host: str) -> str:
    if not host:
        return ""
    host = host.lower().replace("www.", "")
    # basic prettifier: split on dots/hyphens, titlecase tokens
    parts = []
    for token in host.replace("-", " ").split("."):
        token = token.strip()
        if not token:
            continue
        # keep common acronyms uppercased
        if token in {"ai", "mit"}:
            parts.append(token.upper())
        else:
            parts.append(token.capitalize())
    # heuristics: "Technologyreview" -> "Technology Review"
    return " ".join(parts)

def build_source_map() -> dict[str, str]:
    """
    Returns {domain -> display_name}, preferring the most common non-domain 'source' seen.
    Falls back to a prettified domain.
    """
    init_db()
    conn = sqlite3.connect(settings.db_path); cur = conn.cursor()
    cur.execute("SELECT json_extract(summary_json,'$.source'), json_extract(summary_json,'$.domain') FROM summaries")
    rows = cur.fetchall()
    conn.close()

    by_domain_counts: dict[str, defaultdict[str, int]] = {}
    for src, dom in rows:
        dom = (dom or "").strip().lower()
        if not dom:
            continue
        label = (src or "").strip()
        if not label:
            label = _prettify_domain(dom)
        if dom not in by_domain_counts:
            by_domain_counts[dom] = defaultdict(int)
        by_domain_counts[dom][label] += 1

    mapping: dict[str, str] = {}
    for dom, counts in by_domain_counts.items():
        # pick the label with max count; if tie, prefer one that isn't a raw domain
        best = max(counts.items(), key=lambda kv: (kv[1], not "." in kv[0]))
        mapping[dom] = best[0]

    return mapping

def list_sources() -> list[str]:
    init_db()
    # prefer distinct sources from cached items
    conn = sqlite3.connect(settings.db_path); cur = conn.cursor()
    cur.execute("SELECT DISTINCT json_extract(summary_json,'$.source') FROM summaries WHERE json_extract(summary_json,'$.source') IS NOT NULL")
    rows = [r[0] for r in cur.fetchall() if r and r[0]]
    conn.close()
    if rows:
        return sorted(set(rows))
    # fallback: derive domains from feeds.txt
    feeds = load_lines(str(ROOT / "data" / "feeds.txt"))
    doms = sorted({urlsplit(u).netloc for u in feeds if u})
    return doms

def get_rows(limit: int, offset: int, q: str | None, since: str | None, source: str | None = None):
    init_db()
    where = []
    params: list = []

    if q:
        where.append("summary_json LIKE ?")
        params.append(f"%{q}%")
    if since:
        where.append("created_at >= ?")
        params.append(since)
    if source:
        mapping = build_source_map()
        # domains that map to the requested display name
        doms = [d for d, name in mapping.items() if name.lower() == source.lower()]
        if doms:
            placeholders = ",".join("?" for _ in doms)
            where.append(
                "(LOWER(json_extract(summary_json,'$.source')) = LOWER(?) "
                f" OR LOWER(json_extract(summary_json,'$.domain')) IN ({placeholders}))"
            )
            params.append(source)
            params.extend([d.lower() for d in doms])
        else:
            # still allow exact source match fallback
            where.append("LOWER(json_extract(summary_json,'$.source')) = LOWER(?)")
            params.append(source)

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    sql = (
        "SELECT summary_json FROM summaries "
        f"{where_sql} "
        "ORDER BY created_at DESC LIMIT ? OFFSET ?"
    )
    params.extend([limit, offset])

    conn = sqlite3.connect(settings.db_path); cur = conn.cursor()
    cur.execute(sql, params)
    rows = [json.loads(r[0]) for r in cur.fetchall()]
    conn.close()

    # ensure display date for legacy rows
    from datetime import datetime
    def eu_date(iso_ts: str | None) -> str:
        if not iso_ts: return ""
        try:
            dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
            return dt.strftime("%d-%m-%Y")
        except Exception:
            return ""
    for obj in rows:
        if not obj.get("published_date"):
            obj["published_date"] = eu_date(obj.get("published_at"))
    return rows


def get_candidates(limit: int = 200, q: str | None = None, source: str | None = None):
    return get_rows(limit=limit, offset=0, q=q, since=None, source=source)


# Hidden utility endpoint; optional bearer guard
@app.get("/items", include_in_schema=False)
def list_items(
    limit: int = Query(30, ge=1, le=200),
    offset: int = Query(0, ge=0),
    q: str | None = None,
    since: str | None = None,
    authorization: str | None = Header(None),
    source: str | None = None
):
    required = f"Bearer {settings.refresh_token}" if settings.refresh_token else None
    if required and authorization != required:
        raise HTTPException(status_code=401, detail="unauthorized")
    return JSONResponse(get_rows(limit, offset, q, since, source))

@app.get("/health")
def health():
    lr = last_run()
    return {"status": "ok", "last_run": lr}

# at top of file
import time
_last_refresh_ts = 0          # keep this global


@app.post("/refresh")
def refresh(
    per_feed: int | None = Body(None, embed=True),
    authorization: str | None = Header(None),
    # optionally accept token in body as a fallback if proxy strips headers
    token: str | None = Body(None, embed=True),
):
    # 1) Auth FIRST
    required = f"Bearer {settings.refresh_token}" if settings.refresh_token else None

    # allow either header or body 'token' (header preferred)
    presented = authorization or (f"Bearer {token}" if token else None)

    if required and presented != required:
        # Do NOT touch the rate-limit clock on auth failure
        raise HTTPException(status_code=401, detail="unauthorized")

    # 2) Rate-limit only AFTER successful auth
    global _last_refresh_ts
    now = time.time()
    if now - _last_refresh_ts < 5:  # e.g., 5s window
        raise HTTPException(status_code=429, detail="refresh too soon")
    _last_refresh_ts = now

    # 3) ... proceed normally
    s = load_settings()
    per_feed = per_feed or s.per_feed_cap
    feeds = load_lines(str(ROOT / "data" / "feeds.txt"))
    if not feeds:
        return JSONResponse({"error": "no feeds configured"}, status_code=400)
    stats = run_once(feeds=feeds, per_feed=per_feed, dry_run=False)
    return JSONResponse({"ok": True, "stats": stats})


@app.get("/home")
def home_api(limit: int = Query(5, ge=1, le=50),
             offset: int = Query(0, ge=0),
             q: str | None = None,
             source: str | None = None):
    s = load_settings()
    pool = get_candidates(limit=200, q=q, source=source)
    top = pick_home_items(pool, home_count=offset+limit,
                          per_domain_quota=s.per_domain_quota,
                          half_life_hours=s.recency_half_life_hours)
    page = top[offset:offset+limit]
    return JSONResponse(page)

# Single HTML route that supports search via ?q=
@app.get("/", include_in_schema=False)
def home_page(request: Request, q: str | None = None, source: str | None = None):
    s = load_settings()
    pool = get_candidates(limit=200, q=q, source=source)
    initial = pick_home_items(
        pool,
        home_count=5,
        per_domain_quota=s.per_domain_quota,
        half_life_hours=s.recency_half_life_hours,
    )
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "items": initial, "q": q or ""},
    )

@app.get("/sources")
def sources_api():
    mapping = build_source_map()  # builds from SQLite only
    names = sorted(set(mapping.values()), key=str.lower)
    return JSONResponse({"sources": names})

