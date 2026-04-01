import { cn } from "@/lib/utils";
import type { Conversation } from "@/types";
import { inboxShortDateIST } from "@/lib/date";

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
}: Readonly<ConversationItemProps>) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "w-full text-left px-6 py-4 transition-all flex items-start gap-4 border-b border-gray-100/50",
        selected ? "bg-[#eff2f0]" : "hover:bg-[#eff2f0]/60",
      )}
    >
      <div
        className="w-11 h-11 rounded-2xl flex items-center justify-center text-xs font-black text-white shrink-0 mt-0.5 shadow-sm"
        style={{ background: BRAND_GRADIENT }}
      >
        {initials(conv.sender_name, conv.from_phone)}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-1">
          <p
            className={cn(
              "text-sm truncate tracking-tight transition-colors",
              conv.unread_count > 0 ? "font-black text-gray-900" : "font-bold text-gray-700",
              selected && "text-[#24422e]"
            )}
          >
            {conv.sender_name ?? conv.from_phone}
          </p>
          <span className="text-[10px] font-black text-[#24422e]/30 uppercase tracking-widest shrink-0">
            {inboxShortDateIST(conv.last_received_at)}
          </span>
        </div>
        <div className="flex items-center justify-between gap-2 mt-1">
          <p
            className={cn(
              "text-xs truncate leading-relaxed",
              conv.unread_count > 0 ? "text-gray-900 font-bold" : "text-gray-400 font-medium",
            )}
          >
            {getPreview(conv)}
          </p>
          {conv.unread_count > 0 && (
            <span
              className="px-2 py-0.5 text-white text-[10px] rounded-full flex items-center justify-center shrink-0 font-black shadow-sm"
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
