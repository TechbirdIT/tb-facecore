from fastapi.testclient import TestClient

from ai_service.app import app
from ai_service.routes.analyze import get_client


class _FakeClient:
    def __init__(self, healthy: bool):
        self._healthy = healthy

    async def health(self) -> bool:
        return self._healthy


def teardown_function():
    app.dependency_overrides.clear()


def test_health_returns_ok_and_deepface_up():
    app.dependency_overrides[get_client] = lambda: _FakeClient(healthy=True)
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["deepface"] == "up"


def test_health_reports_deepface_down_without_failing():
    app.dependency_overrides[get_client] = lambda: _FakeClient(healthy=False)
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["deepface"] == "down"
