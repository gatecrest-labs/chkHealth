import os
from dotenv import load_dotenv

load_dotenv()


def _require_secret_key() -> str:
    val = os.environ.get("SECRET_KEY", "")
    if not val or val == "change-me-in-production":
        raise RuntimeError(
            "SECRET_KEY is not set or is the insecure default. "
            "Generate one with: python manage_users.py secret"
        )
    return val


class Config:
    SECRET_KEY = _require_secret_key()
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() == "true"
    PERMANENT_SESSION_LIFETIME = int(os.environ.get("PERMANENT_SESSION_LIFETIME", "3600"))
    SESSION_ABSOLUTE_LIFETIME = int(os.environ.get("SESSION_ABSOLUTE_LIFETIME", str(10 * 3600)))
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH", str(4 * 1024 * 1024)))

    CP_MDS_PRIMARY = os.environ.get("CP_MDS_PRIMARY", "")
    CP_MDS_SECONDARY = os.environ.get("CP_MDS_SECONDARY", "")
    CP_MDS_3 = os.environ.get("CP_MDS_3", "")
    CP_MDS_4 = os.environ.get("CP_MDS_4", "")
    CP_API_KEY = os.environ.get("CP_API_KEY", "")
    CP_VERIFY_SSL = os.environ.get("CP_VERIFY_SSL", "false").lower() == "true"
    CP_TIMEOUT = int(os.environ.get("CP_TIMEOUT", "30"))
    GAIA_TIMEOUT = int(os.environ.get("GAIA_TIMEOUT", "15"))

    CP_MDS_PRIMARY_LABEL = os.environ.get("CP_MDS_PRIMARY_LABEL", "MDS Primary")
    CP_MDS_SECONDARY_LABEL = os.environ.get("CP_MDS_SECONDARY_LABEL", "MDS Secondary")
    CP_MDS_3_LABEL = os.environ.get("CP_MDS_3_LABEL", "MDS 3")
    CP_MDS_4_LABEL = os.environ.get("CP_MDS_4_LABEL", "MDS 4")

    CP_SE_1 = os.environ.get("CP_SE_1", "")
    CP_SE_2 = os.environ.get("CP_SE_2", "")
    CP_SE_1_LABEL = os.environ.get("CP_SE_1_LABEL", "SmartEvent Primary")
    CP_SE_2_LABEL = os.environ.get("CP_SE_2_LABEL", "SmartEvent Secondary")

    CP_MLS_1 = os.environ.get("CP_MLS_1", "")
    CP_MLS_2 = os.environ.get("CP_MLS_2", "")
    CP_MLS_1_LABEL = os.environ.get("CP_MLS_1_LABEL", "MLS Primary")
    CP_MLS_2_LABEL = os.environ.get("CP_MLS_2_LABEL", "MLS Secondary")

    CPU_WARN = int(os.environ.get("CPU_WARN", "70"))
    CPU_CRIT = int(os.environ.get("CPU_CRIT", "90"))
    MEM_WARN = int(os.environ.get("MEM_WARN", "75"))
    MEM_CRIT = int(os.environ.get("MEM_CRIT", "90"))

    # ── LDAP / Active Directory ───────────────────────────────────────────────
    LDAP_ENABLED       = os.environ.get("LDAP_ENABLED", "false").lower() == "true"
    LDAP_SERVER        = os.environ.get("LDAP_SERVER", "")
    LDAP_DOMAIN        = os.environ.get("LDAP_DOMAIN", "")
    LDAP_BASE_DN       = os.environ.get("LDAP_BASE_DN", "")
    LDAP_BIND_USER     = os.environ.get("LDAP_BIND_USER", "")
    LDAP_BIND_PASSWORD = os.environ.get("LDAP_BIND_PASSWORD", "")
    LDAP_USER_SEARCH   = os.environ.get("LDAP_USER_SEARCH", "(sAMAccountName={username})")
    LDAP_GROUP_ADMIN   = os.environ.get("LDAP_GROUP_ADMIN", "")
    LDAP_GROUP_VIEWER  = os.environ.get("LDAP_GROUP_VIEWER", "")
    LDAP_VERIFY_SSL    = os.environ.get("LDAP_VERIFY_SSL", "true").lower() == "true"
    LDAP_TIMEOUT       = int(os.environ.get("LDAP_TIMEOUT", "10"))

    # ── TACACS+ ───────────────────────────────────────────────────────────────
    TACACS_ENABLED      = os.environ.get("TACACS_ENABLED", "false").lower() == "true"
    TACACS_HOST         = os.environ.get("TACACS_HOST", "")
    TACACS_PORT         = int(os.environ.get("TACACS_PORT", "49"))
    TACACS_HOST_2       = os.environ.get("TACACS_HOST_2", "")
    TACACS_PORT_2       = int(os.environ.get("TACACS_PORT_2", "49"))
    TACACS_SECRET       = os.environ.get("TACACS_SECRET", "")
    TACACS_TIMEOUT      = int(os.environ.get("TACACS_TIMEOUT", "10"))
    TACACS_PRIV_ADMIN   = os.environ.get("TACACS_PRIV_ADMIN", "15")
    TACACS_GROUP_ADMIN  = os.environ.get("TACACS_GROUP_ADMIN", "")
    TACACS_GROUP_VIEWER = os.environ.get("TACACS_GROUP_VIEWER", "")

    # ── RADIUS ────────────────────────────────────────────────────────────────
    RADIUS_ENABLED      = os.environ.get("RADIUS_ENABLED", "false").lower() == "true"
    RADIUS_HOST         = os.environ.get("RADIUS_HOST", "")
    RADIUS_PORT         = int(os.environ.get("RADIUS_PORT", "1812"))
    RADIUS_HOST_2       = os.environ.get("RADIUS_HOST_2", "")
    RADIUS_PORT_2       = int(os.environ.get("RADIUS_PORT_2", "1812"))
    RADIUS_SECRET       = os.environ.get("RADIUS_SECRET", "")
    RADIUS_TIMEOUT      = int(os.environ.get("RADIUS_TIMEOUT", "10"))
    RADIUS_GROUP_ADMIN  = os.environ.get("RADIUS_GROUP_ADMIN", "")
    RADIUS_GROUP_VIEWER = os.environ.get("RADIUS_GROUP_VIEWER", "")
