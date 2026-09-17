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

# What WhatsApp's own decoders accept. Source clips (exported by CapCut,
# Premiere, phone cameras, etc.) often use a codec, H.264 profile or pixel
# format that Android's hardware decoders reject outright even though iOS's
# VideoToolbox plays them fine — "This video is not available because something
# is wrong with the video file", for Android recipients only. Nothing upstream
# catches it: the browser accept filter and /media/upload both go on the
# OS-reported MIME type, and Meta validates the MIME type and the size but not
# the codecs, so it ingests the file and renders its thumbnail server-side
# before delivering something the handset cannot open.
WHATSAPP_VIDEO_CODECS = {"h264", "avc1"}
WHATSAPP_AUDIO_CODECS = {"aac"}
WHATSAPP_VIDEO_FORMATS = {"mp4", "3gp"}

# Applied only to a video that fails the probe below.
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
    """Name the parts of an uploaded video that WhatsApp cannot decode.

    Reads Cloudinary's probe of the stored file, not the MIME type the browser
    claimed. A stream Cloudinary could not identify is left alone rather than
    guessed at, so an unreadable probe never rejects a file that plays.
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
    """Upload a header video and return a (secure_url, public_id) WhatsApp plays.

    Cloudinary probes every video it stores and reports the container and the
    video and audio codecs in the upload response. A file that already matches
    what WhatsApp decodes is delivered untouched; anything else is re-encoded
    and the derived URL is returned in its place, so what Meta fetches at send
    time is always a file the recipient can open.

    The re-encode is requested synchronously. An `eager_async` upload returns
    the derived URL before the file behind it exists, and Cloudinary does not
    build a *video* derivative on demand the way it does an image — it answers
    423 while the transcode is still queued, so a campaign created in that
    window sends a link Meta cannot fetch. Waiting is affordable because only a
    non-conforming file waits at all: the common case returns after the plain
    upload, having transcoded nothing.

    Raises UnplayableVideoError when the re-encode cannot produce a compliant
    file — better a failure the operator sees at upload than a campaign that
    reaches every recipient broken.
    """
    result = cloudinary.uploader.upload(
        content,
        public_id=public_id,
        resource_type="video",
        overwrite=True,
        timeout=_VIDEO_CALL_TIMEOUT,
    )
    stored_public_id = result["public_id"]

    defects = whatsapp_video_defects(result)
    if not defects:
        return result["secure_url"], stored_public_id

    logger.warning(
        "whatsapp_video_transcode",
        public_id=stored_public_id,
        defects=defects,
    )
    summary = ", ".join(defects)

    try:
        derived = cloudinary.uploader.explicit(
            stored_public_id,
            type="upload",
            resource_type="video",
            eager=_VIDEO_EAGER_TRANSFORM,
            eager_async=False,
            timeout=_VIDEO_CALL_TIMEOUT,
        )
    except Exception as exc:
        raise UnplayableVideoError(
            f"This video uses {summary} and converting it failed. {_REENCODE_ADVICE}"
        ) from exc

    # A timed-out transcode surfaces as an SDK error above; this is the other
    # shape — Cloudinary answering with a derived asset it has not finished.
    eager = next(iter(derived.get("eager") or []), {})
    url = eager.get("secure_url")
    if not url or eager.get("status") in ("pending", "processing"):
        raise UnplayableVideoError(
            f"This video uses {summary} and is taking too long to convert. "
            f"{_REENCODE_ADVICE}"
        )

    size = eager.get("bytes")
    if isinstance(size, int) and size > MAX_VIDEO_BYTES:
        raise UnplayableVideoError(
            f"This video uses {summary}, and converting it produced a file over "
            f"the {MAX_VIDEO_BYTES // (1024 * 1024)} MB WhatsApp limit. "
            "Shorten it or lower its resolution, then upload it again."
        )

    logger.info(
        "whatsapp_video_transcoded",
        public_id=stored_public_id,
        bytes=size,
    )
    return url, stored_public_id
