# facecore — Face Recognition Engine

Pure AI library for face detection, embedding computation, and passive liveness detection.

## Overview

- **Detection**: SCRFD from InsightFace (buffalo_l pack)
- **Embedding**: ArcFace r50 → 512-dimensional L2-normalized vectors
- **Liveness**: MiniFASNet (passive anti-spoof, silent-face)
- **Runtime**: ONNX Runtime (CPU or CUDA)

No camera I/O. No HTTP. No Frappe. Just arrays in, arrays out.

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
    
    # Compare to another embedding
    similarity = analyzer.cosine_similarity(face.embedding, other_embedding)
    print(f"Similarity: {similarity:.3f}")  # 1.0 = identical
```

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
