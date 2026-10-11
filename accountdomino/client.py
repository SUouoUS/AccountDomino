"""Streamlit 이 사용하는 API 클라이언트. 로컬 모의 서버 외에는 요청하지 않는다."""
from __future__ import annotations

from urllib.parse import urlparse

import httpx

from . import config


class ExternalRequestBlocked(ValueError):
    pass


class DominoClient:
    def __init__(self, base_url: str = config.API_BASE_URL, timeout: float = 5.0):
        host = urlparse(base_url).hostname
        if host not in config.ALLOWED_API_HOSTS:
            raise ExternalRequestBlocked(f"로컬 모의 서버만 허용됩니다: {base_url}")
        self._http = httpx.Client(base_url=base_url, timeout=timeout)

    def _request(self, method: str, path: str, **kwargs):
        resp = self._http.request(method, path, **kwargs)
        resp.raise_for_status()
        return resp.json()

    def health(self) -> bool:
        try:
            return self._request("GET", "/health").get("status") == "ok"
        except httpx.HTTPError:
            return False

    def services(self) -> list[dict]:
        return self._request("GET", "/services")

    def scenarios(self) -> list[dict]:
        return self._request("GET", "/scenarios")

    def load_scenario(self, scenario_id: str, count: int = config.DEFAULT_ACCOUNT_COUNT) -> dict:
        return self._request("POST", f"/scenarios/{scenario_id}/load", params={"count": count})

    def accounts(self, profile: str) -> list[dict]:
        return self._request("GET", f"/profiles/{profile}/accounts")

    def save_accounts(self, profile: str, accounts: list[dict]) -> dict:
        return self._request("PUT", f"/profiles/{profile}/accounts", json=accounts)

    def create_run(self, profile: str, leaked_service_id: str, leaked_username: str,
                   scenario: str | None = None) -> int:
        body = {"profile": profile, "leaked_service_id": leaked_service_id,
                "leaked_username": leaked_username, "scenario": scenario}
        return self._request("POST", "/runs", json=body)["run_id"]

    def login(self, service_id: str, profile: str, username: str, password: str,
              run_id: int | None = None) -> dict:
        body = {"profile": profile, "username": username, "password": password, "run_id": run_id}
        return self._request("POST", f"/services/{service_id}/login", json=body)

    def run_logs(self, run_id: int) -> list[dict]:
        return self._request("GET", f"/runs/{run_id}/logs")

    def logs(self, limit: int = 100) -> list[dict]:
        return self._request("GET", "/logs", params={"limit": limit})
