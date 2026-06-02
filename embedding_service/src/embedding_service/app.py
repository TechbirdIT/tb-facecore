"""FastAPI application for the embedding service."""

from __future__ import annotations

import io
import secrets

import cv2
import numpy as np
from facecore import MODEL_VERSION, FaceAnalyzer
from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from PIL import Image
from pydantic import BaseModel

from embedding_service.config import Settings

app = FastAPI(
    title="Embedding Service",
    description="Compute face embeddings from images",
    version="0.1.0",
)

# Guard against unbounded uploads / decompression bombs.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB on the wire
MAX_PIXELS = 50_000_000  # ~50 MP after decode

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
    # Constant-time comparison to avoid leaking the secret via timing.
    # secret is None = auth disabled (v1 localhost-only; prod sets the env var).
    if settings.secret is not None and not secrets.compare_digest(
        x_secret or "", settings.secret
    ):
        raise HTTPException(status_code=401, detail="invalid secret")

    # Cap bytes read into memory. NOTE: Starlette spools the multipart body to
    # a temp file before this runs, so this bounds RAM, not disk — enforce the
    # wire size at the reverse proxy (client_max_body_size) in production.
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="file too large")

    # Probe dimensions from the header BEFORE decoding, so a small compressed
    # file cannot expand into an OOM allocation (decompression bomb).
    try:
        with Image.open(io.BytesIO(raw)) as probe:
            width, height = probe.size
    except Exception:
        raise HTTPException(status_code=422, detail="invalid image") from None
    if width * height > MAX_PIXELS:
        raise HTTPException(status_code=413, detail="image dimensions too large")

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
