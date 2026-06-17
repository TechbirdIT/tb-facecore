import io

import numpy as np
from fastapi.testclient import TestClient
from PIL import Image

from ai_service.app import app
from ai_service.clients.deepface import DeepFaceError
from ai_service.config import Settings
from ai_service.routes.analyze import MAX_UPLOAD_BYTES, _get_settings, get_client


def _png_bytes():
    buf = io.BytesIO()
    Image.fromarray(np.zeros((40, 40, 3), dtype=np.uint8)).save(buf, format="PNG")
    return buf.getvalue()


class _FakeClient:
    def __init__(self, result=None, error=None):
        self._result = result or []
        self._error = error

    async def analyze(self, image_bytes, filename, content_type):
        if self._error:
            raise self._error
        return self._result


def _client(result=None, error=None, settings=None):
    settings = settings or Settings(secret=None, device="cpu", min_det_score=0.5)
    app.dependency_overrides[get_client] = lambda: _FakeClient(result, error)
    app.dependency_overrides[_get_settings] = lambda: settings
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def test_analyze_returns_demographics():
    client = _client(result=[{"age": 30, "dominant_gender": "Man"}])
    r = client.post("/analyze", files={"file": ("f.png", _png_bytes(), "image/png")})
    assert r.status_code == 200
    assert r.json() == {"results": [{"age": 30, "dominant_gender": "Man"}]}


def test_analyze_502_when_sidecar_down():
    client = _client(error=DeepFaceError("unreachable"))
    r = client.post("/analyze", files={"file": ("f.png", _png_bytes(), "image/png")})
    assert r.status_code == 502


def test_non_image_bytes_is_422():
    client = _client(result=[{"age": 30}])
    r = client.post("/analyze", files={"file": ("f.png", b"not an image", "image/png")})
    assert r.status_code == 422


def test_oversized_upload_is_413():
    client = _client(result=[{"age": 30}])
    big = b"\x00" * (MAX_UPLOAD_BYTES + 1)
    r = client.post("/analyze", files={"file": ("big.png", big, "image/png")})
    assert r.status_code == 413


def test_secret_enforced_when_configured():
    client = _client(
        result=[{"age": 30}],
        settings=Settings(secret="s3cret", device="cpu", min_det_score=0.5),
    )
    r = client.post("/analyze", files={"file": ("f.png", _png_bytes(), "image/png")})
    assert r.status_code == 401
    r2 = client.post(
        "/analyze",
        files={"file": ("f.png", _png_bytes(), "image/png")},
        headers={"X-Secret": "s3cret"},
    )
    assert r2.status_code == 200
