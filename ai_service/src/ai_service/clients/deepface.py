"""Async HTTP client for the deepface sidecar (ekansh-tb/deepface API)."""

from __future__ import annotations

import httpx


class DeepFaceError(RuntimeError):
    """Raised when the deepface sidecar errors or is unreachable."""


class DeepFaceClient:
    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def analyze(
        self, image_bytes: bytes, filename: str, content_type: str
    ) -> list[dict]:
        files = {"img": (filename, image_bytes, content_type)}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(f"{self._base_url}/analyze", files=files)
        except httpx.HTTPError as err:
            raise DeepFaceError(f"sidecar unreachable: {err}") from err

        if resp.status_code != 200:
            detail = _safe_error(resp)
            raise DeepFaceError(f"sidecar returned {resp.status_code}: {detail}")
        results: list[dict] = resp.json().get("results", [])
        return results

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(f"{self._base_url}/")
            return resp.status_code == 200
        except httpx.HTTPError:
            return False


def _safe_error(resp: httpx.Response) -> str:
    try:
        return str(resp.json().get("error", resp.text))
    except Exception:
        return resp.text
