import { formatDistanceToNow } from "date-fns";

function parse(date: string | Date): Date {
  if (typeof date === "string") {
    // Ensure the string is treated as UTC even if it lacks Z/offset
    const s = date.endsWith("Z") || date.includes("+") ? date : date + "Z";
    return new Date(s);
  }
  return date;
}

function fmt(d: Date, opts: Intl.DateTimeFormatOptions): string {
  const raw = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Kolkata",
    ...opts,
  }).format(d);
  return raw.replace(/\b(am|pm)\b/i, (m) => m.toUpperCase());
}

// "about 6 hours ago"
export function relativeIST(date: string | Date, addSuffix = true): string {
  return formatDistanceToNow(parse(date), { addSuffix });
}

// "24 Mar 2026, 01:18 AM"
export function absoluteIST(date: string | Date): string {
  return fmt(parse(date), {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
  });
}

// "01:18 AM"
export function timeIST(date: string | Date): string {
  return fmt(parse(date), {
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
  });
}
