import { Send } from "lucide-react";

const BRAND_GRADIENT = "linear-gradient(135deg, #24422e, #3a6b47)";

interface ReplyBarProps {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  disabled?: boolean;
}

export function ReplyBar({
  value,
  onChange,
  onSend,
  disabled,
}: Readonly<ReplyBarProps>) {
  return (
    <div className="px-6 py-4 flex gap-3 items-center bg-white border-t border-gray-100">
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey && value.trim()) {
            e.preventDefault();
            onSend();
          }
        }}
        disabled={disabled}
        placeholder="Type a message…"
        className="flex-1 bg-gray-50 border border-gray-200 rounded-full px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#24422e]/25 focus:border-[#24422e]/40 transition disabled:opacity-50 disabled:cursor-not-allowed"
      />
      <button
        onClick={onSend}
        disabled={!value.trim() || disabled}
        className="w-12 h-12 text-white rounded-2xl flex items-center justify-center transition-all disabled:opacity-30 hover:scale-105 active:scale-95 shadow-lg shadow-green-900/10"
        style={{ background: BRAND_GRADIENT }}
      >
        <Send className="w-5 h-5" />
      </button>
    </div>
  );
}
