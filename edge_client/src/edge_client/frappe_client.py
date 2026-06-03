"""HTTP client for the Frappe sync endpoint and native check-in."""

from __future__ import annotations

import requests

_SYNC_METHOD = "face_attendance.api.get_face_data"
_CHECKIN_METHOD = (
    "hrms.hr.doctype.employee_checkin.employee_checkin.add_log_based_on_employee_field"
)
_TIMEOUT = 10


class FrappeClient:
    def __init__(self, url: str, api_key: str, api_secret: str) -> None:
        # Token auth + full base URL identify the site; no `site` arg needed.
        self.base = url.rstrip("/")
        self.headers = {"Authorization": f"token {api_key}:{api_secret}"}

    def fetch_face_data(self, since: str | None = None) -> list[dict]:
        params = {}
        if since:
            params["since"] = since
        resp = requests.get(
            f"{self.base}/api/method/{_SYNC_METHOD}",
            params=params,
            headers=self.headers,
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"sync failed: {resp.status_code} {resp.text}")
        rows: list[dict] = resp.json()["message"]
        return rows

    def post_checkin(self, device_id: str, timestamp: str, edge_id: str) -> None:
        # log_type omitted so Frappe derives IN/OUT from shift rules.
        data = {
            "employee_field_value": device_id,
            "timestamp": timestamp,
            "device_id": edge_id,
        }
        resp = requests.post(
            f"{self.base}/api/method/{_CHECKIN_METHOD}",
            data=data,
            headers=self.headers,
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"checkin failed: {resp.status_code} {resp.text}")
