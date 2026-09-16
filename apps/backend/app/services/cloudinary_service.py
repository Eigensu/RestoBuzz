import cloudinary
import cloudinary.uploader
from app.config import settings

cloudinary.config(
    cloud_name=settings.cloudinary_cloud_name,
    api_key=settings.cloudinary_api_key,
    api_secret=settings.cloudinary_api_secret,
    secure=True,
)

MAX_IMAGE_BYTES = 5 * 1024 * 1024     # 5 MB
MAX_VIDEO_BYTES = 16 * 1024 * 1024    # 16 MB (WhatsApp template video header cap)
MAX_PDF_BYTES = 16 * 1024 * 1024      # 16 MB

# Source clips (exported by CapCut, Premiere, phone cameras, etc.) often use an
# H.264 profile or pixel format that Android's hardware decoders reject
# outright even though iOS's VideoToolbox plays them fine. Re-encoding to this
# baseline on upload fixes playback for both platforms. This runs once, per
# uploaded video — not on every delivery.
#
# No explicit "faststart" flag: that's not a real Cloudinary flag name (it
# rejects the upload with "Eager Invalid flag in transformation: faststart"
# — confirmed against a live upload). Cloudinary's video pipeline already
# places the moov atom for progressive playback by default when re-encoding.
_VIDEO_EAGER_TRANSFORM = [
    {
        "video_codec": "h264",
        "audio_codec": "aac",
        "format": "mp4",
    }
]


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

    Video re-encoding runs `eager_async` — Cloudinary computes the derived
    asset's URL immediately (it's deterministic from the public_id +
    transformation) but does the actual transcoding in its own background
    queue rather than making this call block on it. A synchronous eager wait
    (`eager_async=False`) was tried first and reverted: it held the upload
    request open for as long as the transcode took, which blew past the
    request timeout for larger/longer clips. If the derived file isn't ready
    yet by the time something first requests this URL, Cloudinary generates
    it on that request instead (the usual lazy-transformation fallback).
    """
    upload_kwargs = {}
    if resource_type == "video":
        upload_kwargs["eager"] = _VIDEO_EAGER_TRANSFORM
        upload_kwargs["eager_async"] = True

    result = cloudinary.uploader.upload(
        content,
        public_id=filename,
        resource_type=resource_type,
        overwrite=True,
        **upload_kwargs,
    )
    eager = result.get("eager") or []
    secure_url = eager[0]["secure_url"] if eager else result["secure_url"]
    return secure_url, result["public_id"]
