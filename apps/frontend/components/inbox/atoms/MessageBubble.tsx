import {
  MapPin,
  FileText,
  Image as ImageIcon,
  CheckCheck,
  Check,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { InboundMessage } from "@/types";
import { MessageStatus } from "@/types/common/enums";
import { timeIST } from "@/lib/date";

import { BRAND_GRADIENT } from "@/lib/brand";

function StatusIcon({ status, isRead }: { status?: string | null; isRead: boolean }) {
  if (status === MessageStatus.READ || isRead) {
    return <CheckCheck className="w-3.5 h-3.5 text-[#34B7F1]" />;
  }
  if (status === MessageStatus.DELIVERED) {
    return <CheckCheck className="w-3.5 h-3.5 text-white/80" />;
  }
  return <Check className="w-3.5 h-3.5 text-white/60" />;
}

export function MessageBubble({ msg }: Readonly<{ msg: InboundMessage }>) {
  const out = msg.direction === "outbound";
  return (
    <div className={cn("flex", out ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-xs lg:max-w-md rounded-2xl px-4 py-2.5 shadow-sm",
          out
            ? "text-white rounded-tr-sm"
            : "bg-white border text-gray-900 rounded-tl-sm",
        )}
        style={out ? { background: BRAND_GRADIENT } : undefined}
      >
        {msg.message_type === "text" && (
          <p className="text-sm leading-relaxed">{msg.body}</p>
        )}
        {msg.message_type === "image" && (
          <div className="flex items-center gap-2 text-sm">
            <ImageIcon className="w-4 h-4 shrink-0" />
            <span>{msg.body || "Image"}</span>
            {msg.media_url && (
              <a
                href={msg.media_url}
                className={cn(
                  "underline text-xs",
                  out ? "text-white/70" : "text-[#24422e]",
                )}
              >
                View
              </a>
            )}
          </div>
        )}
        {msg.message_type === "document" && (
          <div className="flex items-center gap-2 text-sm">
            <FileText className="w-4 h-4 shrink-0" />
            <span className="truncate max-w-[180px]">
              {msg.body || "Document"}
            </span>
            {msg.media_url && (
              <a
                href={msg.media_url}
                className={cn(
                  "underline text-xs shrink-0",
                  out ? "text-white/70" : "text-[#24422e]",
                )}
              >
                Download
              </a>
            )}
          </div>
        )}
        {msg.message_type === "location" && (
          <div className="flex items-center gap-2 text-sm">
            <MapPin className="w-4 h-4 shrink-0" />
            {msg.location ? (
              <a
                href={`https://maps.google.com/?q=${msg.location.lat},${msg.location.lng}`}
                target="_blank"
                rel="noopener noreferrer"
                className={cn(
                  "underline",
                  out ? "text-white/70" : "text-[#24422e]",
                )}
              >
                {msg.location.name ??
                  `${msg.location.lat}, ${msg.location.lng}`}
              </a>
            ) : (
              <span className="italic opacity-80">Location unavailable</span>
            )}
          </div>
        )}
        {!["text", "image", "document", "location"].includes(
          msg.message_type,
        ) && (
          <p className="text-sm italic opacity-80">
            {msg.body || "Unsupported message"}
          </p>
        )}
        <div
          className={cn(
            "flex items-center gap-1 mt-1 justify-end",
            out ? "text-white/60" : "text-gray-400",
          )}
        >
          <span className="text-[10px]">{timeIST(msg.received_at)}</span>
          {out && (
            <div className="flex items-center">
              <StatusIcon status={msg.status} isRead={msg.is_read} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
