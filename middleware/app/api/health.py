from fastapi import APIRouter

from app.core.redis import redis_client

router = APIRouter()


@router.get("/healthz")
async def healthz():
    pong = await redis_client.ping()
    return {"ok": True, "redis": bool(pong)}
