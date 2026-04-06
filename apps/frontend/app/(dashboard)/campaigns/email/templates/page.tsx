"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import type { EmailTemplate } from "@/types";
import { toast } from "sonner";
import { parseApiError } from "@/lib/errors";
import { BRAND_GRADIENT } from "@/lib/brand";
import {
  Plus,
  FileText,
  Eye,
  Pencil,
  Trash2,
  X,
  Loader2,
  Code,
  Variable,
} from "lucide-react";
import { EmptyState } from "@/components/ui/EmptyState";
import { formatDistanceToNow } from "date-fns";

export default function EmailTemplatesPage() {
  const qc = useQueryClient();
  const { restaurant } = useAuthStore();
  const [showEditor, setShowEditor] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState<EmailTemplate | null>(
    null,
  );
  const [showPreview, setShowPreview] = useState(false);
  const [previewHtml, setPreviewHtml] = useState("");

  // Form state
  const [name, setName] = useState("");
  const [subject, setSubject] = useState("");
  const [html, setHtml] = useState("");
  const [variables, setVariables] = useState<
    Array<{ key: string; type: "string" | "number"; fallback_value: string }>
  >([]);

  const { data, isLoading } = useQuery({
    queryKey: ["email-templates", restaurant?.id],
    queryFn: () =>
      api
        .get(`/email-templates?restaurant_id=${restaurant!.id}&page_size=100`)
        .then((r) => r.data),
    enabled: !!restaurant,
  });

  const templates: EmailTemplate[] = data?.items ?? [];

  const resetForm = () => {
    setName("");
    setSubject("");
    setHtml("");
    setVariables([]);
    setEditingTemplate(null);
    setShowEditor(false);
  };

  const openEditor = (t?: EmailTemplate) => {
    if (t) {
      setEditingTemplate(t);
      setName(t.name);
      setSubject(t.subject);
      setHtml(t.html);
      setVariables(
        t.variables.map((v) => ({
          key: v.key,
          type: v.type,
          fallback_value: String(v.fallback_value ?? ""),
        })),
      );
    } else {
      resetForm();
    }
    setShowEditor(true);
  };

  const saveMutation = useMutation({
    mutationFn: async () => {
      const payload = {
        name,
        subject,
        html,
        variables: variables.filter((v) => v.key.trim()),
      };
      if (editingTemplate) {
        return api.put(`/email-templates/${editingTemplate.id}`, payload);
      }
      return api.post(
        `/email-templates?restaurant_id=${restaurant!.id}`,
        payload,
      );
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["email-templates", restaurant?.id] });
      toast.success(editingTemplate ? "Template updated" : "Template created");
      resetForm();
    },
    onError: (e: unknown) => toast.error(parseApiError(e).message),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/email-templates/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["email-templates", restaurant?.id] });
      toast.success("Template deleted");
    },
    onError: (e: unknown) => toast.error(parseApiError(e).message),
  });

  const handlePreview = async (t: EmailTemplate) => {
    try {
      const { data } = await api.post(`/email-templates/${t.id}/preview`, {});
      setPreviewHtml(data.html);
      setShowPreview(true);
    } catch (e) {
      toast.error(parseApiError(e).message);
    }
  };

  const addVariable = () => {
    setVariables([
      ...variables,
      { key: "", type: "string", fallback_value: "" },
    ]);
  };

  return (
    <div className="space-y-8 pb-20 max-w-[1600px] mx-auto p-4 md:p-8">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <div className="p-2 bg-[#eff2f0] rounded-lg">
              <FileText className="w-6 h-6 text-[#24422e]" />
            </div>
            <h1 className="text-2xl font-black text-gray-900 tracking-tight">
              Email Templates
            </h1>
          </div>
          <p className="text-sm text-gray-500 mt-1 ml-11 font-medium">
            Manage reusable email templates for your campaigns
          </p>
        </div>
        <button
          onClick={() => openEditor()}
          className="inline-flex items-center gap-2 text-white text-sm font-bold px-6 py-3 rounded-xl transition hover:scale-[1.02] active:scale-[0.98] shadow-lg shadow-green-900/10"
          style={{ background: BRAND_GRADIENT }}
        >
          <Plus className="w-4 h-4" />
          NEW TEMPLATE
        </button>
      </div>

      {/* Template List */}
      {isLoading ? (
        <div className="bg-white rounded-xl border p-12 text-center text-sm text-gray-400">
          Loading...
        </div>
      ) : templates.length === 0 ? (
        <div className="bg-white rounded-xl border">
          <EmptyState
            icon={FileText}
            title="No email templates yet"
            description="Create your first HTML email template to use in campaigns."
          />
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {templates.map((t) => (
            <div
              key={t.id}
              className="bg-white rounded-xl border p-5 hover:shadow-md transition group"
            >
              <div className="flex items-start justify-between mb-3">
                <div>
                  <h3 className="font-bold text-gray-900">{t.name}</h3>
                  <p className="text-xs text-gray-400 mt-0.5">
                    v{t.version} &middot; Updated{" "}
                    {formatDistanceToNow(new Date(t.updated_at.endsWith("Z") ? t.updated_at : t.updated_at + "Z"), {
                      addSuffix: true,
                    })}
                  </p>
                </div>
                <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition">
                  <button
                    onClick={() => handlePreview(t)}
                    className="p-1.5 rounded-lg hover:bg-blue-50 text-blue-500 transition"
                    title="Preview"
                  >
                    <Eye className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => openEditor(t)}
                    className="p-1.5 rounded-lg hover:bg-amber-50 text-amber-600 transition"
                    title="Edit"
                  >
                    <Pencil className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => {
                      if (globalThis.confirm("Delete this template?"))
                        deleteMutation.mutate(t.id);
                    }}
                    className="p-1.5 rounded-lg hover:bg-red-50 text-red-500 transition"
                    title="Delete"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
              <p className="text-xs text-gray-500 mb-2">
                <span className="font-semibold">Subject:</span> {t.subject}
              </p>
              {t.variables.length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {t.variables.map((v) => (
                    <span
                      key={v.key}
                      className="inline-flex items-center gap-0.5 text-xs bg-violet-50 text-violet-600 px-2 py-0.5 rounded-full font-medium"
                    >
                      <Variable className="w-3 h-3" />
                      {v.key}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Editor Modal */}
      {showEditor && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-6xl w-full max-h-[90vh] overflow-hidden shadow-2xl flex flex-col">
            <div className="px-6 py-4 border-b flex items-center justify-between sticky top-0 bg-white z-10 rounded-t-2xl">
              <h3 className="text-lg font-bold text-gray-900">
                {editingTemplate ? "Edit Template" : "Create Template"}
              </h3>
              <button
                onClick={resetForm}
                className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 transition"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto">
              <div className="grid grid-cols-1 lg:grid-cols-2 divide-x h-full">
                {/* Form Side */}
                <div className="p-6 space-y-5">
                  <div>
                    <label className="text-xs font-semibold text-gray-600 block mb-1">
                      Template Name *
                    </label>
                    <input
                      type="text"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      placeholder="e.g. Welcome Email"
                      className="w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-[#24422e]/20 focus:border-[#24422e]"
                    />
                  </div>

                  <div>
                    <label className="text-xs font-semibold text-gray-600 block mb-1">
                      Subject Line *
                    </label>
                    <input
                      type="text"
                      value={subject}
                      onChange={(e) => setSubject(e.target.value)}
                      placeholder="e.g. Welcome to {{restaurant_name}}!"
                      className="w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-[#24422e]/20 focus:border-[#24422e]"
                    />
                  </div>

                  <div>
                    <label className="text-xs font-semibold text-gray-600 block mb-1">
                      <span className="inline-flex items-center gap-1">
                        <Code className="w-3.5 h-3.5" /> HTML Body *
                      </span>
                    </label>
                    <textarea
                      value={html}
                      onChange={(e) => setHtml(e.target.value)}
                      rows={12}
                      placeholder="<html>...</html>"
                      className="w-full px-3 py-2 border rounded-lg text-sm font-mono focus:outline-none focus:ring-2 focus:ring-[#24422e]/20 focus:border-[#24422e] resize-none"
                    />
                    <p className="text-xs text-gray-400 mt-1">
                      Use {"{{ variable_name }}"} for dynamic content.
                    </p>
                  </div>

                  {/* Variables */}
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <label className="text-xs font-semibold text-gray-600">
                        Template Variables
                      </label>
                      <button
                        onClick={addVariable}
                        className="text-xs text-[#24422e] font-bold hover:underline"
                      >
                        + Add Variable
                      </button>
                    </div>
                    {variables.length === 0 ? (
                      <p className="text-xs text-gray-400">No variables defined.</p>
                    ) : (
                      <div className="space-y-2">
                        {variables.map((v, i) => (
                          <div key={i} className="flex gap-2 items-center">
                            <input
                              type="text"
                              value={v.key}
                              onChange={(e) => {
                                const copy = [...variables];
                                copy[i] = { ...copy[i], key: e.target.value };
                                setVariables(copy);
                              }}
                              placeholder="Variable name"
                              className="flex-1 px-2.5 py-1.5 border rounded-lg text-xs focus:outline-none focus:ring-1 focus:ring-[#24422e]/20"
                            />
                            <input
                              type="text"
                              value={v.fallback_value}
                              onChange={(e) => {
                                const copy = [...variables];
                                copy[i] = {
                                  ...copy[i],
                                  fallback_value: e.target.value,
                                };
                                setVariables(copy);
                              }}
                              placeholder="Fallback value"
                              className="flex-1 px-2.5 py-1.5 border rounded-lg text-xs focus:outline-none focus:ring-1 focus:ring-[#24422e]/20"
                            />
                            <button
                              onClick={() =>
                                setVariables(variables.filter((_, j) => j !== i))
                              }
                              className="p-1 text-red-400 hover:text-red-600 transition"
                            >
                              <X className="w-4 h-4" />
                            </button>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>

                {/* Preview Side */}
                <div className="bg-gray-50 flex flex-col min-h-0 h-full overflow-hidden">
                  <div className="px-5 py-3 border-b flex items-center justify-between bg-white/50">
                    <span className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">
                      Live Preview
                    </span>
                  </div>
                  <div className="flex-1 p-6 overflow-y-auto">
                    {!html ? (
                      <div className="h-full flex flex-col items-center justify-center text-gray-400 gap-3">
                        <Eye className="w-8 h-8 opacity-20" />
                        <p className="text-xs font-medium italic">
                          Start typing HTML to see preview...
                        </p>
                      </div>
                    ) : (
                      <div className="bg-white rounded-xl shadow-sm border border-gray-100 min-h-full overflow-hidden">
                        <iframe
                          title="Preview"
                          srcDoc={html.replace(/\{\{\s*(\w+)\s*\}\}/g, (match, key) => {
                            const v = variables.find((val) => val.key === key);
                            return v?.fallback_value || `[${key}]`;
                          })}
                          className="w-full min-h-[400px] border-0"
                        />
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>

            <div className="px-6 py-4 border-t flex justify-end gap-3 sticky bottom-0 bg-white rounded-b-2xl">
              <button
                onClick={resetForm}
                className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900 transition"
              >
                Cancel
              </button>
              <button
                onClick={() => saveMutation.mutate()}
                disabled={saveMutation.isPending || !name || !subject || !html}
                className="inline-flex items-center gap-1.5 text-white text-sm font-bold px-5 py-2 rounded-xl transition disabled:opacity-40 hover:scale-[1.02]"
                style={{ background: BRAND_GRADIENT }}
              >
                {saveMutation.isPending && (
                  <Loader2 className="w-4 h-4 animate-spin" />
                )}
                {editingTemplate ? "Update" : "Create"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Preview Modal */}
      {showPreview && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-2xl w-full max-h-[80vh] overflow-hidden shadow-2xl">
            <div className="px-5 py-3 border-b flex items-center justify-between">
              <h3 className="text-sm font-bold text-gray-900">
                Template Preview
              </h3>
              <button
                onClick={() => setShowPreview(false)}
                className="text-gray-400 hover:text-gray-600"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-6 overflow-y-auto max-h-[70vh]">
              <iframe
                title="Template Preview"
                srcDoc={previewHtml}
                sandbox=""
                className="w-full min-h-[60vh] bg-white border-0"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
