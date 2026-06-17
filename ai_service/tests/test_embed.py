import io

import numpy as np
from facecore.models import DetectedFace
from fastapi.testclient import TestClient
from PIL import Image

from ai_service.app import app
from ai_service.config import Settings
from ai_service.routes.embed import MAX_UPLOAD_BYTES, _get_settings, get_analyzer


def _png_bytes():
    buf = io.BytesIO()
    Image.fromarray(np.zeros((40, 40, 3), dtype=np.uint8)).save(buf, format="PNG")
    return buf.getvalue()


class _Analyzer:
    def __init__(self, faces):
        self._faces = faces

    def analyze(self, image):
        return self._faces


def _face():
    return DetectedFace(
        bbox=[0, 0, 10, 10], embedding=[0.1] * 512,
        det_score=0.9, liveness_score=0.8,
    )


def _client(faces, settings=None):
    settings = settings or Settings(secret=None, device="cpu", min_det_score=0.5)
    app.dependency_overrides[get_analyzer] = lambda: _Analyzer(faces)
    app.dependency_overrides[_get_settings] = lambda: settings
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def test_single_face_returns_embedding():
    client = _client([_face()])
    r = client.post("/embed", files={"file": ("x.png", _png_bytes(), "image/png")})
    assert r.status_code == 200
    body = r.json()
    assert len(body["embedding"]) == 512
    assert body["det_score"] == 0.9
    assert body["model_version"] == "buffalo_l"


def test_no_face_is_400():
    client = _client([])
    r = client.post("/embed", files={"file": ("x.png", _png_bytes(), "image/png")})
    assert r.status_code == 400


def test_multiple_faces_is_400():
    client = _client([_face(), _face()])
    r = client.post("/embed", files={"file": ("x.png", _png_bytes(), "image/png")})
    assert r.status_code == 400


def test_low_det_score_is_400():
    low = DetectedFace(
        bbox=[0, 0, 1, 1], embedding=[0.1] * 512,
        det_score=0.2, liveness_score=0.5,
    )
    client = _client([low])
    r = client.post("/embed", files={"file": ("x.png", _png_bytes(), "image/png")})
    assert r.status_code == 400


def test_oversized_upload_is_413():
    client = _client([_face()])
    big = b"\x00" * (MAX_UPLOAD_BYTES + 1)
    r = client.post("/embed", files={"file": ("big.png", big, "image/png")})
    assert r.status_code == 413


def test_non_image_bytes_is_422():
    client = _client([_face()])
    r = client.post("/embed", files={"file": ("x.png", b"not an image", "image/png")})
    assert r.status_code == 422


def test_secret_enforced_when_configured():
    client = _client(
        [_face()], Settings(secret="s3cret", device="cpu", min_det_score=0.5)
    )
    r = client.post("/embed", files={"file": ("x.png", _png_bytes(), "image/png")})
    assert r.status_code == 401
    r2 = client.post(
        "/embed",
        files={"file": ("x.png", _png_bytes(), "image/png")},
        headers={"X-Secret": "s3cret"},
    )
    assert r2.status_code == 200
