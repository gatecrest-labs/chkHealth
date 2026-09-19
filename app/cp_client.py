from __future__ import annotations

import warnings

import requests
import urllib3


class CPAPIError(Exception):
    def __init__(self, message: str, command: str, data: dict):
        super().__init__(message)
        self.command = command
        self.data = data


class CPClient:
    def __init__(
        self,
        host: str,
        api_key: str,
        verify_ssl: bool = False,
        timeout: int = 30,
    ):
        self.host = host
        self._api_key = api_key
        self._verify_ssl = verify_ssl
        self._timeout = timeout
        self._sid: str | None = None
        self._domain: str | None = None
        self._session = requests.Session()
        if not verify_ssl:
            warnings.filterwarnings("ignore", category=urllib3.exceptions.InsecureRequestWarning)

    def _url(self, command: str) -> str:
        return f"https://{self.host}/web_api/{command}"

    def login(self, domain: str | None = None) -> None:
        self._domain = domain
        payload: dict = {"api-key": self._api_key}
        if domain:
            payload["domain"] = domain
        resp = self._session.post(
            self._url("login"),
            json=payload,
            headers={"Content-Type": "application/json"},
            verify=self._verify_ssl,
            timeout=self._timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success", True):
            raise CPAPIError(data.get("message", "Login failed"), "login", data)
        self._sid = data["sid"]

    def logout(self) -> None:
        if not self._sid:
            return
        try:
            self._session.post(
                self._url("logout"),
                json={},
                headers={"Content-Type": "application/json", "X-chkp-sid": self._sid},
                verify=self._verify_ssl,
                timeout=self._timeout,
            )
        except Exception:
            pass
        finally:
            self._sid = None

    def call(self, command: str, payload: dict | None = None) -> dict:
        resp = self._session.post(
            self._url(command),
            json=payload or {},
            headers={
                "Content-Type": "application/json",
                "X-chkp-sid": self._sid or "",
            },
            verify=self._verify_ssl,
            timeout=self._timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success", True):
            raise CPAPIError(data.get("message", "API call failed"), command, data)
        return data

    def _fetch_all(self, command: str, extra: dict | None = None) -> list[dict]:
        results: list[dict] = []
        offset = 0
        limit = 500
        while True:
            data = self.call(command, {"limit": limit, "offset": offset, **(extra or {})})
            objects = data.get("objects", [])
            if not objects:
                break
            results.extend(objects)
            if len(results) >= data.get("total", len(results)):
                break
            offset += limit
        return results

    def get_domains(self) -> list[dict]:
        return self._fetch_all("show-domains")

    def get_api_version(self) -> dict:
        return self.call("show-api-versions")

    def get_gateways(self) -> list[dict]:
        return self._fetch_all("show-simple-gateways")

    def get_clusters(self) -> list[dict]:
        return self._fetch_all("show-simple-clusters")

    def get_packages(self) -> list[dict]:
        return self._fetch_all("show-packages")

    def get_access_rulebase(self, package: str) -> list[dict]:
        return self._fetch_all("show-access-rulebase", {"name": package})

    def __enter__(self) -> "CPClient":
        self.login(domain=self._domain)
        return self

    def __exit__(self, *args) -> None:
        self.logout()
