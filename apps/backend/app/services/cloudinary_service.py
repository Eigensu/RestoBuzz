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

# WhatsApp only decodes H.264 video with AAC audio (or no audio track at all)
# inside an MP4/3GP container. Nothing upstream of here enforces that: the
# browser's accept filter and /media/upload both go on the OS-reported MIME
# type, and Meta validates the MIME type and the size but not the codecs — it
# ingests an HEVC MP4 happily and even renders its thumbnail server-side. The
# file then fails on the recipient's handset with "This video is not available
# because something is wrong with the video file", long after anyone could have
# caught it. Cloudinary probes every video it stores and reports the codecs in
# the upload response, so this is the last point in the pipeline where an
# unplayable header video is still detectable.
WHATSAPP_VIDEO_CODECS = {"h264", "avc1"}
WHATSAPP_AUDIO_CODECS = {"aac"}
WHATSAPP_VIDEO_FORMATS = {"mp4", "3gp"}

# Applied only to a video that fails the probe. w_1280/c_limit holds the output
# inside H.264 level 4.0 and, with q_auto, keeps the re-encode from growing past
# MAX_VIDEO_BYTES; c_limit never upscales, so a smaller source keeps its size.
WHATSAPP_VIDEO_TRANSFORMATION = {
    "video_codec": "h264",
    "audio_codec": "aac",
    "format": "mp4",
    "width": 1280,
    "crop": "limit",
    "quality": "auto",
}

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

    A file that is already H.264/AAC MP4 is delivered untouched. Anything else
    is re-encoded by Cloudinary and the derived URL is returned in its place, so
    what Meta fetches at send time is always a file the recipient can open.

    Raises UnplayableVideoError when the re-encode cannot produce a compliant
    file — better a failure the operator sees at upload than a campaign that
    reaches every recipient broken.
    """
    result = cloudinary.uploader.upload(
        content,
        public_id=public_id,
        resource_type="video",
        overwrite=True,
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
            eager=[WHATSAPP_VIDEO_TRANSFORMATION],
            eager_async=False,
        )
    except Exception as exc:
        raise UnplayableVideoError(
            f"This video uses {summary} and converting it failed. {_REENCODE_ADVICE}"
        ) from exc

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
