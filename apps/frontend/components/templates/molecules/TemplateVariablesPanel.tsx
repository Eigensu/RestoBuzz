"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronDown, Plus } from "lucide-react";
import {
  VARIABLE_PRESETS,
  isNumberedVariable,
  toVariableName,
  variableLabel,
  variableNameError,
} from "@/lib/templateVariables";

const FIELD_CLS =
  "w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-[#24422e]/20 focus:border-[#24422e]";

interface AddVariableMenuProps {
  used: string[];
  onPick: (name: string, sample: string) => void;
}

/** Presets first, custom name second — most templates want the same handful of
 *  variables, and picking one is a click rather than a naming decision. */
function AddVariableMenu({ used, onPick }: Readonly<AddVariableMenuProps>) {
  const [open, setOpen] = useState(false);
  const [custom, setCustom] = useState("");
  const wrapRef = useRef<HTMLDivElement>(null);
  // addCustom normalizes before inserting, so "Table Number" is a valid entry.
  // Validating the raw text would reject it for containing a space.
  const customName = toVariableName(custom);
  const customError = (() => {
    if (!custom.trim()) return null;
    const invalid = variableNameError(customName);
    if (invalid) return invalid;
    return used.includes(customName) ? "That variable is already used" : null;
  })();

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const pick = (name: string, sample: string) => {
    onPick(name, sample);
    setOpen(false);
    setCustom("");
  };

  const addCustom = () => {
    if (!custom.trim() || customError) return;
    pick(customName, variableLabel(customName));
  };

  return (
    <div className="relative inline-block" ref={wrapRef}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="menu"
        className="inline-flex items-center gap-1.5 text-xs font-bold text-[#24422e] hover:bg-[#eff2f0] px-2 py-1 rounded-lg transition"
      >
        <Plus className="w-3.5 h-3.5" />
        Add variable
        <ChevronDown
          className={`w-3.5 h-3.5 transition ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open && (
        <div
          role="menu"
          className="absolute left-0 top-full mt-2 z-20 w-72 bg-white rounded-2xl border border-gray-100 shadow-xl p-2"
        >
          <p className="px-3 pt-1 pb-1.5 text-[10px] font-black text-gray-400 uppercase tracking-wider">
            Common
          </p>
          <div className="max-h-56 overflow-y-auto">
            {VARIABLE_PRESETS.map((preset) => {
              const taken = used.includes(preset.name);
              return (
                <button
                  key={preset.name}
                  type="button"
                  disabled={taken}
                  onClick={() => pick(preset.name, preset.sample)}
                  className="w-full text-left px-3 py-2 rounded-lg transition hover:bg-[#eff2f0] disabled:opacity-40 disabled:hover:bg-transparent disabled:cursor-not-allowed"
                >
                  <span className="block text-sm font-bold text-gray-800">
                    {variableLabel(preset.name)}
                  </span>
                  <span className="block text-[11px] text-gray-400 font-medium">
                    {taken ? "Already in this template" : `e.g. ${preset.sample}`}
                  </span>
                </button>
              );
            })}
          </div>

          <div className="h-px bg-gray-100 my-2" />

          <div className="px-1 pb-1">
            <label
              htmlFor="custom-variable"
              className="block px-2 pb-1.5 text-[10px] font-black text-gray-400 uppercase tracking-wider"
            >
              Custom
            </label>
            <div className="flex gap-1.5 px-2">
              <input
                id="custom-variable"
                value={custom}
                onChange={(e) => setCustom(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && addCustom()}
                className={`${FIELD_CLS} text-xs`}
                placeholder="e.g. table_number"
              />
              <button
                type="button"
                onClick={addCustom}
                disabled={!custom.trim() || !!customError}
                className="px-3 rounded-lg bg-[#24422e] text-white text-xs font-bold disabled:opacity-30 transition"
              >
                Add
              </button>
            </div>
            {customError && (
              <p className="text-[10px] text-amber-600 font-medium px-2 mt-1.5">
                {customError}
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

interface TemplateVariablesPanelProps {
  names: string[];
  samples: Record<string, string>;
  onSampleChange: (name: string, sample: string) => void;
}

/** The variables found in the body, each with the sample value Meta reviews the
 *  template against. A template submitted without samples is far likelier to be
 *  rejected, so every one is filled — with a default if the author skips it. */
export function TemplateVariablesPanel({
  names,
  samples,
  onSampleChange,
}: Readonly<TemplateVariablesPanelProps>) {
  if (names.length === 0) return null;
  const numbered = names.some(isNumberedVariable);

  return (
    <div className="mt-4 rounded-2xl bg-gray-50/70 border border-gray-100 p-3">
      <p className="text-[10px] font-black text-gray-400 uppercase tracking-wider px-1 pb-2">
        Variables · sample values
      </p>
      <div className="space-y-2">
        {names.map((name) => (
          <div key={name} className="flex items-center gap-3">
            <code className="text-[11px] font-bold text-[#24422e] bg-[#eff2f0] rounded-lg px-2 py-1.5 shrink-0 w-40 truncate">
              {`{{${name}}}`}
            </code>
            <input
              value={samples[name] ?? ""}
              onChange={(e) => onSampleChange(name, e.target.value)}
              className={FIELD_CLS}
              placeholder={`Example value for ${variableLabel(name)}`}
              aria-label={`Sample value for ${name}`}
            />
          </div>
        ))}
      </div>
      <p className="text-[11px] text-gray-400 font-medium mt-3 px-1">
        {numbered
          ? "Meta reviews the template against these samples. Real values are mapped per recipient when you build a campaign."
          : "Meta reviews the template against these samples. You map each variable to a spreadsheet column, a restaurant detail or a fixed value when you build a campaign."}
      </p>
    </div>
  );
}

export { AddVariableMenu };
