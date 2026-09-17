"""Regression tests for unplayable WhatsApp header videos.

A template header video reached recipients as "This video is not available
because something is wrong with the video file". Nothing in the pipeline looked
at the video stream: the browser's accept filter and /media/upload both keyed
off the OS-reported MIME type, Cloudinary stored the bytes verbatim, and Meta
validated only the MIME type and the 16 MB cap before delivering. A video in a
codec WhatsApp cannot decode passed every check we had and failed on the
handset, where no check of ours could see it.

Cloudinary probes each video it stores, so the codecs are in the upload
response we were discarding. These tests pin that the probe is read, that a
non-conforming file is re-encoded rather than delivered, and that a file we
cannot make playable fails at upload instead of at the recipient.
"""

import pytest

from app.core.errors import ValidationError
from app.routers import media as media_router
from app.services import cloudinary_service
from app.services.cloudinary_service import (
    MAX_VIDEO_BYTES,
    UnplayableVideoError,
    upload_whatsapp_video,
)

ORIGINAL_URL = "https://res.cloudinary.com/demo/video/upload/v1/clip.mp4"
DERIVED_URL = (
    "https://res.cloudinary.com/demo/video/upload/"
    "ac_aac,c_limit,f_mp4,q_auto,vc_h264,w_1280/v1/clip.mp4"
)


def _probe(video="h264", audio="aac", container="mp4"):
    """A Cloudinary video upload response with the probe fields it returns."""
    result = {
        "secure_url": ORIGINAL_URL,
        "public_id": "whatsapp-media/abc",
        "format": container,
        "bytes": 12 * 1024 * 1024,
    }
    if video:
        result["video"] = {"codec": video, "profile": "High", "level": 40}
    if audio:
        result["audio"] = {"codec": audio, "frequency": 44100, "channels": 2}
    return result


@pytest.fixture
def cloudinary_calls(monkeypatch):
    """Record the Cloudinary calls and script their responses."""
    calls = {"upload": [], "explicit": []}
    state = {"upload": _probe(), "explicit": {"eager": [{"secure_url": DERIVED_URL}]}}

    def fake_upload(content, **kwargs):
        calls["upload"].append(kwargs)
        return state["upload"]

    def fake_explicit(public_id, **kwargs):
        calls["explicit"].append({"public_id": public_id, **kwargs})
        response = state["explicit"]
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(cloudinary_service.cloudinary.uploader, "upload", fake_upload)
    monkeypatch.setattr(
        cloudinary_service.cloudinary.uploader, "explicit", fake_explicit
    )
    calls["state"] = state
    return calls


# ── Files WhatsApp can already play are left alone ────────────────────────────


def test_h264_aac_mp4_is_delivered_untouched(cloudinary_calls):
    url, public_id = upload_whatsapp_video(b"data", "whatsapp-media/abc.mp4")

    assert url == ORIGINAL_URL
    assert public_id == "whatsapp-media/abc"
    assert cloudinary_calls["explicit"] == []


def test_video_with_no_audio_track_is_untouched(cloudinary_calls):
    """WhatsApp supports a video with no audio stream — don't re-encode it."""
    cloudinary_calls["state"]["upload"] = _probe(audio=None)

    url, _ = upload_whatsapp_video(b"data", "whatsapp-media/abc.mp4")

    assert url == ORIGINAL_URL
    assert cloudinary_calls["explicit"] == []


def test_unprobed_video_is_not_rejected(cloudinary_calls):
    """A probe Cloudinary could not fill in is no reason to reject the upload."""
    cloudinary_calls["state"]["upload"] = {
        "secure_url": ORIGINAL_URL,
        "public_id": "whatsapp-media/abc",
    }

    url, _ = upload_whatsapp_video(b"data", "whatsapp-media/abc.mp4")

    assert url == ORIGINAL_URL
    assert cloudinary_calls["explicit"] == []


# ── Files WhatsApp cannot decode are re-encoded before delivery ───────────────


