"""Environment-driven settings for the AI service."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    secret: str | None
    device: str
    min_det_score: float

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
        return cls(secret=secret, device=device, min_det_score=min_det_score)
