import { cn } from "@/lib/utils";
import type { Conversation } from "@/types";

const BRAND_GRADIENT = "linear-gradient(135deg, #24422e, #3a6b47)";

function initials(name: string | null, phone: string): string {
  if (!name) return phone.slice(-2);
  return name
    .split(" ")
    .map((w) => w[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

function getPreview(conv: Conversation): string {
  const t = conv.last_message_type;
  if (t === "image") return "🖼️ Photo";
  if (t === "document") return "📎 Document";
  if (t === "location") return "📍 Location";
  return conv.last_message ?? "";
}

interface ConversationItemProps {
  conv: Conversation;
  selected: boolean;
  onClick: () => void;
}

export function ConversationItem({
  conv,
  selected,
  onClick,
}: ConversationItemProps) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "w-full text-left px-4 py-3 transition flex items-start gap-3",
        selected ? "bg-[#24422e]/10" : "hover:bg-[#24422e]/5",
      )}
    >
      <div
        className="w-9 h-9 rounded-full flex items-center justify-center text-xs font-bold text-white shrink-0 mt-0.5"
        style={{ background: BRAND_GRADIENT }}
      >
        {initials(conv.sender_name, conv.from_phone)}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-1">
          <p
            className={cn(
              "text-sm truncate",
              conv.unread_count > 0 ? "font-semibold" : "font-medium",
            )}
          >
            {conv.sender_name ?? conv.from_phone}
          </p>
          <span className="text-[10px] text-gray-400 shrink-0">
            {new Date(conv.last_received_at).toLocaleTimeString("en-IN", {
              hour: "2-digit",
              minute: "2-digit",
            })}
          </span>
        </div>
        <div className="flex items-center justify-between gap-1 mt-0.5">
          <p
            className={cn(
              "text-xs truncate",
              conv.unread_count > 0 ? "text-gray-700" : "text-gray-400",
            )}
          >
            {getPreview(conv)}
          </p>
          {conv.unread_count > 0 && (
            <span
              className="w-5 h-5 text-white text-[10px] rounded-full flex items-center justify-center shrink-0 font-semibold"
              style={{ background: BRAND_GRADIENT }}
            >
              {conv.unread_count}
            </span>
          )}
        </div>
      </div>
    </button>
  );
}
