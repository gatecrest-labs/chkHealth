from __future__ import annotations

import time

from app.app_logger import app_log
from app.cp_client import CPClient


class _HAContext:
    def __init__(self, domain: str | None = None):
        self._domain = domain
        self._client: CPClient | None = None

    def __enter__(self) -> CPClient:
        from app.config import Config
        from app import session_pool

        # Only Provider-1 / MDS hosts are valid targets for domain-scoped
        # logins. SmartEvent appliances (CP_SE_*) must not appear here.
        candidates = [
            (Config.CP_MDS_PRIMARY, Config.CP_MDS_PRIMARY_LABEL),
            (Config.CP_MDS_3,       Config.CP_MDS_3_LABEL),
        ]
        for attempt in range(2):
            for host, label in candidates:
                if not host:
                    continue
                try:
                    client = session_pool.connect(
                        host,
                        Config.CP_API_KEY,
                        Config.CP_VERIFY_SSL,
                        Config.CP_TIMEOUT,
                        domain=self._domain,
                    )
                    self._client = client
                    app_log("DEBUG", "cp_helpers", f"Connected via {label}")
                    return client
                except Exception as exc:
                    app_log("WARN", "cp_helpers", f"Failed to connect to {label}", exc=str(exc))
            if attempt == 0:
                app_log("INFO", "cp_helpers", "All hosts failed, retrying after back-off",
                        domain=self._domain or "global")
                time.sleep(15)
        raise ConnectionError("Could not connect to any configured MDS host")

    def __exit__(self, *args) -> None:
        # Do not logout — SIDs are kept alive and reused via session_pool
        pass


def make_client(domain: str | None = None) -> _HAContext:
    return _HAContext(domain)
