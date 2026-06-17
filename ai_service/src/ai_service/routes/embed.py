"""POST /embed — compute ArcFace embedding from a single-face image."""

from __future__ import annotations

import io
import secrets as _secrets

import cv2
import numpy as np
from facecore import MODEL_VERSION, FaceAnalyzer
from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from PIL import Image
from pydantic import BaseModel

from ai_service.config import Settings

router = APIRouter()

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_PIXELS = 50_000_000  # ~50 MP

_analyzer: FaceAnalyzer | None = None
_settings: Settings | None = None


def _get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings.from_env()
    return _settings


def get_analyzer() -> FaceAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = FaceAnalyzer(device=_get_settings().device)
    return _analyzer


class EmbeddingResponse(BaseModel):
    embedding: list[float]
    det_score: float
    liveness_score: float
    model_version: str


@router.post("/embed", response_model=EmbeddingResponse)
async def embed(
    file: UploadFile = File(...),
    x_secret: str | None = Header(default=None),
    settings: Settings = Depends(_get_settings),
    analyzer: FaceAnalyzer = Depends(get_analyzer),
) -> EmbeddingResponse:
    if settings.secret is not None and not _secrets.compare_digest(
        x_secret or "", settings.secret
    ):
        raise HTTPException(status_code=401, detail="invalid secret")

    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="file too large")

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
