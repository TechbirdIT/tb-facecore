"""Passive liveness (anti-spoof) via Silent-Face MiniFASNet (ONNX)."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort


def _softmax(logits: np.ndarray) -> np.ndarray:
    e = np.exp(logits - logits.max())
    return e / e.sum()


def _expand_bbox(
    bbox: list[float], scale: float, w: int, h: int
) -> tuple[int, int, int, int]:
    """Enlarge a face bbox by `scale` around its center, clamped to the image."""
    x1, y1, x2, y2 = bbox
    cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    bw, bh = (x2 - x1) * scale, (y2 - y1) * scale
    nx1 = int(max(0, cx - bw / 2.0))
    ny1 = int(max(0, cy - bh / 2.0))
    nx2 = int(min(w, cx + bw / 2.0))
    ny2 = int(min(h, cy + bh / 2.0))
    return nx1, ny1, nx2, ny2


class LivenessDetector:
    """Wrap a MiniFASNet ONNX model. Given an image + face bbox, return P(live)."""

    def __init__(self, model_path: str | Path, providers: list[str]) -> None:
        self.session = ort.InferenceSession(str(model_path), providers=providers)
        self.input_name = self.session.get_inputs()[0].name

    def score(self, image_bgr: np.ndarray, bbox: list[float], scale: float = 2.7) -> float:
        """Return the live-class probability in [0.0, 1.0]."""
        h, w = image_bgr.shape[:2]
        x1, y1, x2, y2 = _expand_bbox(bbox, scale, w, h)
        crop = image_bgr[y1:y2, x1:x2]
        if crop.size == 0:
            return 0.0
        blob = cv2.resize(crop, (80, 80)).astype(np.float32)
        blob = np.transpose(blob, (2, 0, 1))[np.newaxis, :]  # NCHW
        logits = self.session.run(None, {self.input_name: blob})[0][0]
        return float(_softmax(np.asarray(logits, dtype=np.float32))[1])
