"""FastAPI application — unified AI service."""

from __future__ import annotations

from fastapi import FastAPI

from ai_service.config import Settings
from ai_service.routes import analyze, embed, health, verify_id

app = FastAPI(
    title="AI Service",
    description="Unified face AI — embeddings, ID verification, analytics",
    version="0.1.0",
)

_settings = Settings.from_env()


def get_settings() -> Settings:
    return _settings


app.include_router(health.router)
app.include_router(embed.router)
app.include_router(verify_id.router)
app.include_router(analyze.router)
