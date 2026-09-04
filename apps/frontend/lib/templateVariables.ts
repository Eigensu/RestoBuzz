/** Template variables: naming them, and mapping them to real data.
 *
 *  Two formats coexist. Templates created before named support carry {{1}},
 *  {{2}} and Meta matches them by position. New ones carry {{customer_name}}
 *  and are matched by name. Meta fixes the format when a template is created
 *  and it can never be changed, so both are handled everywhere.
 */

export const VAR_PATTERN = /\{\{\s*([A-Za-z0-9_]+)\s*\}\}/g;
export const MAX_VAR_NAME = 60;

/** Placeholder names in `text`, first-appearance order, deduplicated. */
export function extractVariables(text: string): string[] {
  const seen: string[] = [];
  for (const match of (text || "").matchAll(VAR_PATTERN)) {
    if (!seen.includes(match[1])) seen.push(match[1]);
  }
  return seen;
}

export const isNumberedVariable = (name: string) => /^\d+$/.test(name);

/** A numbered template reads {{1}}; a named one reads {{customer_name}}. */
export const isNamedTemplate = (names: string[]) =>
  names.length > 0 && !names.some(isNumberedVariable);

/** Human label for a variable, whichever format it is in. */
export function variableLabel(name: string): string {
  if (isNumberedVariable(name)) return `Variable ${name}`;
  return name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Why a name is unusable, or null. Mirrors the router's own check so the
 *  editor refuses it before Meta does. */
export function variableNameError(name: string): string | null {
  const trimmed = name.trim();
  if (!trimmed) return "Give the variable a name";
  if (!/^[a-z][a-z0-9_]*$/.test(trimmed)) {
    return "Lowercase letters, numbers and underscores, starting with a letter";
  }
  if (trimmed.length > MAX_VAR_NAME) {
    return `Name must be ${MAX_VAR_NAME} characters or fewer`;
  }
  return null;
}

export const toVariableName = (raw: string) =>
  raw
    .toLowerCase()
    .replace(/[^a-z0-9_\s]/g, "")
    .trim()
    .replace(/\s+/g, "_")
    .slice(0, MAX_VAR_NAME);

// ── Where a variable's value comes from ──────────────────────────────────────

export type VariableSourceKind = "column" | "restaurant" | "contact" | "fixed";

export interface VariableSourceDraft {
  kind: VariableSourceKind;
  /** kind "column" — a header from the uploaded sheet. */
  column?: string;
  /** kind "restaurant" — a field of the sending restaurant. */
  field?: string;
  /** kind "fixed" — one value for everyone. */
  value?: string;
  /** Used when the resolved value is blank. Meta counts parameters, so a
   *  missing one fails the whole message rather than leaving a gap. */
  fallback?: string;
}

/** Restaurant fields a variable may read. Matches the router's allowlist. */
export const RESTAURANT_FIELDS = [
  { field: "name", label: "Restaurant name" },
  { field: "location", label: "Location" },
] as const;

export const SOURCE_LABELS: Record<VariableSourceKind, string> = {
  column: "From spreadsheet",
  contact: "Contact name",
  restaurant: "Restaurant detail",
  fixed: "Same for everyone",
};

/** Variables offered in the template editor, with the sample Meta reviews
 *  against and the source the campaign wizard should pre-select. */
export const VARIABLE_PRESETS = [
  { name: "customer_name", sample: "Rahul", suggest: { kind: "contact" } },
  {
    name: "restaurant_name",
    sample: "Fielia Soraia",
    suggest: { kind: "restaurant", field: "name" },
  },
  { name: "booking_date", sample: "14 March", suggest: { kind: "column" } },
  { name: "booking_time", sample: "8:30 PM", suggest: { kind: "column" } },
  { name: "party_size", sample: "4", suggest: { kind: "column" } },
  { name: "offer_code", sample: "FEAST20", suggest: { kind: "fixed" } },
  {
    name: "city",
    sample: "Goa",
    suggest: { kind: "restaurant", field: "location" },
  },
] as const satisfies ReadonlyArray<{
  name: string;
  sample: string;
  suggest: VariableSourceDraft;
}>;

/** Column headers that plausibly hold `name`, best match first. Lets the
 *  wizard open already mapped instead of asking for seven decisions. */
function matchColumn(name: string, headers: string[]): string | undefined {
  const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, "");
  const target = norm(name);
  if (!target) return undefined;
  return (
    headers.find((h) => norm(h) === target) ??
    headers.find((h) => norm(h).includes(target) || target.includes(norm(h)))
  );
}

