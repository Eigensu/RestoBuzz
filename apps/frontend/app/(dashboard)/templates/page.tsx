"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import type { Template, EmailTemplate } from "@/types";
import { toast } from "sonner";
import { parseApiError } from "@/lib/errors";
import { BRAND_GRADIENT, GREEN } from "@/lib/brand";
import {
  Plus,
  FileText,
  RefreshCw,
  LayoutTemplate,
  Loader2,
  Variable,
  Eye,
  Pencil,
  Trash2,
  X,
  Code,
  Mail,
  Smartphone
} from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import { TemplateSearchBar } from "@/components/templates/molecules/TemplateSearchBar";
import {
  TemplateGrid,
  TemplateEmptyState,
} from "@/components/templates/organisms/TemplateGrid";
import { EmptyState } from "@/components/ui/EmptyState";
import { cn } from "@/lib/utils";

type TabType = "whatsapp" | "email";

export default function UnifiedTemplatesPage() {
  const [activeTab, setActiveTab] = useState<TabType>("email");
  const { restaurant } = useAuthStore();
  const qc = useQueryClient();

  // WhatsApp State
  const [waSearch, setWaSearch] = useState("");
  const [waFilterStatus, setWaFilterStatus] = useState<"ALL" | "APPROVED" | "PENDING">("ALL");

  // Email State
  const [showEmailEditor, setShowEmailEditor] = useState(false);
  const [editingEmailTemplate, setEditingEmailTemplate] = useState<EmailTemplate | null>(null);
  const [showPreview, setShowPreview] = useState(false);
  const [previewHtml, setPreviewHtml] = useState("");

  // Email Form State
  const [emailName, setEmailName] = useState("");
  const [emailSubject, setEmailSubject] = useState("");
  const [emailHtml, setEmailHtml] = useState("");
  const [emailVariables, setEmailVariables] = useState<
    Array<{ key: string; type: "string" | "number"; fallback_value: string }>
  >([]);

  // Queries
  const { data: waTemplates = [], isLoading: isWaLoading } = useQuery<Template[]>({
    queryKey: ["templates"],
    queryFn: () => api.get("/templates").then((r) => r.data),
    enabled: activeTab === "whatsapp",
  });

  const { data: emailData, isLoading: isEmailLoading } = useQuery({
    queryKey: ["email-templates", restaurant?.id],
    queryFn: () =>
      api
        .get(`/email-templates?restaurant_id=${restaurant!.id}&page_size=100`)
        .then((r) => r.data),
    enabled: activeTab === "email" && !!restaurant,
  });

  const emailTemplates: EmailTemplate[] = emailData?.items ?? [];

  // Mutations
  const syncWaMutation = useMutation({
    mutationFn: () => api.post("/templates/sync"),
    onSuccess: () => {
      toast.success("Sync queued — templates will update shortly");
      setTimeout(() => qc.invalidateQueries({ queryKey: ["templates"] }), 3000);
    },
    onError: (e: unknown) => toast.error(parseApiError(e).message),
  });

  const syncEmailMutation = useMutation({
    mutationFn: () => api.post(`/email-templates/sync?restaurant_id=${restaurant?.id}`),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["email-templates", restaurant?.id] });
      toast.success(`Synced ${res.data.synced} templates from Resend`);
    },
    onError: (e: unknown) => toast.error(parseApiError(e).message),
  });

  const saveEmailMutation = useMutation({
    mutationFn: async () => {
      const payload = {
        name: emailName,
        subject: emailSubject,
        html: emailHtml,
        variables: emailVariables.filter((v) => v.key.trim()),
      };
      if (editingEmailTemplate) {
        return api.put(`/email-templates/${editingEmailTemplate.id}`, payload);
      }
      return api.post(
        `/email-templates?restaurant_id=${restaurant!.id}`,
        payload,
      );
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["email-templates", restaurant?.id] });
      toast.success(editingEmailTemplate ? "Template updated" : "Template created");
      resetEmailForm();
    },
    onError: (e: unknown) => toast.error(parseApiError(e).message),
  });

  const deleteEmailMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/email-templates/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["email-templates", restaurant?.id] });
      toast.success("Template deleted");
    },
    onError: (e: unknown) => toast.error(parseApiError(e).message),
  });

  // Helpers
  const resetEmailForm = () => {
    setEmailName("");
    setEmailSubject("");
    setEmailHtml("");
    setEmailVariables([]);
    setEditingEmailTemplate(null);
    setShowEmailEditor(false);
  };

  const openEmailEditor = (t?: EmailTemplate) => {
    if (t) {
      setEditingEmailTemplate(t);
      setEmailName(t.name);
      setEmailSubject(t.subject);
      setEmailHtml(t.html);
      setEmailVariables(
        t.variables.map((v) => ({
          key: v.key,
          type: v.type,
          fallback_value: String(v.fallback_value ?? ""),
        })),
      );
    } else {
      resetEmailForm();
    }
    setShowEmailEditor(true);
  };

  const handleEmailPreview = async (t: EmailTemplate) => {
    try {
      const { data } = await api.post(`/email-templates/${t.id}/preview`, {});
      setPreviewHtml(data.html);
      setShowPreview(true);
    } catch (e) {
      toast.error(parseApiError(e).message);
    }
  };

  const filteredWa = waTemplates.filter((t) => {
    const matchesSearch = t.name.toLowerCase().includes(waSearch.toLowerCase());
    const matchesStatus =
      waFilterStatus === "ALL" ||
      (waFilterStatus === "APPROVED" && t.status === "APPROVED") ||
      (waFilterStatus === "PENDING" && t.status !== "APPROVED");
    return matchesSearch && matchesStatus;
  });

  return (
    <div className="space-y-6 pb-20 max-w-[1600px] mx-auto p-4 md:p-8">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <div className="p-2 bg-[#eff2f0] rounded-lg">
              <LayoutTemplate className="w-6 h-6 text-[#24422e]" />
            </div>
            <h1 className="text-2xl font-black text-gray-900 tracking-tight uppercase">
              Message Templates
            </h1>
          </div>
          <p className="text-sm text-gray-500 mt-1 ml-11 font-medium">
            Manage your cross-channel message templates
          </p>
        </div>

        {/* Action Buttons */}
        <div className="flex gap-3">
          {activeTab === "whatsapp" ? (
            <button
              onClick={() => syncWaMutation.mutate()}
              disabled={syncWaMutation.isPending}
              className="inline-flex items-center gap-2 text-white text-sm font-bold px-6 py-3 rounded-xl transition hover:scale-[1.02] active:scale-[0.98] shadow-lg shadow-green-900/10 disabled:opacity-50"
              style={{ background: BRAND_GRADIENT }}
            >
              <RefreshCw className={cn("w-4 h-4", syncWaMutation.isPending && "animate-spin")} />
              Sync from Meta
            </button>
          ) : (
            <div className="flex gap-3">
               <button
                onClick={() => openEmailEditor()}
                className="inline-flex items-center gap-2 text-[#24422e] text-sm font-bold px-5 py-3 rounded-xl border-2 border-[#24422e] hover:bg-[#24422e] hover:text-white transition"
              >
                <Plus className="w-4 h-4" />
                CREATE NEW
              </button>
              <button
                onClick={() => syncEmailMutation.mutate()}
                disabled={syncEmailMutation.isPending}
                className="inline-flex items-center gap-2 text-white text-sm font-bold px-6 py-3 rounded-xl transition hover:scale-[1.02] active:scale-[0.98] shadow-lg shadow-green-900/10 disabled:opacity-50"
                style={{ background: BRAND_GRADIENT }}
              >
                <RefreshCw className={cn("w-4 h-4", syncEmailMutation.isPending && "animate-spin")} />
                Sync from Resend
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex p-1 bg-gray-100 rounded-xl w-full md:w-fit">
        <button
          onClick={() => setActiveTab("email")}
          className={cn(
            "flex items-center gap-2 px-6 py-2.5 rounded-lg text-sm font-bold transition",
            activeTab === "email" ? "bg-white text-[#24422e] shadow-sm" : "text-gray-500 hover:text-gray-700"
          )}
        >
          <Mail className="w-4 h-4" />
          Email Templates
        </button>
        <button
          onClick={() => setActiveTab("whatsapp")}
          className={cn(
            "flex items-center gap-2 px-6 py-2.5 rounded-lg text-sm font-bold transition",
            activeTab === "whatsapp" ? "bg-white text-[#24422e] shadow-sm" : "text-gray-500 hover:text-gray-700"
          )}
        >
          <Smartphone className="w-4 h-4" />
          WhatsApp Templates
        </button>
      </div>

      {/* Tab Content */}
      <div className="mt-8">
        {activeTab === "whatsapp" ? (
          <div className="space-y-6">
            <TemplateSearchBar
              search={waSearch}
              onSearchChange={setWaSearch}
              filterStatus={waFilterStatus}
              onFilterChange={setWaFilterStatus}
            />
            {isWaLoading ? (
               <div className="h-64 flex items-center justify-center">
                  <Loader2 className="w-8 h-8 animate-spin text-[#24422e]" />
               </div>
            ) : waTemplates.length === 0 ? (
              <TemplateEmptyState />
            ) : (
              <TemplateGrid templates={filteredWa} />
            )}
          </div>
        ) : (
          <div className="space-y-6">
            {isEmailLoading ? (
              <div className="h-64 flex items-center justify-center">
                <Loader2 className="w-8 h-8 animate-spin text-[#24422e]" />
              </div>
            ) : emailTemplates.length === 0 ? (
              <div className="bg-white rounded-xl border">
                <EmptyState
                  icon={Mail}
                  title="No email templates yet"
                  description="Design on Resend and click 'Sync' or create one manually."
                />
              </div>
            ) : (
              <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                {emailTemplates.map((t) => (
                  <div key={t.id} className="bg-white rounded-xl border p-5 hover:shadow-md transition group relative overflow-hidden">
                    {t.synced_from === "resend" && (
                      <div className="absolute top-0 right-0 bg-[#24422e] text-white text-[10px] font-black px-2 py-0.5 rounded-bl-lg uppercase tracking-tighter">
                        Synced
                      </div>
                    )}
                    <div className="flex items-start justify-between mb-3">
                      <div>
                        <h3 className="font-bold text-gray-900 line-clamp-1">{t.name}</h3>
                        <p className="text-[10px] text-gray-400 mt-0.5 font-bold uppercase tracking-wider">
                          v{t.version} &middot; Updated {formatDistanceToNow(new Date(t.updated_at.endsWith("Z") ? t.updated_at : t.updated_at + "Z"), { addSuffix: true })}
                        </p>
                      </div>
                      <div className="flex gap-1">
                        <button onClick={() => handleEmailPreview(t)} className="p-1.5 rounded-lg hover:bg-blue-50 text-blue-500 transition" title="Preview"><Eye className="w-4 h-4"/></button>
                        <button onClick={() => openEmailEditor(t)} className="p-1.5 rounded-lg hover:bg-amber-50 text-amber-600 transition" title="Edit"><Pencil className="w-4 h-4"/></button>
                        <button onClick={() => { if (confirm("Delete template?")) deleteEmailMutation.mutate(t.id); }} className="p-1.5 rounded-lg hover:bg-red-50 text-red-500 transition" title="Delete"><Trash2 className="w-4 h-4"/></button>
                      </div>
                    </div>
                    <p className="text-xs text-gray-500 mb-2 font-medium line-clamp-1">
                      <span className="text-gray-400 font-bold uppercase text-[10px] mr-1">Subject:</span> {t.subject}
                    </p>
                    {t.variables.length > 0 && (
                      <div className="flex flex-wrap gap-1">
                        {t.variables.map((v) => (
                          <span key={v.key} className="inline-flex items-center gap-0.5 text-[10px] bg-violet-50 text-violet-600 px-2 py-0.5 rounded-full font-black uppercase">
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
          </div>
        )}
      </div>

      {/* Email Editor Modal */}
      {showEmailEditor && (
        <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4 backdrop-blur-sm">
          <div className="bg-white rounded-2xl max-w-6xl w-full max-h-[90vh] overflow-hidden shadow-2xl flex flex-col">
            <div className="px-6 py-4 border-b flex items-center justify-between sticky top-0 bg-white z-10 rounded-t-2xl">
              <h3 className="text-lg font-black text-gray-900 uppercase">
                {editingEmailTemplate ? "Edit Email Template" : "New Email Template"}
              </h3>
              <button onClick={resetEmailForm} className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 transition">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto">
              <div className="grid grid-cols-1 lg:grid-cols-2 divide-x h-full">
                <div className="p-6 space-y-5">
                  <div>
                    <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest block mb-1">Template Name *</label>
                    <input type="text" value={emailName} onChange={(e) => setEmailName(e.target.value)} className="w-full px-3 py-2.5 border rounded-xl text-sm font-bold focus:ring-2 focus:ring-[#24422e]/20" />
                  </div>
                  <div>
                    <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest block mb-1">Subject Line *</label>
                    <input type="text" value={emailSubject} onChange={(e) => setEmailSubject(e.target.value)} className="w-full px-3 py-2.5 border rounded-xl text-sm font-bold focus:ring-2 focus:ring-[#24422e]/20" />
                  </div>
                  <div>
                    <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest block mb-1 flex items-center gap-1"><Code className="w-3 h-3"/> HTML Body *</label>
                    <textarea value={emailHtml} onChange={(e) => setEmailHtml(e.target.value)} rows={10} className="w-full px-3 py-2.5 border rounded-xl text-sm font-mono focus:ring-2 focus:ring-[#24422e]/20 resize-none h-64" />
                  </div>

                   {/* Template Variables Section */}
                   <div>
                    <div className="flex items-center justify-between mb-2">
                       <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest block flex items-center gap-1">Template Variables</label>
                       <button onClick={() => setEmailVariables([...emailVariables, { key: "", type: "string", fallback_value: "" }])} className="text-xs text-[#24422e] font-bold hover:underline">+ Add Variable</button>
                    </div>
                    <div className="space-y-2">
                       {emailVariables.map((v, i) => (
                         <div key={i} className="flex gap-2 items-center">
                            <input type="text" value={v.key} onChange={(e) => { const copy = [...emailVariables]; copy[i].key = e.target.value; setEmailVariables(copy); }} placeholder="e.g. name" className="flex-1 px-3 py-1.5 border rounded-lg text-xs font-bold" />
                            <input type="text" value={v.fallback_value} onChange={(e) => { const copy = [...emailVariables]; copy[i].fallback_value = e.target.value; setEmailVariables(copy); }} placeholder="Fallback" className="flex-1 px-3 py-1.5 border rounded-lg text-xs" />
                            <button onClick={() => setEmailVariables(emailVariables.filter((_, j) => j !== i))} className="p-1 text-red-400 hover:text-red-600 transition"><X className="w-4 h-4"/></button>
                         </div>
                       ))}
                    </div>
                   </div>
                </div>
                <div className="bg-gray-50 p-6 flex flex-col min-h-[400px]">
                  <span className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-4">Live Preview</span>
                  <div className="bg-white rounded-xl shadow-sm border flex-1 overflow-hidden">
                    <iframe title="Preview" srcDoc={emailHtml} className="w-full h-full border-0" />
                  </div>
                </div>
              </div>
            </div>

            <div className="px-6 py-4 border-t flex justify-end gap-3 sticky bottom-0 bg-white rounded-b-2xl">
              <button onClick={resetEmailForm} className="px-5 py-2.5 text-sm font-bold text-gray-500 hover:text-gray-900 transition">CANCEL</button>
              <button
                onClick={() => saveEmailMutation.mutate()}
                disabled={saveEmailMutation.isPending || !emailName || !emailSubject || !emailHtml}
                className="inline-flex items-center gap-2 text-white text-sm font-black px-8 py-2.5 rounded-xl transition hover:scale-[1.02] active:scale-[0.98] disabled:opacity-40 shadow-lg shadow-green-900/20"
                style={{ background: BRAND_GRADIENT }}
              >
                {saveEmailMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
                {editingEmailTemplate ? "SAVE CHANGES" : "CREATE TEMPLATE"}
              </button>
            </div>
          </div>
        </div>
      )}

       {/* Preview Modal */}
       {showPreview && (
        <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4 backdrop-blur-sm">
          <div className="bg-white rounded-3xl max-w-2xl w-full max-h-[85vh] overflow-hidden shadow-2xl flex flex-col border border-white/20">
            <div className="px-6 py-4 border-b flex items-center justify-between bg-white/80 sticky top-0">
              <h3 className="text-sm font-black text-[#24422e] uppercase tracking-tighter">Template Preview</h3>
              <button onClick={() => setShowPreview(false)} className="p-1.5 rounded-full hover:bg-gray-100 text-gray-400 transition"><X className="w-5 h-5"/></button>
            </div>
            <div className="flex-1 overflow-hidden">
              <iframe title="Template Preview" srcDoc={previewHtml} className="w-full h-full bg-white border-0" />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
