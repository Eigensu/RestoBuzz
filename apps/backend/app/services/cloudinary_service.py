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
