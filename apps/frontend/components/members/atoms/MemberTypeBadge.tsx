import { Wifi, CreditCard } from "lucide-react";
import { cn } from "@/lib/utils";

export function MemberTypeBadge({ type }: { type: "nfc" | "ecard" }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-medium",
        type === "nfc"
          ? "bg-blue-50 text-blue-600"
          : "bg-purple-50 text-purple-600",
      )}
    >
      {type === "nfc" ? (
        <Wifi className="w-3 h-3" />
      ) : (
        <CreditCard className="w-3 h-3" />
      )}
      {type === "nfc" ? "NFC" : "E-Card"}
    </span>
  );
}
