import { Trash2 } from "lucide-react";
import { relativeIST } from "@/lib/date";

const REASON_COLORS: Record<string, string> = {
  opt_out: "bg-yellow-100 text-yellow-700",
  bounce: "bg-orange-100 text-orange-700",
  blocked: "bg-red-100 text-red-700",
};

interface SuppressionRowProps {
  item: { id: string; phone: string; reason: string; added_at: string };
  onRemove: (phone: string) => void;
}

export function SuppressionRow({ item, onRemove }: SuppressionRowProps) {
  return (
    <div className="flex items-center gap-3 px-4 py-2.5">
      <span className="font-mono text-sm flex-1">{item.phone}</span>
      <span
        className={`text-xs px-2 py-0.5 rounded-full ${REASON_COLORS[item.reason] ?? "bg-gray-100 text-gray-600"}`}
      >
        {item.reason}
      </span>
      <span className="text-xs text-gray-400">
        {relativeIST(item.added_at)}
      </span>
      <button
        onClick={() => onRemove(item.phone)}
        className="text-gray-400 hover:text-red-500 transition"
      >
        <Trash2 className="w-4 h-4" />
      </button>
    </div>
  );
}
