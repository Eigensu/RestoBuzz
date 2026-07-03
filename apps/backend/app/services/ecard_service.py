"""Personalized e-card image URLs via Cloudinary text overlays.

We upload one blank card, then render each recipient's name onto it purely
through Cloudinary delivery-URL transformations — no per-recipient upload, no
extra storage. The generated URL is passed straight to Meta as the template's
image header (`meta_api._build_payload` -> {"link": media_url}).

Name encoding is delegated to the Cloudinary SDK's structured text overlay:
Cloudinary text layers treat `,` and `/` as delimiters and must be
double-escaped, which the SDK does for us. Never hand-concatenate the name into
the transformation string.
"""

from cloudinary import CloudinaryImage

# Importing the service runs cloudinary.config(...) as an import side effect,
# so CloudinaryImage.build_url() picks up cloud_name / secure automatically.
from app.services import cloudinary_service  # noqa: F401
from app.core.logging import get_logger

logger = get_logger(__name__)

# Cap absurd names so a pasted paragraph can't blow up the overlay. c_fit,w_
# already shrinks-to-fit, this is just a hard safety net.
_MAX_NAME_LEN = 40

# Overlay defaults — every key is overridable per campaign via the `overlay`
# dict stored on campaign_jobs.personalization.overlay. Tuned for the Fielia
# card (1080x1350): gold text seated in the empty band below the divider line,
# matching the card's gold logo/concierge typography.
_DEFAULTS = {
    "font": "Georgia",
    "font_size": 78,
    "font_weight": "bold",
    "color": "c9a24b",   # Fielia gold, hex without leading '#'
    "gravity": "north",
    "x": 0,
    "y": 820,
    "max_width": 900,
}


def _clean_name(name: str) -> str:
    """Collapse whitespace/newlines and truncate to a sane length."""
    cleaned = " ".join((name or "").split())
    return cleaned[:_MAX_NAME_LEN]


def build_card_url(base_public_id: str, name: str, overlay: dict | None = None) -> str:
    """Cloudinary delivery URL for `base_public_id` with `name` overlaid.

    `overlay` may override any key in `_DEFAULTS`. Returns a secure JPG URL sized
    with quality:auto so the header stays well under WhatsApp's 5 MB image cap.

    If `name` is blank the base card is returned unchanged (callers should filter
    nameless rows upstream; this is defensive so we never emit a broken URL).
    """
    cfg = {**_DEFAULTS, **(overlay or {})}
    clean = _clean_name(name)

    output = [{"quality": "auto:good", "fetch_format": "jpg"}]

    if not clean:
        transformation = output
    else:
        color = str(cfg["color"]).lstrip("#")
        transformation = [
            {
                "overlay": {
                    "font_family": cfg["font"],
                    "font_size": cfg["font_size"],
                    "font_weight": cfg["font_weight"],
                    "text": clean,  # SDK escapes this safely
                },
                "color": f"#{color}",
                "gravity": cfg["gravity"],
                "x": cfg["x"],
                "y": cfg["y"],
                "crop": "fit",
                "width": cfg["max_width"],
            },
            *output,
        ]

    return CloudinaryImage(base_public_id).build_url(
        transformation=transformation, secure=True
    )


def sample_card_url(base_public_id: str, overlay: dict | None = None) -> str:
    """Preview/review URL with a stand-in name.

    Use this to generate the sample image submitted to Meta for template review,
    and for the wizard's live preview — it's the exact URL a real recipient gets,
    just with a placeholder name.
    """
    return build_card_url(base_public_id, "Aarav Mehta", overlay)
