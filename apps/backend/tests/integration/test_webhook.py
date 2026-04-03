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

SECRET = "test_secret"  # NOSONAR


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
