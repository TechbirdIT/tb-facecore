"""FaceAnalyzer — main interface to facecore AI engine."""

from pathlib import Path

import cv2
import numpy as np

from facecore import metrics
from facecore.image_io import load_image
from facecore.liveness import LivenessDetector
from facecore.model_download import DEFAULT_LIVENESS_PATH, ensure_liveness_model
from facecore.models import DetectedFace, FaceBox

MODEL_VERSION = "buffalo_l"
_DEFAULT_LIVENESS_PATH = DEFAULT_LIVENESS_PATH


def _age_gender(face: object) -> tuple[int | None, str | None]:
    """Read (age, gender) off an InsightFace Face populated by the genderage model.

    Returns (None, None) if genderage did not run. ``gender`` is normalized to
    ``"male"`` / ``"female"`` (InsightFace encodes gender as 1 = male, 0 = female).
    """
    age = getattr(face, "age", None)
    gender = getattr(face, "gender", None)
    age_out = int(age) if age is not None else None
    if gender is None:
        return age_out, None
    return age_out, ("male" if int(gender) == 1 else "female")


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
        # Load detection + recognition + genderage. The genderage model already
        # ships inside buffalo_l (no extra download) and is cheap; it gives age +
        # gender for free in analyze(). The 2D/3D landmark models stay disabled —
        # unused here, and skipping them speeds load and per-call inference.
        self._app = FaceAnalysis(
            name=MODEL_VERSION,
            providers=providers,
            allowed_modules=["detection", "recognition", "genderage"],
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
            age, gender = _age_gender(face)
            results.append(
                DetectedFace(
                    bbox=bbox,
                    embedding=[float(v) for v in face.normed_embedding],
                    det_score=float(face.det_score),
                    liveness_score=self._liveness.score(image_array, bbox),
                    age=age,
                    gender=gender,
                )
            )
        return results

    def gender_age(self, image_array: np.ndarray, face: FaceBox) -> tuple[int, str]:
        """Estimate (age, gender) for one detected face — for the detect/embed split.

        Runs buffalo_l's genderage model on demand (like :meth:`embed`), so the
        tracking loop can attach demographics once per track instead of every
        frame. ``gender`` is ``"male"`` or ``"female"``. ``analyze()`` already
        fills these in; use this only on the cheap detect()/embed() path.
        """
        from insightface.app.common import Face  # type: ignore[import-untyped]

        kps = np.asarray(face.kps, dtype=np.float32) if face.kps is not None else None
        rec_face = Face(
            bbox=np.asarray(face.bbox, dtype=np.float32),
            kps=kps,
            det_score=face.det_score,
        )
        self._app.models["genderage"].get(image_array, rec_face)
        age, gender = _age_gender(rec_face)
        return (age or 0, gender or "unknown")

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

    def extract_faces(
        self, source: object, align: bool = True, size: int = 112
    ) -> list[dict]:
        """Detect faces in ``source`` and return their crops.

        ``source`` is anything :func:`facecore.image_io.load_image` accepts
        (ndarray / path / URL / base64 / bytes). With ``align=True`` (default)
        each crop is the ArcFace-aligned ``size``×``size`` chip (the same
        alignment used for embedding — ideal for storing the enrolled face);
        with ``align=False`` it is the raw bbox crop. Returns one dict per face:
        ``{"face": ndarray, "facial_area": {x,y,w,h}, "confidence": float}``.
        """
        img = load_image(source)
        self._check_image(img)
        out: list[dict] = []
        for fb in self.detect(img):
            x1, y1, x2, y2 = (int(v) for v in fb.bbox)
            if align and fb.kps is not None:
                from insightface.utils import face_align  # type: ignore[import-untyped]

                crop = face_align.norm_crop(
                    img, np.asarray(fb.kps, dtype=np.float32), image_size=size
                )
            else:
                xa, ya = max(0, x1), max(0, y1)
                crop = img[ya : max(ya + 1, y2), xa : max(xa + 1, x2)].copy()
            out.append(
                {
                    "face": crop,
                    "facial_area": {"x": x1, "y": y1, "w": x2 - x1, "h": y2 - y1},
                    "confidence": fb.det_score,
                }
            )
        return out

    def distance(
        self, emb1: list[float], emb2: list[float], metric: str = "cosine"
    ) -> float:
        """Distance between two embeddings (lower = more similar). See ``metrics``."""
        return metrics.find_distance(emb1, emb2, metric)

    def verify(
        self,
        emb1: list[float],
        emb2: list[float],
        metric: str = "cosine",
        threshold: float | None = None,
    ) -> dict:
        """Same-person check via deepface-style thresholds; see ``metrics.verify``."""
        return metrics.verify(
            emb1, emb2, metric=metric, model_name=MODEL_VERSION, threshold=threshold
        )

    def demography(
        self, source: object, actions: tuple[str, ...] = ("emotion", "race")
    ) -> list[dict]:
        """Emotion / race demography — requires the ``facecore[demography]`` extra.

        Thin delegate to :mod:`facecore.demography` (deepface backend). Age/gender
        are already available for free via :meth:`analyze` / :meth:`gender_age`;
        use this for emotion and race. Raises ``FaceCoreError`` with an install
        hint if the extra isn't installed.
        """
        from facecore import demography as _demography

        return _demography.analyze(source, actions=actions)

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
