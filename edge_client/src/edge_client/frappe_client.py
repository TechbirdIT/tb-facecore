"""HTTP client for the Frappe sync, event, and heartbeat endpoints."""

from __future__ import annotations

import requests

_SYNC_METHOD = "face_attendance.api.get_face_data"
_EVENT_METHOD = "face_attendance.api.post_event"
_HEARTBEAT_METHOD = "face_attendance.api.heartbeat"
_TIMEOUT = 10


class CheckinRejectedError(RuntimeError):
    """Check-in permanently rejected by the server (4xx validation)."""


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

    def post_event(
        self,
        edge_id: str,
        attendance_device_id: str,
        timestamp: str,
        similarity: float,
        liveness: float,
    ) -> None:
        data = {
            "device_id": edge_id,
            "attendance_device_id": attendance_device_id,
            "event_time": timestamp,
            "similarity": similarity,
            "liveness": liveness,
        }
        resp = requests.post(
            f"{self.base}/api/method/{_EVENT_METHOD}",
            data=data,
            headers=self.headers,
            timeout=_TIMEOUT,
        )
        if 400 <= resp.status_code < 500:
            raise CheckinRejectedError(
                f"event rejected: {resp.status_code} {resp.text}"
            )
        if resp.status_code != 200:
            raise RuntimeError(f"event failed: {resp.status_code} {resp.text}")

    def heartbeat(self, edge_id: str, app_version: str | None = None) -> None:
        data = {"device_id": edge_id}
        if app_version:
            data["app_version"] = app_version
        resp = requests.post(
            f"{self.base}/api/method/{_HEARTBEAT_METHOD}",
            data=data,
            headers=self.headers,
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"heartbeat failed: {resp.status_code}")
