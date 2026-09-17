"""Every header video is re-encoded before it can reach a recipient.

A video header reached Android recipients as "This video is not available
because something is wrong with the video file". The re-encode that fixes it
was briefly made conditional on a codec probe, as an optimisation so that
already-conforming files would not wait for a transcode. That shipped, and the
bug came straight back: the offending file reported mp4/h264/aac, passed the
probe, and was delivered untouched.

The codec name cannot answer the question. High 10, 4:2:2 and 4:4:4 streams all
report `codec == "h264"`; Android's hardware decoders refuse them and iOS's
VideoToolbox does not. Profile, level, pixel format and moov placement are what
decide it, and the last of those is not in the probe at all. So the re-encode is
unconditional, and these tests pin that it stays that way.
"""

import pytest

from app.core.errors import ValidationError
from app.routers import media as media_router
from app.services import cloudinary_service
from app.services.cloudinary_service import (
    MAX_VIDEO_BYTES,
    UnplayableVideoError,
    upload_whatsapp_video,
    whatsapp_video_defects,
)

ORIGINAL_URL = "https://res.cloudinary.com/demo/video/upload/v1/clip.mp4"
DERIVED_URL = (
    "https://res.cloudinary.com/demo/video/upload/"
    "ac_aac,c_limit,f_mp4,q_auto,vc_h264,w_1280/v1/clip.mp4"
)


def _probe(video="h264", audio="aac", container="mp4", **video_fields):
    """A Cloudinary video upload response, with its eager entry ready."""
    result = {
        "secure_url": ORIGINAL_URL,
        "public_id": "whatsapp-media/abc",
        "format": container,
        "bytes": 12 * 1024 * 1024,
        "eager": [{"secure_url": DERIVED_URL, "bytes": 6 * 1024 * 1024}],
    }
    if video:
        result["video"] = {"codec": video, **video_fields}
    if audio:
        result["audio"] = {"codec": audio, "frequency": 44100, "channels": 2}
    return result


@pytest.fixture
def cloudinary_calls(monkeypatch):
    """Record the Cloudinary calls and script their responses."""
    calls = {"upload": []}
    state = {"upload": _probe()}

    def fake_upload(content, **kwargs):
        calls["upload"].append(kwargs)
        response = state["upload"]
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(cloudinary_service.cloudinary.uploader, "upload", fake_upload)
    calls["state"] = state
    return calls


# ── The re-encode is unconditional ────────────────────────────────────────────


@pytest.mark.parametrize(
    "probe",
    [
        # The production case: nominally conforming, unplayable on Android.
        _probe(profile="High 10", pix_format="yuv420p10le"),
        _probe(profile="High 4:2:2", pix_format="yuv422p"),
        _probe(profile="High", pix_format="yuv420p", level=51),
        # Plainly wrong, and equally re-encoded.
        _probe(video="hevc"),
        _probe(audio="ac3"),
        _probe(container="webm"),
        # Nothing the probe can fault at all.
        _probe(profile="Main", pix_format="yuv420p"),
        _probe(audio=None),
        {"secure_url": ORIGINAL_URL, "public_id": "whatsapp-media/abc",
         "eager": [{"secure_url": DERIVED_URL}]},
    ],
    ids=[
        "high-10-bit", "high-422", "level-51", "hevc", "ac3-audio",
        "webm", "conforming-main", "no-audio-track", "unprobed",
    ],
)
def test_every_video_is_re_encoded(cloudinary_calls, probe):
    """The regression this file exists for: no probe result skips the re-encode."""
    cloudinary_calls["state"]["upload"] = probe

    url, public_id = upload_whatsapp_video(b"data", "whatsapp-media/abc.mp4")

    # The URL handed on to Meta is always the re-encode, never the source.
    assert url == DERIVED_URL
    assert url != ORIGINAL_URL
    assert public_id == "whatsapp-media/abc"


def test_the_transform_targets_what_whatsapp_decodes(cloudinary_calls):
    upload_whatsapp_video(b"data", "whatsapp-media/abc.mp4")

    eager = cloudinary_calls["upload"][0]["eager"][0]
    assert eager["video_codec"] == "h264"
    assert eager["audio_codec"] == "aac"
    assert eager["format"] == "mp4"
    # Caps the re-encode's cost, which is what makes waiting for it affordable.
    assert eager["width"] == 1280
    assert eager["crop"] == "limit"


