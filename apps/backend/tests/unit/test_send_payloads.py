"""Send-path payload tests.

These exercise the real send functions end to end but terminate the request at
an httpx MockTransport, so the assertions cover exactly what would go on the
wire to Meta without any network call, credential, or billable message.
"""

import httpx
import pytest

from app.services import meta_api
from app.services.meta_api import (
    MetaAPIError,
    send_template_message,
    send_text_message,
)

PHONE = "919876543210"
BSUID = "IN.13491208655302741918"


@pytest.fixture
def capture_send(monkeypatch):
    """Route sends through a mock transport and record the request payloads."""
    sent: list[dict] = []

    def install(response: httpx.Response | None = None):
        def handler(request: httpx.Request) -> httpx.Response:
            import json

            sent.append(
                {
                    "url": str(request.url),
                    "method": request.method,
                    "headers": dict(request.headers),
                    "body": json.loads(request.content or b"{}"),
                }
            )
            return response or httpx.Response(
                200, json={"messages": [{"id": "wamid.STUB"}]}
            )

        original = httpx.AsyncClient

        def factory(*args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            return original(*args, **kwargs)

        monkeypatch.setattr(meta_api.httpx, "AsyncClient", factory)
        return sent

    return install


# ── addressing ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_template_send_to_phone_uses_to_field(capture_send):
    sent = capture_send()

    wa_id, endpoint = await send_template_message(
        to=PHONE,
        template_name="welcome",
        variables={"1": "Ada"},
        phone_id="PHONE_ID",
        access_token="TOKEN",
    )

    assert wa_id == "wamid.STUB"
    assert endpoint == "primary"
    body = sent[0]["body"]
    assert body["to"] == PHONE
    assert body["recipient_type"] == "individual"
    assert "recipient" not in body
    assert body["messaging_product"] == "whatsapp"
    assert body["template"]["name"] == "welcome"


@pytest.mark.asyncio
async def test_template_send_to_bsuid_uses_recipient_field(capture_send):
    # Meta rejects a BSUID passed as `to`, and `to` wins when both are present,
    # so the two must never appear together.
    sent = capture_send()

    await send_template_message(
        to=BSUID,
        template_name="welcome",
        variables={},
        phone_id="PHONE_ID",
        access_token="TOKEN",
    )

    body = sent[0]["body"]
    assert body["recipient"] == BSUID
    assert "to" not in body
    assert "recipient_type" not in body


@pytest.mark.asyncio
async def test_text_send_to_bsuid_uses_recipient_field(capture_send):
    sent = capture_send()

    await send_text_message(
        to=BSUID, body="hello", phone_id="PHONE_ID", token="TOKEN"
    )

    body = sent[0]["body"]
    assert body["recipient"] == BSUID
    assert "to" not in body
    assert body["text"] == {"body": "hello"}


@pytest.mark.asyncio
async def test_text_send_to_phone_is_unchanged(capture_send):
    sent = capture_send()

    await send_text_message(
        to=PHONE, body="hello", phone_id="PHONE_ID", token="TOKEN"
    )

    body = sent[0]["body"]
    assert body["to"] == PHONE
    assert body["recipient_type"] == "individual"
    assert "recipient" not in body


# ── request shape ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_send_targets_the_given_phone_id_with_bearer_auth(capture_send):
    sent = capture_send()

    await send_template_message(
        to=PHONE,
        template_name="t",
        variables={},
        phone_id="PHONE_ID_42",
        access_token="TOKEN_XYZ",
    )

    assert sent[0]["url"].endswith("/PHONE_ID_42/messages")
    assert sent[0]["method"] == "POST"
    assert sent[0]["headers"]["authorization"] == "Bearer TOKEN_XYZ"


@pytest.mark.asyncio
async def test_body_variables_are_ordered_numerically(capture_send):
    # Meta positions body params by order, not by key, so {"10": ...} must not
    # sort ahead of {"2": ...} lexicographically.
    sent = capture_send()

    await send_template_message(
        to=PHONE,
        template_name="t",
        variables={"2": "second", "10": "tenth", "1": "first"},
        phone_id="PHONE_ID",
        access_token="TOKEN",
    )

    body_component = next(
        c for c in sent[0]["body"]["template"]["components"] if c["type"] == "body"
    )
    assert [p["text"] for p in body_component["parameters"]] == [
        "first",
        "second",
        "tenth",
    ]


@pytest.mark.asyncio
async def test_media_header_uses_the_declared_media_type(capture_send):
    sent = capture_send()

    await send_template_message(
        to=PHONE,
        template_name="t",
        variables={},
        media_url="https://example.test/clip.mp4",
        media_type="video",
        phone_id="PHONE_ID",
        access_token="TOKEN",
    )

    header = next(
        c for c in sent[0]["body"]["template"]["components"] if c["type"] == "header"
    )
    assert header["parameters"][0]["type"] == "video"
    assert header["parameters"][0]["video"] == {"link": "https://example.test/clip.mp4"}


# ── failure handling ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_meta_error_is_surfaced_with_its_code(capture_send):
    capture_send(
        httpx.Response(
            400,
            json={"error": {"code": 131049, "message": "healthy ecosystem"}},
        )
    )

    with pytest.raises(MetaAPIError) as exc:
        await send_template_message(
            to=PHONE,
            template_name="t",
            variables={},
            phone_id="PHONE_ID",
            access_token="TOKEN",
        )

    assert exc.value.code == "131049"


@pytest.mark.asyncio
async def test_restaurant_credentials_do_not_fall_back_to_the_global_waba(
    capture_send,
):
    # Cross-tenant leakage guard: a restaurant send must fail loudly rather than
    # silently going out from the global account.
    sent = capture_send(httpx.Response(400, json={"error": {"code": 190}}))

    with pytest.raises(MetaAPIError):
        await send_template_message(
            to=PHONE,
            template_name="t",
            variables={},
            phone_id="PHONE_ID",
            access_token="TOKEN",
        )

    assert len(sent) == 1, "must not retry against the global fallback endpoint"
