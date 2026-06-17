from ai_service.config import Settings


def test_defaults(monkeypatch):
    for key in ("AI_SERVICE_SECRET", "AI_SERVICE_DEVICE",
                "EMBEDDING_SERVICE_SECRET", "EMBEDDING_SERVICE_DEVICE"):
        monkeypatch.delenv(key, raising=False)
    s = Settings.from_env()
    assert s.secret is None
    assert s.device == "cpu"
    assert s.min_det_score == 0.5


def test_reads_new_env_vars(monkeypatch):
    monkeypatch.setenv("AI_SERVICE_SECRET", "newsecret")
    monkeypatch.setenv("AI_SERVICE_DEVICE", "cuda")
    s = Settings.from_env()
    assert s.secret == "newsecret"
    assert s.device == "cuda"


def test_falls_back_to_legacy_env_vars(monkeypatch):
    monkeypatch.delenv("AI_SERVICE_SECRET", raising=False)
    monkeypatch.delenv("AI_SERVICE_DEVICE", raising=False)
    monkeypatch.setenv("EMBEDDING_SERVICE_SECRET", "oldsecret")
    monkeypatch.setenv("EMBEDDING_SERVICE_DEVICE", "cuda")
    s = Settings.from_env()
    assert s.secret == "oldsecret"
    assert s.device == "cuda"
