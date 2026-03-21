from fastapi import APIRouter
from app.database import get_db
from app.config import settings

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/")
async def health():
    status = {"mongodb": "ok", "redis": "ok", "status": "ok"}

    try:
        db = get_db()
        await db.command("ping")
    except Exception as e:
        status["mongodb"] = f"error: {e}"
        status["status"] = "degraded"

    try:
        from redis.asyncio import from_url
        r = from_url(settings.redis_url)
        await r.ping()
        await r.aclose()
    except Exception as e:
        status["redis"] = f"error: {e}"
        status["status"] = "degraded"

    return status
