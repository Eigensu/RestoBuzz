import { Wifi, CreditCard } from "lucide-react";
import { cn } from "@/lib/utils";

export function MemberTypeBadge({ type }: Readonly<{ type: string }>) {
  const isNfc = type.toLowerCase() === "nfc";
  const isEcard = type.toLowerCase() === "ecard";

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-medium uppercase tracking-tight",
        isNfc
          ? "bg-blue-50 text-blue-600"
          : isEcard
            ? "bg-purple-50 text-purple-600"
            : "bg-gray-100 text-gray-600",
      )}
    >
      {isNfc ? (
        <Wifi className="w-3 h-3" />
      ) : isEcard ? (
        <CreditCard className="w-3 h-3" />
      ) : (
        <span className="w-1.5 h-1.5 rounded-full bg-gray-400" />
      )}
      {isNfc ? "NFC" : isEcard ? "E-Card" : type}
    </span>
  );
}
