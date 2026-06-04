"""In-memory NumPy cosine matcher over cached embeddings."""

from __future__ import annotations

import json
import logging

import numpy as np

logger = logging.getLogger(__name__)


class Matcher:
    def __init__(self, face_rows: list[dict], model_version: str) -> None:
        rows = [r for r in face_rows if r.get("model_version") == model_version]
        self.device_ids = [r["attendance_device_id"] for r in rows]
        if rows:
            mat = np.asarray(
                [json.loads(r["embedding"]) for r in rows], dtype=np.float32
            )
            norms = np.linalg.norm(mat, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            self.matrix = mat / norms
        else:
            self.matrix = np.empty((0, 0), dtype=np.float32)

    @property
    def size(self) -> int:
        return len(self.device_ids)

    def match(self, vec: list[float], threshold: float) -> tuple[str, float] | None:
        if self.size == 0:
            return None
        q = np.asarray(vec, dtype=np.float32)
        n = np.linalg.norm(q)
        if n == 0:
            return None
        sims = self.matrix @ (q / n)
        idx = int(np.argmax(sims))
        score = float(sims[idx])
        if score < threshold:
            logger.debug("best score %.3f below threshold %.2f", score, threshold)
            return None
        return self.device_ids[idx], score
