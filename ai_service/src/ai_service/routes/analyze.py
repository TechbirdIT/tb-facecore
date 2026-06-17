"""POST /analyze — emotion, race, age, gender demography (stub)."""

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.post("/analyze")
async def analyze() -> dict:
    raise HTTPException(status_code=501, detail="not implemented")
