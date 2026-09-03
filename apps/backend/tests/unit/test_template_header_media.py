"""Regression tests for template header media uploads.

The Meta-side guard was a flat 10 MB while the app advertises — and
/media/upload accepts — 16 MB video and document headers. A 10-16 MB video
therefore uploaded to Cloudinary fine and then failed with media_too_large the
moment the template was submitted, which is part of why VIDEO headers were
switched off in the template editors.
"""

import httpx
import pytest

from app.services import meta_api
from app.services.cloudinary_service import (
    MAX_IMAGE_BYTES,
    MAX_PDF_BYTES,
    MAX_VIDEO_BYTES,
)


@pytest.fixture
def patched_client(monkeypatch):
    """Route every AsyncClient created inside meta_api through a mock transport."""

    def install(handler):
        original = httpx.AsyncClient

        def factory(*args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            return original(*args, **kwargs)

        monkeypatch.setattr(meta_api.httpx, "AsyncClient", factory)

    return install


def _media_handler(content_type: str, size: int):
    """Serve `size` bytes of `content_type`, then a working upload session."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200,
                headers={"content-type": content_type},
                content=b"\0" * size,
            )
        if request.url.path.endswith("/uploads"):
            return httpx.Response(200, json={"id": "upload:SESSION"})
        return httpx.Response(200, json={"h": "HANDLE"})

    return handler


def test_meta_media_caps_match_what_media_upload_accepts():
    """The two limits drifted apart once; keep them pinned together."""
    assert meta_api.MAX_MEDIA_BYTES_BY_TYPE["image"] == MAX_IMAGE_BYTES
    assert meta_api.MAX_MEDIA_BYTES_BY_TYPE["video"] == MAX_VIDEO_BYTES
    assert meta_api.MAX_MEDIA_BYTES_BY_TYPE["application"] == MAX_PDF_BYTES


async def test_video_header_between_10_and_16mb_is_accepted(patched_client):
    patched_client(_media_handler("video/mp4", 12 * 1024 * 1024))

    handle = await meta_api.create_media_handle_from_url(
        "https://cdn.test/clip.mp4", "APP", "tok"
    )

    assert handle == "HANDLE"


async def test_pdf_header_between_10_and_16mb_is_accepted(patched_client):
    patched_client(_media_handler("application/pdf", 12 * 1024 * 1024))

    handle = await meta_api.create_media_handle_from_url(
        "https://cdn.test/menu.pdf", "APP", "tok"
    )

    assert handle == "HANDLE"


async def test_oversized_image_header_is_rejected_at_its_own_cap(patched_client):
    """An image is capped at 5 MB, well below the 16 MB video ceiling."""
    patched_client(_media_handler("image/png", 6 * 1024 * 1024))

    with pytest.raises(meta_api.MetaAPIError) as exc:
        await meta_api.create_media_handle_from_url(
            "https://cdn.test/big.png", "APP", "tok"
        )

    assert exc.value.code == "media_too_large"


async def test_oversized_video_header_is_still_rejected(patched_client):
    patched_client(_media_handler("video/mp4", 17 * 1024 * 1024))

    with pytest.raises(meta_api.MetaAPIError) as exc:
        await meta_api.create_media_handle_from_url(
            "https://cdn.test/long.mp4", "APP", "tok"
        )

    assert exc.value.code == "media_too_large"
