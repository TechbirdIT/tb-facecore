# edge_client/tests/test_server.py
import yaml

from edge_client.config import load_config
from edge_client.engine import Engine
from edge_client.server import _coerce_source, apply_console_config

BASE = {
    "frappe": {"url": "http://x", "site": "s", "api_key": "k", "api_secret": "sec"},
    "edge": {"id": "edge-001", "camera_source": "rtsp://192.168.1.68:8554", "sync_interval": 300},
    "matching": {"threshold": 0.45, "liveness_threshold": 0.6, "min_det_score": 0.5, "debounce_minutes": 2},
    "offline": {"db_path": ":memory:"},
}


def _write(path, extra=None):
    raw = {**BASE, **(extra or {})}
    path.write_text(yaml.safe_dump(raw))
    return path


def test_coerce_source_webcam_index_and_url():
    assert _coerce_source("0") == 0
    assert _coerce_source(" 1 ") == 1
    assert _coerce_source("rtsp://cam/1") == "rtsp://cam/1"
    assert _coerce_source(0) == 0


def test_apply_rewrites_yaml_and_hot_reloads_engine(tmp_path):
    cfgp = _write(tmp_path / "config.yaml")
    engine = Engine(load_config(str(cfgp)), "buffalo_l")
    assert engine._cameras == [("edge-001", "rtsp://192.168.1.68:8554")]

    body = {
        "cameras": [
            {"id": "edge-001", "source": "rtsp://192.168.1.65:8554", "area": "Floor 2"},
            {"id": "edge-002", "source": "0", "area": "Lab"},
        ],
        "matching": {"threshold": 0.5},
        "rtsp": {"rtsp_transport": "udp"},
    }
    state = apply_console_config(cfgp, body, engine)

    assert state == "stopped"  # was not running, so it stays stopped
    assert engine._cameras == [
        ("edge-001", "rtsp://192.168.1.65:8554"),
        ("edge-002", 0),  # webcam string coerced to int
    ]
    reloaded = load_config(str(cfgp))
    assert reloaded.camera_source == "rtsp://192.168.1.65:8554"
    assert reloaded.threshold == 0.5
    assert reloaded.rtsp_transport == "udp"
    # fields the console didn't send must be preserved
    assert reloaded.liveness_threshold == 0.6
    assert reloaded.debounce_minutes == 2


def test_apply_preserves_unmanaged_sections(tmp_path):
    cfgp = _write(tmp_path / "c.yaml", {"preview": {"enabled": True, "port": 9101}})
    engine = Engine(load_config(str(cfgp)), "buffalo_l")
    apply_console_config(cfgp, {"cameras": [{"id": "e1", "source": "rtsp://a/1"}]}, engine)
    raw = yaml.safe_load(cfgp.read_text())
    assert raw["preview"] == {"enabled": True, "port": 9101}  # untouched


def test_apply_ignores_incomplete_cameras(tmp_path):
    cfgp = _write(tmp_path / "c.yaml")
    engine = Engine(load_config(str(cfgp)), "buffalo_l")
    # camera with no source is dropped; with no valid cameras, edge cameras unset
    apply_console_config(cfgp, {"cameras": [{"id": "x", "source": ""}]}, engine)
    raw = yaml.safe_load(cfgp.read_text())
    assert "cameras" not in raw["edge"]  # nothing valid -> not written
