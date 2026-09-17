import uuid
from fastapi import APIRouter, Depends, UploadFile, File
from starlette.concurrency import run_in_threadpool
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

router = APIRouter(prefix="/media", tags=["media"])

# Each entry maps an accepted upload content-type to the Cloudinary resource
# kind and size cap to enforce. Covers the three WhatsApp template header media
# formats: IMAGE, VIDEO and DOCUMENT.
_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
_VIDEO_TYPES = {"video/mp4", "video/3gpp"}
_DOC_TYPES = {"application/pdf"}

_UPLOAD_RULES = {
    **{t: ("image", MAX_IMAGE_BYTES, "5 MB") for t in _IMAGE_TYPES},
    **{t: ("video", MAX_VIDEO_BYTES, "16 MB") for t in _VIDEO_TYPES},
    **{t: ("raw", MAX_PDF_BYTES, "16 MB") for t in _DOC_TYPES},
}


@router.post("/upload")
async def upload_image(
    file: UploadFile = File(...),
    current_user: dict = Depends(require_role("admin")),
):
    rule = _UPLOAD_RULES.get(file.content_type or "")
    if rule is None:
        raise InvalidFileFormatError(
            f"Unsupported file type '{file.content_type}'. "
            "Allowed: jpeg, png, webp, gif, mp4, 3gp, pdf"
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
