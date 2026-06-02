# edge_client/tests/test_sync.py
import json
from unittest.mock import MagicMock

import numpy as np
from edge_client.store import Store
from edge_client.sync import flush_queue, sync_faces


def _vec(v):
    a = np.asarray(v, dtype=np.float32)
    return (a / np.linalg.norm(a)).tolist()


def test_sync_upserts_and_builds_matcher(tmp_path):
    store = Store(str(tmp_path / "q.sqlite"))
    client = MagicMock()
    client.fetch_face_data.return_value = [
        {"attendance_device_id": "D1", "employee": "E1",
         "embedding": json.dumps(_vec([1, 0, 0])), "model_version": "buffalo_l",
         "modified": "2026-01-01 00:00:00"},
    ]
    matcher = sync_faces(client, store, model_version="buffalo_l")
    assert matcher.size == 1
    assert store.all_faces()[0]["attendance_device_id"] == "D1"
    client.fetch_face_data.assert_called_once_with(since=None)


def test_sync_keeps_last_good_on_failure(tmp_path):
    store = Store(str(tmp_path / "q.sqlite"))
    store.upsert_faces([{"attendance_device_id": "D1", "employee": "E1",
                         "embedding": json.dumps(_vec([1, 0, 0])),
                         "model_version": "buffalo_l", "modified": "2026-01-01 00:00:00"}])
    client = MagicMock()
    client.fetch_face_data.side_effect = RuntimeError("network down")
    matcher = sync_faces(client, store, model_version="buffalo_l")
    assert matcher.size == 1  # rebuilt from cache


def test_flush_posts_and_deletes_on_success(tmp_path):
    store = Store(str(tmp_path / "q.sqlite"))
    store.enqueue_checkin("D1", "2026-01-01 09:00:00", "edge-001")
    client = MagicMock()
    flush_queue(client, store)
    client.post_checkin.assert_called_once_with("D1", "2026-01-01 09:00:00", "edge-001")
    assert store.pending_checkins() == []


def test_flush_stops_on_failure(tmp_path):
    store = Store(str(tmp_path / "q.sqlite"))
    store.enqueue_checkin("D1", "2026-01-01 09:00:00", "edge-001")
    store.enqueue_checkin("D2", "2026-01-01 09:01:00", "edge-001")
    client = MagicMock()
    client.post_checkin.side_effect = RuntimeError("down")
    flush_queue(client, store)
    assert len(store.pending_checkins()) == 2  # nothing deleted
