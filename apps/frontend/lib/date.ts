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

// "01:18 AM" | "Yesterday" | "Friday" | "25/03/26"
export function inboxShortDateIST(date: string | Date): string {
  const parsed = parse(date);
  
  // Shift strictly to UTC timestamp representation of IST for clean midnight boundary math
  const toISTDate = (d: Date) => new Date(d.getTime() + 5.5 * 60 * 60 * 1000);
  const targetIST = toISTDate(parsed);
  const nowIST = toISTDate(new Date());

  const targetDay = new Date(targetIST.getUTCFullYear(), targetIST.getUTCMonth(), targetIST.getUTCDate());
  const today = new Date(nowIST.getUTCFullYear(), nowIST.getUTCMonth(), nowIST.getUTCDate());

  const diffDays = Math.round((today.getTime() - targetDay.getTime()) / (1000 * 60 * 60 * 24));

  if (diffDays === 0) return timeIST(parsed);
  if (diffDays === 1) return "Yesterday";
  if (diffDays > 1 && diffDays < 7) {
    return new Intl.DateTimeFormat("en-IN", {
      timeZone: "Asia/Kolkata",
      weekday: "long"
    }).format(parsed);
  }

  return new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Kolkata",
    day: "2-digit",
    month: "2-digit",
    year: "2-digit"
  }).format(parsed);
}

