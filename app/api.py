from fastapi import FastAPI, Query, Request, Body, Header, HTTPException
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import sqlite3, json
from pathlib import Path
from urllib.parse import urlsplit

from app.db import init_db, last_run
from app.config import settings
from app.ranker import pick_home_items
from app.util import load_lines
from app.pipeline import run_once
from app.settings import load_settings

app = FastAPI(title="Summarizer API")

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

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
        # Case-insensitive match against source (feed title) OR domain
        where.append(
            "(LOWER(json_extract(summary_json,'$.source')) = LOWER(?) "
            " OR LOWER(json_extract(summary_json,'$.domain')) = LOWER(?))"
        )
        params.extend([source, source])

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

@app.post("/refresh")
def refresh(per_feed: int | None = Body(None, embed=True), authorization: str | None = Header(None)):
    required = f"Bearer {settings.refresh_token}" if settings.refresh_token else None
    if required and authorization != required:
        raise HTTPException(status_code=401, detail="unauthorized")

    s = load_settings()
    per_feed = per_feed or s.per_feed_cap

    feeds = load_lines(str(ROOT / "data" / "feeds.txt"))
    inc = load_lines(str(ROOT / "data" / "include.txt"))
    exc = load_lines(str(ROOT / "data" / "exclude.txt"))
    if not feeds:
        return JSONResponse({"error": "no feeds configured"}, status_code=400)

    stats = run_once(feeds=feeds, includes=inc, excludes=exc, per_feed=per_feed, dry_run=False)
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
    init_db()
    conn = sqlite3.connect(settings.db_path); cur = conn.cursor()
    cur.execute("SELECT DISTINCT json_extract(summary_json,'$.source'), json_extract(summary_json,'$.domain') FROM summaries")
    opts = set()
    for s, d in cur.fetchall():
        s = (s or "").strip()
        d = (d or "").strip()
        if s:
            opts.add(s)
        elif d:
            opts.add(d)
    conn.close()

    if not opts:
        # fallback to feeds.txt domains
        from urllib.parse import urlsplit
        feeds = load_lines(str(ROOT / "data" / "feeds.txt"))
        for u in feeds:
            host = urlsplit(u).netloc
            if host:
                opts.add(host)

    return JSONResponse({"sources": sorted(opts, key=str.lower)})

