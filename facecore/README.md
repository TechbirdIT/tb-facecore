# facecore — Face Recognition Engine

Pure AI library for face detection, embedding computation, passive liveness
detection, and lightweight demographics.

## Overview

- **Detection**: SCRFD from InsightFace (buffalo_l pack)
- **Embedding**: ArcFace r50 → 512-dimensional L2-normalized vectors
- **Liveness**: MiniFASNet (passive anti-spoof, silent-face)
- **Age & gender**: buffalo_l `genderage` model — free, no extra dependency
- **Distance & verification**: cosine / euclidean / L2 / angular metrics with
  per-model thresholds (`find_distance`, `find_threshold`, `verify_embeddings`)
- **Image loaders**: `load_image` accepts path / URL / base64 / data-URI / bytes /
  ndarray; `extract_faces` returns aligned face crops
- **Emotion & race** *(optional)*: via the `facecore[demography]` extra — see below
- **Runtime**: ONNX Runtime (CPU or CUDA)

The lean core is ONNX/InsightFace only — no camera I/O, no HTTP, no Frappe, and
deliberately no TensorFlow. Just arrays in, arrays out.

## Installation

```bash
pip install -e ".[dev]"
```

## Usage

```python
from facecore import FaceAnalyzer
import cv2

analyzer = FaceAnalyzer(device="cpu")

# Load image
image = cv2.imread("photo.jpg")  # BGR array (H, W, 3)

# Detect and analyze
faces = analyzer.analyze(image)

for face in faces:
    print(f"Confidence: {face.det_score:.2f}")
    print(f"Liveness: {face.liveness_score:.2f}")
    print(f"Embedding shape: {len(face.embedding)}")  # 512
    
    # Age & gender (free — buffalo_l genderage, no extra dependency)
    print(f"Age: {face.age}, Gender: {face.gender}")

    # Compare to another embedding
    similarity = analyzer.cosine_similarity(face.embedding, other_embedding)
    print(f"Similarity: {similarity:.3f}")  # 1.0 = identical
```

### Distance, thresholds & verification

```python
from facecore import find_distance, find_threshold, verify_embeddings

d = find_distance(emb1, emb2, metric="cosine")
t = find_threshold("buffalo_l", "cosine")        # tuned per model + metric
result = verify_embeddings(emb1, emb2)            # {"verified": bool, "distance", "threshold"}
```

### Image loaders & aligned crops

```python
from facecore import load_image

img = load_image("https://example.com/face.jpg")  # path / URL / base64 / data-URI / bytes / ndarray
crops = analyzer.extract_faces(img, align=True)    # aligned 112×112 face crops
```

### Emotion & race (optional `[demography]` extra)

Emotion and race are the one genuinely-missing piece from the lean core —
deepface's models are TensorFlow/Keras, which the core deliberately avoids. They
live behind an optional extra so the default install stays lean; importing only
pulls the heavy dependency when you actually call it.

```bash
pip install "facecore[demography]"   # adds deepface + tf-keras (~GBs)
```

```python
from facecore import demography

result = demography.analyze("face.jpg", actions=("emotion", "race"))
# [{"facial_area": {...}, "emotion": "happy", "emotion_scores": {...},
#                         "race": "white",   "race_scores": {...}}]
```

Output is coerced to native JSON-serializable types (no numpy scalars), so it can
be returned straight from an API. Without the extra installed, `analyze` raises a
`FaceCoreError` with an install hint.

## Testing

```bash
pytest tests/
pytest tests/ --cov
```

All tests use committed fixture images:
- `tests/fixtures/same_person_*.jpg` — expected high cosine similarity
- `tests/fixtures/different_person_*.jpg` — expected low similarity
- `tests/fixtures/printed_photo.jpg` — expected low liveness score

## Models

Models are auto-downloaded on first use to `facerecog/models/`:
- `buffalo_l/` — detection + embedding (~300 MB)
- `minifasnet/` — liveness (~10 MB)

To pre-download:
```bash
python -c "from insightface.app import FaceAnalysis; FaceAnalysis(name='buffalo_l')"
```

## API Reference

See `src/facecore/models.py` and `src/facecore/analyzer.py` for full type signatures.

## Performance (Mac CPU)

- Single face: ~50–100ms
- Multiple faces: ~100–200ms total

GPU (Linux): 5–10x faster.

## References

- InsightFace: https://github.com/deepinsight/insightface
- SCRFD: https://arxiv.org/abs/2105.04714
- ArcFace: https://arxiv.org/abs/1801.07698
- Silent-Face: https://arxiv.org/abs/1903.10936
