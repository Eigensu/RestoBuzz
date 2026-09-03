"""Integration tests for webhook endpoint. Set INTEGRATION=1 to run."""
import os
import hashlib
import hmac
import json
import pytest
from httpx import AsyncClient, ASGITransport

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION") != "1",
    reason="Set INTEGRATION=1 to run integration tests",
)

# Supplied by the environment — CI mints a throwaway value per run — so no
# credential literal lives in the repo.
SECRET = os.getenv("META_WEBHOOK_SECRET", "")


@pytest.fixture(autouse=True)
def _require_webhook_secret():
    """The app skips signature verification entirely when META_WEBHOOK_SECRET is
    unset (see app/routers/webhooks.py:_verify_signature), so both the valid- and
    invalid-signature cases below would pass for the wrong reason. Fail loudly
    rather than report a green run that proved nothing.
    """
    assert SECRET, (
        "META_WEBHOOK_SECRET must be set to run the webhook signature tests"
    )


def _sign(body: bytes) -> str:
    return "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


@pytest.mark.asyncio
async def test_valid_signature_returns_200():
    from app.main import app
    payload = json.dumps({"entry": []}).encode()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/webhooks/meta",
            content=payload,
            headers={"X-Hub-Signature-256": _sign(payload), "Content-Type": "application/json"},
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_invalid_signature_returns_403():
    from app.main import app
    payload = json.dumps({"entry": []}).encode()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/webhooks/meta",
            content=payload,
            headers={"X-Hub-Signature-256": "sha256=invalidsig", "Content-Type": "application/json"},
        )
    assert resp.status_code == 403
