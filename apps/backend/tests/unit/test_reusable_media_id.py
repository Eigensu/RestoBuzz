"""The reusable Meta media id: payload shape, upload, and its expiry window.

A campaign used to send the same Cloudinary link once per recipient, so Meta
re-fetched the source file for every message. It now uploads the media to Meta
once and references `{"id": ...}` instead. None of that path had tests, and it
is inert in production until celery-worker stops deploying from `main`, so its
first real exercise will be the moment the worker is repointed.

The expiry window matters most: Meta deletes media 30 days after upload, and an
id is resolved at campaign *creation*. Unlike a link, an expired id has no
fallback at send time — every message in the campaign fails.
"""

from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.services import meta_api
from app.services.meta_api import (
    MetaAPIError,
    _build_payload,
    create_reusable_media_id,
    media_id_is_safe_for,
)

NOW = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)
PHONE = "919876543210"
LINK = "https://res.cloudinary.com/demo/video/upload/v1/clip.mp4"


# ── Payload shape ─────────────────────────────────────────────────────────────


def _header(payload):
    return payload["template"]["components"][0]["parameters"][0]


def test_media_id_is_preferred_over_the_link():
    payload = _build_payload(
        PHONE, "promo", {}, LINK, media_type="video", media_id="MEDIA123"
    )

    assert _header(payload)["video"] == {"id": "MEDIA123"}


def test_link_is_used_when_there_is_no_media_id():
    payload = _build_payload(PHONE, "promo", {}, LINK, media_type="video")

    assert _header(payload)["video"] == {"link": LINK}


def test_media_id_keeps_the_header_kind_from_the_template():
    """Meta rejects a send whose parameter type misses the declared format."""
    payload = _build_payload(
        PHONE, "promo", {}, LINK, media_type="document", media_id="MEDIA123"
    )

    assert _header(payload)["type"] == "document"
    assert _header(payload)["document"] == {"id": "MEDIA123"}


def test_no_header_component_without_media():
    payload = _build_payload(PHONE, "promo", {"1": "Aarav"}, None)

    assert all(c["type"] != "header" for c in payload["template"]["components"])


# ── Expiry window ─────────────────────────────────────────────────────────────


def test_an_immediate_campaign_can_use_a_media_id():
    assert media_id_is_safe_for(None, NOW) is True


@pytest.mark.parametrize("days", [0, 1, 7, 24])
def test_a_campaign_inside_the_window_can_use_a_media_id(days):
    assert media_id_is_safe_for(NOW + timedelta(days=days), NOW) is True


@pytest.mark.parametrize("days", [26, 30, 31, 90])
def test_a_campaign_past_the_window_keeps_the_link(days):
    """Meta deletes the media at 30 days; an expired id fails every message."""
    assert media_id_is_safe_for(NOW + timedelta(days=days), NOW) is False


def test_a_naive_scheduled_at_is_read_as_utc():
    """campaign_jobs round-trips datetimes through Mongo, which can drop tzinfo."""
    naive = (NOW + timedelta(days=90)).replace(tzinfo=None)

    assert media_id_is_safe_for(naive, NOW) is False


# ── Upload ────────────────────────────────────────────────────────────────────


@pytest.fixture
def meta_media(monkeypatch):
    """Stub host resolution and route meta_api's clients at a mock transport."""

    async def public_address(host):
        return ["93.184.216.34"]

    monkeypatch.setattr(meta_api, "_resolve_host", public_address)
    requests: list[httpx.Request] = []

    def install(upload_response: httpx.Response):
        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.method == "GET":
                return httpx.Response(
                    200, headers={"content-type": "video/mp4"}, content=b"movie"
                )
            return upload_response

        original = httpx.AsyncClient

        def factory(*args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            return original(*args, **kwargs)

        monkeypatch.setattr(meta_api.httpx, "AsyncClient", factory)
        return requests

    return install


async def test_media_is_uploaded_to_the_campaign_phone_number(meta_media):
    """The id is scoped to the phone_id it was uploaded against."""
    requests = meta_media(httpx.Response(200, json={"id": "MEDIA123"}))

    media_id = await create_reusable_media_id(LINK, PHONE, "tok")

    assert media_id == "MEDIA123"
    upload = next(r for r in requests if r.method == "POST")
    assert upload.url.path.endswith(f"/{PHONE}/media")
    assert upload.headers["authorization"] == "Bearer tok"


async def test_a_meta_error_is_raised_not_swallowed(meta_media):
    """create_campaign catches this and falls back to the link."""
    meta_media(
        httpx.Response(400, json={"error": {"code": 131053, "message": "bad media"}})
    )

    with pytest.raises(MetaAPIError) as excinfo:
        await create_reusable_media_id(LINK, PHONE, "tok")

    assert excinfo.value.code == "131053"


async def test_a_response_without_an_id_is_an_error(meta_media):
    meta_media(httpx.Response(200, json={"messaging_product": "whatsapp"}))

    with pytest.raises(MetaAPIError) as excinfo:
        await create_reusable_media_id(LINK, PHONE, "tok")

    assert excinfo.value.code == "media_id_missing"


async def test_a_non_json_response_is_an_error(meta_media):
    meta_media(httpx.Response(502, content=b"<html>bad gateway</html>"))

    with pytest.raises(MetaAPIError) as excinfo:
        await create_reusable_media_id(LINK, PHONE, "tok")

    assert excinfo.value.code == "parse_error"


async def test_an_oversized_source_is_rejected_before_upload(meta_media, monkeypatch):
    """The size cap still applies on the way in to Meta's own storage."""
    monkeypatch.setattr(meta_api, "MAX_MEDIA_BYTES_BY_TYPE", {"video": 2})
    requests = meta_media(httpx.Response(200, json={"id": "MEDIA123"}))

    with pytest.raises(MetaAPIError) as excinfo:
        await create_reusable_media_id(LINK, PHONE, "tok")

    assert excinfo.value.code == "media_too_large"
    assert not [r for r in requests if r.method == "POST"]


async def test_a_private_media_url_is_rejected_before_upload(monkeypatch):
    """The SSRF check guards this endpoint too, not just template creation."""

    async def private_address(host):
        return ["169.254.169.254"]

    monkeypatch.setattr(meta_api, "_resolve_host", private_address)

    with pytest.raises(MetaAPIError) as excinfo:
        await create_reusable_media_id("https://evil.example/x.mp4", PHONE, "tok")

    assert excinfo.value.code == "media_url_rejected"
