from __future__ import annotations

import sqlite3
from pathlib import Path

_DB_PATH = Path(__file__).parent.parent / "metrics.db"

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS summary_history (
    date       TEXT PRIMARY KEY,
    gw_count   INTEGER NOT NULL,
    rule_count INTEGER NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


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
