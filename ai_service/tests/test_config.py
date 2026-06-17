import pytest

from ai_service.config import Settings


def test_defaults(monkeypatch):
    for key in (
        "AI_SERVICE_SECRET",
        "AI_SERVICE_DEVICE",
        "AI_SERVICE_MIN_DET_SCORE",
        "EMBEDDING_SERVICE_SECRET",
        "EMBEDDING_SERVICE_DEVICE",
        "EMBEDDING_SERVICE_MIN_DET_SCORE",
    ):
        monkeypatch.delenv(key, raising=False)
    s = Settings.from_env()
    assert s.secret is None
    assert s.device == "cpu"
    assert s.min_det_score == 0.5


def test_reads_new_env_vars(monkeypatch):
    monkeypatch.setenv("AI_SERVICE_SECRET", "newsecret")
    monkeypatch.setenv("AI_SERVICE_DEVICE", "cuda")
    monkeypatch.setenv("AI_SERVICE_MIN_DET_SCORE", "0.7")
    s = Settings.from_env()
    assert s.secret == "newsecret"
    assert s.device == "cuda"
    assert s.min_det_score == 0.7


def test_falls_back_to_legacy_env_vars(monkeypatch):
    for key in ("AI_SERVICE_SECRET", "AI_SERVICE_DEVICE", "AI_SERVICE_MIN_DET_SCORE"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("EMBEDDING_SERVICE_SECRET", "oldsecret")
    monkeypatch.setenv("EMBEDDING_SERVICE_DEVICE", "cuda")
    monkeypatch.setenv("EMBEDDING_SERVICE_MIN_DET_SCORE", "0.6")
    s = Settings.from_env()
    assert s.secret == "oldsecret"
    assert s.device == "cuda"
    assert s.min_det_score == 0.6


def test_new_vars_override_legacy(monkeypatch):
    monkeypatch.setenv("AI_SERVICE_SECRET", "new")
    monkeypatch.setenv("EMBEDDING_SERVICE_SECRET", "old")
    s = Settings.from_env()
    assert s.secret == "new"


def test_invalid_min_det_score_raises(monkeypatch):
    monkeypatch.setenv("AI_SERVICE_MIN_DET_SCORE", "notanumber")
    with pytest.raises(ValueError):
        Settings.from_env()
