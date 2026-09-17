"""What /media/upload will accept from a real device.

An upload from an Android phone produced no request at all — the server log has
no POST /api/media/upload for it, so the browser never sent one. The file input
carried accept="video/mp4,video/3gpp", and Android's pickers honour accept:
a clip whose type the picker reports differently simply cannot be chosen, and
nothing is submitted. The accept list is now video/*, which moves the decision
here.

That is only safe because every video is re-encoded to H.264/AAC MP4 before
delivery, so this endpoint no longer has to accept only what WhatsApp can play
— just what Cloudinary can read. It also has to cope with a browser that says
application/octet-stream, or says nothing, which Android does whenever a clip
comes from another app's storage.
"""

import pytest

from app.core.errors import InvalidFileFormatError
from app.routers import media as media_router
from app.routers.media import _resolve_content_type
from app.services import cloudinary_service

DERIVED_URL = (
    "https://res.cloudinary.com/demo/video/upload/"
    "ac_aac,c_limit,f_mp4,q_auto,vc_h264,w_1280/v1/clip.mp4"
)


class _StubUpload:
    def __init__(self, content_type, filename):
        self.content_type = content_type
        self.filename = filename

    async def read(self):
        return b"data"


@pytest.fixture
def cloudinary_stub(monkeypatch):
    """Accept any upload and record the resource_type it was filed under."""
    calls = []

    def fake_upload(content, **kwargs):
        calls.append(kwargs)
        return {
            "secure_url": "https://res.cloudinary.com/demo/x",
            "public_id": "whatsapp-media/abc",
            "eager": [{"secure_url": DERIVED_URL}],
        }

    monkeypatch.setattr(cloudinary_service.cloudinary.uploader, "upload", fake_upload)
    return calls


# ── Type resolution ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "claimed,filename,expected",
    [
        ("video/mp4", "clip.mp4", "video/mp4"),
        # A charset parameter must not defeat the lookup.
        ("video/mp4; charset=binary", "clip.mp4", "video/mp4"),
        ("VIDEO/MP4", "clip.mp4", "video/mp4"),
        # The Android cases: the claim says nothing, the name does.
        ("application/octet-stream", "clip.mp4", "video/mp4"),
        ("binary/octet-stream", "clip.mov", "video/quicktime"),
        (None, "clip.mp4", "video/mp4"),
        ("", "clip.3gp", "video/3gpp"),
        # A stdlib quirk worth pinning: mimetypes calls .3gp audio/3gpp.
        ("application/octet-stream", "clip.3gp", "video/3gpp"),
        # Neither says anything useful — the claim is passed through as-is and
        # fails the rule lookup, which is the rejection we want.
        ("application/octet-stream", "", "application/octet-stream"),
        (None, None, ""),
    ],
)
def test_content_type_falls_back_to_the_filename(claimed, filename, expected):
    assert _resolve_content_type(_StubUpload(claimed, filename)) == expected


# ── What gets through ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "claimed,filename",
    [
        ("video/mp4", "clip.mp4"),
        ("video/3gpp", "clip.3gp"),
        ("video/quicktime", "clip.mov"),
        ("video/x-matroska", "clip.mkv"),
        ("video/webm", "clip.webm"),
        ("application/octet-stream", "clip.mp4"),
        (None, "clip.mov"),
    ],
)
async def test_a_video_any_device_might_send_is_accepted(
    cloudinary_stub, claimed, filename
):
    response = await media_router.upload_image(
        file=_StubUpload(claimed, filename), current_user={}
    )

    assert cloudinary_stub[0]["resource_type"] == "video"
    # Whatever arrived, what leaves is the re-encode.
    assert response["url"] == DERIVED_URL


async def test_images_and_pdfs_are_unchanged(cloudinary_stub):
    for claimed, filename, resource in [
        ("image/png", "card.png", "image"),
        ("application/pdf", "menu.pdf", "raw"),
    ]:
        cloudinary_stub.clear()
        await media_router.upload_image(
            file=_StubUpload(claimed, filename), current_user={}
        )
        assert cloudinary_stub[0]["resource_type"] == resource
        # Only video pays for an eager pass.
        assert ("eager" in cloudinary_stub[0]) is (resource == "video")


@pytest.mark.parametrize(
    "claimed,filename",
    [
        ("text/csv", "contacts.csv"),
        ("application/zip", "bundle.zip"),
        ("application/octet-stream", "mystery"),
    ],
)
async def test_a_file_we_cannot_place_is_still_rejected(
    cloudinary_stub, claimed, filename
):
    with pytest.raises(InvalidFileFormatError) as excinfo:
        await media_router.upload_image(
            file=_StubUpload(claimed, filename), current_user={}
        )

    # The message names the file, so the rejection log says which one.
    if filename:
        assert filename in str(excinfo.value)
    assert not cloudinary_stub
