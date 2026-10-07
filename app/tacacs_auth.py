import logging
from typing import Optional

from tacacs_plus.client import TACACSClient

log = logging.getLogger(__name__)

_TAC_PLUS_AUTHEN_TYPE_PAP = 2


def _try_one_server(
    username: str,
    password: str,
    host: str,
    port: int,
    secret: str,
    timeout: int,
):
    """Attempt PAP authentication against one TACACS+ server.

    Returns (client, auth_reply) on network success, or (None, None) on failure.
    """
    try:
        client = TACACSClient(host, port, secret, timeout=timeout)
        reply = client.authenticate(
            username,
            password,
            authen_type=_TAC_PLUS_AUTHEN_TYPE_PAP,
        )
        return client, reply
    except Exception as exc:
        log.warning("TACACS+: server %s:%d unreachable for %r: %s", host, port, username, exc)
        return None, None


def authenticate(
    username: str,
    password: str,
    host: str,
    port: int,
    secret: str,
    timeout: int,
    priv_admin: str,
    group_admin: str,
    group_viewer: str,
    host2: str = "",
    port2: int = 49,
) -> Optional[dict]:
    servers = [(host, port)]
    if host2:
        servers.append((host2, port2))

    client, auth_reply = None, None
    for srv_host, srv_port in servers:
        client, auth_reply = _try_one_server(username, password, srv_host, srv_port, secret, timeout)
        if client is not None:
            break

    if client is None:
        log.error("TACACS+: all servers unreachable for %r", username)
        return None

    if not auth_reply.valid:
        log.info("TACACS+: authentication failed for %r", username)
        return None

    # Fetch authorization AV pairs
    try:
        authz_reply = client.authorize(username, arguments=[b"service=shell", b"cmd="])
        av_pairs = (
            [arg.decode("utf-8", errors="ignore") for arg in authz_reply.arguments]
            if authz_reply.valid
            else []
        )
    except Exception as exc:
        log.warning("TACACS+: authorization request failed for %r: %s", username, exc)
        av_pairs = []

    if priv_admin:
        # Privilege-level mode
        priv_lvl = None
        for pair in av_pairs:
            if pair.startswith("priv-lvl="):
                try:
                    priv_lvl = int(pair.split("=", 1)[1])
                except ValueError:
                    pass
                break

        if priv_lvl is None:
            return {"role": "viewer", "ad_groups": av_pairs}

        try:
            threshold = int(priv_admin)
        except ValueError:
            threshold = 15

        return {"role": "admin" if priv_lvl >= threshold else "viewer", "ad_groups": av_pairs}

    else:
        # Group AV-pair mode
        if group_admin and any(group_admin.lower() in p.lower() for p in av_pairs):
            return {"role": "admin", "ad_groups": av_pairs}
        if group_viewer and any(group_viewer.lower() in p.lower() for p in av_pairs):
            return {"role": "viewer", "ad_groups": av_pairs}
        if av_pairs and (group_admin or group_viewer):
            log.warning(
                "TACACS+ user %r authenticated but no role group matched. "
                "AV pairs: %s. Expected admin=%r viewer=%r",
                username, av_pairs, group_admin, group_viewer,
            )
            return None

        return {"role": "viewer", "ad_groups": av_pairs}
