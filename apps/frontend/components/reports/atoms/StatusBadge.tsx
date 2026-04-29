import { cn } from "@/lib/utils";

export function StatusBadge({ status }: { readonly status: string }) {
  const map: Record<string, string> = {
    delivered: "bg-emerald-50 text-emerald-700",
    sent: "bg-blue-50 text-blue-700",
    read: "bg-purple-50 text-purple-700",
    opened: "bg-purple-50 text-purple-700",
    clicked: "bg-indigo-50 text-indigo-700",
    failed: "bg-red-50 text-red-600",
    bounced: "bg-orange-50 text-orange-600",
    queued: "bg-gray-50 text-gray-500",
    sending: "bg-blue-50 text-blue-600",
    completed: "bg-emerald-50 text-emerald-700",
    cancelled: "bg-gray-100 text-gray-500",
  };
  const key = (status ?? "").toLowerCase().trim();
  return (
    <span
      className={cn(
        "inline-flex px-2 py-0.5 rounded-full text-[10px] font-black uppercase tracking-widest",
        map[key] ?? "bg-gray-50 text-gray-500",
      )}
    >
      {status}
    </span>
  );
}
