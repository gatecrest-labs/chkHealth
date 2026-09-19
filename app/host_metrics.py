from __future__ import annotations

import contextlib
import os
import sqlite3
from pathlib import Path

_DB_PATH = Path(os.environ.get("METRICS_DB_PATH", str(Path(__file__).parent.parent / "metrics.db")))

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS summary_history (
    date       TEXT PRIMARY KEY,
    gw_count   INTEGER NOT NULL,
    rule_count INTEGER NOT NULL
);
"""


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
        conn.execute(_CREATE_SQL)


def upsert_summary(date: str, gw_count: int, rule_count: int) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO summary_history (date, gw_count, rule_count) VALUES (?, ?, ?)",
            (date, gw_count, rule_count),
        )


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
