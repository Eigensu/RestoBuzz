import { Wifi, CreditCard } from "lucide-react";
import { cn } from "@/lib/utils";

export function MemberTypeBadge({ type }: Readonly<{ type: string }>) {
  const normalizedType = type.toLowerCase();
  const isNfc = normalizedType === "nfc";
  const isEcard = normalizedType === "ecard";

  const badgeStyles = isNfc
    ? "bg-blue-50 text-blue-600"
    : isEcard
      ? "bg-purple-50 text-purple-600"
      : "bg-gray-100 text-gray-600";

  const IconComponent = isNfc ? (
    <Wifi className="w-3 h-3" />
  ) : isEcard ? (
    <CreditCard className="w-3 h-3" />
  ) : (
    <span className="w-1.5 h-1.5 rounded-full bg-gray-400" />
  );

  const label = isNfc ? "NFC" : isEcard ? "E-Card" : type;

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-medium uppercase tracking-tight",
        badgeStyles,
      )}
    >
      {IconComponent}
      {label}
    </span>
  );
}
