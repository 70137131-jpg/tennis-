import logging
import shutil
import threading
from datetime import datetime, timedelta, timezone

from api.store import Store, now
from courtside.pipeline import analyze

log = logging.getLogger("courtside.worker")


def process_next(store: Store):
    session = store.claim()
    if not session:
        return False
    sid = session["id"]
    directory = store.root / "sessions" / sid
    try:
        original = next(directory.glob("original.*"))
        report = analyze(
            original, directory, session["options"], lambda p, s: store.update_progress(sid, p, s)
        )
        with store.connection() as db:
            db.execute(
                "UPDATE sessions SET status='completed',progress=100,stage='Complete',report=?,updated_at=? WHERE id=?",
                (report.model_dump_json(), now(), sid),
            )
    except InterruptedError:
        shutil.rmtree(directory, ignore_errors=True)
    except Exception as exc:
        log.exception("Analysis failed for %s", sid)
        with store.connection() as db:
            db.execute(
                "UPDATE sessions SET status='failed',stage='Analysis needs attention',error=?,updated_at=? WHERE id=?",
                (str(exc)[:1000], now(), sid),
            )
        if not store.get(sid):
            shutil.rmtree(directory, ignore_errors=True)
    return True


def cleanup(store):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=store.settings()["retention_days"])).isoformat()
    with store.connection() as db:
        expired = db.execute(
            "SELECT id FROM sessions WHERE is_demo=0 AND created_at<? AND status!='processing'", (cutoff,)
        ).fetchall()
        for row in expired:
            db.execute("DELETE FROM reviews WHERE session_id=?", (row[0],))
            for table in ('match_states', 'match_actions', 'line_reviews', 'highlight_exports'):
                db.execute(f"DELETE FROM {table} WHERE session_id=?", (row[0],))
            db.execute("DELETE FROM sessions WHERE id=?", (row[0],))
        abandoned = db.execute(
            "SELECT id FROM uploads WHERE created_at<?",
            ((datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),),
        ).fetchall()
        for row in abandoned:
            db.execute("DELETE FROM uploads WHERE id=?", (row[0],))
    for row in expired:
        shutil.rmtree(store.root / "sessions" / row[0], ignore_errors=True)
    for row in abandoned:
        (store.root / "uploads" / f"{row[0]}.part").unlink(missing_ok=True)
    return len(expired)


def run(store=None, stop=None):
    store = store or Store()
    stop = stop or threading.Event()
    with store.connection() as db:
        db.execute(
            "UPDATE sessions SET status='queued',stage='Resuming interrupted job' WHERE status='processing'"
        )
    last_cleanup = 0.0
    import time

    while not stop.is_set():
        if time.time() - last_cleanup > 3600:
            cleanup(store)
            last_cleanup = time.time()
        if not process_next(store):
            stop.wait(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
