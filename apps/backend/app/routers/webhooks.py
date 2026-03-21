import hashlib
import hmac
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Request, Response, HTTPException, Query
from app.config import settings
from app.database import get_db
from app.core.logging import get_logger

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = get_logger(__name__)


def _verify_signature(body: bytes, signature: str) -> bool:
    if not settings.meta_webhook_secret:
        return True  # Skip in dev if not configured
    expected = (
        "sha256="
        + hmac.new(
            settings.meta_webhook_secret.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()
    )
    return hmac.compare_digest(expected, signature)


@router.get("/meta")
async def verify_webhook(
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
):
    if (
        hub_mode == "subscribe"
        and hub_verify_token == settings.meta_webhook_verify_token
    ):
        return Response(content=hub_challenge, media_type="text/plain")
    raise HTTPException(403, "Verification failed")


@router.post("/meta", status_code=200)
async def receive_webhook(request: Request, db=Depends(get_db)):
    body = await request.body()
    sig = request.headers.get("X-Hub-Signature-256", "")

    if not _verify_signature(body, sig):
        logger.warning("webhook_invalid_signature")
        raise HTTPException(403, "Invalid signature")

    try:
        payload = await request.json()
    except Exception as e:
        await db.webhook_errors.insert_one(
            {
                "raw_body": body.decode("utf-8", errors="replace"),
                "headers": dict(request.headers),
                "error": str(e),
                "received_at": datetime.now(timezone.utc),
            }
        )
        return {"status": "ok"}

    from app.workers.webhook_task import process_webhook_task

    process_webhook_task.delay(payload)
    return {"status": "ok"}
