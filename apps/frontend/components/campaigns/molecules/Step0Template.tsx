"use client";
import { RefreshCw, ImageIcon, X, Search } from "lucide-react";
import { useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { parseApiError } from "@/lib/errors";
import { cn } from "@/lib/utils";
import type { Template } from "@/types";
import { WizardTemplatePreview } from "@/components/campaigns/molecules/WizardTemplatePreview";

const INPUT_CLS =
  "w-full border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#24422e]/30";

interface Step0TemplateProps {
  templates: Template[];
  selectedTemplate: Template | null;
  setSelectedTemplate: (t: Template | null) => void;
  variables: Record<string, string>;
  setVariables: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  mediaUrl: string;
  setMediaUrl: (url: string) => void;
  fetchingTemplates: boolean;
  refetchTemplates: () => void;
  uploadingMedia: boolean;
  setUploadingMedia: (b: boolean) => void;
  bodyVars: string[];
}

export function Step0Template({
  templates,
  selectedTemplate,
  setSelectedTemplate,
  variables,
  setVariables,
  mediaUrl,
  setMediaUrl,
  fetchingTemplates,
  refetchTemplates,
  uploadingMedia,
  setUploadingMedia,
  bodyVars,
}: Readonly<Step0TemplateProps>) {
  const [searchQuery, setSearchQuery] = useState("");

  const filteredTemplates = templates.filter((t) =>
    t.name.toLowerCase().includes(searchQuery.toLowerCase()),
  );
  const requiresMedia =
    selectedTemplate?.components.some(
      (component) =>
        component.type === "HEADER" && component.format === "IMAGE",
    ) ?? false;

  return (
    <div className="flex gap-6">
      {/* Left: selection + config */}
      <div className="flex-1 min-w-0 space-y-3 overflow-y-auto max-h-[70vh] pr-1">
        <div className="flex items-center justify-between">
          <h2 className="font-medium">Select Template</h2>
          <button
            onClick={refetchTemplates}
            disabled={fetchingTemplates}
            className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-[#24422e] disabled:opacity-50 transition"
          >
            <RefreshCw
              className={cn("w-3.5 h-3.5", fetchingTemplates && "animate-spin")}
            />
            Refresh
          </button>
        </div>

        {/* Search Bar */}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search templates by name..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className={cn(INPUT_CLS, "pl-9 py-2")}
          />
        </div>

        <div
          className="grid sm:grid-cols-2 gap-2 overflow-y-auto pr-1"
          style={{ maxHeight: "40vh" }}
        >
          {filteredTemplates.length > 0 ? (
            filteredTemplates.map((t) => (
              <button
                key={t.name}
                onClick={() => {
                  setSelectedTemplate(t);
                  setVariables({});
                  setMediaUrl("");
                }}
                className={cn(
                  "text-left border rounded-lg px-4 py-3 transition",
                  selectedTemplate?.name === t.name
                    ? "border-[#24422e] bg-[#24422e]/5"
                    : "hover:border-[#24422e]/30",
                )}
              >
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">{t.name}</span>
                </div>
                <p className="text-xs text-gray-400 mt-1">
                  {t.language} · {t.status}
                </p>
              </button>
            ))
          ) : (
            <div className="col-span-2 py-8 text-center text-gray-400 text-sm">
              No templates found matching &quot;{searchQuery}&quot;
            </div>
          )}
        </div>

        {selectedTemplate && bodyVars.length > 0 && (
          <div className="space-y-2">
            <p className="text-sm font-medium">Template Variables</p>
            {bodyVars.map((v) => (
              <div key={v}>
                <label
                  htmlFor={`var-${v}`}
                  className="text-xs text-gray-500 mb-0.5 block"
                >{`{{${v}}}`}</label>
                <input
                  id={`var-${v}`}
                  value={variables[v] ?? ""}
                  onChange={(e) =>
                    setVariables((prev) => ({ ...prev, [v]: e.target.value }))
                  }
                  className={INPUT_CLS}
                  placeholder={`Value for {{${v}}}`}
                />
              </div>
            ))}
          </div>
        )}

        {selectedTemplate && requiresMedia && (
          <div className="space-y-1.5">
            <label
              htmlFor="media-upload-input"
              className="text-xs text-gray-500 block"
            >
              Media Image (optional)
            </label>
            {mediaUrl ? (
              <div className="relative w-full rounded-lg overflow-hidden border">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={mediaUrl}
                  alt="media preview"
                  className="w-full max-h-36 object-cover"
                />
                <button
                  onClick={() => setMediaUrl("")}
                  className="absolute top-2 right-2 bg-black/50 hover:bg-black/70 text-white rounded-full p-1 transition"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            ) : (
              <label
                className={cn(
                  "flex flex-col items-center justify-center gap-2 border-2 border-dashed rounded-lg p-4 cursor-pointer transition",
                  uploadingMedia
                    ? "opacity-50 pointer-events-none"
                    : "hover:border-[#24422e]/40 hover:bg-[#24422e]/5",
                )}
              >
                <input
                  id="media-upload-input"
                  type="file"
                  accept="image/jpeg,image/png,image/webp,image/gif"
                  className="sr-only"
                  onChange={async (e) => {
                    const img = e.target.files?.[0];
                    if (!img) return;
                    setUploadingMedia(true);
                    try {
                      const form = new FormData();
                      form.append("file", img);
                      const { data } = await api.post("/media/upload", form, {
                        headers: { "Content-Type": "multipart/form-data" },
                      });
                      setMediaUrl(data.url);
                    } catch (err) {
                      toast.error(parseApiError(err).message);
                    } finally {
                      setUploadingMedia(false);
                    }
                  }}
                />
                {uploadingMedia ? (
                  <RefreshCw className="w-5 h-5 text-gray-400 animate-spin" />
                ) : (
                  <ImageIcon className="w-5 h-5 text-gray-300" />
                )}
                <span className="text-xs text-gray-400">
                  {uploadingMedia
                    ? "Uploading…"
                    : "Click to upload · JPG, PNG, WEBP · max 5MB"}
                </span>
              </label>
            )}
            <input
              value={mediaUrl}
              readOnly
              className={cn(
                INPUT_CLS,
                "bg-gray-50 text-gray-500 cursor-not-allowed",
              )}
              placeholder="Or paste a URL directly…"
            />
          </div>
        )}

        {selectedTemplate && !requiresMedia && (
          <div className="rounded-lg border border-dashed border-gray-200 bg-gray-50/70 px-3 py-2 text-xs text-gray-500">
            This template does not require a media header.
          </div>
        )}
      </div>

      {/* Right: preview */}
      <div className="hidden lg:flex w-2/5 border-l pl-6 flex-col self-stretch min-h-100">
        <WizardTemplatePreview
          template={selectedTemplate}
          variables={variables}
          mediaUrl={mediaUrl}
        />
      </div>
    </div>
  );
}
