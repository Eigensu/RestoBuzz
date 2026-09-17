import { FileText, Image as ImageIcon, Video } from "lucide-react";

// Per WhatsApp header media format: upload accept filter, helper copy, URL
// placeholder and the icon shown in the empty drop zone. Single source of truth
// for the template editors and the campaign wizard so the three never drift.
// The size limits mirror the backend caps in cloudinary_service (what
// /media/upload accepts) and meta_api (what the Meta upload handle accepts).
export const MEDIA_CONFIG = {
  IMAGE: {
    label: "Media Image",
    accept: "image/jpeg,image/png,image/webp,image/gif",
    hint: "Click to upload · JPG, PNG, WEBP, GIF · max 5MB",
    urlPlaceholder: "Or paste an image URL",
    Icon: ImageIcon,
  },
  VIDEO: {
    label: "Media Video",
    // "video/*", not a list of exact types: Android's file pickers honour the
    // accept attribute and will not let you choose a clip whose type they
    // report differently, so a narrow list silently blocks selection and no
    // request is ever made. The backend re-encodes whatever arrives.
    accept: "video/*",
    hint: "Click to upload · any video, converted for WhatsApp · max 16MB",
    urlPlaceholder: "Or paste a video URL",
    Icon: Video,
  },
  DOCUMENT: {
    label: "Media Document",
    accept: "application/pdf",
    hint: "Click to upload · PDF · max 16MB",
    urlPlaceholder: "Or paste a document URL",
    Icon: FileText,
  },
} as const;

export type MediaFormat = keyof typeof MEDIA_CONFIG;

/** True for the HEADER formats that carry a media handle rather than text.
 *  Meta types `format` as a free string, so this has to reject inherited keys
 *  ("constructor" and friends) that `in` would wave through into a config
 *  object with no accept/hint/Icon. */
export function isMediaFormat(
  format: string | null | undefined,
): format is MediaFormat {
  return !!format && Object.hasOwn(MEDIA_CONFIG, format);
}
