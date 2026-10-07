import logging
import ssl
from typing import Optional

from ldap3 import Connection, NONE as GET_INFO_NONE, Server, SUBTREE, Tls

log = logging.getLogger(__name__)


def _extract_cn(dn: str) -> str:
    """Extract the CN value from the first component of an LDAP DN."""
    for part in dn.split(","):
        part = part.strip()
        if part.upper().startswith("CN="):
            return part[3:]
    return dn


def authenticate(
    username: str,
    password: str,
    server_url: str,
    base_dn: str,
    bind_user: str,
    bind_password: str,
    user_search: str,
    group_admin: str,
    group_viewer: str,
    verify_ssl: bool = True,
    timeout: int = 10,
) -> Optional[dict]:
    try:
        from ldap3.utils.conv import escape_filter_chars
        tls = Tls(validate=ssl.CERT_REQUIRED if verify_ssl else ssl.CERT_NONE)
        server = Server(server_url, get_info=GET_INFO_NONE, tls=tls, connect_timeout=timeout)

        # Service-account bind to locate the user's DN
        service_conn = Connection(server, user=bind_user, password=bind_password, auto_bind=True,
                                  receive_timeout=timeout)
        safe_username = escape_filter_chars(username)
        search_filter = user_search.replace("{username}", safe_username)
        service_conn.search(
            search_base=base_dn,
            search_filter=search_filter,
            search_scope=SUBTREE,
            attributes=["memberOf"],
        )

        if not service_conn.entries:
            log.warning("LDAP: user %r not found under %s", username, base_dn)
            service_conn.unbind()
            return None

        entry = service_conn.entries[0]
        user_dn = entry.entry_dn
        member_of_dns = (
            [str(v) for v in entry.memberOf]
            if "memberOf" in entry
            else []
        )
        service_conn.unbind()

        # User re-bind validates the supplied password
        user_conn = Connection(server, user=user_dn, password=password, auto_bind=True,
                               receive_timeout=timeout)
        user_conn.unbind()

        # Extract CN names from memberOf DNs
        ad_groups = [_extract_cn(dn) for dn in member_of_dns]

        # Role resolution
        if group_admin and any(group_admin.lower() == g.lower() for g in ad_groups):
            return {"role": "admin", "ad_groups": ad_groups}
        if group_viewer and any(group_viewer.lower() == g.lower() for g in ad_groups):
            return {"role": "viewer", "ad_groups": ad_groups}
        if ad_groups and (group_admin or group_viewer):
            log.warning(
                "LDAP user %r authenticated but no role group matched. "
                "Groups: %s. Expected admin=%r viewer=%r",
                username, ad_groups, group_admin, group_viewer,
            )
            return None

        return {"role": "viewer", "ad_groups": ad_groups}

    except Exception as exc:
        log.warning("LDAP authentication failed for %r: %s", username, exc)
        return None
