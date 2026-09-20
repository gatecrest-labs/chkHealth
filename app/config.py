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

    CP_MDS_PRIMARY_LABEL = os.environ.get("CP_MDS_PRIMARY_LABEL", "MDS Primary")
    CP_MDS_SECONDARY_LABEL = os.environ.get("CP_MDS_SECONDARY_LABEL", "MDS Secondary")
    CP_MDS_3_LABEL = os.environ.get("CP_MDS_3_LABEL", "MDS 3")
    CP_MDS_4_LABEL = os.environ.get("CP_MDS_4_LABEL", "MDS 4")

    CP_MLS_1 = os.environ.get("CP_MLS_1", "")
    CP_MLS_2 = os.environ.get("CP_MLS_2", "")
    CP_MLS_1_LABEL = os.environ.get("CP_MLS_1_LABEL", "MLS Primary")
    CP_MLS_2_LABEL = os.environ.get("CP_MLS_2_LABEL", "MLS Secondary")

    CPU_WARN = int(os.environ.get("CPU_WARN", "70"))
    CPU_CRIT = int(os.environ.get("CPU_CRIT", "90"))
    MEM_WARN = int(os.environ.get("MEM_WARN", "75"))
    MEM_CRIT = int(os.environ.get("MEM_CRIT", "90"))
