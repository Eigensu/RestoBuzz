"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronDown, Plus, Trash2, ChevronUp } from "lucide-react";
import {
  BUTTON_CONFIG,
  CTA_TYPES,
  DIAL_CODES,
  MAX_BUTTONS,
  MAX_BUTTON_TEXT,
  MAX_OFFER_CODE,
  buttonError,
  buttonsError,
  isCallToAction,
  isTypeFull,
  newButton,
} from "@/lib/templateButtons";
import type { ButtonDraft, ButtonType } from "@/lib/templateButtons";

const FIELD_CLS =
  "w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-[#24422e]/20 focus:border-[#24422e]";

/** The one preset worth a menu entry of its own: every marketing template
 *  wants an opt-out, and typing it by hand is where people get it wrong. */
const OPT_OUT_TEXT = "Stop promotions";

interface TemplateButtonsEditorProps {
  buttons: ButtonDraft[];
  onChange: (buttons: ButtonDraft[]) => void;
}

function FieldLabel({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <span className="block text-[10px] font-black text-gray-400 uppercase tracking-wider mb-1">
      {children}
    </span>
  );
}

interface AddButtonMenuProps {
  buttons: ButtonDraft[];
  onAdd: (type: ButtonType, text?: string) => void;
}

/** "Add button" split into the two families Meta groups them by, with the
 *  options that are already at their cap greyed out rather than hidden — the
 *  reason a choice is unavailable is more useful than its absence. */
