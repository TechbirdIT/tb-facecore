# Face Recognition Attendance for Frappe HRMS — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a facial-recognition biometric attendance system that posts check-ins to Frappe HRMS's native attendance pipeline, with all heavy AI decoupled from the bench.

**Architecture:** Four units. `facecore` (pure InsightFace + MiniFASNet engine, no I/O). `embedding_service` (FastAPI wrapper over facecore — the only thing that touches AI on the server side). `face_attendance` (Frappe v16 app: enrollment DocTypes, sync API, role fixtures — never imports InsightFace). `edge_client` (camera → liveness → embed → NumPy match → debounce → native check-in, with a durable SQLite offline queue). See `docs/design/architecture.md` for the approved design.

**Tech Stack:** Python 3.11 (AI stack), Python 3.14 (Frappe bench), InsightFace `buffalo_l` (SCRFD + ArcFace r50), Silent-Face MiniFASNet (ONNX), ONNX Runtime, NumPy, FastAPI, OpenCV, SQLite, Frappe/ERPNext/HRMS v16.

**Reference paths:**
- AI repo: `/Users/saurabh/facerecog` (scaffold exists; stubs raise `NotImplementedError`)
- Bench: `~/frappe-bench`, site `site1.localhost`
- Native check-in: `hrms.hr.doctype.employee_checkin.employee_checkin.add_log_based_on_employee_field`

**Conventions for this plan:**
- All `cd` targets are absolute.
- AI-stack commands run inside the Python 3.11 venv: `source /Users/saurabh/facerecog/venv/bin/activate`.
- Frappe commands run from `~/frappe-bench`.
- Tests requiring downloaded models (~310 MB) are marked `@pytest.mark.integration` and skipped in the default unit run.

---

## File Structure

### AI repo (`/Users/saurabh/facerecog`)

| File | Responsibility |
|------|----------------|
| `facecore/src/facecore/exceptions.py` | Custom exception hierarchy (`FaceCoreError`, subclasses). |
| `facecore/src/facecore/models.py` | `DetectedFace` dataclass (exists). |
| `facecore/src/facecore/liveness.py` | `LivenessDetector` — MiniFASNet ONNX wrapper. Crop → softmax → live score. |
| `facecore/src/facecore/analyzer.py` | `FaceAnalyzer` — InsightFace detect+embed, liveness, `cosine_similarity` (exists as stub). |
| `facecore/src/facecore/__init__.py` | Public exports. |
| `facecore/tests/` | Unit + integration tests, committed fixture images. |
| `embedding_service/src/embedding_service/app.py` | FastAPI `/embed` + `/health` (stub exists). |
| `embedding_service/src/embedding_service/config.py` | Env-driven settings (secret, device). |
| `embedding_service/tests/` | `TestClient` tests with facecore mocked. |
| `edge_client/src/edge_client/config.py` | YAML→dataclass loader + validation. |
| `edge_client/src/edge_client/store.py` | SQLite face cache + offline check-in queue. |
| `edge_client/src/edge_client/matcher.py` | NumPy matrix builder + cosine argmax match. |
| `edge_client/src/edge_client/debounce.py` | In-memory per-device punch suppressor. |
| `edge_client/src/edge_client/frappe_client.py` | `get_face_data` GET + check-in POST. |
| `edge_client/src/edge_client/sync.py` | Sync worker: pull → upsert → rebuild matrix. |
| `edge_client/src/edge_client/capture.py` | OpenCV capture loop wiring all of the above. |
| `edge_client/src/edge_client/main.py` | argparse entry (stub exists). |
| `edge_client/tests/` | matcher, debounce, store, config, sync-merge tests. |

### Frappe app (`~/frappe-bench/apps/face_attendance`, created via `bench new-app`)

| File | Responsibility |
|------|----------------|
| `face_attendance/hooks.py` | `required_apps`, `fixtures`. |
| `.../face_attendance/doctype/employee_face_profile/employee_face_profile.json` | DocType schema. |
| `.../employee_face_profile/employee_face_profile.py` | Enrollment controller (`validate`). |
| `.../employee_face_profile/test_employee_face_profile.py` | Enrollment + permission tests. |
| `.../face_attendance/doctype/face_recognition_settings/face_recognition_settings.json` | Single DocType schema. |
| `.../face_attendance/doctype/face_recognition_settings/face_recognition_settings.py` | Empty controller. |
| `face_attendance/api.py` | `get_face_data` sync endpoint. |
| `face_attendance/tests/test_sync_api.py` | Sync shape + `since` filter tests. |
| `.../face_attendance/report/face_profiles_needing_reenrollment/` | Query report (model-version drift). |
| `face_attendance/fixtures/role.json` | "Face Edge Device" Role. |
| `face_attendance/fixtures/custom_docperm.json` | create+read on Employee Checkin. |

### Docs

| File | Responsibility |
|------|----------------|
| `docs/operations.md` | Model download, enrollment, edge config, shift setup, E2E checklist. |

---

# Phase 0 — Dev environment

### Task 0: Python 3.11 venv + editable installs + test scaffolding

**Files:**
- Create: `/Users/saurabh/facerecog/venv/` (venv, gitignored)
- Create: `facecore/tests/__init__.py`, `embedding_service/tests/__init__.py`, `edge_client/tests/__init__.py`

- [ ] **Step 1: Create the 3.11 venv and install all three packages editable**

```bash
cd /Users/saurabh/facerecog
python3.11 -m venv venv
source venv/bin/activate
python --version   # expect: Python 3.11.x
pip install -U pip
pip install -e "facecore/[dev]"
pip install -e "embedding_service/[dev]"
pip install -e "edge_client/[dev]"
```

Expected: all three install without error (pulls insightface, onnxruntime, fastapi, opencv, etc.). First install is slow.

- [ ] **Step 2: Create empty test packages**

```bash
mkdir -p facecore/tests embedding_service/tests edge_client/tests
touch facecore/tests/__init__.py embedding_service/tests/__init__.py edge_client/tests/__init__.py
```

- [ ] **Step 3: Verify pytest collects (zero tests is fine)**

Run: `cd /Users/saurabh/facerecog && source venv/bin/activate && pytest facecore embedding_service edge_client`
Expected: `no tests ran` — no collection/import errors.

- [ ] **Step 4: Confirm venv is gitignored**

Run: `git -C /Users/saurabh/facerecog check-ignore venv`
Expected: prints `venv`. If not, add `venv/` to `.gitignore` and commit.

- [ ] **Step 5: Commit**

```bash
cd /Users/saurabh/facerecog
git add facecore/tests embedding_service/tests edge_client/tests .gitignore
git commit -m "chore: add test packages and confirm venv ignored"
```

---

# Phase 1 — facecore

### Task 1: Exception hierarchy

**Files:**
- Create: `facecore/src/facecore/exceptions.py`
- Test: `facecore/tests/test_exceptions.py`

- [ ] **Step 1: Write the failing test**

```python
# facecore/tests/test_exceptions.py
import pytest
from facecore.exceptions import (
    FaceCoreError,
    NoFaceError,
    MultipleFacesError,
    LowQualityError,
)


def test_subclasses_are_facecore_errors():
    for exc in (NoFaceError, MultipleFacesError, LowQualityError):
        assert issubclass(exc, FaceCoreError)


def test_raisable_with_message():
    with pytest.raises(FaceCoreError, match="boom"):
        raise NoFaceError("boom")
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest facecore/tests/test_exceptions.py -v`
Expected: FAIL — `ModuleNotFoundError: facecore.exceptions`.

- [ ] **Step 3: Implement**

```python
# facecore/src/facecore/exceptions.py
"""Exception hierarchy for facecore."""


class FaceCoreError(Exception):
    """Base class for all facecore errors."""


class NoFaceError(FaceCoreError):
    """No face detected in the image."""


class MultipleFacesError(FaceCoreError):
    """More than one face detected where exactly one was required."""


class LowQualityError(FaceCoreError):
    """A face was detected but its detector confidence is below threshold."""
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest facecore/tests/test_exceptions.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add facecore/src/facecore/exceptions.py facecore/tests/test_exceptions.py
git commit -m "feat(facecore): add exception hierarchy"
```

---

### Task 2: `cosine_similarity` (pure NumPy, no models)

**Files:**
- Modify: `facecore/src/facecore/analyzer.py:63-73`
- Test: `facecore/tests/test_cosine.py`

- [ ] **Step 1: Write the failing test**

```python
# facecore/tests/test_cosine.py
import numpy as np
from facecore.analyzer import FaceAnalyzer


def _analyzer():
    # __init__ must NOT load models, so this is cheap and offline.
    return FaceAnalyzer.__new__(FaceAnalyzer)


def test_identical_vectors_similarity_is_one():
    a = analyzer = _analyzer()
    v = [1.0, 0.0, 0.0]
    assert abs(FaceAnalyzer.cosine_similarity(a, v, v) - 1.0) < 1e-6


def test_orthogonal_vectors_similarity_is_zero():
    a = _analyzer()
    assert abs(FaceAnalyzer.cosine_similarity(a, [1.0, 0.0], [0.0, 1.0])) < 1e-6


def test_opposite_vectors_similarity_is_minus_one():
    a = _analyzer()
    assert abs(FaceAnalyzer.cosine_similarity(a, [1.0, 0.0], [-1.0, 0.0]) + 1.0) < 1e-6
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest facecore/tests/test_cosine.py -v`
Expected: FAIL — `NotImplementedError`.

- [ ] **Step 3: Implement** — replace the body of `cosine_similarity` in `facecore/src/facecore/analyzer.py`

```python
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
```

Add at the top of `analyzer.py` (after the existing imports):

```python
import numpy as np
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest facecore/tests/test_cosine.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add facecore/src/facecore/analyzer.py facecore/tests/test_cosine.py
git commit -m "feat(facecore): implement cosine_similarity"
```

---

### Task 3: `LivenessDetector` (MiniFASNet ONNX wrapper)

**Files:**
- Create: `facecore/src/facecore/liveness.py`
- Test: `facecore/tests/test_liveness.py`

**Note on the model:** Silent-Face MiniFASNet expects an enlarged crop around the face bbox, resized to 80×80, in NCHW float32. The network outputs 3 logits; index 1 is the "real/live" class. We unit-test the pure helpers (`_expand_bbox`, `_softmax`) here; the full ONNX path is exercised by an integration test in Task 6.

- [ ] **Step 1: Write the failing test**

```python
# facecore/tests/test_liveness.py
import numpy as np
from facecore.liveness import _softmax, _expand_bbox


def test_softmax_sums_to_one():
    out = _softmax(np.array([2.0, 1.0, 0.1], dtype=np.float32))
    assert abs(float(out.sum()) - 1.0) < 1e-6
    assert out.argmax() == 0


def test_expand_bbox_grows_and_clamps():
    # bbox well inside a 200x200 image, scale 2.0 doubles the box around its center.
    x1, y1, x2, y2 = _expand_bbox([80, 80, 120, 120], scale=2.0, w=200, h=200)
    assert x1 < 80 and y1 < 80 and x2 > 120 and y2 > 120
    assert 0 <= x1 and 0 <= y1 and x2 <= 200 and y2 <= 200


def test_expand_bbox_clamps_at_edges():
    x1, y1, x2, y2 = _expand_bbox([0, 0, 50, 50], scale=4.0, w=100, h=100)
    assert x1 == 0 and y1 == 0
    assert x2 <= 100 and y2 <= 100
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest facecore/tests/test_liveness.py -v`
Expected: FAIL — `ModuleNotFoundError: facecore.liveness`.

