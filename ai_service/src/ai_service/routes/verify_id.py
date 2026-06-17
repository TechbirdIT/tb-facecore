"""POST /verify-id — compare face in ID document vs live face (stub)."""

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.post("/verify-id")
async def verify_id() -> dict:
    raise HTTPException(status_code=501, detail="not implemented")
