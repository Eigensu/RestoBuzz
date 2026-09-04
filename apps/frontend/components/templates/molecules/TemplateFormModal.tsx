"use client";
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { parseApiError } from "@/lib/errors";
import { X, Plus, Trash2, RefreshCw } from "lucide-react";
import type { Template } from "@/types";
import { HeaderMediaPreview } from "@/components/templates/atoms/HeaderMediaPreview";
import { MEDIA_CONFIG, isMediaFormat } from "@/lib/templateMedia";

import { BRAND_GRADIENT } from "@/lib/brand";
const INPUT_CLS =
  "w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#24422e]/20 focus:border-[#24422e]";



interface ComponentRow {
  type: string;
  text: string;
  format?: string;
  example?: Record<string, unknown>;
}

interface TemplateFormModalProps {
  /** Pass a template to edit, undefined to create new */
  editing?: Template;
  onClose: () => void;
  mode?: "modal" | "page";
}

const COMPONENT_TYPES = ["HEADER", "BODY", "FOOTER", "BUTTONS"];
const LANGUAGES = ["en", "en_US", "hi", "ar", "es", "fr", "pt_BR", "id"];

/** Text-area placeholder for a component row. A media header has nothing to
 *  type into it, so it points at the upload control instead. */
function placeholderFor(componentType: string, hasMedia: boolean): string {
  if (componentType === "BODY") {
    return "Message body — use {{1}}, {{2}} for variables";
  }
  if (componentType === "FOOTER") {
    return "Footer text (e.g. unsubscribe info)";
  }
  if (componentType === "HEADER") {
    return hasMedia ? "Upload media above" : "Header text";
  }
  return "Button text";
}

function defaultComponents(t?: Template): ComponentRow[] {
  if (t) {
    return t.components
      .filter((c) => c.type !== "BUTTONS")
      .map((c) => ({
        type: c.type,
        text: c.text ?? "",
        format: c.format,
        example: c.example,
      }));
  }
  return [{ type: "BODY", text: "" }];
}

