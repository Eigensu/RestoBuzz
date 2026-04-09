import { LayoutTemplate } from "lucide-react";
import type { Template } from "@/types";
import { TemplateCard } from "@/components/templates/molecules/TemplateCard";

interface TemplateGridProps {
  templates: Template[];
}

export function TemplateGrid({ templates }: Readonly<TemplateGridProps>) {
  if (templates.length === 0) {
    return (
      <div className="bg-white rounded-2xl border border-gray-100 p-10 text-center shadow-sm">
        <p className="text-sm text-gray-400 font-medium">
          No templates match your search.
        </p>
      </div>
    );
  }

  return (
    <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
      {templates.map((t) => (
        <TemplateCard key={`${t.name}:${t.language}`} template={t} />
      ))}
    </div>
  );
}

export function TemplateEmptyState() {
  return (
    <div className="bg-white rounded-3xl border border-gray-100 p-16 text-center shadow-sm">
      <div className="w-20 h-20 bg-[#eff2f0] rounded-3xl flex items-center justify-center mb-6 mx-auto shadow-sm">
        <LayoutTemplate className="w-10 h-10 text-[#24422e]" />
      </div>
      <h2 className="text-xl font-black text-gray-900 tracking-tight">
        No templates yet
      </h2>
      <p className="text-sm text-gray-500 mt-2 font-medium">
        Click &quot;Sync Templates&quot; to pull from Meta or create one manually.
      </p>
    </div>
  );
}
