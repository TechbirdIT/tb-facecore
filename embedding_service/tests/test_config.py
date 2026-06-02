# embedding_service/tests/test_config.py
from embedding_service.config import Settings


def test_defaults(monkeypatch):
    monkeypatch.delenv("EMBEDDING_SERVICE_SECRET", raising=False)
    monkeypatch.delenv("EMBEDDING_SERVICE_DEVICE", raising=False)
    s = Settings.from_env()
    assert s.secret is None
    assert s.device == "cpu"
    assert s.min_det_score == 0.5


def test_reads_env(monkeypatch):
    monkeypatch.setenv("EMBEDDING_SERVICE_SECRET", "topsecret")
    monkeypatch.setenv("EMBEDDING_SERVICE_DEVICE", "cuda")
    s = Settings.from_env()
    assert s.secret == "topsecret"
    assert s.device == "cuda"
