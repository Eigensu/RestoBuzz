"use client";
import { useState } from "react";
import { FileText } from "lucide-react";
import type { Template } from "@/types";
import { StatusBadge } from "@/components/templates/atoms/StatusBadge";
import { CategoryBadge } from "@/components/templates/atoms/CategoryBadge";
import { ComponentPill } from "@/components/templates/atoms/ComponentPill";
import { TemplateModal } from "@/components/templates/molecules/TemplateModal";

interface TemplateCardProps {
  template: Template;
}

export function TemplateCard({ template: t }: Readonly<TemplateCardProps>) {
  const [open, setOpen] = useState(false);
  const bodyText = t.components.find((c) => c.type === "BODY")?.text;
  const hasHeader = t.components.some((c) => c.type === "HEADER");
  const hasButtons = t.components.some((c) => c.type === "BUTTONS");

  return (
    <>
      {open && <TemplateModal template={t} onClose={() => setOpen(false)} />}
      <div
        role="button"
        tabIndex={0}
        onClick={() => setOpen(true)}
        onKeyDown={(e) => e.key === "Enter" && setOpen(true)}
        className="bg-white rounded-3xl border border-gray-100 p-6 shadow-sm hover:shadow-lg hover:-translate-y-0.5 transition-all flex flex-col gap-4 cursor-pointer"
      >
        {/* Header row */}
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2 min-w-0">
            <div className="w-8 h-8 rounded-xl bg-[#eff2f0] flex items-center justify-center shrink-0">
              <FileText className="w-4 h-4 text-[#24422e]" />
            </div>
            <p className="font-black text-sm text-gray-900 truncate">
              {t.name}
            </p>
          </div>
          <StatusBadge status={t.status} />
        </div>

        {/* Body preview */}
        <p className="text-xs text-gray-500 leading-relaxed line-clamp-3 flex-1">
          {bodyText ?? "No body text"}
        </p>

        {/* Footer */}
        <div className="flex items-center justify-between pt-3 border-t border-gray-50">
          <div className="flex gap-2 flex-wrap">
            <CategoryBadge category={t.category} />
            <span className="text-[10px] font-bold px-2.5 py-1 rounded-full bg-gray-100 text-gray-500 tracking-wider">
              {t.language}
            </span>
          </div>
          <div className="flex gap-1">
            {hasHeader && <ComponentPill label="HEADER" />}
            {hasButtons && <ComponentPill label="BUTTONS" />}
          </div>
        </div>
      </div>
    </>
  );
}
