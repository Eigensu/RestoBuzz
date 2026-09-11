import { formatDistanceToNow } from "date-fns";

// Matches a trailing "Z" or a +HH:MM / -HH:MM offset, e.g. "...+05:30" or "...-05:00"
const HAS_TZ_OFFSET = /(Z|[+-]\d{2}:\d{2})$/;

/**
 * Parse a backend timestamp, treating an offset-less string as UTC (the
 * backend serializes naive-UTC datetimes with no Z/offset suffix). Exported
 * so callers never need to re-implement this offset detection themselves.
 */
export function parse(date: string | Date): Date {
  if (typeof date === "string") {
    const s = HAS_TZ_OFFSET.test(date) ? date : date + "Z";
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
 * Format as 'D MMM YYYY' in Indian Standard Time (Asia/Kolkata), e.g. '24 Mar 2026'.
 */
export function toISTDateMedium(date: string | Date): string {
  return new Intl.DateTimeFormat("en-IN", {
    timeZone: "Asia/Kolkata",
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(parse(date));
}

export interface ISTDateParts {
  year: number;
  month: number;
  day: number;
}

/**
 * Today's calendar date in Indian Standard Time (Asia/Kolkata), as parts.
 * Compute this once and pass it to getISTDateOffset() when deriving several
 * offsets in a loop, instead of re-resolving "now" on every call.
 */
export function getISTTodayParts(): ISTDateParts {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "numeric",
    day: "numeric",
  }).formatToParts(new Date());

  const p: Record<string, number> = {};
  for (const part of parts) {
    if (part.type !== "literal") {
      p[part.type] = Number.parseInt(part.value, 10);
    }
  }
  return { year: p.year, month: p.month, day: p.day };
}

/**
 * Get a Date instance anchored to `daysAgo` calendar days in Indian Standard Time (Asia/Kolkata).
 * Uses Intl.DateTimeFormat with Asia/Kolkata to ensure exact calendar day alignment without manual offsets.
 * Pass `base` (from getISTTodayParts()) to avoid re-resolving "now" on every call in a loop.
 */
export function getISTDateOffset(daysAgo: number, base?: ISTDateParts): Date {
  const p = base ?? getISTTodayParts();
  return new Date(Date.UTC(p.year, p.month - 1, p.day - daysAgo, 12, 0, 0));
}


