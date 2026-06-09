# edge_client/tests/test_config.py
import textwrap

import pytest

from edge_client.config import EdgeConfig, load_config


def _write(tmp_path, text):
    p = tmp_path / "config.yaml"
    p.write_text(textwrap.dedent(text))
    return str(p)


def test_load_valid_config(tmp_path):
    path = _write(
        tmp_path,
        """
        frappe:
          url: http://localhost:8000
          site: site1.localhost
          api_key: k
          api_secret: s
        edge:
          id: edge-001
          camera_index: 0
          sync_interval: 300
        matching:
          threshold: 0.45
          liveness_threshold: 0.6
          min_det_score: 0.5
          debounce_minutes: 2
        offline:
          db_path: /tmp/queue.sqlite
    """,
    )
    cfg = load_config(path)
    assert isinstance(cfg, EdgeConfig)
    assert cfg.frappe_url == "http://localhost:8000"
    assert cfg.edge_id == "edge-001"
    assert cfg.threshold == 0.45
    assert cfg.camera_source == 0
    assert cfg.db_path == "/tmp/queue.sqlite"


def test_camera_source_rtsp_url(tmp_path):
    path = _write(
        tmp_path,
        """
        frappe:
          url: http://localhost:8000
          site: site1.localhost
          api_key: k
          api_secret: s
        edge:
          id: edge-001
          camera_source: rtsp://admin:pass@192.168.1.64:554/Streaming/Channels/102
          sync_interval: 300
        matching:
          threshold: 0.45
          liveness_threshold: 0.6
          min_det_score: 0.5
          debounce_minutes: 2
        offline:
          db_path: /tmp/queue.sqlite
    """,
    )
    cfg = load_config(path)
    assert cfg.camera_source == (
        "rtsp://admin:pass@192.168.1.64:554/Streaming/Channels/102"
    )


def test_legacy_camera_index_still_works(tmp_path):
    path = _write(
        tmp_path,
        """
        frappe:
          url: http://localhost:8000
          site: site1.localhost
          api_key: k
          api_secret: s
        edge:
          id: edge-001
          camera_index: 1
          sync_interval: 300
        matching:
          threshold: 0.45
          liveness_threshold: 0.6
          min_det_score: 0.5
          debounce_minutes: 2
        offline:
          db_path: /tmp/queue.sqlite
    """,
    )
    cfg = load_config(path)
    assert cfg.camera_source == 1


def test_missing_camera_source_raises(tmp_path):
    path = _write(
        tmp_path,
        """
        frappe:
          url: http://localhost:8000
          site: site1.localhost
          api_key: k
          api_secret: s
        edge:
          id: edge-001
          sync_interval: 300
        matching:
          threshold: 0.45
          liveness_threshold: 0.6
          min_det_score: 0.5
          debounce_minutes: 2
        offline:
          db_path: /tmp/queue.sqlite
    """,
    )
    with pytest.raises(KeyError):
        load_config(path)


def test_missing_required_key_raises(tmp_path):
    path = _write(
        tmp_path,
        """
        frappe:
          url: http://localhost:8000
        edge:
          id: edge-001
    """,
    )
    with pytest.raises(KeyError):
        load_config(path)


def test_rtsp_options_default_when_absent(tmp_path):
    path = _write(
        tmp_path,
        """
        frappe:
          url: http://localhost:8000
          site: site1.localhost
          api_key: k
          api_secret: s
        edge:
          id: edge-001
          camera_source: 0
          sync_interval: 300
        matching:
          threshold: 0.45
          liveness_threshold: 0.6
          min_det_score: 0.5
          debounce_minutes: 2
        offline:
          db_path: /tmp/queue.sqlite
    """,
    )
    cfg = load_config(path)
    assert cfg.rtsp_transport == "tcp"
    assert cfg.rtsp_timeout_seconds == 10.0
    assert cfg.ffmpeg_capture_options is None


def test_rtsp_options_parsed(tmp_path):
    path = _write(
        tmp_path,
        """
        frappe:
          url: http://localhost:8000
          site: site1.localhost
          api_key: k
          api_secret: s
        edge:
          id: edge-001
          camera_source: rtsp://admin:pass@192.168.1.64:554/Streaming/Channels/102
          sync_interval: 300
          rtsp_transport: udp
          rtsp_timeout_seconds: 5
          ffmpeg_capture_options: "rtsp_transport;tcp|timeout;5000000"
        matching:
          threshold: 0.45
          liveness_threshold: 0.6
          min_det_score: 0.5
          debounce_minutes: 2
        offline:
          db_path: /tmp/queue.sqlite
    """,
    )
    cfg = load_config(path)
    assert cfg.rtsp_transport == "udp"
    assert cfg.rtsp_timeout_seconds == 5
    assert cfg.ffmpeg_capture_options == "rtsp_transport;tcp|timeout;5000000"
