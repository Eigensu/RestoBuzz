import { FileText } from "lucide-react";
import { cn } from "@/lib/utils";

interface HeaderMediaPreviewProps {
  /** WhatsApp header format — IMAGE, VIDEO or DOCUMENT. */
  headerFormat: string;
  mediaUrl: string;
  /** Sizing for the media element; each surface previews at its own scale. */
  className?: string;
}

/** Renders a template header media URL as the element its format needs. A PDF
 *  has no inline thumbnail, so DOCUMENT falls back to a link. */
export function HeaderMediaPreview({
  headerFormat,
  mediaUrl,
  className,
}: Readonly<HeaderMediaPreviewProps>) {
  if (headerFormat === "VIDEO") {
    return (
      <video
        src={mediaUrl}
        controls
        className={cn("w-full max-h-36 bg-black object-contain", className)}
      >
        <track kind="captions" />
      </video>
    );
  }
  if (headerFormat === "DOCUMENT") {
    return (
      <a
        href={mediaUrl}
        target="_blank"
        rel="noreferrer"
        className="flex items-center gap-2 px-3 py-4 text-sm text-[#24422e] hover:underline"
      >
        <FileText className="w-5 h-5 shrink-0" />
        <span className="truncate">View attached document</span>
      </a>
    );
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={mediaUrl}
      alt="media preview"
      className={cn("w-full max-h-36 object-cover", className)}
    />
  );
}
