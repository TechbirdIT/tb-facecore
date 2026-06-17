import pytest
from fastapi.testclient import TestClient

from ai_service.app import app
from ai_service.routes import analyze as analyze_route
from ai_service.clients.deepface import DeepFaceError


class _FakeClient:
    def __init__(self, result=None, error=None):
        self._result = result or []
        self._error = error

    async def analyze(self, image_bytes, filename, content_type):
        if self._error:
            raise self._error
        return self._result


def teardown_function():
    app.dependency_overrides.clear()


def test_analyze_returns_demographics():
    app.dependency_overrides[analyze_route.get_client] = lambda: _FakeClient(
        result=[{"age": 30, "dominant_gender": "Man"}]
    )
    client = TestClient(app)
    resp = client.post("/analyze", files={"file": ("f.jpg", b"x", "image/jpeg")})
    assert resp.status_code == 200
    assert resp.json() == {"results": [{"age": 30, "dominant_gender": "Man"}]}


def test_analyze_502_when_sidecar_down():
    app.dependency_overrides[analyze_route.get_client] = lambda: _FakeClient(
        error=DeepFaceError("unreachable")
    )
    client = TestClient(app)
    resp = client.post("/analyze", files={"file": ("f.jpg", b"x", "image/jpeg")})
    assert resp.status_code == 502
