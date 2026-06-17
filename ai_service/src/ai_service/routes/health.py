"""GET /health — liveness probe + deepface sidecar reachability."""

from fastapi import APIRouter, Depends

from ai_service.clients.deepface import DeepFaceClient
from ai_service.routes.analyze import get_client

router = APIRouter()


@router.get("/health")
async def health(client: DeepFaceClient = Depends(get_client)) -> dict:
    # Always 200 — this is ai_service's own liveness. The deepface field
    # surfaces sidecar reachability without failing the probe when it is down.
    deepface_up = await client.health()
    return {
        "status": "ok",
        "version": "0.1.0",
        "deepface": "up" if deepface_up else "down",
    }
