"""FaceAnalyzer — main interface to facecore AI engine."""

from pathlib import Path

import cv2
import numpy as np

from facecore.liveness import LivenessDetector
from facecore.model_download import DEFAULT_LIVENESS_PATH, ensure_liveness_model
from facecore.models import DetectedFace, FaceBox

MODEL_VERSION = "buffalo_l"
_DEFAULT_LIVENESS_PATH = DEFAULT_LIVENESS_PATH


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
            liveness_model_path: Path to the MiniFASNet ONNX model. Auto-downloaded
                (pinned by SHA-256) on first use if absent.

        Note: Models auto-download on first use (~300MB), cached in facerecog/models/.
        """
        liveness_model_path = ensure_liveness_model(liveness_model_path)
        from insightface.app import FaceAnalysis  # type: ignore[import-untyped]

        self.device = device
        self.det_thresh = det_thresh
        self.liveness_thresh = liveness_thresh
        providers = (
            ["CUDAExecutionProvider", "CPUExecutionProvider"]
            if device == "cuda"
            else ["CPUExecutionProvider"]
        )
        # Load only detection + recognition: genderage and the 2D/3D landmark
        # models in buffalo_l are unused here, and skipping them speeds both load
        # and per-call inference. det_model + recognition are what detect()/embed()
        # and analyze() rely on.
        self._app = FaceAnalysis(
            name=MODEL_VERSION,
            providers=providers,
            allowed_modules=["detection", "recognition"],
        )
        self._app.prepare(ctx_id=0 if device == "cuda" else -1, det_thresh=det_thresh)
        self._liveness = LivenessDetector(liveness_model_path, providers)

    @staticmethod
    def _check_image(image_array: np.ndarray) -> None:
        if image_array.ndim != 3 or image_array.shape[2] != 3:
            raise ValueError("image_array must be a (H, W, 3) BGR array")

    def detect(self, image_array: np.ndarray) -> list[FaceBox]:
        """Detect faces only — no embedding (the expensive step).

        Runs just the SCRFD detector, so it is cheap enough to call every frame
        in a tracking loop. Returns boxes above ``det_thresh`` with the landmarks
        needed by :meth:`embed`. Embedding/liveness are computed separately, on
        demand (e.g. once per track), via :meth:`embed` / :meth:`liveness`.
        """
        self._check_image(image_array)
        bboxes, kpss = self._app.det_model.detect(
            image_array, max_num=0, metric="default"
        )
        out: list[FaceBox] = []
        for i in range(bboxes.shape[0]):
            score = float(bboxes[i, 4])
            if score < self.det_thresh:
                continue
            out.append(
                FaceBox(
                    bbox=[float(v) for v in bboxes[i, :4]],
                    det_score=score,
                    kps=(kpss[i] if kpss is not None else None),
                )
            )
        return out

    def embed(self, image_array: np.ndarray, face: FaceBox) -> list[float]:
        """Compute the 512-d L2-normalized ArcFace embedding for one detected face.

        Aligns the crop using ``face.kps`` and runs the recognition model only —
        call this lazily (once per track), not for every face every frame.
        """
        from insightface.app.common import Face  # type: ignore[import-untyped]

        if face.kps is None:
            raise ValueError("FaceBox.kps is required to align the crop for embedding")
        rec_face = Face(
            bbox=np.asarray(face.bbox, dtype=np.float32),
            kps=np.asarray(face.kps, dtype=np.float32),
            det_score=face.det_score,
        )
        self._app.models["recognition"].get(image_array, rec_face)
        return [float(v) for v in rec_face.normed_embedding]

    def liveness(self, image_array: np.ndarray, bbox: list[float]) -> float:
        """Anti-spoof probability [0,1] for the face at ``bbox`` (MiniFASNet)."""
        return float(self._liveness.score(image_array, bbox))

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
