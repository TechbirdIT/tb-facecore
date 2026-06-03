# facecore/tests/test_analyze_unit.py
import numpy as np

from facecore.analyzer import FaceAnalyzer
from facecore.models import DetectedFace


class _FakeFace:
    def __init__(self, bbox, det_score, embedding):
        self.bbox = np.array(bbox, dtype=np.float32)
        self.det_score = det_score
        self.normed_embedding = np.array(embedding, dtype=np.float32)


class _FakeApp:
    def __init__(self, faces):
        self._faces = faces

    def get(self, image):
        return self._faces


class _FakeLiveness:
    def __init__(self, value):
        self.value = value

    def score(self, image, bbox, scale=2.7):
        return self.value


def _analyzer(faces, liveness=0.9, det_thresh=0.5):
    a = FaceAnalyzer.__new__(FaceAnalyzer)
    a.device = "cpu"
    a.det_thresh = det_thresh
    a.liveness_thresh = 0.5
    a._app = _FakeApp(faces)
    a._liveness = _FakeLiveness(liveness)
    return a


def test_analyze_returns_detected_faces():
    emb = [0.1] * 512
    a = _analyzer([_FakeFace([0, 0, 10, 10], 0.95, emb)], liveness=0.8)
    out = a.analyze(np.zeros((100, 100, 3), dtype=np.uint8))
    assert len(out) == 1
    f = out[0]
    assert isinstance(f, DetectedFace)
    assert f.det_score == 0.95
    assert f.liveness_score == 0.8
    assert len(f.embedding) == 512
    assert f.bbox == [0.0, 0.0, 10.0, 10.0]


def test_analyze_filters_below_det_thresh():
    a = _analyzer([_FakeFace([0, 0, 10, 10], 0.3, [0.1] * 512)], det_thresh=0.5)
    assert a.analyze(np.zeros((100, 100, 3), dtype=np.uint8)) == []


def test_analyze_empty_when_no_faces():
    a = _analyzer([])
    assert a.analyze(np.zeros((100, 100, 3), dtype=np.uint8)) == []


def test_analyze_rejects_bad_image():
    a = _analyzer([])
    import pytest
    with pytest.raises(ValueError):
        a.analyze(np.zeros((100, 100), dtype=np.uint8))  # not 3-channel
