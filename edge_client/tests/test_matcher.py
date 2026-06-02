# edge_client/tests/test_matcher.py
import json

import numpy as np
from edge_client.matcher import Matcher


def _row(device_id, vec, model="buffalo_l"):
    v = np.asarray(vec, dtype=np.float32)
    v = v / np.linalg.norm(v)
    return {"attendance_device_id": device_id, "employee": device_id,
            "embedding": json.dumps(v.tolist()), "model_version": model}


def test_matches_nearest_above_threshold():
    rows = [_row("D1", [1, 0, 0]), _row("D2", [0, 1, 0])]
    m = Matcher(rows, model_version="buffalo_l")
    assert m.match([1, 0, 0], threshold=0.45) == ("D1", 1.0)


def test_below_threshold_returns_none():
    rows = [_row("D1", [1, 0, 0])]
    m = Matcher(rows, model_version="buffalo_l")
    assert m.match([0, 1, 0], threshold=0.45) is None


def test_filters_foreign_model_version():
    rows = [_row("D1", [1, 0, 0], model="other_model")]
    m = Matcher(rows, model_version="buffalo_l")
    assert m.size == 0
    assert m.match([1, 0, 0], threshold=0.45) is None


def test_empty_matcher_returns_none():
    m = Matcher([], model_version="buffalo_l")
    assert m.match([1, 0, 0], threshold=0.45) is None
