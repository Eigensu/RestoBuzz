"use client";

import { Check, TriangleAlert } from "lucide-react";
import {
  RESTAURANT_FIELDS,
  SOURCE_LABELS,
  resolvePreviewValue,
  sourceError,
  variableLabel,
} from "@/lib/templateVariables";
import type {
  VariableSourceDraft,
  VariableSourceKind,
} from "@/lib/templateVariables";

const FIELD_CLS =
  "w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-[#24422e]/20 focus:border-[#24422e]";

const KINDS: VariableSourceKind[] = ["column", "contact", "restaurant", "fixed"];

interface VariableMappingPanelProps {
  names: string[];
  headers: string[];
  sources: Record<string, VariableSourceDraft>;
  onChange: (name: string, source: VariableSourceDraft) => void;
  restaurant: { name?: string; location?: string } | null;
  /** First valid contact, used to show what row 1 will actually receive. */
  sampleRow?: { name?: string; row?: Record<string, string> };
}

/** Maps each of the template's variables to where its value comes from.
 *
 *  Lives in the pre-flight step rather than template selection because the
 *  spreadsheet's column names only exist once the file has been parsed.
 */
export function VariableMappingPanel({
  names,
  headers,
  sources,
  onChange,
  restaurant,
  sampleRow,
}: Readonly<VariableMappingPanelProps>) {
  if (names.length === 0) return null;

  const context = {
    row: sampleRow?.row,
    contactName: sampleRow?.name,
    restaurant,
  };

  return (
    <div className="space-y-3">
      <div>
        <h3 className="font-medium">Personalization</h3>
        <p className="text-xs text-gray-500 mt-0.5">
          Point each variable at the data it should use. Values shown on the
          right are what your first contact will actually receive.
        </p>
      </div>

      <div className="space-y-2">
        {names.map((name) => {
          const source = sources[name];
          const error = sourceError(source);
          const preview = resolvePreviewValue(source, context);
          const varies = source?.kind === "column" || source?.kind === "contact";

          return (
            <div
              key={name}
              className="rounded-xl border border-gray-100 bg-gray-50/70 p-3"
            >
              <div className="flex items-center justify-between gap-3 mb-2">
                <code className="text-[11px] font-bold text-[#24422e] bg-[#eff2f0] rounded-lg px-2 py-1">
                  {`{{${name}}}`}
                </code>
                <span className="text-[11px] text-gray-400 font-medium truncate">
                  {variableLabel(name)}
                </span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                <select
                  value={source?.kind ?? "fixed"}
                  onChange={(e) =>
                    onChange(name, {
                      // Switching source drops the previous kind's field so a
                      // stale column can't be submitted with a fixed value.
                      kind: e.target.value as VariableSourceKind,
                      fallback: source?.fallback,
                    })
                  }
                  className={FIELD_CLS}
                  aria-label={`Source for ${name}`}
                >
                  {KINDS.map((kind) => (
                    <option
                      key={kind}
                      value={kind}
                      disabled={kind === "column" && headers.length === 0}
                    >
                      {SOURCE_LABELS[kind]}
                    </option>
                  ))}
                </select>

                {source?.kind === "column" && (
                  <select
                    value={source.column ?? ""}
                    onChange={(e) =>
                      onChange(name, { ...source, column: e.target.value })
                    }
                    className={FIELD_CLS}
                    aria-label={`Column for ${name}`}
                  >
                    <option value="">Choose a column…</option>
                    {headers.map((h) => (
                      <option key={h} value={h}>
                        {h}
                      </option>
                    ))}
                  </select>
                )}

                {source?.kind === "restaurant" && (
                  <select
                    value={source.field ?? "name"}
                    onChange={(e) =>
                      onChange(name, { ...source, field: e.target.value })
                    }
                    className={FIELD_CLS}
                    aria-label={`Restaurant detail for ${name}`}
                  >
                    {RESTAURANT_FIELDS.map((f) => (
                      <option key={f.field} value={f.field}>
                        {f.label}
                      </option>
                    ))}
                  </select>
                )}

                {source?.kind === "fixed" && (
                  <input
                    value={source.value ?? ""}
                    onChange={(e) =>
                      onChange(name, { ...source, value: e.target.value })
                    }
                    className={FIELD_CLS}
                    placeholder="Value sent to everyone"
                    aria-label={`Value for ${name}`}
                  />
                )}

                {source?.kind === "contact" && (
                  <div className="flex items-center px-3 text-xs text-gray-400 font-medium">
                    Uses each contact&apos;s detected name
                  </div>
                )}

                {varies && (
                  <input
                    value={source.fallback ?? ""}
                    onChange={(e) =>
                      onChange(name, { ...source, fallback: e.target.value })
                    }
                    className={`${FIELD_CLS} sm:col-span-2`}
                    placeholder='Fallback when blank — e.g. "there"'
                    aria-label={`Fallback for ${name}`}
                  />
                )}
              </div>

              <div className="flex items-start gap-1.5 mt-2">
                {error ? (
                  <>
                    <TriangleAlert className="w-3.5 h-3.5 text-amber-600 shrink-0 mt-px" />
                    <p className="text-[11px] text-amber-600 font-medium">
                      {error}
                    </p>
                  </>
                ) : (
                  <>
                    <Check className="w-3.5 h-3.5 text-[#24422e] shrink-0 mt-px" />
                    <p className="text-[11px] text-gray-500 font-medium truncate">
                      First contact gets{" "}
                      <span className="text-gray-800 font-bold">
                        {preview || "—"}
                      </span>
                    </p>
                  </>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
