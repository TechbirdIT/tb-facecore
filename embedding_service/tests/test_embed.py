# embedding_service/tests/test_embed.py
import io

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from embedding_service.app import app, get_analyzer, get_settings
from embedding_service.config import Settings
from facecore.models import DetectedFace


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
    return DetectedFace(bbox=[0, 0, 10, 10], embedding=[0.1] * 512,
                        det_score=0.9, liveness_score=0.8)


def _client(faces, settings=None):
    settings = settings or Settings(secret=None, device="cpu", min_det_score=0.5)
    app.dependency_overrides[get_analyzer] = lambda: _Analyzer(faces)
    app.dependency_overrides[get_settings] = lambda: settings
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
    low = DetectedFace(bbox=[0, 0, 1, 1], embedding=[0.1] * 512,
                       det_score=0.2, liveness_score=0.5)
    client = _client([low])
    r = client.post("/embed", files={"file": ("x.png", _png_bytes(), "image/png")})
    assert r.status_code == 400


def test_secret_enforced_when_configured():
    client = _client([_face()], Settings(secret="s3cret", device="cpu", min_det_score=0.5))
    r = client.post("/embed", files={"file": ("x.png", _png_bytes(), "image/png")})
    assert r.status_code == 401
    r2 = client.post("/embed", files={"file": ("x.png", _png_bytes(), "image/png")},
                     headers={"X-Secret": "s3cret"})
    assert r2.status_code == 200
