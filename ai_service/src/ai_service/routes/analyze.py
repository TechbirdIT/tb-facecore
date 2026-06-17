"""POST /analyze — face demographics (age/gender/emotion/race) via deepface sidecar."""

from __future__ import annotations

import io
import secrets as _secrets

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from PIL import Image

from ai_service.clients.deepface import DeepFaceClient, DeepFaceError
from ai_service.config import Settings

router = APIRouter()

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_PIXELS = 50_000_000  # ~50 MP

_settings: Settings | None = None
_client: DeepFaceClient | None = None


def _get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings.from_env()
    return _settings


def get_client() -> DeepFaceClient:
    global _client
    if _client is None:
        _client = DeepFaceClient(base_url=_get_settings().deepface_url)
    return _client


@router.post("/analyze")
async def analyze(
    file: UploadFile = File(...),
    x_secret: str | None = Header(default=None),
    settings: Settings = Depends(_get_settings),
    client: DeepFaceClient = Depends(get_client),
) -> dict:
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

    try:
        results = await client.analyze(
            raw, file.filename or "upload.jpg", file.content_type or "image/jpeg"
        )
    except DeepFaceError as err:
        raise HTTPException(status_code=502, detail=str(err)) from err
    return {"results": results}
