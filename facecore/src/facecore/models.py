"""Data models for facecore."""

from dataclasses import dataclass
from typing import Any


@dataclass
class FaceBox:
    """A detected face location, without the (costly) ArcFace embedding.

    Output of ``FaceAnalyzer.detect()``. ``kps`` are the 5 SCRFD landmarks needed
    to align the crop before embedding; pass the whole FaceBox to
    ``FaceAnalyzer.embed()`` to compute the vector on demand. This split lets a
    tracking loop run detection every frame but embed only once per track."""

    bbox: list[float]
    """Bounding box [x1, y1, x2, y2] in pixel coordinates."""

    det_score: float
    """Detector confidence [0.0, 1.0]. SCRFD output."""

    kps: Any | None = None
    """5x2 facial landmarks (numpy array) for alignment; None if unavailable."""


@dataclass
class DetectedFace:
    """A face detected in an image with embedding and scores."""

    bbox: list[float]
    """Bounding box [x1, y1, x2, y2] in pixel coordinates."""

    embedding: list[float]
    """512-dimensional L2-normalized face embedding from ArcFace."""

    det_score: float
    """Detector confidence [0.0, 1.0]. SCRFD output."""

    liveness_score: float
    """Anti-spoof probability [0.0, 1.0]. MiniFASNet output.
    > 0.5 typically indicates a live face; < 0.5 indicates a print/screen."""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DetectedFace":
        """Construct from dictionary (e.g., from API response)."""
        return cls(
            bbox=data["bbox"],
            embedding=data["embedding"],
            det_score=data["det_score"],
            liveness_score=data["liveness_score"],
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "bbox": self.bbox,
            "embedding": self.embedding,
            "det_score": self.det_score,
            "liveness_score": self.liveness_score,
        }
