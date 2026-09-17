import cloudinary
import cloudinary.uploader
from app.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

cloudinary.config(
    cloud_name=settings.cloudinary_cloud_name,
    api_key=settings.cloudinary_api_key,
    api_secret=settings.cloudinary_api_secret,
    secure=True,
)

MAX_IMAGE_BYTES = 5 * 1024 * 1024     # 5 MB
MAX_VIDEO_BYTES = 16 * 1024 * 1024    # 16 MB (WhatsApp template video header cap)
MAX_PDF_BYTES = 16 * 1024 * 1024      # 16 MB

# Diagnostic only — these decide what gets logged, never whether a video is
# re-encoded. A file can satisfy all three and still be unplayable on Android,
# because the codec name says nothing about the H.264 profile, level or pixel
# format, and nothing here can see where the moov atom sits. Gating on them is
# what let an unplayable video through in production.
#
# Nothing upstream catches it either: the browser accept filter and
# /media/upload both go on the OS-reported MIME type, and Meta validates the
# MIME type and the size but not the encoding, so it ingests the file and
# renders its thumbnail server-side before delivering something the handset
# cannot open.
WHATSAPP_VIDEO_CODECS = {"h264", "avc1"}
WHATSAPP_AUDIO_CODECS = {"aac"}
WHATSAPP_VIDEO_FORMATS = {"mp4", "3gp"}

# Applied to every uploaded video. Re-encoding normalises the profile, the
# pixel format and the moov placement together — the three things that decide
# whether Android will play it and that no probe here can rule out.
#
# No explicit "faststart" flag: that's not a real Cloudinary flag name (it
# rejects the upload with "Eager Invalid flag in transformation: faststart"
# — confirmed against a live upload). Cloudinary's video pipeline already
# places the moov atom for progressive playback by default when re-encoding.
#
# w_1280/c_limit holds the output inside H.264 level 4.0 and, with q_auto,
# keeps the re-encode from growing past MAX_VIDEO_BYTES; c_limit never
# upscales, so a smaller source keeps its dimensions.
_VIDEO_EAGER_TRANSFORM = [
    {
        "video_codec": "h264",
        "audio_codec": "aac",
        "format": "mp4",
        "width": 1280,
        "crop": "limit",
        "quality": "auto",
    }
]

# The Cloudinary SDK has no default timeout, so a stuck transcode would hold a
# threadpool worker — and the upload request behind it — open forever. 16 MB is
# well inside Cloudinary's synchronous-transform ceiling, so anything still
# running at this point is not going to finish.
_VIDEO_CALL_TIMEOUT = 120

_REENCODE_ADVICE = (
    "WhatsApp only plays H.264 video with AAC audio in an MP4 container. "
    "Re-export the file with those settings and upload it again."
)


class UnplayableVideoError(Exception):
    """A video WhatsApp cannot decode, that we could not normalise either."""


def upload_media(content: bytes, filename: str, resource_type: str = "auto") -> str:
    """Upload bytes to Cloudinary and return the secure URL."""
    return upload_media_result(content, filename, resource_type)[0]


def upload_media_result(
    content: bytes, filename: str, resource_type: str = "auto"
) -> tuple[str, str]:
    """Upload bytes to Cloudinary and return (secure_url, public_id).

    The public_id is needed by per-recipient personalization (e-cards), which
    builds text-overlay delivery URLs from the base image's public_id rather
    than its full URL.

    Header videos go through upload_whatsapp_video instead, which has to look
    at what it stored before it can hand back a URL.
    """
    result = cloudinary.uploader.upload(
        content,
        public_id=filename,
        resource_type=resource_type,
        overwrite=True,
    )
    return result["secure_url"], result["public_id"]


def whatsapp_video_defects(result: dict) -> list[str]:
    """Name the parts of an uploaded video that WhatsApp plainly cannot decode.

    Reads Cloudinary's probe of the stored file, not the MIME type the browser
    claimed. An empty list does NOT mean the file is playable — it means
    nothing is wrong at the level a codec name can express. This is for the
    log; the re-encode happens either way.
    """
    defects: list[str] = []

    container = str(result.get("format") or "").lower()
    if container and container not in WHATSAPP_VIDEO_FORMATS:
        defects.append(f"{container} container")

    video_codec = str((result.get("video") or {}).get("codec") or "").lower()
    if video_codec and video_codec not in WHATSAPP_VIDEO_CODECS:
        defects.append(f"{video_codec} video")

    # An absent audio block means the file has no audio track, which WhatsApp
    # explicitly supports — only an audio track in the wrong codec is a defect.
    audio_codec = str((result.get("audio") or {}).get("codec") or "").lower()
    if audio_codec and audio_codec not in WHATSAPP_AUDIO_CODECS:
        defects.append(f"{audio_codec} audio")

    return defects


def upload_whatsapp_video(content: bytes, public_id: str) -> tuple[str, str]:
    """Upload a header video, re-encode it, and return the (secure_url, public_id).

    Every video is re-encoded, not just the ones that look wrong. Android's
    hardware decoders reject a file for its H.264 profile, level or pixel
    format, none of which the codec name tells you: a 10-bit High 10, a 4:2:2
    or a 4:4:4 stream all report `codec == "h264"`, and all of them play on
    iOS and fail on Android with "something is wrong with the video file".
    moov placement is not reported at all. Gating the re-encode on a codec
    probe therefore passes exactly the files that need it, which is what it
    did in production — so the probe now only explains the decision in the
    log, it does not make it.

    The re-encode is requested synchronously. An `eager_async` upload returns
    the derived URL before the file behind it exists, and Cloudinary does not
    build a *video* derivative on demand the way it does an image — it answers
    423 while the transcode is still queued, so a campaign created in that
    window sends a link Meta cannot fetch. The transform caps the output at
    1280 wide with q_auto, which is what keeps the wait affordable: the source
    is re-encoded down, not at whatever resolution it arrived in.

    Raises UnplayableVideoError when the re-encode cannot produce a compliant
    file — better a failure the operator sees at upload than a campaign that
    reaches every recipient broken.
    """
    try:
        result = cloudinary.uploader.upload(
            content,
            public_id=public_id,
            resource_type="video",
            overwrite=True,
            eager=_VIDEO_EAGER_TRANSFORM,
            eager_async=False,
            timeout=_VIDEO_CALL_TIMEOUT,
        )
    except Exception as exc:
        raise UnplayableVideoError(
            f"Converting this video failed or took too long. {_REENCODE_ADVICE}"
        ) from exc

    stored_public_id = result["public_id"]
    source = result.get("video") or {}
    logger.info(
        "whatsapp_video_transcoded",
        public_id=stored_public_id,
        source_codec=source.get("codec"),
        source_profile=source.get("profile"),
        source_pix_format=source.get("pix_format"),
        source_level=source.get("level"),
        # Empty for a file that was already nominally conforming — which is
        # most of them, and says nothing about whether Android could play it.
        defects=whatsapp_video_defects(result),
    )

    eager = next(iter(result.get("eager") or []), {})
    url = eager.get("secure_url")
    if not url or eager.get("status") in ("pending", "processing"):
        raise UnplayableVideoError(
            f"This video is still converting. {_REENCODE_ADVICE}"
        )

    size = eager.get("bytes")
    if isinstance(size, int) and size > MAX_VIDEO_BYTES:
        raise UnplayableVideoError(
            f"Converting this video produced a file over the "
            f"{MAX_VIDEO_BYTES // (1024 * 1024)} MB WhatsApp limit. "
            "Shorten it or lower its resolution, then upload it again."
        )

    return url, stored_public_id
