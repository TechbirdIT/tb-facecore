"""Stub routes return 501 Not Implemented until built out."""

from fastapi.testclient import TestClient
from ai_service.app import app

client = TestClient(app)


def test_verify_id_stub_returns_501():
    r = client.post("/verify-id", json={})
    assert r.status_code == 501
    assert r.json()["detail"] == "not implemented"


