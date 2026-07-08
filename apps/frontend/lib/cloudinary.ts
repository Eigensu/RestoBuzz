// Helpers for personalized e-card previews. The authoritative render happens
// server-side (ecard_service.build_card_url); these mirror its default overlay
// purely so the wizard can show a live "what the recipient gets" preview.

// Default overlay — keep in sync with ecard_service._DEFAULTS on the backend.
const ECARD_TRANSFORM =
  "c_fit,co_rgb:c9a24b,g_north,l_text:Georgia_78_bold:%NAME%,w_900,x_0,y_820/f_jpg,q_auto:good";

/** Escape a name for a Cloudinary text overlay layer (double-escape `,` and `/`). */
function escapeOverlayText(name: string): string {
  return encodeURIComponent(name)
    .replace(/%2C/gi, "%252C")
    .replace(/%2F/gi, "%252F");
}

/**
 * Extract a Cloudinary public_id from a delivery URL, e.g.
 * `.../upload/v123/whatsapp-media/fielia_card.png` -> `whatsapp-media/fielia_card`.
 * Returns null for non-Cloudinary URLs (personalization needs a public_id).
 */
export function cloudinaryPublicId(url: string): string | null {
  if (!url.includes("/upload/")) return null;
  const rest = url.split("/upload/")[1];
  let parts = rest.split("/");
  // Drop a leading version segment (v1234567890).
  if (/^v\d+$/.test(parts[0])) parts = parts.slice(1);
  const id = parts.join("/").replace(/\.[^/.]+$/, ""); // strip extension
  return id || null;
}

/** Build a preview URL that overlays `name` onto a base Cloudinary card URL. */
export function buildEcardPreviewUrl(baseUrl: string, name: string): string {
  if (!baseUrl.includes("/upload/")) return baseUrl;
  const transform = ECARD_TRANSFORM.replace("%NAME%", escapeOverlayText(name));
  return baseUrl.replace("/upload/", `/upload/${transform}/`);
}
