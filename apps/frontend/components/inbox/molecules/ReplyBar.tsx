import { Send } from "lucide-react";

const BRAND_GRADIENT = "linear-gradient(135deg, #24422e, #3a6b47)";

interface ReplyBarProps {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  disabled?: boolean;
}

export function ReplyBar({ value, onChange, onSend, disabled }: Readonly<ReplyBarProps>) {
  return (
    <div className="px-4 py-3 flex gap-2 items-center">
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
        className="w-9 h-9 text-white rounded-full flex items-center justify-center transition-all disabled:opacity-30 hover:scale-105"
        style={{ background: BRAND_GRADIENT }}
      >
        <Send className="w-4 h-4" />
      </button>
    </div>
  );
}
