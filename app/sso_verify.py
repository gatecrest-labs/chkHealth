"""Verify a 4tSuite-issued JWT and map it to a username or a service scope.

This is the whole trust boundary between chkHealth and 4tSuite. Login tokens
carry no `scope` claim; service tokens (manifest/groups/health) do and must
never start a browser session. The public key file may hold one PEM or a
rotation bundle; it is re-read on every call so a rotated file takes effect
without a restart.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

import jwt
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization

APP_ID = "chkhealth"

_PEM_RE = re.compile(rb"-----BEGIN PUBLIC KEY-----.+?-----END PUBLIC KEY-----", re.DOTALL)


def _key_path() -> Path:
    default = Path(__file__).parent.parent / "sso_public_key.pem"
    return Path(os.environ.get("SSO_PUBLIC_KEY_PATH", str(default)))


def _load_keys() -> dict[str, bytes]:
    """Map kid -> PEM for every valid public key in the file (re-read per call)."""
    try:
        data = _key_path().read_bytes()
    except OSError:
        return {}
    found: dict[str, bytes] = {}
    for block in _PEM_RE.findall(data):
        try:
            raw = serialization.load_pem_public_key(block).public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw
            )
        except (ValueError, TypeError, UnsupportedAlgorithm):
            continue
        found[hashlib.sha256(raw).hexdigest()[:16]] = block
    return found


def _decode(token: str) -> dict | None:
    """Verify `token` against the bundle: select by kid, else try every key.

    Only a bad signature moves on to the next key; any other invalid-token
    reason (expired, wrong audience, ...) fails closed immediately.
    """
    keys = _load_keys()
    if not keys:
        return None
    try:
        kid = jwt.get_unverified_header(token).get("kid")
    except jwt.PyJWTError:
        return None
    if not isinstance(kid, str):
        kid = None
    candidates = [keys[kid]] if kid in keys else list(keys.values())
    for pem in candidates:
        try:
            return jwt.decode(
                token,
                pem,
                algorithms=["EdDSA"],
                audience=APP_ID,
                issuer="4tsuite",
                leeway=30,
                options={"require": ["exp", "iat", "nbf", "sub", "aud", "iss"]},
            )
        except jwt.InvalidSignatureError:
            continue
        except jwt.PyJWTError:
            return None
    return None


def verify_token(token: str) -> str | None:
    """Username (`sub`) for a valid SSO *login* token, else None. Service tokens are refused."""
    claims = _decode(token)
    if claims is None or "scope" in claims:
        return None
    return claims.get("sub") or None


def verify_service_token(token: str, expected_scope: str) -> dict | None:
    claims = _decode(token)
    if claims is None or claims.get("scope") != expected_scope:
        return None
    return claims