const NAME_ALIASES = ["customer_name", "guest_name", "name", "first_name"];
const VENUE_ALIASES = ["restaurant_name", "venue", "venue_name", "restaurant"];
const CITY_ALIASES = ["city", "location", "area"];

/** The mapping to open the wizard with. A guess the user can override beats an
 *  empty row they must fill in for every variable. */
export function suggestSource(
  name: string,
  headers: string[],
): VariableSourceDraft {
  if (isNumberedVariable(name)) {
    const column = matchColumn(name, headers);
    return column ? { kind: "column", column } : { kind: "fixed", value: "" };
  }

  if (VENUE_ALIASES.includes(name)) {
    return { kind: "restaurant", field: "name" };
  }
  if (CITY_ALIASES.includes(name)) {
    return { kind: "restaurant", field: "location" };
  }

  const column = matchColumn(name, headers);
  if (column) return { kind: "column", column, fallback: "" };
  if (NAME_ALIASES.includes(name)) return { kind: "contact", fallback: "there" };
  return { kind: "fixed", value: "" };
}

/** What this source would produce for one recipient — used for the live
 *  preview and for the test send, so both show what will actually go out. */
export function resolvePreviewValue(
  source: VariableSourceDraft | undefined,
  context: {
    row?: Record<string, string>;
    contactName?: string;
    restaurant?: { name?: string; location?: string } | null;
  },
): string {
  if (!source) return "";
  let value = "";
  if (source.kind === "column") {
    value = (context.row?.[source.column ?? ""] ?? "").trim();
  } else if (source.kind === "contact") {
    value = (context.contactName ?? "").trim();
  } else if (source.kind === "restaurant") {
    const field = source.field === "location" ? "location" : "name";
    value = (context.restaurant?.[field] ?? "").trim();
  } else {
    value = (source.value ?? "").trim();
  }
  return value || (source.fallback ?? "").trim();
}

/** Why this mapping cannot be submitted, or null.
 *
 *  A variable with neither a value nor a fallback reaches Meta one parameter
 *  short, and every message using it fails with error 132000 — after the
 *  campaign has already started sending.
 */
export function sourceError(
  source: VariableSourceDraft | undefined,
): string | null {
  if (!source) return "Choose where this value comes from";
  if (source.kind === "fixed") {
    return (source.value ?? "").trim() ? null : "Enter a value";
  }
  if (source.kind === "column" && !(source.column ?? "").trim()) {
    return "Pick a column";
  }
  if (source.kind === "restaurant" && !(source.field ?? "").trim()) {
    return "Pick a restaurant detail";
  }
  // Column and contact values vary per row, so a blank one needs a fallback.
  if (
    (source.kind === "column" || source.kind === "contact") &&
    !(source.fallback ?? "").trim()
  ) {
    return "Add a fallback for rows where this is blank";
  }
  return null;
}

/** Substitute values into template text for a preview, leaving unmapped
 *  placeholders visible rather than blanking them out. */
export function renderWithVariables(
  text: string,
  values: Record<string, string>,
): string {
  return (text || "").replace(
    VAR_PATTERN,
    (whole, name: string) => values[name]?.trim() || whole,
  );
}

/** Sample values Meta holds for a template, so a preview reads like a real
 *  message before any contacts have been uploaded. Covers both formats: named
 *  templates store `body_text_named_params`, numbered ones `body_text`. */
export function templateSampleValues(
  components: Array<{ type: string; text?: string; example?: Record<string, unknown> }>,
): Record<string, string> {
  const body = components.find((c) => c.type === "BODY");
  const example = body?.example ?? {};
  const values: Record<string, string> = {};

  const named = example.body_text_named_params;
  if (Array.isArray(named)) {
    for (const item of named) {
      if (item && typeof item === "object") {
        const entry = item as { param_name?: unknown; example?: unknown };
        if (typeof entry.param_name === "string" && typeof entry.example === "string") {
          values[entry.param_name] = entry.example;
        }
      }
    }
  }

  const positional = example.body_text;
  if (Array.isArray(positional) && Array.isArray(positional[0])) {
    positional[0].forEach((sample: unknown, i: number) => {
      if (typeof sample === "string") values[String(i + 1)] = sample;
    });
  }

  return values;
}
