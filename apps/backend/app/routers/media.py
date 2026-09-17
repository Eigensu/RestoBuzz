import mimetypes
import uuid
from fastapi import APIRouter, Depends, UploadFile, File
from starlette.concurrency import run_in_threadpool
from app.core.logging import get_logger
from app.dependencies import require_role
from app.core.errors import InvalidFileFormatError, ValidationError
from app.services.cloudinary_service import (
    upload_media_result,
    upload_whatsapp_video,
    UnplayableVideoError,
    MAX_IMAGE_BYTES,
    MAX_VIDEO_BYTES,
    MAX_PDF_BYTES,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/media", tags=["media"])

# Each entry maps an accepted upload content-type to the Cloudinary resource
# kind and size cap to enforce. Covers the three WhatsApp template header media
# formats: IMAGE, VIDEO and DOCUMENT.
_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
# Any container Cloudinary can read as a video. This list does not have to be
# what WhatsApp can play — every upload is re-encoded to H.264/AAC MP4 before
# it is delivered — so it only has to cover what a device might hand us. A
# phone sharing a clip from another app names it whatever that app named it.
_VIDEO_TYPES = {
    "video/mp4",
    "video/3gpp",
    "video/quicktime",
    "video/x-matroska",
    "video/webm",
    "video/x-m4v",
    "video/mpeg",
    "video/x-msvideo",
}
_DOC_TYPES = {"application/pdf"}

# What a browser sends when it has no idea. Android pickers routinely hand over
# a video from another app's storage as octet-stream, or with no type at all,
# and keying only off the claim rejected those uploads before anything could
# look at the file itself.
_UNINFORMATIVE_TYPES = {"", "application/octet-stream", "binary/octet-stream"}

# Extension -> media type for the ones mimetypes cannot be trusted with. Its
# table is platform-dependent and maps .3gp to audio/3gpp, so a 3GP video from
# a device that failed to name its type would be filed as audio and rejected.
_EXTENSION_TYPES = {
    "3gp": "video/3gpp",
    "3gpp": "video/3gpp",
    "mp4": "video/mp4",
    "m4v": "video/x-m4v",
    "mov": "video/quicktime",
    "mkv": "video/x-matroska",
    "webm": "video/webm",
    "avi": "video/x-msvideo",
    "mpeg": "video/mpeg",
    "mpg": "video/mpeg",
}

_UPLOAD_RULES = {
    **{t: ("image", MAX_IMAGE_BYTES, "5 MB") for t in _IMAGE_TYPES},
    **{t: ("video", MAX_VIDEO_BYTES, "16 MB") for t in _VIDEO_TYPES},
    **{t: ("raw", MAX_PDF_BYTES, "16 MB") for t in _DOC_TYPES},
}


def _resolve_content_type(file: UploadFile) -> str:
    """The upload's media type, falling back to its filename when unhelpful."""
    claimed = (file.content_type or "").split(";")[0].strip().lower()
    if claimed not in _UNINFORMATIVE_TYPES:
        return claimed

    filename = file.filename or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in _EXTENSION_TYPES:
        return _EXTENSION_TYPES[ext]

    guessed, _ = mimetypes.guess_type(filename)
    return (guessed or claimed).lower()


@router.post("/upload")
async def upload_image(
    file: UploadFile = File(...),
    current_user: dict = Depends(require_role("admin")),
):
    content_type = _resolve_content_type(file)
    logger.info(
        "media_upload_received",
        filename=file.filename,
        claimed_type=file.content_type,
        resolved_type=content_type,
    )

    rule = _UPLOAD_RULES.get(content_type)
    if rule is None:
        raise InvalidFileFormatError(
            f"Unsupported file type '{file.content_type or 'unknown'}'"
            f"{f' for {file.filename}' if file.filename else ''}. "
            "Allowed: images (jpeg, png, webp, gif), video, or PDF"
        )
    resource_type, max_bytes, limit_label = rule

    content = await file.read()
    if len(content) > max_bytes:
        raise ValidationError(f"File exceeds the {limit_label} size limit")

    ext = (file.filename or "media").rsplit(".", 1)[-1]
    public_id = f"whatsapp-media/{uuid.uuid4().hex}.{ext}"

    # The Cloudinary SDK is synchronous, and a video that has to be re-encoded
    # holds its connection open for as long as that takes — off the event loop,
    # or one header upload stalls every other request in the process.
    if resource_type == "video":
        try:
            url, cloudinary_public_id = await run_in_threadpool(
                upload_whatsapp_video, content, public_id
            )
        except UnplayableVideoError as e:
            raise ValidationError(str(e)) from e
    else:
        url, cloudinary_public_id = await run_in_threadpool(
            upload_media_result, content, public_id, resource_type
        )
    return {"url": url, "public_id": cloudinary_public_id}
