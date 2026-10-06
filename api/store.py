import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, root: Path | None = None):
        self.root = (root or Path(os.environ.get("COURTSIDE_STORAGE", "storage"))).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "sessions").mkdir(exist_ok=True)
        (self.root / "uploads").mkdir(exist_ok=True)
        with self.connection() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS sessions (
                  id TEXT PRIMARY KEY, title TEXT NOT NULL, created_at TEXT NOT NULL,
                  status TEXT NOT NULL, progress INTEGER DEFAULT 0, stage TEXT DEFAULT '',
                  error TEXT, options TEXT NOT NULL, metadata TEXT NOT NULL,
                  report TEXT, is_demo INTEGER DEFAULT 0, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS uploads (
                  id TEXT PRIMARY KEY, filename TEXT NOT NULL, size INTEGER NOT NULL,
                  offset INTEGER DEFAULT 0, options TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS reviews (
                  id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,
                  shot_id TEXT NOT NULL, tip_id TEXT NOT NULL, rating TEXT NOT NULL,
                  correction TEXT NOT NULL, created_at TEXT NOT NULL,
                  UNIQUE(session_id, shot_id, tip_id));
            """)
            default = {
                "display_name": "Ali",
                "player_name": "Ali Haider",
                "handedness": "right",
                "backhand_style": "two-handed",
                "level": "competitive",
                "retention_days": int(os.environ.get("COURTSIDE_RETENTION_DAYS", "30")),
                "blur_faces": True,
            }
            db.execute("INSERT OR IGNORE INTO settings VALUES(1, ?)", (json.dumps(default),))

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.root / "courtside.sqlite", timeout=30)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def settings(self):
        with self.connection() as db:
            return json.loads(db.execute("SELECT value FROM settings WHERE id=1").fetchone()[0])

    def list_sessions(self):
        with self.connection() as db:
            rows = db.execute("SELECT * FROM sessions ORDER BY created_at DESC").fetchall()
        return [self.serialize(row) for row in rows]

    def get(self, session_id):
        with self.connection() as db:
            row = db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        return self.serialize(row) if row else None

    def serialize(self, row):
        value = dict(row)
        for key in ["options", "metadata", "report"]:
            value[key] = json.loads(value[key]) if value[key] else None
        value["is_demo"] = bool(value["is_demo"])
        return value

    def claim(self):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT id FROM sessions WHERE status='queued' ORDER BY created_at LIMIT 1"
            ).fetchone()
            if not row:
                return None
            db.execute(
                "UPDATE sessions SET status='processing', stage='Starting analysis', updated_at=? WHERE id=?",
                (now(), row[0]),
            )
        return self.get(row[0])

    def update_progress(self, session_id, percent, stage):
        with self.connection() as db:
            row = db.execute("SELECT id FROM sessions WHERE id=?", (session_id,)).fetchone()
            if not row:
                raise InterruptedError("Session deleted; analysis cancelled")
            db.execute(
                "UPDATE sessions SET progress=?,stage=?,updated_at=? WHERE id=?",
                (percent, stage, now(), session_id),
            )
