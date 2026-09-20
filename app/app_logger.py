"""Application-level logging with an in-memory ring buffer.

Log levels (in ascending severity): TRACE DEBUG INFO WARN ERROR

Usage:
    from app.app_logger import app_log, set_log_level, get_log_entries
    app_log("INFO", "auth", "User logged in", username="admin")
"""

import sys
import threading
from collections import deque
from datetime import datetime, timezone

_LEVELS = ["TRACE", "DEBUG", "INFO", "WARN", "ERROR"]
_LEVEL_RANK = {lvl: i for i, lvl in enumerate(_LEVELS)}

_MAX_ENTRIES = 2000
_buffer: deque = deque(maxlen=_MAX_ENTRIES)
_lock = threading.Lock()
_current_level = "INFO"


def set_log_level(level: str) -> None:
    global _current_level
    level = level.upper()
    if level not in _LEVEL_RANK:
        raise ValueError(f"Invalid log level '{level}'. Choose from: {', '.join(_LEVELS)}")
    with _lock:
        _current_level = level


def get_log_level() -> str:
    return _current_level


def get_log_levels() -> list[str]:
    return list(_LEVELS)


def app_log(level: str, component: str, message: str, **extra) -> None:
    level = level.upper()
    with _lock:
        current = _current_level
    if _LEVEL_RANK.get(level, 0) < _LEVEL_RANK.get(current, 0):
        return
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "level": level,
        "component": component,
        "message": message,
    }
    if extra:
        entry["extra"] = extra
    extra_str = " ".join(f"{k}={v}" for k, v in extra.items()) if extra else ""
    print(
        f"[{entry['ts']}] {level} {component}: {message}" + (f" {extra_str}" if extra_str else ""),
        file=sys.stderr,
    )
    with _lock:
        _buffer.append(entry)


def get_log_entries(
    level: str | None = None,
    component: str | None = None,
    limit: int = 500,
) -> list[dict]:
    min_rank = _LEVEL_RANK.get((level or "").upper(), 0)
    with _lock:
        entries = list(_buffer)
    if level:
        entries = [e for e in entries if _LEVEL_RANK.get(e["level"], 0) >= min_rank]
    if component:
        entries = [e for e in entries if e["component"] == component]
    return entries[-limit:]


def clear_log_entries() -> None:
    with _lock:
        _buffer.clear()
