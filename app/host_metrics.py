from __future__ import annotations

import contextlib
import os
import sqlite3
from pathlib import Path

_DB_PATH = Path(os.environ.get("METRICS_DB_PATH", str(Path(__file__).parent.parent / "metrics.db")))

@contextlib.contextmanager
def _connect():
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS summary_history "
            "(date TEXT PRIMARY KEY, gw_count INTEGER NOT NULL, rule_count INTEGER NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS startup_log (slot TEXT PRIMARY KEY)"
        )


def upsert_summary(date: str, gw_count: int, rule_count: int) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO summary_history (date, gw_count, rule_count) VALUES (?, ?, ?)",
            (date, gw_count, rule_count),
        )


def try_claim_startup() -> bool:
    """Return True if this process should run startup data collection.

    Uses the current UTC hour as a slot key. The first process to INSERT wins;
    subsequent workers (gunicorn multi-worker or Flask reloader child) get False
    and skip the collection, preventing concurrent MDS login floods.
    Fails open — if the DB is unavailable, allow the run rather than block it.
    """
    from datetime import datetime, timezone
    slot = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")
    try:
        with _connect() as conn:
            cur = conn.execute(
                "INSERT OR IGNORE INTO startup_log (slot) VALUES (?)", (slot,)
            )
            return cur.rowcount > 0
    except Exception:
        return True


def get_history(days: int = 30) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT date, gw_count, rule_count
            FROM (
                SELECT date, gw_count, rule_count
                FROM summary_history
                ORDER BY date DESC LIMIT ?
            )
            ORDER BY date ASC
            """,
            (days,),
        ).fetchall()
    return [dict(row) for row in rows]
