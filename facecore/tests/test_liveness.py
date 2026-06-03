# facecore/tests/test_liveness.py
import numpy as np

from facecore.liveness import _expand_bbox, _softmax


def test_softmax_sums_to_one():
    out = _softmax(np.array([2.0, 1.0, 0.1], dtype=np.float32))
    assert abs(float(out.sum()) - 1.0) < 1e-6
    assert out.argmax() == 0


def test_expand_bbox_grows_and_clamps():
    # bbox well inside a 200x200 image, scale 2.0 doubles the box around its center.
    x1, y1, x2, y2 = _expand_bbox([80, 80, 120, 120], scale=2.0, w=200, h=200)
    assert x1 < 80 and y1 < 80 and x2 > 120 and y2 > 120
    assert 0 <= x1 and 0 <= y1 and x2 <= 200 and y2 <= 200


def test_expand_bbox_clamps_at_edges():
    x1, y1, x2, y2 = _expand_bbox([0, 0, 50, 50], scale=4.0, w=100, h=100)
    assert x1 == 0 and y1 == 0
    assert x2 <= 100 and y2 <= 100