- [ ] **Step 3: Implement**

```python
# facecore/src/facecore/liveness.py
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest facecore/tests/test_liveness.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add facecore/src/facecore/liveness.py facecore/tests/test_liveness.py
git commit -m "feat(facecore): add MiniFASNet liveness detector"
```

---

### Task 4: `FaceAnalyzer.__init__` lazy model loading + `analyze`

**Files:**
- Modify: `facecore/src/facecore/analyzer.py` (`__init__`, `analyze`)
- Test: `facecore/tests/test_analyze_unit.py`

**Design:** `__init__` stores config and constructs the InsightFace `FaceAnalysis` app + `LivenessDetector`. To keep unit tests offline, `analyze` is tested by injecting fakes for `self._app` and `self._liveness`. The liveness model path defaults to `<repo>/models/minifasnet.onnx` and is configurable.

- [ ] **Step 1: Write the failing test**

```python
# facecore/tests/test_analyze_unit.py
import numpy as np
from facecore.analyzer import FaceAnalyzer
from facecore.models import DetectedFace


class _FakeFace:
    def __init__(self, bbox, det_score, embedding):
        self.bbox = np.array(bbox, dtype=np.float32)
        self.det_score = det_score
        self.normed_embedding = np.array(embedding, dtype=np.float32)


class _FakeApp:
    def __init__(self, faces):
        self._faces = faces

    def get(self, image):
        return self._faces


class _FakeLiveness:
    def __init__(self, value):
        self.value = value

    def score(self, image, bbox, scale=2.7):
        return self.value


def _analyzer(faces, liveness=0.9, det_thresh=0.5):
    a = FaceAnalyzer.__new__(FaceAnalyzer)
    a.device = "cpu"
    a.det_thresh = det_thresh
    a.liveness_thresh = 0.5
    a._app = _FakeApp(faces)
    a._liveness = _FakeLiveness(liveness)
    return a


def test_analyze_returns_detected_faces():
    emb = [0.1] * 512
    a = _analyzer([_FakeFace([0, 0, 10, 10], 0.95, emb)], liveness=0.8)
    out = a.analyze(np.zeros((100, 100, 3), dtype=np.uint8))
    assert len(out) == 1
    f = out[0]
    assert isinstance(f, DetectedFace)
    assert f.det_score == 0.95
    assert f.liveness_score == 0.8
    assert len(f.embedding) == 512
    assert f.bbox == [0.0, 0.0, 10.0, 10.0]


def test_analyze_filters_below_det_thresh():
    a = _analyzer([_FakeFace([0, 0, 10, 10], 0.3, [0.1] * 512)], det_thresh=0.5)
    assert a.analyze(np.zeros((100, 100, 3), dtype=np.uint8)) == []


def test_analyze_empty_when_no_faces():
    a = _analyzer([])
    assert a.analyze(np.zeros((100, 100, 3), dtype=np.uint8)) == []


def test_analyze_rejects_bad_image():
    a = _analyzer([])
    import pytest
    with pytest.raises(ValueError):
        a.analyze(np.zeros((100, 100), dtype=np.uint8))  # not 3-channel
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest facecore/tests/test_analyze_unit.py -v`
Expected: FAIL — `analyze` raises `NotImplementedError`.

- [ ] **Step 3: Implement** — rewrite `__init__` and `analyze` in `analyzer.py`

```python
"""FaceAnalyzer — main interface to facecore AI engine."""

from pathlib import Path

import numpy as np

from facecore.liveness import LivenessDetector
from facecore.models import DetectedFace

MODEL_VERSION = "buffalo_l"
_DEFAULT_LIVENESS_PATH = Path(__file__).resolve().parents[3] / "models" / "minifasnet.onnx"


class FaceAnalyzer:
    """Detect, embed, and analyze liveness for faces in images."""

    def __init__(
        self,
        device: str = "cpu",
        det_thresh: float = 0.5,
        liveness_thresh: float = 0.5,
        liveness_model_path: str | Path = _DEFAULT_LIVENESS_PATH,
    ) -> None:
        from insightface.app import FaceAnalysis

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
        """Detect and analyze faces in a BGR image array (H, W, 3)."""
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
```

Keep the existing `analyze_image_file` stub for Task 5 and the implemented `cosine_similarity` from Task 2.

- [ ] **Step 4: Run to verify it passes**

Run: `pytest facecore/tests/test_analyze_unit.py facecore/tests/test_cosine.py -v`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add facecore/src/facecore/analyzer.py facecore/tests/test_analyze_unit.py
git commit -m "feat(facecore): implement FaceAnalyzer init + analyze"
```

---

### Task 5: `analyze_image_file` + public exports

**Files:**
- Modify: `facecore/src/facecore/analyzer.py` (`analyze_image_file`)
- Modify: `facecore/src/facecore/__init__.py`
- Test: `facecore/tests/test_analyze_file.py`

- [ ] **Step 1: Write the failing test**

```python
# facecore/tests/test_analyze_file.py
import cv2
import numpy as np
import pytest
from facecore.analyzer import FaceAnalyzer


def _analyzer_recording():
    captured = {}

    def fake_analyze(image):
        captured["shape"] = image.shape
        return ["sentinel"]

    a = FaceAnalyzer.__new__(FaceAnalyzer)
    a.analyze = fake_analyze  # type: ignore[method-assign]
    return a, captured


def test_analyze_image_file_reads_and_delegates(tmp_path):
    img_path = tmp_path / "x.png"
    cv2.imwrite(str(img_path), np.zeros((20, 20, 3), dtype=np.uint8))
    a, captured = _analyzer_recording()
    out = a.analyze_image_file(str(img_path))
    assert out == ["sentinel"]
    assert captured["shape"] == (20, 20, 3)


def test_analyze_image_file_missing_raises():
    a, _ = _analyzer_recording()
    with pytest.raises(FileNotFoundError):
        a.analyze_image_file("/no/such/file.jpg")
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest facecore/tests/test_analyze_file.py -v`
Expected: FAIL — `NotImplementedError`.

- [ ] **Step 3: Implement** — replace `analyze_image_file` body

```python
    def analyze_image_file(self, filepath: str) -> list[DetectedFace]:
        """Detect and analyze faces from an image file path."""
        path = Path(filepath)
        if not path.is_file():
            raise FileNotFoundError(filepath)
        image = cv2.imread(str(path))
        if image is None:
            raise ValueError(f"not a readable image: {filepath}")
        return self.analyze(image)
```

Add `import cv2` to the top of `analyzer.py`.

Then set exports:

```python
# facecore/src/facecore/__init__.py
"""facecore — pure face detection, embedding, and liveness engine."""

from facecore.analyzer import MODEL_VERSION, FaceAnalyzer
from facecore.exceptions import (
    FaceCoreError,
    LowQualityError,
    MultipleFacesError,
    NoFaceError,
)
from facecore.models import DetectedFace

__all__ = [
    "FaceAnalyzer",
    "DetectedFace",
    "MODEL_VERSION",
    "FaceCoreError",
    "NoFaceError",
    "MultipleFacesError",
    "LowQualityError",
]
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest facecore/tests/test_analyze_file.py -v && python -c "import facecore; print(facecore.MODEL_VERSION)"`
Expected: PASS (2 tests); prints `buffalo_l`.

- [ ] **Step 5: Commit**

```bash
git add facecore/src/facecore/analyzer.py facecore/src/facecore/__init__.py facecore/tests/test_analyze_file.py
git commit -m "feat(facecore): implement analyze_image_file and public exports"
```

---

### Task 6: Integration test against real models (committed fixtures)

**Files:**
- Create: `facecore/tests/fixtures/same_person_1.jpg`, `same_person_2.jpg`, `different_person.jpg`, `printed_photo.jpg`
- Create: `facecore/tests/conftest.py`
- Test: `facecore/tests/test_integration.py`

**Note:** These tests require the buffalo_l pack (~300 MB) and `models/minifasnet.onnx`. See `docs/operations.md` (Task 22) for the download commands. They are marked `integration` and excluded from the default unit run.

- [ ] **Step 1: Register the marker and a shared analyzer fixture**

```python
# facecore/tests/conftest.py
import os
import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: requires downloaded models")


@pytest.fixture(scope="session")
def analyzer():
    if os.getenv("FACECORE_RUN_INTEGRATION") != "1":
        pytest.skip("set FACECORE_RUN_INTEGRATION=1 to run model-backed tests")
    from facecore import FaceAnalyzer

    return FaceAnalyzer(device="cpu")
```

- [ ] **Step 2: Write the integration test**

```python
# facecore/tests/test_integration.py
from pathlib import Path

import pytest

FIX = Path(__file__).parent / "fixtures"


@pytest.mark.integration
def test_same_person_high_similarity(analyzer):
    f1 = analyzer.analyze_image_file(str(FIX / "same_person_1.jpg"))
    f2 = analyzer.analyze_image_file(str(FIX / "same_person_2.jpg"))
    assert len(f1) == 1 and len(f2) == 1
    sim = analyzer.cosine_similarity(f1[0].embedding, f2[0].embedding)
    assert sim > 0.45


@pytest.mark.integration
def test_different_person_low_similarity(analyzer):
    f1 = analyzer.analyze_image_file(str(FIX / "same_person_1.jpg"))
    f2 = analyzer.analyze_image_file(str(FIX / "different_person.jpg"))
    sim = analyzer.cosine_similarity(f1[0].embedding, f2[0].embedding)
    assert sim < 0.45


@pytest.mark.integration
def test_printed_photo_low_liveness(analyzer):
    faces = analyzer.analyze_image_file(str(FIX / "printed_photo.jpg"))
    assert len(faces) >= 1
    assert faces[0].liveness_score < 0.5
```

- [ ] **Step 3: Add fixture images**

Place four small face JPEGs in `facecore/tests/fixtures/`:
- `same_person_1.jpg`, `same_person_2.jpg` — two photos of the same consenting person.
- `different_person.jpg` — a different person.
- `printed_photo.jpg` — a photo of a printed/screen face (for the spoof case).

Use your own/team consenting photos. Keep each < 200 KB.

- [ ] **Step 4: Verify default run skips, integration run can be invoked**

Run: `pytest facecore/tests/test_integration.py -v`
Expected: 3 SKIPPED (env var unset).

Run (after models downloaded per Task 22): `FACECORE_RUN_INTEGRATION=1 pytest facecore/tests/test_integration.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add facecore/tests/conftest.py facecore/tests/test_integration.py facecore/tests/fixtures
git commit -m "test(facecore): add model-backed integration tests with fixtures"
```

---

### Task 7: Full facecore suite green

- [ ] **Step 1: Run the unit suite**

Run: `cd /Users/saurabh/facerecog && source venv/bin/activate && pytest facecore -v`
Expected: all unit tests PASS, integration tests SKIPPED.

- [ ] **Step 2: Lint + type-check**

Run: `ruff check facecore/src && mypy facecore/src/facecore`
Expected: no errors. Fix any reported issues inline, then re-run.

- [ ] **Step 3: Commit any lint fixes**

```bash
git add -A facecore && git commit -m "chore(facecore): lint and type-check clean" || echo "nothing to commit"
```

---

# Phase 2 — embedding_service

### Task 8: Config module

**Files:**
- Create: `embedding_service/src/embedding_service/config.py`
- Test: `embedding_service/tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# embedding_service/tests/test_config.py
from embedding_service.config import Settings


