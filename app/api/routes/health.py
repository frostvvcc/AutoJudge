from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    return {"status": "ok", "service": "autojudge"}


@router.get("/ready")
async def readiness_check():
    return {"status": "ready"}
