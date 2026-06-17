import httpx
import pytest
import respx

from ai_service.clients.deepface import DeepFaceClient, DeepFaceError

BASE = "http://sidecar:5005/api/v1"


@respx.mock
async def test_analyze_returns_results():
    respx.post(f"{BASE}/analyze").mock(
        return_value=httpx.Response(200, json={"results": [{"age": 31}]})
    )
    client = DeepFaceClient(base_url=BASE)
    out = await client.analyze(b"\xff\xd8jpeg", "face.jpg", "image/jpeg")
    assert out == [{"age": 31}]


@respx.mock
async def test_analyze_raises_on_sidecar_error():
    respx.post(f"{BASE}/analyze").mock(
        return_value=httpx.Response(400, json={"error": "no face"})
    )
    client = DeepFaceClient(base_url=BASE)
    with pytest.raises(DeepFaceError):
        await client.analyze(b"x", "f.jpg", "image/jpeg")


@respx.mock
async def test_analyze_raises_on_connect_error():
    respx.post(f"{BASE}/analyze").mock(side_effect=httpx.ConnectError("down"))
    client = DeepFaceClient(base_url=BASE)
    with pytest.raises(DeepFaceError):
        await client.analyze(b"x", "f.jpg", "image/jpeg")


@respx.mock
async def test_health_true_when_root_ok():
    respx.get(f"{BASE}/").mock(return_value=httpx.Response(200, text="ok"))
    client = DeepFaceClient(base_url=BASE)
    assert await client.health() is True
