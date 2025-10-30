from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import sqlite3, json
from pathlib import Path
from app.config import settings

app = FastAPI(title="Summarizer API")

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

def get_rows(limit: int = 50, q: str | None = None):
    conn = sqlite3.connect(settings.db_path)
    cur = conn.cursor()
    if q:
        cur.execute(
            "SELECT summary_json FROM summaries "
            "WHERE summary_json LIKE ? ORDER BY created_at DESC LIMIT ?",
            (f"%{q}%", limit),
        )
    else:
        cur.execute(
            "SELECT summary_json FROM summaries ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
    rows = [json.loads(r[0]) for r in cur.fetchall()]
    conn.close()
    return rows

@app.get("/items")
def list_items(limit: int = Query(50, ge=1, le=200), q: str | None = None):
    return JSONResponse(get_rows(limit, q))

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/", include_in_schema=False)
def home(request: Request, q: str | None = None, limit: int = Query(30, ge=1, le=200)):
    items = get_rows(limit, q)
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "items": items, "q": q or ""},
    )