def test_the_transform_is_synchronous(cloudinary_calls):
    """An async eager hands Meta a URL Cloudinary answers 423 for."""
    upload_whatsapp_video(b"data", "whatsapp-media/abc.mp4")

    assert cloudinary_calls["upload"][0]["eager_async"] is False


def test_the_call_is_bounded(cloudinary_calls):
    """The SDK has no default timeout; a stuck transcode would hang the request."""
    upload_whatsapp_video(b"data", "whatsapp-media/abc.mp4")

    assert cloudinary_calls["upload"][0]["timeout"] > 0


# ── A file we cannot make playable fails at upload, not at the recipient ──────


def test_a_failed_upload_or_transcode_is_surfaced(cloudinary_calls):
    cloudinary_calls["state"]["upload"] = RuntimeError("cloudinary timed out")

    with pytest.raises(UnplayableVideoError) as excinfo:
        upload_whatsapp_video(b"data", "whatsapp-media/abc.mp4")

    assert "H.264" in str(excinfo.value)


def test_an_unfinished_transcode_is_rejected(cloudinary_calls):
    """Cloudinary reports a slow eager as pending; its URL 423s until built."""
    probe = _probe()
    probe["eager"] = [{"secure_url": DERIVED_URL, "status": "pending"}]
    cloudinary_calls["state"]["upload"] = probe

    with pytest.raises(UnplayableVideoError):
        upload_whatsapp_video(b"data", "whatsapp-media/abc.mp4")


def test_a_missing_eager_result_is_rejected(cloudinary_calls):
    """Never silently fall back to the source file — that is the whole bug."""
    probe = _probe()
    del probe["eager"]
    cloudinary_calls["state"]["upload"] = probe

    with pytest.raises(UnplayableVideoError):
        upload_whatsapp_video(b"data", "whatsapp-media/abc.mp4")


def test_a_transcode_over_the_whatsapp_cap_is_rejected(cloudinary_calls):
    probe = _probe()
    probe["eager"] = [{"secure_url": DERIVED_URL, "bytes": MAX_VIDEO_BYTES + 1}]
    cloudinary_calls["state"]["upload"] = probe

    with pytest.raises(UnplayableVideoError) as excinfo:
        upload_whatsapp_video(b"data", "whatsapp-media/abc.mp4")

    assert "16 MB" in str(excinfo.value)


# ── The probe still reports, it just does not decide ──────────────────────────


@pytest.mark.parametrize(
    "probe,expected",
    [
        (_probe(video="hevc"), ["hevc video"]),
        (_probe(audio="ac3"), ["ac3 audio"]),
        (_probe(container="webm"), ["webm container"]),
        (_probe(), []),
        (_probe(audio=None), []),
        # The case that defeated the old gate: nothing to report, unplayable.
        (_probe(profile="High 10", pix_format="yuv420p10le"), []),
    ],
    ids=["hevc", "ac3", "webm", "conforming", "no-audio", "high-10-bit"],
)
def test_defects_describe_only_what_a_codec_name_can_express(probe, expected):
    assert whatsapp_video_defects(probe) == expected


# ── The upload endpoint ───────────────────────────────────────────────────────


class _StubUpload:
    def __init__(self, content_type, filename):
        self.content_type = content_type
        self.filename = filename

    async def read(self):
        return b"data"


async def test_upload_endpoint_returns_the_re_encoded_url(cloudinary_calls):
    response = await media_router.upload_image(
        file=_StubUpload("video/mp4", "clip.mp4"), current_user={}
    )

    assert response["url"] == DERIVED_URL


async def test_upload_endpoint_surfaces_a_failure_to_the_operator(cloudinary_calls):
    cloudinary_calls["state"]["upload"] = RuntimeError("cloudinary is down")

    with pytest.raises(ValidationError):
        await media_router.upload_image(
            file=_StubUpload("video/mp4", "clip.mp4"), current_user={}
        )


async def test_image_upload_is_untouched_by_any_of_this(cloudinary_calls):
    cloudinary_calls["state"]["upload"] = {
        "secure_url": "https://res.cloudinary.com/demo/image/upload/v1/card.png",
        "public_id": "whatsapp-media/card",
    }

    response = await media_router.upload_image(
        file=_StubUpload("image/png", "card.png"), current_user={}
    )

    assert response["public_id"] == "whatsapp-media/card"
    assert cloudinary_calls["upload"][0]["resource_type"] == "image"
    assert "eager" not in cloudinary_calls["upload"][0]
