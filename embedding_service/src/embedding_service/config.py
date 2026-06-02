"""Environment-driven settings for the embedding service."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    secret: str | None
    device: str
    min_det_score: float

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            secret=os.getenv("EMBEDDING_SERVICE_SECRET") or None,
            device=os.getenv("EMBEDDING_SERVICE_DEVICE", "cpu"),
            min_det_score=float(os.getenv("EMBEDDING_SERVICE_MIN_DET_SCORE", "0.5")),
        )
