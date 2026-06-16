# edge_client/tests/test_preview.py
import numpy as np

from edge_client.preview import FrameHub, annotate, encode_jpeg
from edge_client.tracker import Track


def _track(**kw):
    t = Track(id=1, bbox=[10, 10, 40, 50])
    for k, v in kw.items():
        setattr(t, k, v)
    return t


def test_annotate_returns_copy_same_shape():
    frame = np.zeros((80, 80, 3), np.uint8)
    t = _track(
        identity=("HR-EMP-00001", 0.74), last_liveness=0.9,
        est_age=33, est_gender="female",
    )
    out = annotate(frame, [t])
    assert out.shape == frame.shape
    assert out is not frame  # must not mutate the caller's frame


def test_annotate_handles_spoof_and_unknown_and_demographics():
    frame = np.zeros((80, 80, 3), np.uint8)
    tracks = [
        _track(spoof=True, last_liveness=0.2),
        _track(first_attempt=object(), est_age=25, est_gender="male"),  # unknown + demo
    ]
    out = annotate(frame, tracks)  # must not raise
    assert out.shape == frame.shape


def test_encode_jpeg_roundtrip():
    frame = (np.random.rand(40, 40, 3) * 255).astype(np.uint8)
    j = encode_jpeg(frame, quality=70, scale=0.5)
    assert j is not None and j[:2] == b"\xff\xd8"  # valid JPEG magic


def test_framehub_publish_latest_and_freshness():
    h = FrameHub()
    assert h.freshness("c") is None
    h.publish("c", b"jpeg")
    assert h.latest("c") == b"jpeg"
    fresh = h.freshness("c")
    assert fresh is not None and 0.0 <= fresh < 1.0
    assert "c" in h.camera_ids()
