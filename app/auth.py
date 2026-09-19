import json
import os
import secrets
import string
from pathlib import Path

import bcrypt

from app.atomic_io import atomic_write_json

USERS_FILE = Path(os.environ.get("USERS_FILE", str(Path(__file__).parent.parent / "users.json")))


def _load_users() -> dict:
    if not USERS_FILE.exists():
        return {}
    with USERS_FILE.open() as f:
        return json.load(f)


def _save_users(users: dict) -> None:
    atomic_write_json(USERS_FILE, users)


def authenticate(username: str, password: str) -> tuple[str, list] | None:
    users = _load_users()
    entry = users.get(username)
    if not entry:
        return None
    stored_hash = entry.get("password_hash", "")
    if not stored_hash:
        return None
    try:
        if not bcrypt.checkpw(password.encode(), stored_hash.encode()):
            return None
    except Exception:
        return None
    return entry.get("role", "viewer"), []


def add_user(username: str, password: str, role: str = "viewer") -> None:
    users = _load_users()
    if username in users:
        raise ValueError(f"User '{username}' already exists.")
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    users[username] = {"password_hash": hashed, "role": role}
    _save_users(users)


def update_password(username: str, password: str) -> None:
    users = _load_users()
    if username not in users:
        raise ValueError(f"User '{username}' not found.")
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    users[username]["password_hash"] = hashed
    _save_users(users)


def delete_user(username: str) -> bool:
    users = _load_users()
    if username not in users:
        return False
    del users[username]
    _save_users(users)
    return True


def list_users() -> list[dict]:
    users = _load_users()
    return [{"username": k, "role": v.get("role", "viewer")} for k, v in users.items()]


def generate_secret_key() -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(secrets.choice(alphabet) for _ in range(48))
