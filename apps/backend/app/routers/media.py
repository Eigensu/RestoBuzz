import uuid
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from app.dependencies import require_role
from app.services.cloudinary_service import upload_media, MAX_IMAGE_BYTES

router = APIRouter(prefix="/media", tags=["media"])

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


@router.post("/upload")
async def upload_image(
    file: UploadFile = File(...),
    current_user: dict = Depends(require_role("admin")),
):
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(400, f"Unsupported file type: {file.content_type}")

    content = await file.read()
    if len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(400, "File exceeds 5 MB limit")

    ext = (file.filename or "image").rsplit(".", 1)[-1]
    public_id = f"whatsapp-media/{uuid.uuid4().hex}.{ext}"

    url = upload_media(content, public_id, resource_type="image")
    return {"url": url}
