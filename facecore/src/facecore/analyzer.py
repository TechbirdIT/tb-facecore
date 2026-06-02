"""FaceAnalyzer — main interface to facecore AI engine."""

from pathlib import Path

import cv2
import numpy as np

from facecore.liveness import LivenessDetector
from facecore.models import DetectedFace

MODEL_VERSION = "buffalo_l"
_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_LIVENESS_PATH = _REPO_ROOT / "models" / "minifasnet.onnx"


class FaceAnalyzer:
    """Detect, embed, and analyze liveness for faces in images.

    Wraps InsightFace (buffalo_l) for detection/embedding and MiniFASNet for liveness.
    """

    def __init__(
        self,
        device: str = "cpu",
        det_thresh: float = 0.5,
        liveness_thresh: float = 0.5,
        liveness_model_path: str | Path = _DEFAULT_LIVENESS_PATH,
    ) -> None:
        """Initialize the analyzer.

        Args:
            device: 'cpu' or 'cuda' (requires NVIDIA Container Toolkit in production).
            det_thresh: Detection confidence threshold [0.0, 1.0]. Default 0.5.
            liveness_thresh: Liveness confidence threshold. Default 0.5.
            liveness_model_path: Path to the MiniFASNet ONNX model.

        Note: Models auto-download on first use (~300MB), cached in facerecog/models/.
        """
        from insightface.app import FaceAnalysis  # type: ignore[import-untyped]

        self.device = device
        self.det_thresh = det_thresh
        self.liveness_thresh = liveness_thresh
        providers = (
            ["CUDAExecutionProvider", "CPUExecutionProvider"]
            if device == "cuda"
            else ["CPUExecutionProvider"]
        )
        self._app = FaceAnalysis(name=MODEL_VERSION, providers=providers)
        self._app.prepare(ctx_id=0 if device == "cuda" else -1, det_thresh=det_thresh)
        self._liveness = LivenessDetector(liveness_model_path, providers)

    def analyze(self, image_array: np.ndarray) -> list[DetectedFace]:
        """Detect and analyze faces in a BGR image array (H, W, 3).

        Args:
            image_array: numpy array (H, W, 3) in BGR format (OpenCV convention).

        Returns:
            List of DetectedFace objects. Empty if no faces detected or below threshold.

        Raises:
            ValueError: If image is invalid (wrong shape, dtype, etc.).
        """
        if image_array.ndim != 3 or image_array.shape[2] != 3:
            raise ValueError("image_array must be a (H, W, 3) BGR array")
        results: list[DetectedFace] = []
        for face in self._app.get(image_array):
            if float(face.det_score) < self.det_thresh:
                continue
            bbox = [float(v) for v in face.bbox]
            results.append(
                DetectedFace(
                    bbox=bbox,
                    embedding=[float(v) for v in face.normed_embedding],
                    det_score=float(face.det_score),
                    liveness_score=self._liveness.score(image_array, bbox),
                )
            )
        return results

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
        path = Path(filepath)
        if not path.is_file():
            raise FileNotFoundError(filepath)
        image = cv2.imread(str(path))
        if image is None:
            raise ValueError(f"not a readable image: {filepath}")
        return self.analyze(image)

    def cosine_similarity(self, emb1: list[float], emb2: list[float]) -> float:
        """Compute cosine similarity between two embeddings.

        Args:
            emb1, emb2: embeddings of equal length.

        Returns:
            Cosine similarity in [-1.0, 1.0]. 1.0 = identical direction.
        """
        a = np.asarray(emb1, dtype=np.float32)
        b = np.asarray(emb2, dtype=np.float32)
        denom = float(np.linalg.norm(a) * np.linalg.norm(b))
        if denom == 0.0:
            return 0.0
        return float(np.dot(a, b) / denom)
