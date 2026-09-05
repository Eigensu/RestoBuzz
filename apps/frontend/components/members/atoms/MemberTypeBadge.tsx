import { Wifi, CreditCard, Tag } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Member categories are configured per restaurant, so this cannot switch on a
 * fixed list. `nfc` and `ecard` keep their established icon and colour; any
 * other category gets a stable colour derived from its name, so the same
 * category always looks the same without needing to be registered anywhere.
 */
const CUSTOM_PALETTE = [
  "bg-emerald-50 text-emerald-700",
  "bg-amber-50 text-amber-700",
  "bg-sky-50 text-sky-700",
  "bg-fuchsia-50 text-fuchsia-700",
  "bg-teal-50 text-teal-700",
  "bg-indigo-50 text-indigo-700",
];

function paletteFor(name: string): string {
  let hash = 0;
  for (const char of name) hash = (hash * 31 + char.codePointAt(0)!) >>> 0;
  return CUSTOM_PALETTE[hash % CUSTOM_PALETTE.length];
}

function labelFor(type: string): string {
  const normalized = type.toLowerCase();
  if (normalized === "nfc") return "NFC";
  if (normalized === "ecard") return "E-Card";
  return type.replaceAll("-", " ").replaceAll("_", " ");
}

export function MemberTypeBadge({ type }: Readonly<{ type: string }>) {
  if (!type) return null;

  const normalizedType = type.toLowerCase();
  const isNfc = normalizedType === "nfc";
  const isEcard = normalizedType === "ecard";

  let badgeStyles: string;
  if (isNfc) badgeStyles = "bg-blue-50 text-blue-600";
  else if (isEcard) badgeStyles = "bg-purple-50 text-purple-600";
  else badgeStyles = paletteFor(normalizedType);

  let icon;
  if (isNfc) icon = <Wifi className="w-3 h-3" />;
  else if (isEcard) icon = <CreditCard className="w-3 h-3" />;
  else icon = <Tag className="w-3 h-3" />;

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-medium uppercase tracking-tight",
        badgeStyles,
      )}
    >
      {icon}
      {labelFor(type)}
    </span>
  );
}