@pytest.mark.parametrize(
    "probe",
    [
        _probe(video="hevc"),          # iPhone / "HD" exports
        _probe(video="vp9"),
        _probe(audio="ac3"),
        _probe(container="webm"),
    ],
    ids=["hevc-video", "vp9-video", "ac3-audio", "webm-container"],
)
def test_unplayable_video_is_transcoded_and_the_derived_url_is_delivered(
    cloudinary_calls, probe
):
    cloudinary_calls["state"]["upload"] = probe

    url, public_id = upload_whatsapp_video(b"data", "whatsapp-media/abc.mp4")

    # The URL handed on to Meta is the re-encode, not the file we were given.
    assert url == DERIVED_URL
    assert public_id == "whatsapp-media/abc"

    eager = cloudinary_calls["explicit"][0]["eager"][0]
    assert eager["video_codec"] == "h264"
    assert eager["audio_codec"] == "aac"
    assert eager["format"] == "mp4"


def test_transcode_is_requested_synchronously(cloudinary_calls):
    """An async eager would hand Meta a URL Cloudinary has not built yet."""
    cloudinary_calls["state"]["upload"] = _probe(video="hevc")

    upload_whatsapp_video(b"data", "whatsapp-media/abc.mp4")

    assert cloudinary_calls["explicit"][0]["eager_async"] is False


# ── A file we cannot make playable fails at upload, not at the recipient ──────


def test_failed_transcode_names_the_offending_codec(cloudinary_calls):
    cloudinary_calls["state"]["upload"] = _probe(video="hevc")
    cloudinary_calls["state"]["explicit"] = RuntimeError("cloudinary is down")

    with pytest.raises(UnplayableVideoError) as excinfo:
        upload_whatsapp_video(b"data", "whatsapp-media/abc.mp4")

    assert "hevc video" in str(excinfo.value)


def test_unfinished_transcode_is_rejected(cloudinary_calls):
    """Cloudinary reports a slow eager as pending; its URL 404s until it's built."""
    cloudinary_calls["state"]["upload"] = _probe(video="hevc")
    cloudinary_calls["state"]["explicit"] = {
        "eager": [{"secure_url": DERIVED_URL, "status": "pending"}]
    }

    with pytest.raises(UnplayableVideoError):
        upload_whatsapp_video(b"data", "whatsapp-media/abc.mp4")


def test_transcode_over_the_whatsapp_cap_is_rejected(cloudinary_calls):
    cloudinary_calls["state"]["upload"] = _probe(video="hevc")
    cloudinary_calls["state"]["explicit"] = {
        "eager": [{"secure_url": DERIVED_URL, "bytes": MAX_VIDEO_BYTES + 1}]
    }

    with pytest.raises(UnplayableVideoError) as excinfo:
        upload_whatsapp_video(b"data", "whatsapp-media/abc.mp4")

    assert "16 MB" in str(excinfo.value)


# ── The upload endpoint routes video through the check ────────────────────────


class _StubUpload:
    def __init__(self, content_type, filename):
        self.content_type = content_type
        self.filename = filename

    async def read(self):
        return b"data"


async def test_upload_endpoint_returns_the_playable_url(cloudinary_calls):
    cloudinary_calls["state"]["upload"] = _probe(video="hevc")

    response = await media_router.upload_image(
        file=_StubUpload("video/mp4", "clip.mp4"), current_user={}
    )

    assert response["url"] == DERIVED_URL


async def test_upload_endpoint_surfaces_an_unplayable_video_to_the_operator(
    cloudinary_calls,
):
    cloudinary_calls["state"]["upload"] = _probe(video="hevc")
    cloudinary_calls["state"]["explicit"] = RuntimeError("cloudinary is down")

    with pytest.raises(ValidationError) as excinfo:
        await media_router.upload_image(
            file=_StubUpload("video/mp4", "clip.mp4"), current_user={}
        )

    assert "H.264" in str(excinfo.value)


async def test_image_upload_still_goes_through_the_plain_path(cloudinary_calls):
    cloudinary_calls["state"]["upload"] = {
        "secure_url": "https://res.cloudinary.com/demo/image/upload/v1/card.png",
        "public_id": "whatsapp-media/card",
    }

    response = await media_router.upload_image(
        file=_StubUpload("image/png", "card.png"), current_user={}
    )

    assert response["public_id"] == "whatsapp-media/card"
    assert cloudinary_calls["upload"][0]["resource_type"] == "image"