def test_defaults(monkeypatch):
    monkeypatch.delenv("EMBEDDING_SERVICE_SECRET", raising=False)
    monkeypatch.delenv("EMBEDDING_SERVICE_DEVICE", raising=False)
    s = Settings.from_env()
    assert s.secret is None
    assert s.device == "cpu"
    assert s.min_det_score == 0.5


def test_reads_env(monkeypatch):
    monkeypatch.setenv("EMBEDDING_SERVICE_SECRET", "topsecret")
    monkeypatch.setenv("EMBEDDING_SERVICE_DEVICE", "cuda")
    s = Settings.from_env()
    assert s.secret == "topsecret"
    assert s.device == "cuda"
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest embedding_service/tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

```python
# embedding_service/src/embedding_service/config.py
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest embedding_service/tests/test_config.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add embedding_service/src/embedding_service/config.py embedding_service/tests/test_config.py
git commit -m "feat(embedding_service): add env-driven settings"
```

---

### Task 9: `/embed` endpoint (facecore + analyzer injected)

**Files:**
- Modify: `embedding_service/src/embedding_service/app.py`
- Test: `embedding_service/tests/test_embed.py`

**Design:** The analyzer is expensive to build, so it is created once via FastAPI dependency injection (`get_analyzer`) and overridden with a fake in tests. `/embed` enforces: optional `X-Secret` (401 if configured and mismatched), exactly one face above `min_det_score` (400 otherwise). Returns embedding + scores + `model_version`.

- [ ] **Step 1: Write the failing tests**

```python
# embedding_service/tests/test_embed.py
import io

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from embedding_service.app import app, get_analyzer, get_settings
from embedding_service.config import Settings
from facecore.models import DetectedFace


def _png_bytes():
    buf = io.BytesIO()
    Image.fromarray(np.zeros((40, 40, 3), dtype=np.uint8)).save(buf, format="PNG")
    return buf.getvalue()


class _Analyzer:
    def __init__(self, faces):
        self._faces = faces

    def analyze(self, image):
        return self._faces


def _face():
    return DetectedFace(bbox=[0, 0, 10, 10], embedding=[0.1] * 512,
                        det_score=0.9, liveness_score=0.8)


def _client(faces, settings=None):
    settings = settings or Settings(secret=None, device="cpu", min_det_score=0.5)
    app.dependency_overrides[get_analyzer] = lambda: _Analyzer(faces)
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def test_single_face_returns_embedding():
    client = _client([_face()])
    r = client.post("/embed", files={"file": ("x.png", _png_bytes(), "image/png")})
    assert r.status_code == 200
    body = r.json()
    assert len(body["embedding"]) == 512
    assert body["det_score"] == 0.9
    assert body["model_version"] == "buffalo_l"


def test_no_face_is_400():
    client = _client([])
    r = client.post("/embed", files={"file": ("x.png", _png_bytes(), "image/png")})
    assert r.status_code == 400


def test_multiple_faces_is_400():
    client = _client([_face(), _face()])
    r = client.post("/embed", files={"file": ("x.png", _png_bytes(), "image/png")})
    assert r.status_code == 400


def test_low_det_score_is_400():
    low = DetectedFace(bbox=[0, 0, 1, 1], embedding=[0.1] * 512,
                       det_score=0.2, liveness_score=0.5)
    client = _client([low])
    r = client.post("/embed", files={"file": ("x.png", _png_bytes(), "image/png")})
    assert r.status_code == 400


def test_secret_enforced_when_configured():
    client = _client([_face()], Settings(secret="s3cret", device="cpu", min_det_score=0.5))
    r = client.post("/embed", files={"file": ("x.png", _png_bytes(), "image/png")})
    assert r.status_code == 401
    r2 = client.post("/embed", files={"file": ("x.png", _png_bytes(), "image/png")},
                     headers={"X-Secret": "s3cret"})
    assert r2.status_code == 200
```

- [ ] **Step 2: Add Pillow to dev deps and install**

In `embedding_service/pyproject.toml`, add `"pillow>=10.0.0"` to the `dev` optional-dependencies list. Then:

Run: `pip install -e "embedding_service/[dev]"`
Expected: installs Pillow.

- [ ] **Step 3: Run to verify it fails**

Run: `pytest embedding_service/tests/test_embed.py -v`
Expected: FAIL — `/embed` raises `NotImplementedError` (and `get_analyzer`/`get_settings` undefined).

- [ ] **Step 4: Implement** — rewrite `app.py`

```python
"""FastAPI application for the embedding service."""

from __future__ import annotations

import io

import cv2
import numpy as np
from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from pydantic import BaseModel

from embedding_service.config import Settings
from facecore import MODEL_VERSION, FaceAnalyzer

app = FastAPI(
    title="Embedding Service",
    description="Compute face embeddings from images",
    version="0.1.0",
)

_settings = Settings.from_env()
_analyzer: FaceAnalyzer | None = None


def get_settings() -> Settings:
    return _settings


def get_analyzer() -> FaceAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = FaceAnalyzer(device=_settings.device)
    return _analyzer


class EmbeddingResponse(BaseModel):
    embedding: list[float]
    det_score: float
    liveness_score: float
    model_version: str


@app.post("/embed", response_model=EmbeddingResponse)
async def embed(
    file: UploadFile = File(...),
    x_secret: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
    analyzer: FaceAnalyzer = Depends(get_analyzer),
) -> EmbeddingResponse:
    if settings.secret is not None and x_secret != settings.secret:
        raise HTTPException(status_code=401, detail="invalid secret")

    raw = await file.read()
    arr = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    if arr is None:
        raise HTTPException(status_code=422, detail="invalid image")

    faces = [f for f in analyzer.analyze(arr) if f.det_score >= settings.min_det_score]
    if len(faces) == 0:
        raise HTTPException(status_code=400, detail="no face detected")
    if len(faces) > 1:
        raise HTTPException(status_code=400, detail="multiple faces detected")

    face = faces[0]
    return EmbeddingResponse(
        embedding=face.embedding,
        det_score=face.det_score,
        liveness_score=face.liveness_score,
        model_version=MODEL_VERSION,
    )


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": "0.1.0"}
```

- [ ] **Step 5: Run to verify it passes**

Run: `pytest embedding_service/tests/test_embed.py embedding_service/tests/test_config.py -v`
Expected: PASS (all).

- [ ] **Step 6: Lint + commit**

```bash
ruff check embedding_service/src
git add embedding_service/src/embedding_service/app.py embedding_service/pyproject.toml embedding_service/tests/test_embed.py
git commit -m "feat(embedding_service): implement /embed with auth and face validation"
```

---

# Phase 3 — face_attendance Frappe app

> All commands in this phase run from `~/frappe-bench`. The Frappe app uses the bench's Python 3.14 and has **no AI dependencies** — only `requests`.

### Task 10: Create the app, set `required_apps`, install

**Files:**
- Create: `~/frappe-bench/apps/face_attendance/` (via `bench new-app`)
- Modify: `~/frappe-bench/apps/face_attendance/face_attendance/hooks.py`

- [ ] **Step 1: Create the app**

```bash
cd ~/frappe-bench
bench new-app face_attendance --no-git
```

When prompted, accept defaults (App Title: Face Attendance; publisher/email/license as you like).

- [ ] **Step 2: Set `required_apps` in `hooks.py`**

Edit `~/frappe-bench/apps/face_attendance/face_attendance/hooks.py` — find the commented `required_apps` line (or add near the top app-metadata block):

```python
required_apps = ["frappe", "erpnext", "hrms"]
```

- [ ] **Step 3: Install on the site + migrate**

```bash
cd ~/frappe-bench
bench --site site1.localhost install-app face_attendance
bench --site site1.localhost migrate
```

Expected: installs without error.

- [ ] **Step 4: Verify it is installed**

Run: `bench --site site1.localhost list-apps`
Expected: `face_attendance` appears in the list.

- [ ] **Step 5: Commit (app has its own git)**

```bash
cd ~/frappe-bench/apps/face_attendance
git init -q && git add -A
git commit -q -m "feat: scaffold face_attendance app with required_apps"
```

---

### Task 11: Face Recognition Settings (Single DocType)

**Files:**
- Create via UI or JSON: `.../face_attendance/face_attendance/doctype/face_recognition_settings/face_recognition_settings.json`
- Create: matching `.py` controller (empty)

- [ ] **Step 1: Enable developer mode (if not already)**

```bash
cd ~/frappe-bench
bench --site site1.localhost set-config developer_mode 1
bench --site site1.localhost clear-cache
```

- [ ] **Step 2: Create the Single DocType in the app's `Face Attendance` module**

> **Module ownership (validated against frappe 16.19 / hrms 16.7):** `bench new-app face_attendance` auto-creates a module **`Face Attendance`** (in `modules.txt`). Do **not** use module `HR` — that module is owned by the `hrms` app (`get_module_app("HR") → "hrms"`), so a DocType declaring `module: "HR"` resolves its controller to `hrms.hr.doctype.*` and `face_attendance`'s migrate never syncs it. All DocTypes/Reports here use module `Face Attendance`, with files under `face_attendance/face_attendance/<doctype|report>/…`.

Create the DocType JSON at `.../face_attendance/face_attendance/doctype/face_recognition_settings/face_recognition_settings.json`. (Either via Desk → New DocType with the fields below and `issingle=1`, then it auto-writes the file in developer mode; or write the file directly and migrate.)

```json
{
 "actions": [],
 "creation": "2026-06-02 00:00:00",
 "doctype": "DocType",
 "engine": "InnoDB",
 "field_order": [
  "embedding_service_url",
  "embedding_service_secret",
  "match_threshold",
  "liveness_threshold",
  "min_det_score",
  "punch_debounce_minutes"
 ],
 "fields": [
  {"fieldname": "embedding_service_url", "fieldtype": "Data", "label": "Embedding Service URL", "default": "http://localhost:8080", "reqd": 1},
  {"fieldname": "embedding_service_secret", "fieldtype": "Password", "label": "Embedding Service Secret"},
  {"fieldname": "match_threshold", "fieldtype": "Float", "label": "Match Threshold", "default": "0.45"},
  {"fieldname": "liveness_threshold", "fieldtype": "Float", "label": "Liveness Threshold", "default": "0.60"},
  {"fieldname": "min_det_score", "fieldtype": "Float", "label": "Min Detection Score", "default": "0.50"},
  {"fieldname": "punch_debounce_minutes", "fieldtype": "Int", "label": "Punch Debounce Minutes", "default": "2"}
 ],
 "issingle": 1,
 "module": "Face Attendance",
 "name": "Face Recognition Settings",
 "owner": "Administrator",
 "permissions": [
  {"role": "System Manager", "read": 1, "write": 1, "create": 1},
  {"role": "HR Manager", "read": 1, "write": 1}
 ],
 "sort_field": "modified",
 "sort_order": "DESC"
}
```

```python
# face_recognition_settings.py
import frappe
from frappe.model.document import Document


class FaceRecognitionSettings(Document):
    pass
```

- [ ] **Step 3: Migrate and verify**

```bash
cd ~/frappe-bench
bench --site site1.localhost migrate
bench --site site1.localhost execute frappe.client.get_single_value --kwargs "{'doctype':'Face Recognition Settings','field':'match_threshold'}"
```

