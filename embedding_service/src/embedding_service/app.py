"""FastAPI application for embedding service."""

from fastapi import FastAPI, File, UploadFile, HTTPException, Header
from pydantic import BaseModel
from typing import Optional
import io

app = FastAPI(
    title="Embedding Service",
    description="Compute face embeddings from images",
    version="0.1.0",
)


class EmbeddingResponse(BaseModel):
    """Response from the embedding endpoint."""

    embedding: list[float]
    """512-dimensional L2-normalized embedding."""

    det_score: float
    """Detector confidence [0.0, 1.0]."""

    liveness_score: float
    """Anti-spoof probability [0.0, 1.0]."""

    model_version: str
    """Model version tag (e.g. 'buffalo_l')."""


@app.post("/embed", response_model=EmbeddingResponse)
async def embed(
    file: UploadFile = File(...),
    x_secret: Optional[str] = Header(None),
) -> EmbeddingResponse:
    """
    Compute embedding from an uploaded image.

    Args:
        file: Image file (jpg, png).
        x_secret: Shared secret header (v1: localhost only; prod: required HTTPS).

    Returns:
        Embedding + scores + model version.

    Raises:
        400: No face / multiple faces / low quality.
        401: Missing/invalid secret header (prod only).
        422: Invalid image.
    """
    # Stub — will be implemented in phase 2
    raise NotImplementedError("POST /embed — phase 2 implementation")


@app.get("/health")
async def health() -> dict:
    """Health check endpoint."""
    return {"status": "ok", "version": "0.1.0"}
