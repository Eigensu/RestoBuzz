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
  
  const targetKey = toISTDateKey(parsed);
  const todayKey = toISTDateKey(new Date());

  const targetMidnight = new Date(targetKey + "T00:00:00Z").getTime();
  const todayMidnight = new Date(todayKey + "T00:00:00Z").getTime();

  const diffDays = Math.round((todayMidnight - targetMidnight) / (1000 * 60 * 60 * 24));

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

/**
 * Format as 'YYYY-MM-DD' in Indian Standard Time (Asia/Kolkata).
 * Single source of truth for daily grouping keys matching backend IST aggregation.
 */
export function toISTDateKey(date: string | Date): string {
  const d = parse(date);
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(d);
}

/**
 * Format as 'MMM D' in Indian Standard Time (Asia/Kolkata), e.g. 'May 6'.
 */
export function toISTDateLabel(date: string | Date): string {
  const d = parse(date);
  return new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Kolkata",
    month: "short",
    day: "numeric",
  }).format(d);
}

/**
 * Get a Date instance anchored to `daysAgo` calendar days in Indian Standard Time (Asia/Kolkata).
 * Uses Intl.DateTimeFormat with Asia/Kolkata to ensure exact calendar day alignment without manual offsets.
 */
export function getISTDateOffset(daysAgo: number): Date {
  const now = new Date();
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "numeric",
    day: "numeric",
  }).formatToParts(now);

  const p: Record<string, number> = {};
  for (const part of parts) {
    if (part.type !== "literal") {
      p[part.type] = Number.parseInt(part.value, 10);
    }
  }
  return new Date(Date.UTC(p.year, p.month - 1, p.day - daysAgo, 12, 0, 0));
}