Expected: prints `0.45`.

- [ ] **Step 4: Commit**

```bash
cd ~/frappe-bench/apps/face_attendance
git add -A && git commit -q -m "feat: add Face Recognition Settings single doctype"
```

---

### Task 12: Employee Face Profile DocType (schema only)

**Files:**
- Create: `.../face_attendance/doctype/employee_face_profile/employee_face_profile.json`
- Create: `.../face_attendance/doctype/employee_face_profile/employee_face_profile.py` (empty controller for now)

- [ ] **Step 1: Create the DocType JSON**

```json
{
 "actions": [],
 "autoname": "field:employee",
 "creation": "2026-06-02 00:00:00",
 "doctype": "DocType",
 "engine": "InnoDB",
 "field_order": [
  "employee", "enrollment_image", "embedding", "model_version",
  "det_score", "liveness_score", "enrolled_on"
 ],
 "fields": [
  {"fieldname": "employee", "fieldtype": "Link", "options": "Employee", "label": "Employee", "reqd": 1, "unique": 1, "in_list_view": 1},
  {"fieldname": "enrollment_image", "fieldtype": "Attach Image", "label": "Enrollment Image"},
  {"fieldname": "embedding", "fieldtype": "Long Text", "label": "Embedding", "read_only": 1},
  {"fieldname": "model_version", "fieldtype": "Data", "label": "Model Version", "read_only": 1},
  {"fieldname": "det_score", "fieldtype": "Float", "label": "Detection Score", "read_only": 1},
  {"fieldname": "liveness_score", "fieldtype": "Float", "label": "Liveness Score", "read_only": 1},
  {"fieldname": "enrolled_on", "fieldtype": "Datetime", "label": "Enrolled On", "read_only": 1}
 ],
 "module": "Face Attendance",
 "name": "Employee Face Profile",
 "owner": "Administrator",
 "permissions": [
  {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1},
  {"role": "HR Manager", "read": 1, "write": 1, "create": 1, "delete": 1},
  {"role": "HR User", "read": 1, "write": 1, "create": 1}
 ],
 "sort_field": "modified",
 "sort_order": "DESC",
 "track_changes": 1
}
```

```python
# employee_face_profile.py
import frappe
from frappe.model.document import Document


class EmployeeFaceProfile(Document):
    pass
```

- [ ] **Step 2: Migrate and verify the table exists**

```bash
cd ~/frappe-bench
bench --site site1.localhost migrate
bench --site site1.localhost execute frappe.db.get_table_columns --kwargs "{'doctype':'Employee Face Profile'}"
```

Expected: lists columns including `employee`, `embedding`, `model_version`.

- [ ] **Step 3: Commit**

```bash
cd ~/frappe-bench/apps/face_attendance
git add -A && git commit -q -m "feat: add Employee Face Profile doctype schema"
```

---

### Task 13: Enrollment controller (`validate`) — TDD with mocked service

**Files:**
- Modify: `.../employee_face_profile/employee_face_profile.py`
- Test: `.../employee_face_profile/test_employee_face_profile.py`

**Design:** On `validate`, if `enrollment_image` changed (or embedding is empty), read the attached file bytes, POST to the embedding service, validate the response (single face implied by service; `det_score >= min_det_score`), and store `embedding`/`model_version`/`det_score`/`liveness_score`/`enrolled_on`. Also require the linked Employee to have a non-blank `attendance_device_id`. HTTP uses a hard 10s timeout. On any failure: `frappe.log_error` then `frappe.throw` a generic message. Liveness is **not** gated here.

- [ ] **Step 1: Write the failing test**

```python
# test_employee_face_profile.py
import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase


def _make_employee(device_id):
    emp = frappe.get_doc({
        "doctype": "Employee",
        "first_name": "Face",
        "last_name": "Tester",
        "company": frappe.defaults.get_global_default("company") or frappe.get_all("Company", limit=1)[0].name,
        "date_of_joining": "2024-01-01",
        "date_of_birth": "1990-01-01",
        "gender": "Other",
        "status": "Active",
        "attendance_device_id": device_id,
    }).insert(ignore_permissions=True)
    return emp


class _Resp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


class TestEmployeeFaceProfile(FrappeTestCase):
    def test_blank_device_id_rejected(self):
        emp = _make_employee("")
        prof = frappe.get_doc({
            "doctype": "Employee Face Profile",
            "employee": emp.name,
            "enrollment_image": "/files/fake.jpg",
        })
        with self.assertRaises(frappe.ValidationError):
            prof.insert(ignore_permissions=True)

    @patch("face_attendance.face_attendance.doctype.employee_face_profile.employee_face_profile._read_image_bytes",
           return_value=b"jpegbytes")
    @patch("face_attendance.face_attendance.doctype.employee_face_profile.employee_face_profile.requests.post")
    def test_successful_enrollment_stores_embedding(self, mock_post, _read):
        mock_post.return_value = _Resp(200, {
            "embedding": [0.1] * 512, "det_score": 0.9,
            "liveness_score": 0.7, "model_version": "buffalo_l",
        })
        emp = _make_employee("EMP-DEV-1")
        prof = frappe.get_doc({
            "doctype": "Employee Face Profile",
            "employee": emp.name,
            "enrollment_image": "/files/fake.jpg",
        }).insert(ignore_permissions=True)
        self.assertEqual(len(json.loads(prof.embedding)), 512)
        self.assertEqual(prof.model_version, "buffalo_l")
        self.assertEqual(prof.det_score, 0.9)

    @patch("face_attendance.face_attendance.doctype.employee_face_profile.employee_face_profile._read_image_bytes",
           return_value=b"jpegbytes")
    @patch("face_attendance.face_attendance.doctype.employee_face_profile.employee_face_profile.requests.post")
    def test_low_det_score_rejected(self, mock_post, _read):
        mock_post.return_value = _Resp(400, {"detail": "no face detected"})
        emp = _make_employee("EMP-DEV-2")
        prof = frappe.get_doc({
            "doctype": "Employee Face Profile",
            "employee": emp.name,
            "enrollment_image": "/files/fake.jpg",
        })
        with self.assertRaises(frappe.ValidationError):
            prof.insert(ignore_permissions=True)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd ~/frappe-bench && bench --site site1.localhost run-tests --app face_attendance --module face_attendance.face_attendance.doctype.employee_face_profile.test_employee_face_profile`
Expected: FAIL — controller does not enforce anything yet.

- [ ] **Step 3: Implement the controller**

```python
# employee_face_profile.py
import json

import frappe
import requests
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

_TIMEOUT_SECONDS = 10


def _read_image_bytes(file_url: str) -> bytes:
    """Read the bytes of an attached file by its file URL."""
    file_doc = frappe.get_doc("File", {"file_url": file_url})
    return file_doc.get_content()


class EmployeeFaceProfile(Document):
    def validate(self):
        device_id = frappe.db.get_value("Employee", self.employee, "attendance_device_id")
        if not device_id:
            frappe.throw(
                _("Employee {0} has no Attendance Device ID. Set it before enrolling a face.")
                .format(self.employee)
            )

        needs_embed = self.has_value_changed("enrollment_image") or not self.embedding
        if not (self.enrollment_image and needs_embed):
            return

        settings = frappe.get_single("Face Recognition Settings")
        try:
            image_bytes = _read_image_bytes(self.enrollment_image)
            headers = {}
            secret = settings.get_password("embedding_service_secret", raise_exception=False)
            if secret:
                headers["X-Secret"] = secret
            resp = requests.post(
                f"{settings.embedding_service_url.rstrip('/')}/embed",
                files={"file": ("enrollment.jpg", image_bytes, "image/jpeg")},
                headers=headers,
                timeout=_TIMEOUT_SECONDS,
            )
        except Exception:
            # v16 log_error(title, message) — pass by keyword (explicit > relying
            # on Frappe's newline-based title/message auto-swap heuristic).
            frappe.log_error(title="face_attendance.enroll", message=frappe.get_traceback())
            frappe.throw(_("Could not reach the face embedding service. Try again later."))

        if resp.status_code != 200:
            frappe.log_error(
                title="face_attendance.enroll",
                message=f"embed status {resp.status_code}: {resp.text}",
            )
            frappe.throw(_("Enrollment image rejected: no clear single face detected."))

        data = resp.json()
        if data.get("det_score", 0) < (settings.min_det_score or 0.5):
            frappe.throw(_("Enrollment image quality too low. Use a clear front-facing photo."))

        self.embedding = json.dumps(data["embedding"])
        self.model_version = data["model_version"]
        self.det_score = data["det_score"]
        self.liveness_score = data.get("liveness_score")
        self.enrolled_on = now_datetime()
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd ~/frappe-bench && bench --site site1.localhost run-tests --app face_attendance --module face_attendance.face_attendance.doctype.employee_face_profile.test_employee_face_profile`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
cd ~/frappe-bench/apps/face_attendance
git add -A && git commit -q -m "feat: enrollment controller posts to embedding service and stores vector"
```

---

### Task 14: "Face Edge Device" Role + Custom DocPerm fixtures

**Files:**
- Modify: `.../face_attendance/hooks.py` (`fixtures`)
- Create: `.../face_attendance/fixtures/role.json`
- Create: `.../face_attendance/fixtures/custom_docperm.json`

- [ ] **Step 1: Create the Role via console, then the Custom DocPerm**

```bash
cd ~/frappe-bench
bench --site site1.localhost console
```

In the console:

```python
import frappe
if not frappe.db.exists("Role", "Face Edge Device"):
    frappe.get_doc({"doctype": "Role", "role_name": "Face Edge Device",
                    "desk_access": 0}).insert()
# Custom DocPerm: create + read on Employee Checkin for the edge role
frappe.get_doc({
    "doctype": "Custom DocPerm",
    "parent": "Employee Checkin", "parenttype": "DocType", "parentfield": "permissions",
    "role": "Face Edge Device", "permlevel": 0, "read": 1, "create": 1,
}).insert()
frappe.db.commit()
exit()
```

- [ ] **Step 2: Declare fixtures in `hooks.py`**

```python
fixtures = [
    {"dt": "Role", "filters": [["name", "=", "Face Edge Device"]]},
    {"dt": "Custom DocPerm", "filters": [["role", "=", "Face Edge Device"]]},
]
```

- [ ] **Step 3: Export fixtures**

```bash
cd ~/frappe-bench
bench --site site1.localhost export-fixtures --app face_attendance
```

Expected: writes `fixtures/role.json` and `fixtures/custom_docperm.json`.

- [ ] **Step 4: Verify the fixture files contain the expected entries**

Run: `cat ~/frappe-bench/apps/face_attendance/face_attendance/fixtures/custom_docperm.json`
Expected: a Custom DocPerm with `"role": "Face Edge Device"`, `"create": 1`, `"read": 1`, parent `Employee Checkin`.

- [ ] **Step 5: Commit**

```bash
cd ~/frappe-bench/apps/face_attendance
git add -A && git commit -q -m "feat: ship Face Edge Device role + Custom DocPerm fixtures"
```

---

### Task 15: Permission test — edge user can create Employee Checkin, nothing else

**Files:**
- Create: `.../face_attendance/tests/__init__.py`
- Create: `.../face_attendance/tests/test_permissions.py`

- [ ] **Step 1: Write the failing test**

```python
# test_permissions.py
import frappe
from frappe.tests.utils import FrappeTestCase


