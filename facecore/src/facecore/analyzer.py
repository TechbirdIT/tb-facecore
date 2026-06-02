"""FaceAnalyzer — main interface to facecore AI engine."""

from typing import Any
from facecore.models import DetectedFace


class FaceAnalyzer:
    """Detect, embed, and analyze liveness for faces in images.

    Wraps InsightFace (buffalo_l) for detection/embedding and MiniFASNet for liveness.
    """

    def __init__(
        self,
        device: str = "cpu",
        det_thresh: float = 0.5,
        liveness_thresh: float = 0.5,
    ):
        """Initialize the analyzer.

        Args:
            device: 'cpu' or 'cuda' (requires NVIDIA Container Toolkit in production).
            det_thresh: Detection confidence threshold [0.0, 1.0]. Default 0.5.
            liveness_thresh: Liveness confidence threshold. Default 0.5.

        Note: Models are auto-downloaded on first use (~300MB). Cache in facerecog/models/.
        """
        self.device = device
        self.det_thresh = det_thresh
        self.liveness_thresh = liveness_thresh

    def analyze(self, image_array: Any) -> list[DetectedFace]:
        """Detect and analyze faces in an image.

        Args:
            image_array: numpy array (H, W, 3) in BGR format (OpenCV convention).

        Returns:
            List of DetectedFace objects. Empty if no faces detected or below threshold.

        Raises:
            ValueError: If image is invalid (wrong shape, dtype, etc.).
        """
        # Stub — will be implemented in phase 1
        raise NotImplementedError("FaceAnalyzer.analyze() — phase 1 implementation")

    def analyze_image_file(self, filepath: str) -> list[DetectedFace]:
        """Detect and analyze faces from a file path.

        Args:
            filepath: path to image (jpg, png, etc.).

        Returns:
            List of DetectedFace objects.

        Raises:
            FileNotFoundError: If file not found.
            ValueError: If file is not a valid image.
        """
        # Stub — will be implemented in phase 1
        raise NotImplementedError("FaceAnalyzer.analyze_image_file() — phase 1")

    def cosine_similarity(self, emb1: list[float], emb2: list[float]) -> float:
        """Compute cosine similarity between two embeddings.

        Args:
            emb1, emb2: 512-dim embeddings (L2-normalized).

        Returns:
            Cosine similarity in range [0.0, 1.0]. 1.0 = identical.
        """
        # Stub — will be implemented in phase 1
        raise NotImplementedError("FaceAnalyzer.cosine_similarity() — phase 1")
