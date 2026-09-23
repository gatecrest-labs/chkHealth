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
            "CREATE TABLE IF NOT EXISTS startup_log (slot TEXT PRIMARY KEY, ts REAL)"
        )
        try:
            conn.execute("SELECT ts FROM startup_log LIMIT 1")
        except Exception:
            conn.execute("ALTER TABLE startup_log ADD COLUMN ts REAL")
        for col in ("gw_single", "gw_cluster_members"):
            try:
                conn.execute(f"SELECT {col} FROM summary_history LIMIT 1")
            except Exception:
                conn.execute(f"ALTER TABLE summary_history ADD COLUMN {col} INTEGER NOT NULL DEFAULT 0")
        try:
            conn.execute("SELECT collected_at FROM summary_history LIMIT 1")
        except Exception:
            conn.execute("ALTER TABLE summary_history ADD COLUMN collected_at TEXT")


def upsert_summary(date: str, gw_count: int, rule_count: int,
                   gw_single: int = 0, gw_cluster_members: int = 0,
                   collected_at: str | None = None) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO summary_history "
            "(date, gw_count, rule_count, gw_single, gw_cluster_members, collected_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (date, gw_count, rule_count, gw_single, gw_cluster_members, collected_at),
        )


def try_claim_startup(debounce_secs: int = 90) -> bool:
    """Return True if this process should run startup data collection.

    Uses a timestamp-based debounce: if another process started within the
    last debounce_secs seconds, return False.  This lets concurrent workers
    (gunicorn, Flask reloader child) be deduplicated while still allowing a
    clean re-run after a restart.  Fails open — if the DB is unavailable,
    allow the run rather than block it.
    """
    import time
    now = time.time()
    try:
        with _connect() as conn:
            conn.execute("DELETE FROM startup_log WHERE ts < ? OR ts IS NULL",
                         (now - debounce_secs,))
            cur = conn.execute(
                "INSERT OR IGNORE INTO startup_log (slot, ts) VALUES ('running', ?)", (now,)
            )
            return cur.rowcount > 0
    except Exception:
        return True


def get_history(days: int = 30) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT date, gw_count, rule_count, gw_single, gw_cluster_members, collected_at
            FROM (
                SELECT date, gw_count, rule_count, gw_single, gw_cluster_members, collected_at
                FROM summary_history
                ORDER BY date DESC LIMIT ?
            )
            ORDER BY date ASC
            """,
            (days,),
        ).fetchall()
    return [dict(row) for row in rows]