def _edge_user():
    email = "edge-device@example.com"
    if not frappe.db.exists("User", email):
        u = frappe.get_doc({
            "doctype": "User", "email": email, "first_name": "Edge",
            "send_welcome_email": 0,
        })
        u.insert(ignore_permissions=True)
        u.add_roles("Face Edge Device")
    return email


class TestEdgePermissions(FrappeTestCase):
    def test_edge_user_can_create_employee_checkin(self):
        frappe.set_user(_edge_user())
        try:
            self.assertTrue(frappe.has_permission("Employee Checkin", "create"))
        finally:
            frappe.set_user("Administrator")

    def test_edge_user_cannot_write_salary_structure(self):
        frappe.set_user(_edge_user())
        try:
            self.assertFalse(frappe.has_permission("Salary Structure", "write"))
        finally:
            frappe.set_user("Administrator")
```

- [ ] **Step 2: Run to verify it passes (fixtures already grant the permission)**

Run: `cd ~/frappe-bench && bench --site site1.localhost run-tests --app face_attendance --module face_attendance.tests.test_permissions`
Expected: PASS (2 tests). If `test_edge_user_can_create_employee_checkin` fails, the Custom DocPerm from Task 14 was not applied — run `bench --site site1.localhost migrate` and retry.

- [ ] **Step 3: Commit**

```bash
cd ~/frappe-bench/apps/face_attendance
git add -A && git commit -q -m "test: verify edge role least-privilege on Employee Checkin"
```

---

### Task 16: `get_face_data` sync API — TDD

**Files:**
- Create: `.../face_attendance/api.py`
- Create: `.../face_attendance/tests/test_sync_api.py`

**Design:** `@frappe.whitelist(methods=["GET"])`. First line: `frappe.only_for(["Face Edge Device", "System Manager"])`. Returns `[{attendance_device_id, employee, embedding, model_version, modified}]`. Incremental via `since` (returns rows with `modified > since`). Employees with blank `attendance_device_id` are excluded.

- [ ] **Step 1: Write the failing test**

```python
# test_sync_api.py
import json

import frappe
from frappe.tests.utils import FrappeTestCase

from face_attendance.api import get_face_data


def _enrolled_profile(device_id, suffix):
    company = frappe.get_all("Company", limit=1)[0].name
    emp = frappe.get_doc({
        "doctype": "Employee", "first_name": f"Sync{suffix}",
        "company": company, "date_of_joining": "2024-01-01",
        "date_of_birth": "1990-01-01", "gender": "Other", "status": "Active",
        "attendance_device_id": device_id,
    }).insert(ignore_permissions=True)
    prof = frappe.get_doc({
        "doctype": "Employee Face Profile", "employee": emp.name,
        "embedding": json.dumps([0.1] * 512), "model_version": "buffalo_l",
    })
    prof.flags.ignore_validate = True  # skip embedding-service call in this test
    prof.insert(ignore_permissions=True)
    return emp, prof