export function TemplateFormModal({
  editing,
  onClose,
  mode = "modal",
}: TemplateFormModalProps) {
  const qc = useQueryClient();
  const isEdit = !!editing;
  const isModal = mode === "modal";

  const [name, setName] = useState(editing?.name ?? "");
  const [language, setLanguage] = useState(editing?.language ?? "en");
  const [components, setComponents] = useState<ComponentRow[]>(
    defaultComponents(editing),
  );
  const [uploadingHeaderMedia, setUploadingHeaderMedia] = useState(false);

  const setComp = <K extends keyof ComponentRow>(
    i: number,
    field: K,
    value: ComponentRow[K],
  ) =>
    setComponents((prev) =>
      prev.map((c, idx) => (idx === i ? { ...c, [field]: value } : c)),
    );

  const hasBodyElsewhere = (idx: number) =>
    components.some((c, i) => i !== idx && c.type === "BODY");

  const handleTypeChange = (idx: number, nextType: string) => {
    if (nextType === "BODY" && hasBodyElsewhere(idx)) {
      toast.error("Only one BODY component is allowed in a template");
      return;
    }

    setComponents((prev) =>
      prev.map((c, i) => {
        if (i !== idx) return c;
        if (nextType !== "HEADER") {
          return {
            ...c,
            type: nextType,
            format: undefined,
            example: undefined,
          };
        }
        return { ...c, type: "HEADER", format: c.format ?? "TEXT" };
      }),
    );
  };

  const setHeaderMediaUrl = (idx: number, url: string) => {
    setComponents((prev) =>
      prev.map((c, i) => {
        if (i !== idx) return c;
        return {
          ...c,
          text: "",
          example: {
            ...(c.example ?? {}),
            media_url: url,
          },
        };
      }),
    );
  };

  const getHeaderMediaUrl = (comp: ComponentRow) =>
    typeof comp.example?.media_url === "string" ? comp.example.media_url : "";

  const componentHasPayload = (comp: ComponentRow) => {
    if (comp.type === "HEADER" && isMediaFormat(comp.format)) {
      return !!getHeaderMediaUrl(comp).trim();
    }
    return !!comp.text.trim();
  };

  const addComp = () =>
    setComponents((prev) => {
      const hasBody = prev.some((c) => c.type === "BODY");
      return [...prev, { type: hasBody ? "HEADER" : "BODY", text: "" }];
    });
  const removeComp = (i: number) =>
    setComponents((prev) => prev.filter((_, idx) => idx !== i));

  const mutation = useMutation({
    mutationFn: async () => {
      const payload = {
        components: components.filter(componentHasPayload).map((c) => ({
          type: c.type,
          text: c.text,
          ...(c.format ? { format: c.format } : {}),
          ...(c.example ? { example: c.example } : {}),
        })),
      };
      // Awaited rather than returned. The response body is unused (onSuccess
      // ignores it), and axios now carries the request-body type in
      // AxiosResponse, so returning the patch and post branches directly gives
      // two response types that no longer unify into one MutationFunction.
      if (isEdit) {
        await api.patch(`/templates/${editing!.name}`, payload);
        return;
      }
      await api.post("/templates", {
        name: name.toLowerCase().replace(/\s+/g, "_"),
        category: "MARKETING",
        language,
        ...payload,
      });
    },
    onSuccess: () => {
      toast.success(
        isEdit
          ? "Template updated — pending Meta review"
          : "Template created — pending Meta review",
      );
      qc.invalidateQueries({ queryKey: ["templates"] });
      onClose();
    },
    onError: (e: unknown) => toast.error(parseApiError(e).message),
  });

  // Editing hides the media controls, and a stored header carries a Meta
  // header_handle rather than a media_url, so this only guards creation.
  const missingHeaderMedia =
    !isEdit &&
    components.some(
      (c) =>
        c.type === "HEADER" &&
        isMediaFormat(c.format) &&
        !getHeaderMediaUrl(c).trim(),
    );

  const canSubmit = isEdit
    ? components.some(componentHasPayload) &&
      !components.some((c) => c.type === "BODY" && c.text.length > 1024) &&
      !uploadingHeaderMedia
    : !!name.trim() &&
      components.some((c) => c.type === "BODY" && c.text.trim()) &&
      !components.some((c) => c.type === "BODY" && c.text.length > 1024) &&
      !uploadingHeaderMedia &&
      !missingHeaderMedia;

  const previewHeader = components.find((c) => c.type === "HEADER");
  const previewBody = components.find((c) => c.type === "BODY");
  const previewFooter = components.find((c) => c.type === "FOOTER");
  const previewTitle = name || editing?.name || "new_template";
  const previewHeaderFormat = previewHeader?.format ?? "";
  const previewHeaderMedia = previewHeader
    ? getHeaderMediaUrl(previewHeader)
    : "";
  const previewHeaderText = previewHeader?.text?.trim();
  const previewBodyText = previewBody?.text?.trim();
  const previewFooterText = previewFooter?.text?.trim();

  const content = (
    <div
      className={`bg-white w-full flex flex-col ${
        isModal
          ? "rounded-3xl shadow-2xl max-w-lg max-h-[90vh]"
          : "rounded-2xl border border-gray-100 shadow-sm max-w-4xl"
      }`}
      onClick={(e) => isModal && e.stopPropagation()}
      onKeyDown={(e) => {
        if (isModal && e.key !== "Escape") e.stopPropagation();
      }}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b">
        <div>
          <p className="font-black text-gray-900">
            {isEdit ? `Edit "${editing!.name}"` : "New Template"}
          </p>
          {isEdit && (
            <p className="text-xs text-amber-600 mt-0.5 font-medium">
              Meta allows editing body text only · 1 edit/day · 10/month
            </p>
          )}
        </div>
        {isModal ? (
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-gray-100 transition text-gray-400"
          >
            <X className="w-4 h-4" />
          </button>
        ) : (
          <button
            onClick={onClose}
            className="text-sm font-medium text-gray-500 hover:text-gray-700 transition"
          >
            Back
          </button>
        )}
      </div>

      {/* Form */}
      <div className="flex-1 overflow-y-auto p-6 space-y-5">
        {/* Name + Category + Language — only for create */}
        {!isEdit && (
          <div className="grid grid-cols-2 gap-4">
            <div className="col-span-2">
              <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-1.5">
                Template Name
              </label>
              <input
                value={name}
                onChange={(e) =>
                  setName(
                    e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ""),
                  )
                }
                className={INPUT_CLS}
                placeholder="e.g. welcome_offer"
              />
              <p className="text-[10px] text-gray-400 mt-1">
                Lowercase letters, numbers, underscores only
              </p>
            </div>
            <div>
              <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-1.5">
                Language
              </label>
              <select
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
                className={INPUT_CLS}
              >
                {LANGUAGES.map((l) => (
                  <option key={l} value={l}>
                    {l}
                  </option>
                ))}
              </select>
            </div>
          </div>
        )}

        {/* Components */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <label className="text-xs font-bold text-gray-500 uppercase tracking-wider">
              Components
            </label>
            {!isEdit && (
              <button
                onClick={addComp}
                className="flex items-center gap-1 text-xs font-bold text-[#24422e] hover:underline"
              >
                <Plus className="w-3 h-3" /> Add
              </button>
            )}
          </div>

          {components.map((comp, i) => {
            // null for TEXT / non-HEADER rows; drives the upload control.
            const mediaCfg = isMediaFormat(comp.format)
              ? MEDIA_CONFIG[comp.format]
              : null;
            return (
              <div
                key={i}
                className="border border-gray-100 rounded-2xl p-4 space-y-3 bg-gray-50/50"
              >
                <div className="flex items-center justify-between gap-3">
                  {isEdit ? (
                    <span className="text-[10px] font-bold px-2.5 py-1 rounded-full bg-[#eff2f0] text-[#24422e] tracking-wider">
                      {comp.type}
                    </span>
                  ) : (
                    <select
                      value={comp.type}
                      onChange={(e) => handleTypeChange(i, e.target.value)}
                      className="text-xs font-bold border border-gray-200 rounded-lg px-2 py-1 focus:outline-none focus:ring-2 focus:ring-[#24422e]/20 bg-white"
                    >
                      {COMPONENT_TYPES.map((t) => (
                        <option
                          key={t}
                          value={t}
                          disabled={t === "BODY" && hasBodyElsewhere(i)}
                        >
                          {t}
                        </option>
                      ))}
                    </select>
                  )}
                  {!isEdit && components.length > 1 && (
                    <button
                      onClick={() => removeComp(i)}
                      className="text-gray-300 hover:text-red-400 transition"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>

                {/* Format selector for HEADER */}
                {comp.type === "HEADER" && !isEdit && (
                  <select
                    value={comp.format ?? "TEXT"}
                    onChange={(e) => {
                      const nextFormat = e.target.value;
                      setComp(i, "format", nextFormat);
                      // A media handle is format-specific, so an upload never
                      // carries across a switch.
                      setComp(i, "example", undefined);
                      if (nextFormat !== "TEXT") {
                        setComp(i, "text", "");
                      }
                    }}
                    className="text-xs border border-gray-200 rounded-lg px-2 py-1 focus:outline-none w-full bg-white"
                  >
                    <option value="TEXT">Text</option>
                    <option value="IMAGE">Image</option>
                    <option value="VIDEO">Video</option>
                    <option value="DOCUMENT">Document</option>
                  </select>
                )}

                {comp.type === "HEADER" && mediaCfg && !isEdit && (
                  <div className="space-y-2">
                    {getHeaderMediaUrl(comp) ? (
                      <div className="relative w-full rounded-lg overflow-hidden border bg-white">
                        <HeaderMediaPreview
                          headerFormat={comp.format ?? ""}
                          mediaUrl={getHeaderMediaUrl(comp)}
                        />
                        <button
                          onClick={() => setHeaderMediaUrl(i, "")}
                          className="absolute top-2 right-2 bg-black/50 hover:bg-black/70 text-white rounded-full p-1 transition"
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    ) : (
                      <label
                        className={`flex flex-col items-center justify-center gap-2 border-2 border-dashed rounded-lg p-4 cursor-pointer transition ${
                          uploadingHeaderMedia
                            ? "opacity-50 pointer-events-none"
                            : "hover:border-[#24422e]/40 hover:bg-[#24422e]/5"
                        }`}
                      >
                        <input
                          type="file"
                          accept={mediaCfg.accept}
                          className="sr-only"
                          onChange={async (e) => {
                            const media = e.target.files?.[0];
                            if (!media) return;
                            setUploadingHeaderMedia(true);
                            try {
                              const form = new FormData();
                              form.append("file", media);
                              const { data } = await api.post(
                                "/media/upload",
                                form,
                                {
                                  headers: {
                                    "Content-Type": "multipart/form-data",
                                  },
                                },
                              );
                              setHeaderMediaUrl(i, data.url);
                            } catch (err) {
                              toast.error(parseApiError(err).message);
                            } finally {
                              setUploadingHeaderMedia(false);
                            }
                          }}
                        />
                        {uploadingHeaderMedia ? (
                          <RefreshCw className="w-5 h-5 text-gray-400 animate-spin" />
                        ) : (
                          <mediaCfg.Icon className="w-5 h-5 text-gray-300" />
                        )}
                        <span className="text-xs text-gray-400">
                          {uploadingHeaderMedia ? "Uploading..." : mediaCfg.hint}
                        </span>
                      </label>
                    )}
                    <input
                      value={getHeaderMediaUrl(comp)}
                      onChange={(e) => setHeaderMediaUrl(i, e.target.value)}
                      className={INPUT_CLS}
                      placeholder={mediaCfg.urlPlaceholder}
                    />
                  </div>
                )}

                <textarea
                  value={comp.text}
                  onChange={(e) =>
                    setComp(
                      i,
                      "text",
                      comp.type === "BODY"
                        ? e.target.value.slice(0, 1024)
                        : e.target.value,
                    )
                  }
                  rows={comp.type === "BODY" ? 4 : 2}
                  className={`w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#24422e]/20 focus:border-[#24422e] resize-none ${isEdit && comp.type !== "BODY" ? "bg-gray-100 text-gray-500 cursor-not-allowed" : "bg-white"}`}
                  maxLength={comp.type === "BODY" ? 1024 : undefined}
                  disabled={(comp.type === "HEADER" && !!mediaCfg) || (isEdit && comp.type !== "BODY")}
                  readOnly={isEdit && comp.type !== "BODY"}
                  aria-readonly={isEdit && comp.type !== "BODY"}
                  placeholder={placeholderFor(comp.type, !!mediaCfg)}
                />
                {comp.type === "BODY" && (
                  <p
                    className={`text-[11px] text-right ${
                      comp.text.length >= 1024
                        ? "text-amber-600"
                        : "text-gray-400"
                    }`}
                  >
                    {comp.text.length}/1024
                  </p>
                )}
              </div>
            );
          })}
        </div>

        {/* Info box */}
        <div className="bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 text-xs text-amber-700 leading-relaxed">
          <span className="font-bold">Note:</span> Templates are submitted to
          Meta for review and may take up to 24 hours to be approved before they
          can be used in campaigns.
        </div>
      </div>

      {/* Footer */}
      <div className="flex gap-3 px-6 py-4 border-t">
        <button
          onClick={onClose}
          className="flex-1 border rounded-xl py-2.5 text-sm font-medium hover:bg-gray-50 transition"
        >
          {isModal ? "Cancel" : "Back"}
        </button>
        <button
          onClick={() => mutation.mutate()}
          disabled={!canSubmit || mutation.isPending}
          className="flex-1 text-white text-sm font-bold py-2.5 rounded-xl transition disabled:opacity-50"
          style={{ background: BRAND_GRADIENT }}
        >
          {mutation.isPending
            ? "Submitting..."
            : isEdit
              ? "Save & Submit"
              : "Create Template"}
        </button>
      </div>
    </div>
  );

  if (!isModal) {
    return (
      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_340px] gap-6 items-start">
        {content}

        <aside className="hidden xl:block sticky top-6">
          <div className="rounded-2xl border border-gray-100 bg-white shadow-sm overflow-hidden">
            <div className="px-4 py-3 border-b bg-[#f8faf9]">
              <p className="text-xs font-bold tracking-wide text-gray-500 uppercase">
                Live Preview
              </p>
              <p className="text-sm font-semibold text-gray-900 mt-1">
                {previewTitle}
              </p>
            </div>

            <div className="p-4">
              <div className="rounded-2xl border border-gray-200 bg-[#f3f7f4] p-3">
                <div className="rounded-xl bg-white border border-gray-200 overflow-hidden">
                  {previewHeaderMedia && isMediaFormat(previewHeaderFormat) ? (
                    <HeaderMediaPreview
                      headerFormat={previewHeaderFormat}
                      mediaUrl={previewHeaderMedia}
                      className="h-40 max-h-40"
                    />
                  ) : previewHeaderText ? (
                    <div className="px-3 pt-3 text-xs font-bold text-gray-900">
                      {previewHeaderText}
                    </div>
                  ) : null}

                  <div className="px-3 py-3">
                    <p className="text-sm text-gray-800 leading-relaxed whitespace-pre-wrap wrap-break-word">
                      {previewBodyText ||
                        "Your body content will appear here as you type."}
                    </p>
                    {previewFooterText && (
                      <p className="text-[11px] text-gray-500 mt-3">
                        {previewFooterText}
                      </p>
                    )}
                  </div>
                </div>
              </div>

                <span className="px-2 py-0.5 rounded-full bg-gray-100 font-semibold">
                  {language}
                </span>
            </div>
          </div>
        </aside>
      </div>
    );
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={isEdit ? `Edit template ${editing?.name}` : "New template"}
      className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4"
      onClick={onClose}
      onKeyDown={(e) => e.key === "Escape" && onClose()}
    >
      {content}
    </div>
  );
}
