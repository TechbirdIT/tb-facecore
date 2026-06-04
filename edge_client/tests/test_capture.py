# edge_client/tests/test_capture.py
import json
from datetime import datetime
from unittest.mock import MagicMock

import numpy as np
from facecore.models import DetectedFace

from edge_client.capture import process_frame
from edge_client.config import EdgeConfig
from edge_client.debounce import Debouncer
from edge_client.matcher import Matcher
from edge_client.store import Store


def _cfg():
    return EdgeConfig(
        frappe_url="x", site="s", api_key="k", api_secret="s", edge_id="edge-001",
        camera_source=0, sync_interval=300, threshold=0.45, liveness_threshold=0.6,
        min_det_score=0.5, debounce_minutes=2, db_path=":memory:",
    )


def _matcher():
    v = (np.array([1, 0, 0], dtype=np.float32)).tolist()
    return Matcher([{"attendance_device_id": "D1", "employee": "E1",
                     "embedding": json.dumps(v), "model_version": "buffalo_l"}],
                   model_version="buffalo_l")


def _analyzer_with(face):
    a = MagicMock()
    a.analyze.return_value = [face] if face else []
    return a


def _live_face():
    return DetectedFace(bbox=[0, 0, 1, 1], embedding=[1.0, 0.0, 0.0],
                        det_score=0.9, liveness_score=0.9)


def test_match_posts_event(tmp_path):
    client = MagicMock()
    store = Store(str(tmp_path / "q.sqlite"))
    process_frame(np.zeros((4, 4, 3), np.uint8), _analyzer_with(_live_face()),
                  _matcher(), Debouncer(2), client, store, _cfg(),
                  now=datetime(2026, 1, 1, 9, 0, 0))
    client.post_event.assert_called_once()
    args = client.post_event.call_args[0]
    assert args[0] == "edge-001"
    assert args[1] == "D1"
    assert store.pending_events() == []


def test_spoof_below_liveness_no_event(tmp_path):
    spoof = DetectedFace(bbox=[0, 0, 1, 1], embedding=[1.0, 0.0, 0.0],
                         det_score=0.9, liveness_score=0.1)
    client = MagicMock()
    store = Store(str(tmp_path / "q.sqlite"))
    process_frame(np.zeros((4, 4, 3), np.uint8), _analyzer_with(spoof),
                  _matcher(), Debouncer(2), client, store, _cfg(),
                  now=datetime(2026, 1, 1, 9, 0, 0))
    client.post_event.assert_not_called()


def test_post_failure_enqueues(tmp_path):
    client = MagicMock()
    client.post_event.side_effect = RuntimeError("frappe down")
    store = Store(str(tmp_path / "q.sqlite"))
    process_frame(np.zeros((4, 4, 3), np.uint8), _analyzer_with(_live_face()),
                  _matcher(), Debouncer(2), client, store, _cfg(),
                  now=datetime(2026, 1, 1, 9, 0, 0))
    assert len(store.pending_events()) == 1


def test_debounced_second_punch_skipped(tmp_path):
    client = MagicMock()
    store = Store(str(tmp_path / "q.sqlite"))
    deb = Debouncer(2)
    args = (_analyzer_with(_live_face()), _matcher(), deb, client, store, _cfg())
    frame = np.zeros((4, 4, 3), np.uint8)
    process_frame(frame, *args, now=datetime(2026, 1, 1, 9, 0, 0))
    process_frame(frame, *args, now=datetime(2026, 1, 1, 9, 0, 30))
    assert client.post_event.call_count == 1