class TestSyncApi(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")  # System Manager passes only_for

    def test_returns_enrolled_rows(self):
        emp, _ = _enrolled_profile("SYNC-1", "1")
        rows = get_face_data()
        match = [r for r in rows if r["attendance_device_id"] == "SYNC-1"]
        self.assertEqual(len(match), 1)
        self.assertEqual(match[0]["employee"], emp.name)
        self.assertEqual(len(json.loads(match[0]["embedding"])), 512)
        self.assertEqual(match[0]["model_version"], "buffalo_l")

    def test_since_filter_excludes_old(self):
        _enrolled_profile("SYNC-2", "2")
        future = "2099-01-01 00:00:00"
        rows = get_face_data(since=future)
        self.assertEqual([r for r in rows if r["attendance_device_id"] == "SYNC-2"], [])

    def test_unauthorized_role_blocked(self):
        email = "plain-user@example.com"
        if not frappe.db.exists("User", email):
            frappe.get_doc({"doctype": "User", "email": email,
                            "first_name": "Plain", "send_welcome_email": 0}).insert(ignore_permissions=True)
        frappe.set_user(email)
        try:
            with self.assertRaises(frappe.PermissionError):
                get_face_data()
        finally:
            frappe.set_user("Administrator")
```

> The controller's `validate` honours `flags.ignore_validate` automatically (Frappe skips `validate()` when that flag is set), so these sync tests do not hit the embedding service.

- [ ] **Step 2: Run to verify it fails**

Run: `cd ~/frappe-bench && bench --site site1.localhost run-tests --app face_attendance --module face_attendance.tests.test_sync_api`
Expected: FAIL — `face_attendance.api` does not exist.

- [ ] **Step 3: Implement**

```python
# face_attendance/api.py
import frappe


@frappe.whitelist(methods=["GET"])
def get_face_data(since: str | None = None):
    """Return enrolled face embeddings for edge devices.

    Authorization: restricted to the Face Edge Device role (and System Manager).
    Without this gate, any logged-in user could pull biometric embeddings.
    """
    frappe.only_for(["Face Edge Device", "System Manager"])

    filters: dict = {"embedding": ["is", "set"]}
    if since:
        filters["modified"] = [">", since]

    profiles = frappe.get_all(
        "Employee Face Profile",
        filters=filters,
        fields=["employee", "embedding", "model_version", "modified"],
    )

    # Resolve all device ids in one query — avoid an N+1 lookup per profile.
    employee_ids = [p.employee for p in profiles]
    device_ids = (
        dict(
            frappe.get_all(
                "Employee",
                filters={"name": ["in", employee_ids]},
                fields=["name", "attendance_device_id"],
                as_list=True,
            )
        )
        if employee_ids
        else {}
    )

    rows = []
    for p in profiles:
        device_id = device_ids.get(p.employee)
        if not device_id:
            continue  # cannot check in without a device id; excluded by design
        rows.append({
            "attendance_device_id": device_id,
            "employee": p.employee,
            "embedding": p.embedding,
            "model_version": p.model_version,
            "modified": str(p.modified),
        })
    return rows
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd ~/frappe-bench && bench --site site1.localhost run-tests --app face_attendance --module face_attendance.tests.test_sync_api`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
cd ~/frappe-bench/apps/face_attendance
git add -A && git commit -q -m "feat: add role-gated get_face_data sync endpoint"
```

---

### Task 17: Model-version drift report

**Files:**
- Create: `.../face_attendance/face_attendance/report/face_profiles_needing_reenrollment/face_profiles_needing_reenrollment.json`
- Create: matching `.py`

**Design:** A Query/Script Report listing profiles whose `model_version` differs from the current service version (passed as a filter, default `buffalo_l`). No auto re-embedding (v1 non-goal).

- [ ] **Step 1: Create the report (Script Report) JSON**

```json
{
 "doctype": "Report",
 "report_name": "Face Profiles Needing Reenrollment",
 "ref_doctype": "Employee Face Profile",
 "report_type": "Script Report",
 "module": "Face Attendance",
 "is_standard": "Yes",
 "roles": [{"role": "HR Manager"}, {"role": "System Manager"}]
}
```

- [ ] **Step 2: Implement the report controller**

```python
# face_profiles_needing_reenrollment.py
import frappe

CURRENT_MODEL = "buffalo_l"


def execute(filters=None):
    filters = filters or {}
    target = filters.get("current_model") or CURRENT_MODEL
    columns = [
        {"label": "Profile", "fieldname": "name", "fieldtype": "Link", "options": "Employee Face Profile", "width": 200},
        {"label": "Employee", "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 200},
        {"label": "Model Version", "fieldname": "model_version", "fieldtype": "Data", "width": 150},
    ]
    rows = frappe.get_all(
        "Employee Face Profile",
        filters={"model_version": ["!=", target]},
        fields=["name", "employee", "model_version"],
    )
    return columns, rows
```

- [ ] **Step 3: Migrate and smoke-test the report**

```bash
cd ~/frappe-bench
bench --site site1.localhost migrate
bench --site site1.localhost execute "frappe.desk.query_report.run" --kwargs "{'report_name':'Face Profiles Needing Reenrollment'}"
```

Expected: returns a result dict with `columns` and `result` keys (empty result if all profiles are current).

- [ ] **Step 4: Commit**

```bash
cd ~/frappe-bench/apps/face_attendance
git add -A && git commit -q -m "feat: add model-version drift re-enrollment report"
```

---

### Task 18: Full face_attendance suite + migrate clean

- [ ] **Step 1: Run the whole app test suite**

Run: `cd ~/frappe-bench && bench --site site1.localhost run-tests --app face_attendance`
Expected: all tests PASS.

- [ ] **Step 2: Fresh migrate to confirm no schema drift**

Run: `cd ~/frappe-bench && bench --site site1.localhost migrate`
Expected: completes without error.

- [ ] **Step 3: Commit any fixes**

```bash
cd ~/frappe-bench/apps/face_attendance
git add -A && git commit -q -m "chore: face_attendance suite green" || echo "nothing to commit"
```

---

# Phase 4 — edge_client

> Back in the AI repo with the 3.11 venv active: `cd /Users/saurabh/facerecog && source venv/bin/activate`.

### Task 19: Config loader

**Files:**
- Create: `edge_client/src/edge_client/config.py`
- Test: `edge_client/tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# edge_client/tests/test_config.py
import textwrap

import pytest
from edge_client.config import EdgeConfig, load_config


def _write(tmp_path, text):
    p = tmp_path / "config.yaml"
    p.write_text(textwrap.dedent(text))
    return str(p)


def test_load_valid_config(tmp_path):
    path = _write(tmp_path, """
        frappe:
          url: http://localhost:8000
          site: site1.localhost
          api_key: k
          api_secret: s
        edge:
          id: edge-001
          camera_index: 0
          sync_interval: 300
        matching:
          threshold: 0.45
          liveness_threshold: 0.6
          min_det_score: 0.5
          debounce_minutes: 2
        offline:
          db_path: /tmp/queue.sqlite
    """)
    cfg = load_config(path)
    assert isinstance(cfg, EdgeConfig)
    assert cfg.frappe_url == "http://localhost:8000"
    assert cfg.edge_id == "edge-001"
    assert cfg.threshold == 0.45
    assert cfg.db_path == "/tmp/queue.sqlite"


def test_missing_required_key_raises(tmp_path):
    path = _write(tmp_path, """
        frappe:
          url: http://localhost:8000
        edge:
          id: edge-001
    """)
    with pytest.raises(KeyError):
        load_config(path)
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest edge_client/tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

```python
# edge_client/src/edge_client/config.py
"""Load and validate edge client YAML config."""

from __future__ import annotations

from dataclasses import dataclass

import yaml


@dataclass(frozen=True)
class EdgeConfig:
    frappe_url: str
    site: str
    api_key: str
    api_secret: str
    edge_id: str
    camera_index: int
    sync_interval: int
    threshold: float
    liveness_threshold: float
    min_det_score: float
    debounce_minutes: int
    db_path: str


def load_config(path: str) -> EdgeConfig:
    with open(path) as f:
        raw = yaml.safe_load(f)
    return EdgeConfig(
        frappe_url=raw["frappe"]["url"],
        site=raw["frappe"]["site"],
        api_key=raw["frappe"]["api_key"],
        api_secret=raw["frappe"]["api_secret"],
        edge_id=raw["edge"]["id"],
        camera_index=raw["edge"]["camera_index"],
        sync_interval=raw["edge"]["sync_interval"],
        threshold=raw["matching"]["threshold"],
        liveness_threshold=raw["matching"]["liveness_threshold"],
        min_det_score=raw["matching"]["min_det_score"],
        debounce_minutes=raw["matching"]["debounce_minutes"],
        db_path=raw["offline"]["db_path"],
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest edge_client/tests/test_config.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add edge_client/src/edge_client/config.py edge_client/tests/test_config.py
git commit -m "feat(edge): YAML config loader with validation"
```

---

### Task 20: SQLite store (face cache + offline queue)

**Files:**
- Create: `edge_client/src/edge_client/store.py`
- Test: `edge_client/tests/test_store.py`

**Design:** One SQLite file, two tables: `faces(attendance_device_id PRIMARY KEY, employee, embedding, model_version, modified)` and `checkin_queue(id INTEGER PK, device_id, timestamp, edge_id, created_at)`. `upsert_faces` merges incremental sync rows; `all_faces` returns them; `enqueue_checkin`/`pending_checkins`/`delete_checkin` drive the offline queue. Uses a context-managed connection.

- [ ] **Step 1: Write the failing test**

```python
# edge_client/tests/test_store.py
from edge_client.store import Store


def test_upsert_and_read_faces(tmp_path):
    store = Store(str(tmp_path / "q.sqlite"))
    store.upsert_faces([
        {"attendance_device_id": "D1", "employee": "EMP-1",
         "embedding": "[0.1]", "model_version": "buffalo_l", "modified": "2026-01-01 00:00:00"},
    ])
    faces = store.all_faces()
    assert len(faces) == 1 and faces[0]["attendance_device_id"] == "D1"


def test_upsert_replaces_on_same_device_id(tmp_path):
    store = Store(str(tmp_path / "q.sqlite"))
    row = {"attendance_device_id": "D1", "employee": "EMP-1",
           "embedding": "[0.1]", "model_version": "buffalo_l", "modified": "2026-01-01 00:00:00"}
    store.upsert_faces([row])
    row2 = dict(row, embedding="[0.2]", modified="2026-02-01 00:00:00")
    store.upsert_faces([row2])
    faces = store.all_faces()
    assert len(faces) == 1 and faces[0]["embedding"] == "[0.2]"


def test_max_modified(tmp_path):
    store = Store(str(tmp_path / "q.sqlite"))
    store.upsert_faces([
        {"attendance_device_id": "D1", "employee": "E1", "embedding": "[]",
         "model_version": "v", "modified": "2026-01-01 00:00:00"},
        {"attendance_device_id": "D2", "employee": "E2", "embedding": "[]",
         "model_version": "v", "modified": "2026-03-01 00:00:00"},
    ])
    assert store.max_modified() == "2026-03-01 00:00:00"


def test_checkin_queue_roundtrip(tmp_path):
    store = Store(str(tmp_path / "q.sqlite"))
    store.enqueue_checkin("D1", "2026-01-01 09:00:00", "edge-001")
    pending = store.pending_checkins()
    assert len(pending) == 1
    store.delete_checkin(pending[0]["id"])
    assert store.pending_checkins() == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest edge_client/tests/test_store.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

```python
# edge_client/src/edge_client/store.py
"""SQLite-backed face cache and offline check-in queue."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS faces (
    attendance_device_id TEXT PRIMARY KEY,
    employee TEXT NOT NULL,
    embedding TEXT NOT NULL,
    model_version TEXT,
    modified TEXT
);
CREATE TABLE IF NOT EXISTS checkin_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    edge_id TEXT NOT NULL
);
"""


class Store:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(_SCHEMA)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def upsert_faces(self, rows: list[dict]) -> None:
        with self._conn() as c:
            c.executemany(
                """INSERT INTO faces
                   (attendance_device_id, employee, embedding, model_version, modified)
                   VALUES (:attendance_device_id, :employee, :embedding, :model_version, :modified)
                   ON CONFLICT(attendance_device_id) DO UPDATE SET
                     employee=excluded.employee, embedding=excluded.embedding,
                     model_version=excluded.model_version, modified=excluded.modified""",
                rows,
            )

    def all_faces(self) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM faces")]

    def max_modified(self) -> str | None:
        with self._conn() as c:
            row = c.execute("SELECT MAX(modified) AS m FROM faces").fetchone()
            return row["m"]

    def enqueue_checkin(self, device_id: str, timestamp: str, edge_id: str) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO checkin_queue (device_id, timestamp, edge_id) VALUES (?, ?, ?)",
                (device_id, timestamp, edge_id),
            )

    def pending_checkins(self) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM checkin_queue ORDER BY id")]

    def delete_checkin(self, row_id: int) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM checkin_queue WHERE id = ?", (row_id,))
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest edge_client/tests/test_store.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add edge_client/src/edge_client/store.py edge_client/tests/test_store.py
git commit -m "feat(edge): SQLite face cache and offline check-in queue"
```

---

### Task 21: Matcher (NumPy matrix + cosine argmax)

**Files:**
- Create: `edge_client/src/edge_client/matcher.py`
- Test: `edge_client/tests/test_matcher.py`

**Design:** Build an `N×512 float32` matrix from cached face rows (filtered to the active `model_version`) plus a parallel `device_ids` list. `match(vec, threshold)` returns `(device_id, score)` for the best row at/above threshold, else `None`. Embeddings are stored normalized; the query vector is normalized before the dot product.

- [ ] **Step 1: Write the failing test**

```python
# edge_client/tests/test_matcher.py
import json

import numpy as np
from edge_client.matcher import Matcher


def _row(device_id, vec, model="buffalo_l"):
    v = np.asarray(vec, dtype=np.float32)
    v = v / np.linalg.norm(v)
    return {"attendance_device_id": device_id, "employee": device_id,
            "embedding": json.dumps(v.tolist()), "model_version": model}


def test_matches_nearest_above_threshold():
    rows = [_row("D1", [1, 0, 0]), _row("D2", [0, 1, 0])]
    m = Matcher(rows, model_version="buffalo_l")
    assert m.match([1, 0, 0], threshold=0.45) == ("D1", 1.0)


def test_below_threshold_returns_none():
    rows = [_row("D1", [1, 0, 0])]
    m = Matcher(rows, model_version="buffalo_l")
    assert m.match([0, 1, 0], threshold=0.45) is None


def test_filters_foreign_model_version():
    rows = [_row("D1", [1, 0, 0], model="other_model")]
    m = Matcher(rows, model_version="buffalo_l")
    assert m.size == 0
    assert m.match([1, 0, 0], threshold=0.45) is None


def test_empty_matcher_returns_none():
    m = Matcher([], model_version="buffalo_l")
    assert m.match([1, 0, 0], threshold=0.45) is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest edge_client/tests/test_matcher.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

```python
# edge_client/src/edge_client/matcher.py
"""In-memory NumPy cosine matcher over cached embeddings."""

from __future__ import annotations

import json

import numpy as np


class Matcher:
    def __init__(self, face_rows: list[dict], model_version: str) -> None:
        rows = [r for r in face_rows if r.get("model_version") == model_version]
        self.device_ids = [r["attendance_device_id"] for r in rows]
        if rows:
            mat = np.asarray([json.loads(r["embedding"]) for r in rows], dtype=np.float32)
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
            return None
        return self.device_ids[idx], score
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest edge_client/tests/test_matcher.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add edge_client/src/edge_client/matcher.py edge_client/tests/test_matcher.py
git commit -m "feat(edge): NumPy cosine matcher with model-version filter"
```

---

### Task 22: Debounce

**Files:**
- Create: `edge_client/src/edge_client/debounce.py`
- Test: `edge_client/tests/test_debounce.py`

**Design:** Pure, time-injected. `Debouncer(window_minutes)`; `allow(device_id, now) -> bool` returns True and records the punch if no punch within the window, else False. `now` is a `datetime` passed in (no wall-clock reads inside — testable).

- [ ] **Step 1: Write the failing test**

```python
# edge_client/tests/test_debounce.py
from datetime import datetime, timedelta

from edge_client.debounce import Debouncer


def test_first_punch_allowed():
    d = Debouncer(window_minutes=2)
    assert d.allow("D1", datetime(2026, 1, 1, 9, 0, 0)) is True


def test_repeat_within_window_suppressed():
    d = Debouncer(window_minutes=2)
    t0 = datetime(2026, 1, 1, 9, 0, 0)
    assert d.allow("D1", t0) is True
    assert d.allow("D1", t0 + timedelta(minutes=1)) is False


def test_after_window_allowed_again():
    d = Debouncer(window_minutes=2)
    t0 = datetime(2026, 1, 1, 9, 0, 0)
    d.allow("D1", t0)
    assert d.allow("D1", t0 + timedelta(minutes=3)) is True


def test_independent_per_device():
    d = Debouncer(window_minutes=2)
    t0 = datetime(2026, 1, 1, 9, 0, 0)
    assert d.allow("D1", t0) is True
    assert d.allow("D2", t0) is True
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest edge_client/tests/test_debounce.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

```python
# edge_client/src/edge_client/debounce.py
"""Per-device punch debounce (in-memory, time injected for testability)."""

from __future__ import annotations

from datetime import datetime, timedelta


class Debouncer:
    def __init__(self, window_minutes: int) -> None:
        self.window = timedelta(minutes=window_minutes)
        self._last: dict[str, datetime] = {}

    def allow(self, device_id: str, now: datetime) -> bool:
        last = self._last.get(device_id)
        if last is not None and now - last < self.window:
            return False
        self._last[device_id] = now
        return True
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest edge_client/tests/test_debounce.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add edge_client/src/edge_client/debounce.py edge_client/tests/test_debounce.py
git commit -m "feat(edge): per-device debounce window"
```

---

### Task 23: Frappe client (sync GET + check-in POST)

**Files:**
- Create: `edge_client/src/edge_client/frappe_client.py`
- Test: `edge_client/tests/test_frappe_client.py`

**Design:** Thin `requests` wrapper holding base URL + token auth header (`token <key>:<secret>`). `fetch_face_data(since)` GETs the whitelisted method and returns `message`. `post_checkin(device_id, timestamp, edge_id)` POSTs to `add_log_based_on_employee_field` with `log_type` omitted; raises on non-200. Tested with `requests` mocked.

- [ ] **Step 1: Write the failing test**

```python
# edge_client/tests/test_frappe_client.py
from unittest.mock import MagicMock, patch

from edge_client.frappe_client import FrappeClient


def _client():
    return FrappeClient("http://localhost:8000", "k", "s", site="site1.localhost")


@patch("edge_client.frappe_client.requests.get")
def test_fetch_face_data_returns_message(mock_get):
    mock_get.return_value = MagicMock(status_code=200,
                                      json=lambda: {"message": [{"attendance_device_id": "D1"}]})
    rows = _client().fetch_face_data(since="2026-01-01 00:00:00")
    assert rows == [{"attendance_device_id": "D1"}]
    _, kwargs = mock_get.call_args
    assert kwargs["params"]["since"] == "2026-01-01 00:00:00"
    assert "token k:s" in kwargs["headers"]["Authorization"]


@patch("edge_client.frappe_client.requests.post")
def test_post_checkin_omits_log_type(mock_post):
    mock_post.return_value = MagicMock(status_code=200, json=lambda: {"message": {}})
    _client().post_checkin("D1", "2026-01-01 09:00:00", "edge-001")
    _, kwargs = mock_post.call_args
    assert "log_type" not in kwargs["data"]
    assert kwargs["data"]["employee_field_value"] == "D1"
    assert kwargs["data"]["timestamp"] == "2026-01-01 09:00:00"
    assert kwargs["data"]["device_id"] == "edge-001"


@patch("edge_client.frappe_client.requests.post")
def test_post_checkin_raises_on_error(mock_post):
    mock_post.return_value = MagicMock(status_code=417, text="boom")
    import pytest
    with pytest.raises(RuntimeError):
        _client().post_checkin("D1", "2026-01-01 09:00:00", "edge-001")
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest edge_client/tests/test_frappe_client.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

```python
# edge_client/src/edge_client/frappe_client.py
"""HTTP client for the Frappe sync endpoint and native check-in."""

from __future__ import annotations

import requests

_SYNC_METHOD = "face_attendance.api.get_face_data"
_CHECKIN_METHOD = (
    "hrms.hr.doctype.employee_checkin.employee_checkin.add_log_based_on_employee_field"
)
_TIMEOUT = 10


class FrappeClient:
    def __init__(self, url: str, api_key: str, api_secret: str, site: str | None = None) -> None:
        self.base = url.rstrip("/")
        self.headers = {"Authorization": f"token {api_key}:{api_secret}"}

    def fetch_face_data(self, since: str | None = None) -> list[dict]:
        params = {}
        if since:
            params["since"] = since
        resp = requests.get(
            f"{self.base}/api/method/{_SYNC_METHOD}",
            params=params, headers=self.headers, timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"sync failed: {resp.status_code} {resp.text}")
        return resp.json()["message"]

    def post_checkin(self, device_id: str, timestamp: str, edge_id: str) -> None:
        # log_type omitted so Frappe derives IN/OUT from shift rules.
        data = {
            "employee_field_value": device_id,
            "timestamp": timestamp,
            "device_id": edge_id,
        }
        resp = requests.post(
            f"{self.base}/api/method/{_CHECKIN_METHOD}",
            data=data, headers=self.headers, timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"checkin failed: {resp.status_code} {resp.text}")
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest edge_client/tests/test_frappe_client.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add edge_client/src/edge_client/frappe_client.py edge_client/tests/test_frappe_client.py
git commit -m "feat(edge): Frappe sync + native check-in HTTP client"
```

---

### Task 24: Sync worker (pull → upsert → rebuild matcher) + queue flush

**Files:**
- Create: `edge_client/src/edge_client/sync.py`
- Test: `edge_client/tests/test_sync.py`

**Design:** `sync_faces(client, store, model_version)` fetches since `store.max_modified()`, upserts, and returns a fresh `Matcher` built from `store.all_faces()`. On fetch failure it logs and returns a Matcher from the existing cache (last-good). `flush_queue(client, store)` posts each pending check-in; deletes on success, stops on first failure (keeps order, avoids storms).

- [ ] **Step 1: Write the failing test**

```python
# edge_client/tests/test_sync.py
import json
from unittest.mock import MagicMock

import numpy as np
from edge_client.store import Store
from edge_client.sync import flush_queue, sync_faces


def _vec(v):
    a = np.asarray(v, dtype=np.float32)
    return (a / np.linalg.norm(a)).tolist()


def test_sync_upserts_and_builds_matcher(tmp_path):
    store = Store(str(tmp_path / "q.sqlite"))
    client = MagicMock()
    client.fetch_face_data.return_value = [
        {"attendance_device_id": "D1", "employee": "E1",
         "embedding": json.dumps(_vec([1, 0, 0])), "model_version": "buffalo_l",
         "modified": "2026-01-01 00:00:00"},
    ]
    matcher = sync_faces(client, store, model_version="buffalo_l")
    assert matcher.size == 1
    assert store.all_faces()[0]["attendance_device_id"] == "D1"
    client.fetch_face_data.assert_called_once_with(since=None)


def test_sync_keeps_last_good_on_failure(tmp_path):
    store = Store(str(tmp_path / "q.sqlite"))
    store.upsert_faces([{"attendance_device_id": "D1", "employee": "E1",
                         "embedding": json.dumps(_vec([1, 0, 0])),
                         "model_version": "buffalo_l", "modified": "2026-01-01 00:00:00"}])
    client = MagicMock()
    client.fetch_face_data.side_effect = RuntimeError("network down")
    matcher = sync_faces(client, store, model_version="buffalo_l")
    assert matcher.size == 1  # rebuilt from cache


def test_flush_posts_and_deletes_on_success(tmp_path):
    store = Store(str(tmp_path / "q.sqlite"))
    store.enqueue_checkin("D1", "2026-01-01 09:00:00", "edge-001")
    client = MagicMock()
    flush_queue(client, store)
    client.post_checkin.assert_called_once_with("D1", "2026-01-01 09:00:00", "edge-001")
    assert store.pending_checkins() == []


def test_flush_stops_on_failure(tmp_path):
    store = Store(str(tmp_path / "q.sqlite"))
    store.enqueue_checkin("D1", "2026-01-01 09:00:00", "edge-001")
    store.enqueue_checkin("D2", "2026-01-01 09:01:00", "edge-001")
    client = MagicMock()
    client.post_checkin.side_effect = RuntimeError("down")
    flush_queue(client, store)
    assert len(store.pending_checkins()) == 2  # nothing deleted
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest edge_client/tests/test_sync.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

```python
# edge_client/src/edge_client/sync.py
"""Sync worker and offline-queue flush."""

from __future__ import annotations

import logging

from edge_client.matcher import Matcher

logger = logging.getLogger(__name__)


def sync_faces(client, store, model_version: str) -> Matcher:
    """Pull incremental face data, upsert to cache, return a fresh Matcher.

    On fetch failure, rebuild the Matcher from the last-good cache.
    """
    try:
        rows = client.fetch_face_data(since=store.max_modified())
        if rows:
            store.upsert_faces(rows)
    except Exception:
        logger.exception("face sync failed; using last-good cache")
    return Matcher(store.all_faces(), model_version=model_version)


def flush_queue(client, store) -> None:
    """Post pending check-ins in order; stop at the first failure."""
    for item in store.pending_checkins():
        try:
            client.post_checkin(item["device_id"], item["timestamp"], item["edge_id"])
        except Exception:
            logger.warning("flush stopped; Frappe still unreachable")
            return
        store.delete_checkin(item["id"])
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest edge_client/tests/test_sync.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add edge_client/src/edge_client/sync.py edge_client/tests/test_sync.py
git commit -m "feat(edge): sync worker with last-good fallback and ordered queue flush"
```

---

### Task 25: Capture loop + main wiring

**Files:**
- Create: `edge_client/src/edge_client/capture.py`
- Modify: `edge_client/src/edge_client/main.py`
- Test: `edge_client/tests/test_capture.py`

**Design:** `process_frame(frame, analyzer, matcher, debouncer, client, store, cfg, now)` is the pure, testable core for one frame: analyze → for each face, liveness gate → match → debounce → try `post_checkin`, enqueue on failure. The OpenCV read loop (`run_capture`) is thin I/O glue wiring `process_frame`, periodic `sync_faces`, and `flush_queue`; it is exercised in the E2E task, not unit-tested. `main` loads config, builds dependencies, calls `run_capture`.

- [ ] **Step 1: Write the failing test for `process_frame`**

```python
# edge_client/tests/test_capture.py
import json
from datetime import datetime
from unittest.mock import MagicMock

import numpy as np
from edge_client.capture import process_frame
from edge_client.config import EdgeConfig
from edge_client.debounce import Debouncer
from edge_client.matcher import Matcher
from edge_client.store import Store
from facecore.models import DetectedFace


def _cfg():
    return EdgeConfig(
        frappe_url="x", site="s", api_key="k", api_secret="s", edge_id="edge-001",
        camera_index=0, sync_interval=300, threshold=0.45, liveness_threshold=0.6,
        min_det_score=0.5, debounce_minutes=2, db_path=":memory:",
    )


def _matcher():
    v = (np.array([1, 0, 0], dtype=np.float32)).tolist()
    return Matcher([{"attendance_device_id": "D1", "employee": "E1",
                     "embedding": json.dumps(v), "model_version": "buffalo_l"}],
                   model_version="buffalo_l")


def _analyzer_with(face):
    a = MagicMock()
    a.analyze.return_value = [face] if face else []
    return a


def _live_face():
    return DetectedFace(bbox=[0, 0, 1, 1], embedding=[1.0, 0.0, 0.0],
                        det_score=0.9, liveness_score=0.9)


def test_match_posts_checkin(tmp_path):
    client = MagicMock()
    store = Store(str(tmp_path / "q.sqlite"))
    process_frame(np.zeros((4, 4, 3), np.uint8), _analyzer_with(_live_face()),
                  _matcher(), Debouncer(2), client, store, _cfg(),
                  now=datetime(2026, 1, 1, 9, 0, 0))
    client.post_checkin.assert_called_once()
    assert store.pending_checkins() == []


def test_spoof_below_liveness_no_checkin(tmp_path):
    spoof = DetectedFace(bbox=[0, 0, 1, 1], embedding=[1.0, 0.0, 0.0],
                         det_score=0.9, liveness_score=0.1)
    client = MagicMock()
    store = Store(str(tmp_path / "q.sqlite"))
    process_frame(np.zeros((4, 4, 3), np.uint8), _analyzer_with(spoof),
                  _matcher(), Debouncer(2), client, store, _cfg(),
                  now=datetime(2026, 1, 1, 9, 0, 0))
    client.post_checkin.assert_not_called()


def test_post_failure_enqueues(tmp_path):
    client = MagicMock()
    client.post_checkin.side_effect = RuntimeError("frappe down")
    store = Store(str(tmp_path / "q.sqlite"))
    process_frame(np.zeros((4, 4, 3), np.uint8), _analyzer_with(_live_face()),
                  _matcher(), Debouncer(2), client, store, _cfg(),
                  now=datetime(2026, 1, 1, 9, 0, 0))
    assert len(store.pending_checkins()) == 1


def test_debounced_second_punch_skipped(tmp_path):
    client = MagicMock()
    store = Store(str(tmp_path / "q.sqlite"))
    deb = Debouncer(2)
    args = (_analyzer_with(_live_face()), _matcher(), deb, client, store, _cfg())
    process_frame(np.zeros((4, 4, 3), np.uint8), *args, now=datetime(2026, 1, 1, 9, 0, 0))
    process_frame(np.zeros((4, 4, 3), np.uint8), *args, now=datetime(2026, 1, 1, 9, 0, 30))
    assert client.post_checkin.call_count == 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest edge_client/tests/test_capture.py -v`
Expected: FAIL — `ModuleNotFoundError: edge_client.capture`.

- [ ] **Step 3: Implement `capture.py`**

```python
# edge_client/src/edge_client/capture.py
"""Per-frame recognition core and the OpenCV capture loop."""

from __future__ import annotations

import logging
import time
from datetime import datetime

from edge_client.sync import flush_queue, sync_faces

logger = logging.getLogger(__name__)


def process_frame(frame, analyzer, matcher, debouncer, client, store, cfg, now: datetime) -> None:
    """Handle one frame: detect → liveness → match → debounce → check-in/enqueue."""
    for face in analyzer.analyze(frame):
        if face.liveness_score < cfg.liveness_threshold:
            logger.debug("liveness %.2f below threshold; skipping", face.liveness_score)
            continue
        result = matcher.match(face.embedding, threshold=cfg.threshold)
        if result is None:
            continue
        device_id, score = result
        if not debouncer.allow(device_id, now):
            continue
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
        try:
            client.post_checkin(device_id, timestamp, cfg.edge_id)
            logger.info("check-in posted for %s (score %.3f)", device_id, score)
        except Exception:
            logger.warning("check-in failed for %s; enqueueing offline", device_id)
            store.enqueue_checkin(device_id, timestamp, cfg.edge_id)


def run_capture(analyzer, client, store, cfg, model_version: str) -> None:  # pragma: no cover
    """OpenCV read loop. Thin I/O glue around process_frame + periodic sync/flush."""
    import cv2

    from edge_client.debounce import Debouncer

    debouncer = Debouncer(cfg.debounce_minutes)
    matcher = sync_faces(client, store, model_version)
    last_sync = time.monotonic()
    cap = cv2.VideoCapture(cfg.camera_index)
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                logger.warning("camera read failed; retrying")
                time.sleep(1.0)
                if not cap.isOpened():
                    cap.open(cfg.camera_index)
                continue
            process_frame(frame, analyzer, matcher, debouncer, client, store, cfg,
                          now=datetime.now())
            if time.monotonic() - last_sync >= cfg.sync_interval:
                matcher = sync_faces(client, store, model_version)
                flush_queue(client, store)
                last_sync = time.monotonic()
    finally:
        cap.release()
```

- [ ] **Step 4: Wire `main.py`** — replace the `NotImplementedError` block

```python
# main.py
import argparse
import logging

from edge_client.capture import run_capture
from edge_client.config import load_config
from edge_client.frappe_client import FrappeClient
from edge_client.store import Store

logger = logging.getLogger(__name__)
MODEL_VERSION = "buffalo_l"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Edge device client for face recognition attendance"
    )
    parser.add_argument("--config", required=True, help="Path to YAML config")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)

    cfg = load_config(args.config)
    from facecore import FaceAnalyzer

    analyzer = FaceAnalyzer(device="cpu", det_thresh=cfg.min_det_score)
    client = FrappeClient(cfg.frappe_url, cfg.api_key, cfg.api_secret, site=cfg.site)
    store = Store(cfg.db_path)

    logger.info("edge client starting: %s", cfg.edge_id)
    run_capture(analyzer, client, store, cfg, MODEL_VERSION)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run to verify it passes**

Run: `pytest edge_client/tests/test_capture.py -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Lint + commit**

```bash
ruff check edge_client/src
git add edge_client/src/edge_client/capture.py edge_client/src/edge_client/main.py edge_client/tests/test_capture.py
git commit -m "feat(edge): per-frame recognition core + capture loop + main wiring"
```

---

### Task 26: Full edge_client suite green

- [ ] **Step 1: Run the suite**

Run: `cd /Users/saurabh/facerecog && source venv/bin/activate && pytest edge_client -v`
Expected: all PASS.

- [ ] **Step 2: Lint + type-check**

Run: `ruff check edge_client/src && mypy edge_client/src/edge_client`
Expected: no errors. Fix inline and re-run if needed.

- [ ] **Step 3: Commit any fixes**

```bash
git add -A edge_client && git commit -m "chore(edge): suite lint and type clean" || echo "nothing to commit"
```

---

# Phase 5 — E2E + operator docs

### Task 27: Operator documentation

**Files:**
- Create: `docs/operations.md`

- [ ] **Step 1: Write `docs/operations.md`**

````markdown
# Operations Guide

## 1. Download models (~310 MB, once)

```bash
cd /Users/saurabh/facerecog && source venv/bin/activate
# buffalo_l (SCRFD + ArcFace) — auto-downloads to ~/.insightface/models
python -c "from insightface.app import FaceAnalysis; FaceAnalysis(name='buffalo_l').prepare(ctx_id=-1)"
# MiniFASNet liveness ONNX → models/minifasnet.onnx
# Place the Silent-Face MiniFASNet ONNX at: /Users/saurabh/facerecog/models/minifasnet.onnx
```

## 2. Start the embedding service

```bash
cd /Users/saurabh/facerecog && source venv/bin/activate
export EMBEDDING_SERVICE_SECRET=change-me   # match Face Recognition Settings
uvicorn embedding_service.app:app --host 127.0.0.1 --port 8080
curl http://127.0.0.1:8080/health   # {"status":"ok",...}
```

## 3. Configure Frappe

1. **Face Recognition Settings** (single): set `embedding_service_url=http://localhost:8080`,
   `embedding_service_secret` to match step 2, keep default thresholds.
2. Create an **API user**, assign the **"Face Edge Device"** role, generate **API key + secret**.
3. On each employee, set a unique **Attendance Device ID**.
4. **Shift Type** → enable **Auto Attendance**, set **Process Attendance After** = today,
   assign employees to the shift.

## 4. Enroll a face

HR → **Employee Face Profile** → New → link employee → upload a clear front-facing photo → Save.
On save the controller posts the image to the embedding service and stores the 512-d vector.
A failure (service down, no/multi/low-quality face, blank device id) blocks the save with a message.

## 5. Run an edge device

```bash
cd /Users/saurabh/facerecog && source venv/bin/activate
cp edge_client/config.example.yaml config.yaml   # fill url/api_key/api_secret/camera_index
python -m edge_client.main --config config.yaml --debug
```

## 6. Attendance timing

Check-ins post instantly as **Employee Checkin** rows. **Attendance** documents are produced by
Frappe's native `process_auto_attendance_for_all_shifts`, which runs on the **hourly** scheduler.
Expect Attendance up to ~1h after check-in. To force it now:

```bash
cd ~/frappe-bench
bench --site site1.localhost execute hrms.hr.doctype.shift_type.shift_type.process_auto_attendance_for_all_shifts
```

## 7. Model upgrades

If the embedding model changes, run report **"Face Profiles Needing Reenrollment"**
(HR module) to list profiles whose `model_version` differs, and re-enroll them.
````

- [ ] **Step 2: Commit**

```bash
cd /Users/saurabh/facerecog
git add docs/operations.md
git commit -m "docs: add operator guide (models, service, enrollment, shifts, timing)"
```

---

### Task 28: End-to-end verification on the Mac (manual, scripted checks)

**Goal:** Prove the full chain: enroll → recognize → Employee Checkin → Attendance.

- [ ] **Step 1: Bring up the stack**

- Start bench: `cd ~/frappe-bench && bench start` (separate terminal).
- Start embedding service (operations.md §2).
- Complete Frappe config (operations.md §3): API user + role, one employee with `attendance_device_id`, one Shift Type with auto-attendance.

- [ ] **Step 2: Enroll a real face**

Enroll yourself (consenting) via Employee Face Profile with a webcam photo. Confirm the saved
profile has a non-empty `embedding` and `model_version=buffalo_l`.

- [ ] **Step 3: Run the edge client against the webcam**

```bash
cd /Users/saurabh/facerecog && source venv/bin/activate
python -m edge_client.main --config config.yaml --debug
```

Look at the camera. Expected log: `check-in posted for <device_id>`.

- [ ] **Step 4: Assert an Employee Checkin row exists**

> **Note (validated against hrms 16.7):** Employee Checkin has **no** `attendance_device_id` field. `add_log_based_on_employee_field` resolves the person's `attendance_device_id` to the linked `employee`, and stores the edge id in `device_id`. So filter by `employee` (the enrolled employee, `<EMP_ID>`); `device_id` holds the edge/location id (`edge-001`).

```bash
cd ~/frappe-bench
bench --site site1.localhost execute frappe.client.get_list \
  --kwargs "{'doctype':'Employee Checkin','filters':{'employee':'<EMP_ID>'},'fields':['name','time','log_type','device_id']}"
```

Expected: at least one row (`device_id` = your edge id; `log_type` derived by Frappe — may be `IN`).

- [ ] **Step 5: Force auto-attendance and assert an Attendance doc**

```bash
cd ~/frappe-bench
bench --site site1.localhost execute hrms.hr.doctype.shift_type.shift_type.process_auto_attendance_for_all_shifts
bench --site site1.localhost execute frappe.client.get_list \
  --kwargs "{'doctype':'Attendance','filters':{'employee':'<EMP_ID>'},'fields':['name','status','attendance_date']}"
```

Expected: an Attendance document for the employee.

- [ ] **Step 6: Verify offline resilience**

Stop bench, look at the camera (edge should log `enqueueing offline`), restart bench, wait one
`sync_interval`, and confirm the queued check-in flushes (`pending_checkins` returns empty in the
edge SQLite, and a new Employee Checkin appears).

- [ ] **Step 7: Record the result**

Append an "E2E verified <date>" note to `docs/operations.md` and commit. If any step fails, capture
the failing log and revisit the relevant task before declaring done.

---

## Self-Review

**Spec coverage** (each §13 build phase → tasks):
- facecore + tests → Tasks 1–7 ✓ (exceptions, cosine, liveness, analyze, file, integration).
- embedding_service + tests → Tasks 8–9 ✓ (config, /embed with auth + single-face gate).
- face_attendance (required_apps, DocTypes+autoname, enrollment controller, sync API, role+Custom DocPerm fixture create+read, re-enroll report, tests) → Tasks 10–18 ✓.
- edge_client (matcher, sync, capture, debounce, offline queue) + tests → Tasks 19–26 ✓.
- E2E + operator docs → Tasks 27–28 ✓.

**Spec specifics checked:**
- `add_log_based_on_employee_field` with `log_type` omitted → Task 23 (`test_post_checkin_omits_log_type`). ✓
- `attendance_device_id` mapping + blank rejection → Tasks 13, 16. ✓
- Sync `only_for(["Face Edge Device","System Manager"])` + GET-only → Task 16. ✓
- Liveness gated only on edge, not enrollment → enrollment controller (Task 13) stores liveness as informational, no gate; edge gates in Task 25 (`test_spoof_below_liveness_no_checkin`). ✓
- `has_value_changed("enrollment_image")` guard → Task 13 controller. ✓
- 10s HTTP timeout + `frappe.log_error` then generic `frappe.throw` → Task 13. ✓
- Custom DocPerm create+read on Employee Checkin + permission test → Tasks 14–15. ✓
- Model-version filter in matcher + drift report → Tasks 21, 17. ✓
- Last-good matrix on sync failure; original-timestamp offline enqueue → Task 24, Task 25. ✓
- `required_apps=["frappe","erpnext","hrms"]` → Task 10. ✓

**Type consistency:** `FrappeClient.post_checkin(device_id, timestamp, edge_id)` signature is identical across Tasks 23, 24, 25. `Matcher(face_rows, model_version)` and `.match(vec, threshold)` consistent across Tasks 21, 24, 25. `Store` method names (`upsert_faces`, `all_faces`, `max_modified`, `enqueue_checkin`, `pending_checkins`, `delete_checkin`) consistent across Tasks 20, 24, 25. `MODEL_VERSION="buffalo_l"` defined in facecore (Task 4) and reused. ✓

**Placeholder scan:** every code step contains complete code; no TBD/TODO. The only non-code "fill in" is the four consenting fixture images (Task 6) and operator-supplied credentials/camera index — both inherently environment-specific, not plan gaps.

**Known external dependency:** the Silent-Face MiniFASNet ONNX file is operator-supplied (Task 22/27). Liveness integration tests (Task 6) and E2E (Task 28) require it; all other tests run without it.
