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

export function SuppressionRow({ item, onRemove }: Readonly<SuppressionRowProps>) {
  return (
    <div className="group flex items-center justify-between px-6 py-4 hover:bg-[#eff2f0]/50 transition-colors">
      <div className="space-y-1">
        <p className="font-bold text-gray-900">{item.phone}</p>
        <div className="flex items-center gap-3">
          <span className="text-[10px] font-black uppercase tracking-widest px-2.5 py-1 bg-[#eff2f0] text-[#24422e] rounded-full">
            {item.reason}
          </span>
          <span className="text-[11px] font-medium text-gray-400">
            Added {relativeIST(item.added_at)}
          </span>
        </div>
      </div>
      <button
        onClick={() => {
          if (confirm(`Remove ${item.phone} from suppression list?`))
            onRemove(item.phone);
        }}
        className="p-2 text-gray-300 hover:text-red-500 hover:bg-red-50 rounded-xl opacity-0 group-hover:opacity-100 transition-all"
      >
        <Trash2 className="w-4 h-4" />
      </button>
    </div>
  );
}
