"use client";
import { useState } from "react";
import { X, ImageIcon, ExternalLink, Pencil } from "lucide-react";
import type { Template } from "@/types";
import { StatusBadge } from "@/components/templates/atoms/StatusBadge";
import { CategoryBadge } from "@/components/templates/atoms/CategoryBadge";
import { ComponentPill } from "@/components/templates/atoms/ComponentPill";
import { TemplateFormModal } from "@/components/templates/molecules/TemplateFormModal";

import { BRAND_GRADIENT } from "@/lib/brand";

interface TemplateModalProps {
  template: Template;
  onClose: () => void;
}

export function TemplateModal({ template: t, onClose }: Readonly<TemplateModalProps>) {
  const [editing, setEditing] = useState(false);

  const header = t.components.find((c) => c.type === "HEADER");
  const body = t.components.find((c) => c.type === "BODY");
  const footer = t.components.find((c) => c.type === "FOOTER");
  const buttonsComp = t.components.find((c) => c.type === "BUTTONS") as
    | { type: string; buttons?: { type: string; text: string; url?: string }[] }
    | undefined;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`Template: ${t.name}`}
      className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4"
      onClick={onClose}
      onKeyDown={(e) => e.key === "Escape" && onClose()}
    >
      {editing && (
        <TemplateFormModal editing={t} onClose={() => setEditing(false)} />
      )}
      <div
        className="bg-white rounded-3xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => e.stopPropagation()}
      >
        {/* Modal header */}
        <div className="flex items-center justify-between px-6 py-4 border-b">
          <div className="flex items-center gap-3 min-w-0">
            <div>
              <p className="font-black text-gray-900 truncate">{t.name}</p>
              <p className="text-xs text-gray-400 mt-0.5">{t.language}</p>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <StatusBadge status={t.status} />
            <CategoryBadge category={t.category} />
            <button
              onClick={() => setEditing(true)}
              className="ml-1 flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[#24422e]/30 text-[#24422e] text-xs font-bold hover:bg-[#24422e] hover:text-white transition"
            >
              <Pencil className="w-3 h-3" /> Edit
            </button>
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg hover:bg-gray-100 transition text-gray-400 hover:text-gray-600"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto">
          <div className="grid md:grid-cols-2 gap-0 h-full">
            {/* Left: component breakdown */}
            <div className="p-6 space-y-4 border-r">
              <p className="text-xs font-bold text-gray-400 uppercase tracking-widest">
                Components
              </p>

              {header && (
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <ComponentPill label="HEADER" />
                    {header.format && (
                      <span className="text-[10px] text-gray-400 font-medium">
                        {header.format}
                      </span>
                    )}
                  </div>
                  {header.text && (
                    <p className="text-sm font-semibold text-gray-800 bg-gray-50 rounded-xl px-3 py-2">
                      {header.text}
                    </p>
                  )}
                  {header.format === "IMAGE" && !header.text && (
                    <div className="flex items-center gap-2 text-xs text-gray-400 bg-gray-50 rounded-xl px-3 py-2">
                      <ImageIcon className="w-4 h-4" /> Image header
                    </div>
                  )}
                </div>
              )}

              {body && (
                <div className="space-y-1">
                  <ComponentPill label="BODY" />
                  <p className="text-sm text-gray-700 leading-relaxed bg-gray-50 rounded-xl px-3 py-2 whitespace-pre-wrap">
                    {body.text}
                  </p>
                </div>
              )}

              {footer && (
                <div className="space-y-1">
                  <ComponentPill label="FOOTER" />
                  <p className="text-xs text-gray-400 bg-gray-50 rounded-xl px-3 py-2">
                    {footer.text}
                  </p>
                </div>
              )}

              {buttonsComp?.buttons && buttonsComp.buttons.length > 0 && (
                <div className="space-y-2">
                  <ComponentPill label="BUTTONS" />
                  <div className="space-y-1.5">
                    {buttonsComp.buttons.map((btn, i) => (
                      <div
                        key={`btn-${i}`}
                        className="flex items-center gap-2 bg-gray-50 rounded-xl px-3 py-2"
                      >
                        <ExternalLink className="w-3.5 h-3.5 text-[#24422e] shrink-0" />
                        <span className="text-sm font-medium text-[#24422e]">
                          {btn.text}
                        </span>
                        {btn.url && (
                          <span className="text-[10px] text-gray-400 truncate ml-auto">
                            {btn.url}
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Right: WhatsApp phone preview */}
            <div className="p-6 flex flex-col items-center justify-start bg-[#eff2f0]/40 overflow-y-auto">
              <p className="text-xs font-bold text-gray-400 uppercase tracking-widest mb-4">
                Preview
              </p>
              <div className="w-full max-w-xs bg-[#e5ddd5] rounded-2xl overflow-hidden shadow-xl border border-gray-200">
                {/* Status bar */}
                <div
                  className="h-8 flex items-center px-4 gap-2"
                  style={{ background: BRAND_GRADIENT }}
                >
                  <div className="w-5 h-5 rounded-full bg-white/20 flex items-center justify-center">
                    <span className="text-white text-[8px] font-bold">R</span>
                  </div>
                  <span className="text-white text-[10px] font-medium flex-1">
                    RestoBuzz
                  </span>
                </div>

                {/* Chat bubble */}
                <div className="p-3">
                  <div className="bg-white rounded-xl rounded-tl-sm shadow-sm overflow-hidden">
                    {/* Image header placeholder */}
                    {header?.format === "IMAGE" && (
                      <div className="bg-gray-100 h-28 flex items-center justify-center">
                        <ImageIcon className="w-8 h-8 text-gray-300" />
                      </div>
                    )}
                    {/* Text header */}
                    {header?.text && (
                      <div className="px-3 pt-2.5">
                        <p className="text-xs font-bold text-gray-900">
                          {header.text}
                        </p>
                      </div>
                    )}
                    {/* Body */}
                    {body?.text && (
                      <div className="px-3 py-2">
                        <p className="text-xs text-gray-800 leading-relaxed whitespace-pre-wrap wrap-break-word">
                          {body.text}
                        </p>
                      </div>
                    )}
                    {/* Footer */}
                    {footer?.text && (
                      <div className="px-3 pb-1">
                        <p className="text-[10px] text-gray-400">
                          {footer.text}
                        </p>
                      </div>
                    )}
                    {/* Timestamp */}
                    <div className="px-3 pb-1.5 flex justify-end">
                      <span className="text-[9px] text-gray-400">
                        10:30 AM ✓✓
                      </span>
                    </div>
                    {/* Buttons */}
                    {buttonsComp?.buttons && buttonsComp.buttons.length > 0 && (
                      <div className="border-t divide-y">
                        {buttonsComp.buttons.map((btn) => (
                          <div
                            key={btn.text}
                            className="flex items-center justify-center gap-1.5 py-2 text-[11px] font-medium"
                            style={{ color: "#24422e" }}
                          >
                            <ExternalLink className="w-3 h-3" />
                            {btn.text}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
