import sqlite3, json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List
from app.config import settings

DB_PATH = settings.db_path

def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db() -> None:
    conn = connect(); c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS summaries(
            url TEXT PRIMARY KEY,
            title TEXT,
            published_at TEXT,
            content_hash TEXT,
            summary_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_hash ON summaries(content_hash)")
    # NEW: runs table
    c.execute("""
        CREATE TABLE IF NOT EXISTS runs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            finished_at TEXT NOT NULL,
            seen INTEGER NOT NULL,
            summarized INTEGER NOT NULL,
            cached INTEGER NOT NULL,
            skipped INTEGER NOT NULL,
            errors INTEGER NOT NULL
        )
    """)
    conn.commit(); conn.close()

def has_url(url: str) -> bool:
    conn = connect(); cur = conn.cursor()
    cur.execute("SELECT 1 FROM summaries WHERE url=?", (url,))
    r = cur.fetchone(); conn.close()
    return bool(r)

def insert_summary(data: Dict[str, Any], content_hash: str, published_at: str = "") -> None:
    conn = connect(); cur = conn.cursor()
    cur.execute(
        """INSERT OR REPLACE INTO summaries(url,title,published_at,content_hash,summary_json,created_at)
           VALUES(?,?,?,?,?,?)""",
        (
            data.get("url",""),
            data.get("title",""),
            published_at,
            content_hash,
            json.dumps(data, ensure_ascii=False),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit(); conn.close()

def recent(limit: int = 50) -> List[Dict[str, Any]]:
    conn = connect(); cur = conn.cursor()
    cur.execute("SELECT summary_json FROM summaries ORDER BY created_at DESC LIMIT ?", (limit,))
    rows = [json.loads(r[0]) for r in cur.fetchall()]
    conn.close()
    return rows

# NEW: record and fetch run stats
def record_run(stats: Dict[str, int], started_at: str, finished_at: str) -> None:
    conn = connect(); cur = conn.cursor()
    cur.execute(
        """INSERT INTO runs(started_at, finished_at, seen, summarized, cached, skipped, errors)
           VALUES(?,?,?,?,?,?,?)""",
        (
            started_at, finished_at,
            int(stats.get("seen",0)),
            int(stats.get("summarized",0)),
            int(stats.get("cached",0)),
            int(stats.get("skipped",0)),
            int(stats.get("errors",0)),
        ),
    )
    conn.commit(); conn.close()

def last_run() -> Dict[str, Any] | None:
    conn = connect(); cur = conn.cursor()
    cur.execute("SELECT started_at, finished_at, seen, summarized, cached, skipped, errors "
                "FROM runs ORDER BY id DESC LIMIT 1")
    r = cur.fetchone(); conn.close()
    if not r: return None
    cols = ["started_at","finished_at","seen","summarized","cached","skipped","errors"]
    return {k: r[i] for i,k in enumerate(cols)}
