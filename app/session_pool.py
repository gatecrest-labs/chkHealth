"""
Persistent SID cache for the Check Point management API.

Instead of logging in on every API call, callers obtain a CPClient via
connect() which reuses a cached SID for the (host, domain) pair.  The
SID is only replaced when the server rejects it (401/403), at which
point one re-authentication is attempted automatically.
"""
from __future__ import annotations

import threading

from app.app_logger import app_log
from app.cp_client import CPClient

_lock = threading.Lock()
# (host, domain_or_empty) -> sid
_sids: dict[tuple[str, str], str] = {}


def _key(host: str, domain: str | None) -> tuple[str, str]:
    return (host, domain or "")


def _get(host: str, domain: str | None) -> str | None:
    with _lock:
        return _sids.get(_key(host, domain))


def _put(host: str, domain: str | None, sid: str) -> None:
    with _lock:
        _sids[_key(host, domain)] = sid


def invalidate(host: str, domain: str | None) -> None:
    with _lock:
        _sids.pop(_key(host, domain), None)


def clear_all() -> None:
    with _lock:
        _sids.clear()


def list_cached_keys() -> list[dict]:
    """Return cached (host, domain) pairs — for diagnostics only."""
    with _lock:
        return [{"host": h, "domain": d or None} for h, d in _sids]


def connect(
    host: str,
    api_key: str,
    verify_ssl: bool,
    timeout: int,
    domain: str | None = None,
) -> CPClient:
    """
    Return a CPClient ready to make API calls.

    If a valid SID exists in the cache it is injected (no login round-trip).
    The returned client's call() method is wrapped so that a stale SID
    triggers a single transparent re-authentication before propagating the
    error to the caller.
    """
    client = CPClient(host, api_key, verify_ssl, timeout)
    cached = _get(host, domain)
    if cached:
        client._sid = cached
        client._domain = domain
        app_log("DEBUG", "session_pool", f"Reusing session {host} domain={domain or 'global'}")
    else:
        client.login(domain=domain)
        _put(host, domain, client._sid)
        app_log("INFO", "session_pool", f"New session {host} domain={domain or 'global'}")

    # Wrap client.call so expired SIDs trigger one automatic re-auth
    orig_call = client.call

    def _call_with_reauth(command: str, payload: dict | None = None) -> dict:
        try:
            return orig_call(command, payload)
        except Exception as exc:
            err = str(exc)
            if "401" in err or "403" in err:
                app_log("INFO", "session_pool",
                        f"Session expired for {host}/{domain or 'global'} — re-authenticating")
                invalidate(host, domain)
                client.login(domain=domain)
                _put(host, domain, client._sid)
                return orig_call(command, payload)
            raise

    client.call = _call_with_reauth
    return client
