"use client";

import { useRouter } from "next/navigation";
import { Plus, ArrowLeft } from "lucide-react";
import { TemplateFormModal } from "@/components/templates/molecules/TemplateFormModal";

export default function NewTemplatePage() {
  const router = useRouter();

  return (
    <div className="space-y-6 pb-20 max-w-[1600px] mx-auto p-4 md:p-8">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <button
            onClick={() => router.push("/templates")}
            className="inline-flex items-center gap-2 text-sm text-gray-500 hover:text-gray-800 transition"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to templates
          </button>
          <div className="flex items-center gap-3 mt-2">
            <div className="p-2 bg-[#eff2f0] rounded-lg">
              <Plus className="w-6 h-6 text-[#24422e]" />
            </div>
            <h1 className="text-2xl font-black text-gray-900 tracking-tight">
              Create New Template
            </h1>
          </div>
          <p className="text-sm text-gray-500 mt-1 ml-11 font-medium">
            Use the extra space to build richer template structures.
          </p>
        </div>
      </div>

      <TemplateFormModal
        mode="page"
        onClose={() => router.push("/templates")}
      />
    </div>
  );
}
