# edge_client/tests/test_store.py
from edge_client.store import Store


def test_upsert_and_read_faces(tmp_path):
    store = Store(str(tmp_path / "q.sqlite"))
    store.upsert_faces([
        {"attendance_device_id": "D1", "employee": "EMP-1",
         "embedding": "[0.1]", "model_version": "buffalo_l", "modified": "2026-01-01 00:00:00"},
    ])
    faces = store.all_faces()
    assert len(faces) == 1 and faces[0]["attendance_device_id"] == "D1"


def test_upsert_replaces_on_same_device_id(tmp_path):
    store = Store(str(tmp_path / "q.sqlite"))
    row = {"attendance_device_id": "D1", "employee": "EMP-1",
           "embedding": "[0.1]", "model_version": "buffalo_l", "modified": "2026-01-01 00:00:00"}
    store.upsert_faces([row])
    row2 = dict(row, embedding="[0.2]", modified="2026-02-01 00:00:00")
    store.upsert_faces([row2])
    faces = store.all_faces()
    assert len(faces) == 1 and faces[0]["embedding"] == "[0.2]"


def test_max_modified(tmp_path):
    store = Store(str(tmp_path / "q.sqlite"))
    store.upsert_faces([
        {"attendance_device_id": "D1", "employee": "E1", "embedding": "[]",
         "model_version": "v", "modified": "2026-01-01 00:00:00"},
        {"attendance_device_id": "D2", "employee": "E2", "embedding": "[]",
         "model_version": "v", "modified": "2026-03-01 00:00:00"},
    ])
    assert store.max_modified() == "2026-03-01 00:00:00"


def test_checkin_queue_roundtrip(tmp_path):
    store = Store(str(tmp_path / "q.sqlite"))
    store.enqueue_checkin("D1", "2026-01-01 09:00:00", "edge-001")
    pending = store.pending_checkins()
    assert len(pending) == 1
    store.delete_checkin(pending[0]["id"])
    assert store.pending_checkins() == []
