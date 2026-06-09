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


# --- detect() / embed() / liveness() split ---


class _FakeDet:
    def __init__(self, bboxes, kpss):
        self.bboxes, self.kpss = bboxes, kpss

    def detect(self, img, max_num=0, metric="default"):
        return self.bboxes, self.kpss


class _FakeRec:
    def __init__(self):
        self.called_with = None

    def get(self, img, face):
        self.called_with = face
        face.embedding = np.array([0.5] * 512, dtype=np.float32)


class _FakeAppDM:
    def __init__(self, bboxes, kpss):
        self.det_model = _FakeDet(bboxes, kpss)
        self.models = {"recognition": _FakeRec()}


def _analyzer_dm(bboxes, kpss, det_thresh=0.5, liveness=0.8):
    a = FaceAnalyzer.__new__(FaceAnalyzer)
    a.det_thresh = det_thresh
    a.liveness_thresh = 0.5
    a._app = _FakeAppDM(bboxes, kpss)
    a._liveness = _FakeLiveness(liveness)
    return a


def test_detect_returns_faceboxes_and_filters_below_thresh():
    from facecore.models import FaceBox

    bboxes = np.array([[0, 0, 10, 10, 0.9], [0, 0, 5, 5, 0.3]], dtype=np.float32)
    kpss = np.zeros((2, 5, 2), dtype=np.float32)
    out = _analyzer_dm(bboxes, kpss).detect(np.zeros((100, 100, 3), dtype=np.uint8))
    assert len(out) == 1  # second box below det_thresh is dropped
    assert isinstance(out[0], FaceBox)
    assert out[0].det_score == 0.9
    assert out[0].bbox == [0.0, 0.0, 10.0, 10.0]
    assert out[0].kps is not None


def test_embed_runs_recognition_and_returns_512():
    from facecore.models import FaceBox

    a = _analyzer_dm(np.zeros((0, 5), np.float32), np.zeros((0, 5, 2), np.float32))
    fb = FaceBox(bbox=[0, 0, 10, 10], det_score=0.9, kps=np.zeros((5, 2), np.float32))
    emb = a.embed(np.zeros((100, 100, 3), dtype=np.uint8), fb)
    assert len(emb) == 512
    assert a._app.models["recognition"].called_with is not None


def test_embed_requires_kps():
    import pytest

    from facecore.models import FaceBox

    a = _analyzer_dm(np.zeros((0, 5), np.float32), None)
    fb = FaceBox(bbox=[0, 0, 10, 10], det_score=0.9, kps=None)
    with pytest.raises(ValueError):
        a.embed(np.zeros((100, 100, 3), dtype=np.uint8), fb)


def test_liveness_delegates_to_detector():
    a = _analyzer_dm(np.zeros((0, 5), np.float32), None, liveness=0.73)
    assert a.liveness(np.zeros((100, 100, 3), dtype=np.uint8), [0, 0, 10, 10]) == 0.73