function AddButtonMenu({ buttons, onAdd }: Readonly<AddButtonMenuProps>) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const atTotalCap = buttons.length >= MAX_BUTTONS;

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

  const pick = (type: ButtonType, text?: string) => {
    onAdd(type, text);
    setOpen(false);
  };

  const renderItem = (
    type: ButtonType,
    label: string,
    hint: string,
    text?: string,
  ) => {
    const full = isTypeFull(buttons, type);
    return (
      <button
        key={label}
        type="button"
        disabled={full}
        onClick={() => pick(type, text)}
        className="w-full text-left px-3 py-2 rounded-lg transition hover:bg-[#eff2f0] disabled:opacity-40 disabled:hover:bg-transparent disabled:cursor-not-allowed"
      >
        <span className="block text-sm font-bold text-gray-800">{label}</span>
        <span className="block text-[11px] text-gray-400 font-medium">
          {full ? (atTotalCap ? "Button limit reached" : "Limit reached") : hint}
        </span>
      </button>
    );
  };

  return (
    <div className="relative inline-block" ref={wrapRef}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        disabled={atTotalCap}
        aria-expanded={open}
        aria-haspopup="menu"
        className="inline-flex items-center gap-2 border border-gray-200 rounded-xl px-4 py-2.5 text-sm font-bold text-gray-700 bg-white hover:border-[#24422e]/40 hover:bg-[#24422e]/5 transition disabled:opacity-40 disabled:cursor-not-allowed"
      >
        <Plus className="w-4 h-4" />
        Add button
        <ChevronDown
          className={`w-4 h-4 text-gray-400 transition ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open && (
        <div
          role="menu"
          className="absolute left-0 top-full mt-2 z-20 w-72 bg-white rounded-2xl border border-gray-100 shadow-xl p-2"
        >
          <p className="px-3 pt-1 pb-1.5 text-[10px] font-black text-gray-400 uppercase tracking-wider">
            Quick reply
          </p>
          {renderItem(
            "QUICK_REPLY",
            "Custom",
            BUTTON_CONFIG.QUICK_REPLY.hint,
          )}
          {renderItem(
            "QUICK_REPLY",
            "Marketing opt-out",
            `Adds a "${OPT_OUT_TEXT}" reply`,
            OPT_OUT_TEXT,
          )}

          <div className="h-px bg-gray-100 my-2" />

          <p className="px-3 pb-1.5 text-[10px] font-black text-gray-400 uppercase tracking-wider">
            Call to action
          </p>
          {CTA_TYPES.map((type) =>
            renderItem(type, BUTTON_CONFIG[type].label, BUTTON_CONFIG[type].hint),
          )}
        </div>
      )}
    </div>
  );
}

interface ButtonRowProps {
  button: ButtonDraft;
  buttons: ButtonDraft[];
  isFirst: boolean;
  isLast: boolean;
  onPatch: (patch: Partial<ButtonDraft>) => void;
  onMove: (direction: -1 | 1) => void;
  onRemove: () => void;
}

function ButtonRow({
  button,
  buttons,
  isFirst,
  isLast,
  onPatch,
  onMove,
  onRemove,
}: Readonly<ButtonRowProps>) {
  const error = buttonError(button);
  const cta = isCallToAction(button.type);

  return (
    <div className="rounded-xl border border-gray-100 bg-white p-3">
      <div className="flex items-start gap-3">
        <div className="flex-1 grid grid-cols-1 sm:grid-cols-2 gap-3 min-w-0">
          {cta && (
            <label className="block">
              <FieldLabel>Type of action</FieldLabel>
              <select
                value={button.type}
                onChange={(e) =>
                  onPatch({ type: e.target.value as ButtonType })
                }
                className={FIELD_CLS}
              >
                {CTA_TYPES.map((type) => (
                  <option
                    key={type}
                    value={type}
                    disabled={isTypeFull(buttons, type, button.id)}
                  >
                    {BUTTON_CONFIG[type].label}
                  </option>
                ))}
              </select>
            </label>
          )}

          {button.type !== "COPY_CODE" && (
            <label className="block">
              <FieldLabel>Button text</FieldLabel>
              <div className="relative">
                <input
                  value={button.text}
                  onChange={(e) =>
                    onPatch({ text: e.target.value.slice(0, MAX_BUTTON_TEXT) })
                  }
                  maxLength={MAX_BUTTON_TEXT}
                  className={`${FIELD_CLS} pr-14`}
                  placeholder={
                    button.type === "URL"
                      ? "e.g. View menu"
                      : button.type === "PHONE_NUMBER"
                        ? "e.g. Call now"
                        : "e.g. Book a table"
                  }
                />
                <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] text-gray-400 font-medium">
                  {button.text.length}/{MAX_BUTTON_TEXT}
                </span>
              </div>
            </label>
          )}

          {button.type === "URL" && (
            <label className="block sm:col-span-2">
              <FieldLabel>Website URL</FieldLabel>
              <input
                value={button.url}
                onChange={(e) => onPatch({ url: e.target.value })}
                className={FIELD_CLS}
                placeholder="https://your-restaurant.com/menu"
                inputMode="url"
              />
            </label>
          )}

          {button.type === "PHONE_NUMBER" && (
            <>
              <label className="block">
                <FieldLabel>Country</FieldLabel>
                <select
                  value={button.dial}
                  onChange={(e) => onPatch({ dial: e.target.value })}
                  className={FIELD_CLS}
                >
                  {DIAL_CODES.map((c) => (
                    <option key={c.iso} value={c.dial}>
                      {c.iso} {c.dial}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block">
                <FieldLabel>Phone number</FieldLabel>
                <input
                  value={button.phone}
                  onChange={(e) =>
                    onPatch({ phone: e.target.value.replace(/[^\d\s-]/g, "") })
                  }
                  className={FIELD_CLS}
                  placeholder="98765 43210"
                  inputMode="tel"
                />
              </label>
            </>
          )}

          {button.type === "COPY_CODE" && (
            <label className="block">
              <FieldLabel>Offer code</FieldLabel>
              <div className="relative">
                <input
                  value={button.code}
                  onChange={(e) =>
                    onPatch({ code: e.target.value.slice(0, MAX_OFFER_CODE) })
                  }
                  maxLength={MAX_OFFER_CODE}
                  className={`${FIELD_CLS} pr-14`}
                  placeholder="e.g. FEAST20"
                />
                <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] text-gray-400 font-medium">
                  {button.code.length}/{MAX_OFFER_CODE}
                </span>
              </div>
            </label>
          )}
        </div>

        <div className="flex flex-col items-center gap-0.5 pt-5 shrink-0">
          <button
            type="button"
            onClick={() => onMove(-1)}
            disabled={isFirst}
            aria-label="Move button up"
            className="p-1 rounded-md text-gray-300 hover:text-gray-600 hover:bg-gray-100 transition disabled:opacity-30 disabled:hover:bg-transparent"
          >
            <ChevronUp className="w-3.5 h-3.5" />
          </button>
          <button
            type="button"
            onClick={() => onMove(1)}
            disabled={isLast}
            aria-label="Move button down"
            className="p-1 rounded-md text-gray-300 hover:text-gray-600 hover:bg-gray-100 transition disabled:opacity-30 disabled:hover:bg-transparent"
          >
            <ChevronDown className="w-3.5 h-3.5" />
          </button>
          <button
            type="button"
            onClick={onRemove}
            aria-label="Remove button"
            className="p-1 rounded-md text-gray-300 hover:text-red-500 hover:bg-red-50 transition"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {error && (
        <p className="text-[11px] text-amber-600 font-medium mt-2">{error}</p>
      )}
    </div>
  );
}

export function TemplateButtonsEditor({
  buttons,
  onChange,
}: Readonly<TemplateButtonsEditorProps>) {
  const add = (type: ButtonType, text = "") =>
    onChange([...buttons, newButton(type, text)]);

  const patch = (id: string, next: Partial<ButtonDraft>) =>
    onChange(buttons.map((b) => (b.id === id ? { ...b, ...next } : b)));

  const remove = (id: string) => onChange(buttons.filter((b) => b.id !== id));

  /** Reorder within the button's own group — the two groups are separate lists
   *  on screen, and Meta wants the quick replies kept together regardless. */
  const move = (id: string, direction: -1 | 1) => {
    const target = buttons.find((b) => b.id === id);
    if (!target) return;
    const group = buttons.filter(
      (b) => isCallToAction(b.type) === isCallToAction(target.type),
    );
    const at = group.findIndex((b) => b.id === id);
    const to = at + direction;
    if (to < 0 || to >= group.length) return;

    const reordered = [...group];
    [reordered[at], reordered[to]] = [reordered[to], reordered[at]];

    // Splice the reordered group back over the positions it occupied so the
    // other group's rows keep their own order.
    let cursor = 0;
    onChange(
      buttons.map((b) =>
        isCallToAction(b.type) === isCallToAction(target.type)
          ? reordered[cursor++]
          : b,
      ),
    );
  };

  const ctaButtons = buttons.filter((b) => isCallToAction(b.type));
  const quickReplies = buttons.filter((b) => !isCallToAction(b.type));

  // Rows report their own problems inline; this only surfaces the set-level
  // ones (a duplicate label, a cap overrun) that belong to no single row.
  const groupError = buttons.some((b) => buttonError(b))
    ? null
    : buttonsError(buttons);

  const renderGroup = (title: string, group: ButtonDraft[]) =>
    group.length > 0 && (
      <div className="mt-5">
        <p className="text-sm font-black text-gray-800">
          {title} <span className="text-gray-400 font-medium">· Optional</span>
        </p>
        <div className="mt-2 space-y-2 rounded-2xl bg-gray-50/70 border border-gray-100 p-2">
          {group.map((button, i) => (
            <ButtonRow
              key={button.id}
              button={button}
              buttons={buttons}
              isFirst={i === 0}
              isLast={i === group.length - 1}
              onPatch={(next) => patch(button.id, next)}
              onMove={(direction) => move(button.id, direction)}
              onRemove={() => remove(button.id)}
            />
          ))}
        </div>
      </div>
    );

  return (
    <div className="bg-white rounded-2xl border border-gray-100 p-6 shadow-sm">
      <h3 className="text-sm font-black text-gray-900">
        Buttons <span className="text-gray-400 font-medium">· Optional</span>
      </h3>
      <p className="text-xs text-gray-500 mt-1 font-medium">
        Create buttons that let customers respond to your message or take
        action. You can add up to {MAX_BUTTONS} buttons. If you add more than{" "}
        three, they will appear in a list.
      </p>

      <div className="mt-4">
        <AddButtonMenu buttons={buttons} onAdd={add} />
      </div>

      {renderGroup("Call to action", ctaButtons)}
      {renderGroup("Quick reply", quickReplies)}

      {groupError && (
        <p className="text-[11px] text-amber-600 font-medium mt-4">
          {groupError}
        </p>
      )}

      {buttons.length > 0 && (
        <p className="text-[11px] text-gray-400 font-medium mt-4">
          {buttons.length}/{MAX_BUTTONS} buttons used. Links must be fixed —
          per-customer variables in a button link aren&apos;t supported yet.
        </p>
      )}
    </div>
  );
}
