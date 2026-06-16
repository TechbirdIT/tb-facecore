# edge_client/tests/test_engine.py
import importlib.util
from types import SimpleNamespace

import numpy as np
import pytest

from edge_client.engine import Engine

_HAS_DEEPFACE = importlib.util.find_spec("deepface") is not None


def _cfg():
    # SimpleNamespace is enough: Engine.__init__ only reads these + builds a hub
    # (no model load), and demography()/status() don't need the rest.
    return SimpleNamespace(
        frappe_url="x", api_key="k", api_secret="s", edge_id="edge-001",
        camera_source=0, cameras=None, db_path=":memory:",
        min_det_score=0.5, sync_interval=300,
    )


def test_demography_no_frame_yet():
    e = Engine(_cfg(), "buffalo_l")
    r = e.demography("edge-001")
    assert "error" in r and "no frame" in r["error"]


def test_demography_serializes_overlapping_calls(monkeypatch):
    # overlapping Analyze clicks must not run heavy deepface inference
    # concurrently — the engine holds _demo_lock around analyze()
    import threading

    from facecore import demography as real_demography

    e = Engine(_cfg(), "buffalo_l")
    e._raw["edge-001"] = np.zeros((8, 8, 3), np.uint8)

    concurrency = {"now": 0, "max": 0}
    gate = threading.Event()

    def fake_analyze(frame, actions=("emotion", "race")):
        concurrency["now"] += 1
        concurrency["max"] = max(concurrency["max"], concurrency["now"])
        gate.wait(0.5)  # hold the "model" so a racing caller would overlap if unlocked
        concurrency["now"] -= 1
        return [{"emotion": "happy", "race": "white"}]

    monkeypatch.setattr(real_demography, "analyze", fake_analyze)

    threads = [
        threading.Thread(target=e.demography, args=("edge-001",)) for _ in range(3)
    ]
    for t in threads:
        t.start()
    gate.set()
    for t in threads:
        t.join()

    assert concurrency["max"] == 1  # never more than one analyze at a time
    assert e._demo_warmed is True


@pytest.mark.skipif(_HAS_DEEPFACE, reason="deepface installed; missing-extra path N/A")
def test_demography_missing_extra_returns_install_hint():
    e = Engine(_cfg(), "buffalo_l")
    e._raw["edge-001"] = np.zeros((8, 8, 3), np.uint8)
    r = e.demography("edge-001")
    # deepface intentionally absent from the lean venv -> graceful error dict
    assert "error" in r and "facecore[demography]" in r["error"]


@pytest.mark.skipif(not _HAS_DEEPFACE, reason="needs the facecore[demography] extra")
def test_demography_with_extra_returns_json_safe_faces():
    e = Engine(_cfg(), "buffalo_l")
    from skimage import data

    e._raw["edge-001"] = data.astronaut()[:, :, ::-1]  # RGB->BGR, like a frame
    r = e.demography("edge-001")
    assert r["camera"] == "edge-001"
    assert "faces" in r and len(r["faces"]) >= 1
    import json

    json.dumps(r)  # must not raise (no numpy float32 leaking through)


def test_record_event_includes_age_gender():
    e = Engine(_cfg(), "buffalo_l")
    e._record_event(
        "edge-001", "HR-EMP-00001", "2026-01-01 09:00:00", 0.7, 0.9,
        age=30, gender="male",
    )
    ev = e.status()["events"][0]
    assert ev["age"] == 30 and ev["gender"] == "male"
    assert ev["name"] == "HR-EMP-00001" and ev["time"] == "09:00:00"


def test_status_lists_cameras_stopped():
    e = Engine(_cfg(), "buffalo_l")
    st = e.status()
    assert st["state"] == "stopped"
    assert [c["id"] for c in st["cameras"]] == ["edge-001"]
    assert st["cameras"][0]["live"] is False
