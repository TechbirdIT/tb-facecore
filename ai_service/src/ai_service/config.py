"""Environment-driven settings for the AI service."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    secret: str | None
    device: str
    min_det_score: float
    deepface_url: str = field(default="http://localhost:5005/api/v1")

    @classmethod
    def from_env(cls) -> Settings:
        # Read AI_SERVICE_* vars; fall back to legacy EMBEDDING_SERVICE_* so
        # existing deployments keep working without config changes.
        secret = (
            os.getenv("AI_SERVICE_SECRET")
            or os.getenv("EMBEDDING_SERVICE_SECRET")
        )
        device = (
            os.getenv("AI_SERVICE_DEVICE")
            or os.getenv("EMBEDDING_SERVICE_DEVICE")
            or "cpu"
        )
        min_det_score = float(
            os.getenv("AI_SERVICE_MIN_DET_SCORE")
            or os.getenv("EMBEDDING_SERVICE_MIN_DET_SCORE")
            or "0.5"
        )
        deepface_url = os.getenv("AI_SERVICE_DEEPFACE_URL") or "http://localhost:5005/api/v1"
        return cls(secret=secret, device=device, min_det_score=min_det_score, deepface_url=deepface_url)
