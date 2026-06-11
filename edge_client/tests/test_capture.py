# edge_client/tests/test_capture.py
import json
from datetime import datetime
from unittest.mock import MagicMock

import numpy as np
from facecore.models import FaceBox

from edge_client.capture import process_frame
from edge_client.config import EdgeConfig
from edge_client.debounce import Debouncer
from edge_client.matcher import Matcher
from edge_client.store import Store
from edge_client.tracker import Tracker


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


def _box(bbox=(0, 0, 10, 10)):
    return FaceBox(bbox=list(bbox), det_score=0.9, kps=[[0, 0]] * 5)


def _analyzer(box=True, liveness=0.9, embedding=(1.0, 0.0, 0.0)):
    """Mock FaceAnalyzer exposing detect()/liveness()/embed()."""
    a = MagicMock()
    a.detect.return_value = [_box()] if box else []
    a.liveness.return_value = liveness
    a.embed.return_value = list(embedding)
    return a


def test_match_posts_event(tmp_path):
    client = MagicMock()
    store = Store(str(tmp_path / "q.sqlite"))
    process_frame(np.zeros((4, 4, 3), np.uint8), _analyzer(),
                  _matcher(), Tracker(), Debouncer(2), client, store, _cfg(),
                  now=datetime(2026, 1, 1, 9, 0, 0))
    client.post_event.assert_called_once()
    args = client.post_event.call_args[0]
    assert args[0] == "edge-001"
    assert args[1] == "D1"
    assert store.pending_events() == []


def test_spoof_below_liveness_no_event(tmp_path):
    client = MagicMock()
    store = Store(str(tmp_path / "q.sqlite"))
    process_frame(np.zeros((4, 4, 3), np.uint8), _analyzer(liveness=0.1),
                  _matcher(), Tracker(), Debouncer(2), client, store, _cfg(),
                  now=datetime(2026, 1, 1, 9, 0, 0))
    client.post_event.assert_not_called()


def test_no_face_no_embed(tmp_path):
    """No detections → no embedding work, no event."""
    client = MagicMock()
    store = Store(str(tmp_path / "q.sqlite"))
    a = _analyzer(box=False)
    process_frame(np.zeros((4, 4, 3), np.uint8), a, _matcher(), Tracker(),
                  Debouncer(2), client, store, _cfg(), now=datetime(2026, 1, 1, 9, 0))
    a.embed.assert_not_called()
    client.post_event.assert_not_called()


def test_post_failure_enqueues(tmp_path):
    client = MagicMock()
    client.post_event.side_effect = RuntimeError("frappe down")
    store = Store(str(tmp_path / "q.sqlite"))
    process_frame(np.zeros((4, 4, 3), np.uint8), _analyzer(),
                  _matcher(), Tracker(), Debouncer(2), client, store, _cfg(),
                  now=datetime(2026, 1, 1, 9, 0, 0))
    assert len(store.pending_events()) == 1


def test_embed_once_per_track_within_reverify_window(tmp_path):
    """Same face across frames is embedded once until the re-verify window."""
    client = MagicMock()
    store = Store(str(tmp_path / "q.sqlite"))
    a = _analyzer()
    tracker, deb, cfg = Tracker(), Debouncer(2), _cfg()
    frame = np.zeros((4, 4, 3), np.uint8)
    # 3 frames seconds apart, well under reverify_seconds (30)
    process_frame(frame, a, _matcher(), tracker, deb, client, store, cfg,
                  now=datetime(2026, 1, 1, 9, 0, 0))
    process_frame(frame, a, _matcher(), tracker, deb, client, store, cfg,
                  now=datetime(2026, 1, 1, 9, 0, 5))
    process_frame(frame, a, _matcher(), tracker, deb, client, store, cfg,
                  now=datetime(2026, 1, 1, 9, 0, 10))
    # embedded once (track recognized once); debounce keeps it to one event
    assert a.embed.call_count == 1
    assert client.post_event.call_count == 1


def test_reverify_after_window_reembeds(tmp_path):
    client = MagicMock()
    store = Store(str(tmp_path / "q.sqlite"))
    a = _analyzer()
    tracker, cfg = Tracker(), _cfg()
    frame = np.zeros((4, 4, 3), np.uint8)
    process_frame(frame, a, _matcher(), tracker, Debouncer(0), client, store, cfg,
                  now=datetime(2026, 1, 1, 9, 0, 0))
    # > reverify_seconds (30) later → re-embed
    process_frame(frame, a, _matcher(), tracker, Debouncer(0), client, store, cfg,
                  now=datetime(2026, 1, 1, 9, 1, 0))
    assert a.embed.call_count == 2


def test_distinct_faces_get_distinct_tracks(tmp_path):
    """Two far-apart boxes → two tracks → two embeds in one frame."""
    client = MagicMock()
    store = Store(str(tmp_path / "q.sqlite"))
    a = MagicMock()
    a.detect.return_value = [_box((0, 0, 10, 10)), _box((100, 100, 120, 120))]
    a.liveness.return_value = 0.9
    a.embed.return_value = [1.0, 0.0, 0.0]
    process_frame(np.zeros((4, 4, 3), np.uint8), a, _matcher(), Tracker(),
                  Debouncer(2), client, store, _cfg(), now=datetime(2026, 1, 1, 9, 0))
    assert a.embed.call_count == 2


def test_failed_attempt_retries_next_frame_not_after_reverify(tmp_path):
    """A bad first glimpse (low liveness) must retry immediately, not freeze the
    unidentified track for reverify_seconds."""
    client = MagicMock()
    store = Store(str(tmp_path / "q.sqlite"))
    a = MagicMock()
    a.detect.return_value = [_box()]
    a.embed.return_value = [1.0, 0.0, 0.0]
    a.liveness.side_effect = [0.1, 0.9]  # frame 1 fails liveness, frame 2 passes
    tracker, cfg = Tracker(), _cfg()
    frame = np.zeros((4, 4, 3), np.uint8)

    process_frame(frame, a, _matcher(), tracker, Debouncer(2), client, store, cfg,
                  now=datetime(2026, 1, 1, 9, 0, 0))
    assert client.post_event.call_count == 0  # rejected on frame 1
    # only 1s later — far inside reverify_seconds(30); old logic would freeze it
    process_frame(frame, a, _matcher(), tracker, Debouncer(2), client, store, cfg,
                  now=datetime(2026, 1, 1, 9, 0, 1))
    assert a.liveness.call_count == 2         # retried, not frozen
    assert client.post_event.call_count == 1  # acquired + posted
