"""Distance metrics and verification thresholds.

facecore matches on cosine *similarity* (``FaceAnalyzer.cosine_similarity`` /
the edge matcher, where higher = closer, attendance default 0.45). This module
adds the deepface-style *distance* view (lower = closer) and its calibrated
per-model thresholds, ported from serengil/deepface
(``deepface/modules/verification.py``, MIT licensed), for callers that want
euclidean / L2 / angular metrics or a drop-in ``verify()``.

Convention here matches deepface: a pair is a match when ``distance <= threshold``.
Cosine distance = ``1 - cosine_similarity``.
"""

from __future__ import annotations

import numpy as np

Vector = list[float] | np.ndarray

VALID_METRICS = ("cosine", "euclidean", "euclidean_l2", "angular")

# Calibrated distance thresholds from deepface (match when distance <= threshold).
# facecore embeds with buffalo_l (ArcFace-family, 512-d L2-normalized), so
# "buffalo_l" aliases the ArcFace row. NOTE: facecore's empirical attendance
# default is cosine *similarity* >= 0.45 (== cosine *distance* <= 0.55), tighter
# than the generic 0.68 below to resist buddy-punching — see RT-1.
_THRESHOLDS: dict[str, dict[str, float]] = {
    "ArcFace": {"cosine": 0.68, "euclidean": 4.15, "euclidean_l2": 1.13},
    "buffalo_l": {"cosine": 0.68, "euclidean": 4.15, "euclidean_l2": 1.13},
    "Facenet512": {"cosine": 0.30, "euclidean": 23.56, "euclidean_l2": 1.04},
    "Facenet": {"cosine": 0.40, "euclidean": 10.0, "euclidean_l2": 0.80},
    "VGG-Face": {"cosine": 0.68, "euclidean": 1.17, "euclidean_l2": 1.17},
    "SFace": {"cosine": 0.593, "euclidean": 10.734, "euclidean_l2": 1.055},
    "GhostFaceNet": {"cosine": 0.65, "euclidean": 35.71, "euclidean_l2": 1.10},
}
_DEFAULT_THRESHOLD = {"cosine": 0.40, "euclidean": 4.15, "euclidean_l2": 0.75}
# angular distance is in [0,1]; derive its threshold from the cosine one.
_ANGULAR_FALLBACK = 0.30


def _as_array(v: Vector) -> np.ndarray:
    return np.asarray(v, dtype=np.float32)


def cosine_distance(a: Vector, b: Vector) -> float:
    """1 - cosine similarity. 0 = identical direction, 2 = opposite."""
    x, y = _as_array(a), _as_array(b)
    denom = float(np.linalg.norm(x) * np.linalg.norm(y))
    if denom == 0.0:
        return 1.0
    return float(1.0 - np.dot(x, y) / denom)


def euclidean_distance(a: Vector, b: Vector) -> float:
    """L2 distance between the raw vectors."""
    x, y = _as_array(a), _as_array(b)
    return float(np.linalg.norm(x - y))


def _l2_normalize(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    return v if n == 0.0 else v / n


def euclidean_l2_distance(a: Vector, b: Vector) -> float:
    """L2 distance after L2-normalizing both vectors (scale-invariant)."""
    na, nb = _l2_normalize(_as_array(a)), _l2_normalize(_as_array(b))
    return float(np.linalg.norm(na - nb))


def angular_distance(a: Vector, b: Vector) -> float:
    """Normalized angular distance arccos(cos_sim)/pi, in [0, 1]."""
    sim = 1.0 - cosine_distance(a, b)
    return float(np.arccos(np.clip(sim, -1.0, 1.0)) / np.pi)


_DISPATCH = {
    "cosine": cosine_distance,
    "euclidean": euclidean_distance,
    "euclidean_l2": euclidean_l2_distance,
    "angular": angular_distance,
}


def find_distance(a: Vector, b: Vector, metric: str = "cosine") -> float:
    """Distance between two embeddings under ``metric`` (lower = more similar)."""
    if metric not in _DISPATCH:
        raise ValueError(f"unknown metric {metric!r}; valid: {VALID_METRICS}")
    return _DISPATCH[metric](a, b)


def find_threshold(model_name: str = "buffalo_l", metric: str = "cosine") -> float:
    """Calibrated match threshold for (model, metric) — match when distance <= it."""
    if metric not in VALID_METRICS:
        raise ValueError(f"unknown metric {metric!r}; valid: {VALID_METRICS}")
    if metric == "angular":
        return _ANGULAR_FALLBACK
    row = _THRESHOLDS.get(model_name, _DEFAULT_THRESHOLD)
    return row.get(metric, _DEFAULT_THRESHOLD[metric])


def verify(
    a: Vector,
    b: Vector,
    metric: str = "cosine",
    model_name: str = "buffalo_l",
    threshold: float | None = None,
) -> dict:
    """Compare two embeddings; returns {verified, distance, threshold, metric}.

    ``verified`` is True when ``distance <= threshold`` (deepface convention).
    """
    dist = find_distance(a, b, metric)
    thr = find_threshold(model_name, metric) if threshold is None else threshold
    return {
        "verified": bool(dist <= thr),
        "distance": round(dist, 6),
        "threshold": thr,
        "metric": metric,
        "model": model_name,
    }
