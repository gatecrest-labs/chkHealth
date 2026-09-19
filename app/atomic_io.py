"""Atomic file writes that degrade gracefully on Docker bind mounts."""

from __future__ import annotations

import errno
import json
import os
from pathlib import Path


def atomic_write_text(path, text: str) -> None:
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    try:
        os.replace(tmp, path)
    except OSError as exc:
        if exc.errno != errno.EBUSY:
            raise
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        try:
            os.unlink(tmp)
        except OSError:
            pass


def atomic_write_json(path, data, *, indent: int = 2) -> None:
    atomic_write_text(path, json.dumps(data, indent=indent))
