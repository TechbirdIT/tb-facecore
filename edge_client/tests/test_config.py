# edge_client/tests/test_config.py
import textwrap

import pytest

from edge_client.config import EdgeConfig, load_config


def _write(tmp_path, text):
    p = tmp_path / "config.yaml"
    p.write_text(textwrap.dedent(text))
    return str(p)


def test_load_valid_config(tmp_path):
    path = _write(tmp_path, """
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
    """)
    cfg = load_config(path)
    assert isinstance(cfg, EdgeConfig)
    assert cfg.frappe_url == "http://localhost:8000"
    assert cfg.edge_id == "edge-001"
    assert cfg.threshold == 0.45
    assert cfg.db_path == "/tmp/queue.sqlite"


def test_missing_required_key_raises(tmp_path):
    path = _write(tmp_path, """
        frappe:
          url: http://localhost:8000
        edge:
          id: edge-001
    """)
    with pytest.raises(KeyError):
        load_config(path)
