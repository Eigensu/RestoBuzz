"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { toast } from "sonner";
import { parseApiError } from "@/lib/errors";
import type { EmailTemplate, PreflightResult } from "@/types";
import { useDropzone } from "react-dropzone";
import {
  ChevronLeft,
  ChevronRight,
  Mail,
  Upload,
  CheckCircle2,
  FileText,
  Eye,
  Loader2,
  Users,
  ArrowLeft,
  Download,
} from "lucide-react";
import Link from "next/link";
import { BRAND_GRADIENT, GREEN } from "@/lib/brand";

const STEPS = ["Template", "Contacts", "Review"];

export default function NewEmailCampaignPage() {
  const { restaurant } = useAuthStore();
  const router = useRouter();
  const [step, setStep] = useState(0);

  // Step 0 - Template
  const [selectedTemplate, setSelectedTemplate] =
    useState<EmailTemplate | null>(null);
  const [subject, setSubject] = useState("");
  const [previewHtml, setPreviewHtml] = useState<string | null>(null);
  const [showPreview, setShowPreview] = useState(false);

  // Step 1 - Contacts
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [loadingMembers, setLoadingMembers] = useState(false);
  const [preflight, setPreflight] = useState<PreflightResult | null>(null);

  // Step 2 - Review
  const [campaignName, setCampaignName] = useState("");

  // Fetch templates for this restaurant
  const { data: templatesData, isLoading: loadingTemplates } = useQuery<{ items: EmailTemplate[] }>({
    queryKey: ["email-templates", restaurant?.id],
    queryFn: () =>
      api
        .get(`/email-templates?restaurant_id=${restaurant!.id}&page_size=100`)
        .then((r) => r.data),
    enabled: !!restaurant && step === 0,
  });
  const templates = templatesData?.items ?? [];

  // File upload dropzone
  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept: {
      "text/csv": [".csv"],
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [
        ".xlsx",
      ],
    },
    maxFiles: 1,
    onDrop: (files) => setFile(files[0] ?? null),
  });

  // Upload contacts
  const uploadFile = async () => {
    if (!file) return;
    setUploading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const { data } = await api.post("/contacts/upload", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setPreflight(data);
      setStep(2);
    } catch (e) {
      toast.error(parseApiError(e).message);
    } finally {
      setUploading(false);
    }
  };

  // Use members as contacts
  const handleUseMembersAsContacts = async (type: "all" | "nfc" | "ecard") => {
    setLoadingMembers(true);
    try {
      const params = new URLSearchParams({ restaurant_id: restaurant!.id });
      if (type !== "all") params.set("type", type);
      const { data } = await api.post(`/members/as-contacts?${params}`);
      if (data.valid_count === 0) {
        toast.error("No active members found.");
        return;
      }
      setPreflight(data);
      setStep(2);
    } catch (e) {
      toast.error(parseApiError(e).message);
    } finally {
      setLoadingMembers(false);
    }
  };

  // Preview template
  const handlePreview = async (templateId: string) => {
    try {
      const { data } = await api.post(
        `/email-templates/${templateId}/preview`,
        {},
      );
      setPreviewHtml(data.html);
    } catch (e) {
      toast.error(parseApiError(e).message);
    }
  };

  const downloadSampleCSV = () => {
    const csvContent = "email,name,phone,custom_field1\ntest@example.com,John Doe,+1234567890,Value1";
    const blob = new Blob([csvContent], { type: "text/csv" });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "dishpatch_sample_contacts.csv";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
  };

  // Create campaign
  const createMutation = useMutation({
    mutationFn: () =>
      api.post("/email-campaigns", {
        restaurant_id: restaurant?.id ?? "",
        name: campaignName,
        template_id: selectedTemplate?.id ?? "",
        subject: subject || selectedTemplate?.subject || "",
        contact_file_ref: preflight?.file_ref,
      }),
    onSuccess: (res) => {
      toast.success("Email campaign created!");
      router.push(`/campaigns/email/${res.data.id}`);
    },
    onError: (e: unknown) => toast.error(parseApiError(e).message),
  });

  let canNext = false;
  if (step === 0) canNext = !!selectedTemplate;
  else if (step === 1) canNext = !!preflight;
  else canNext = !!campaignName;

  if (!restaurant) return null;

  return (
    <div className="max-w-[1600px] mx-auto p-4 md:p-10 pb-20 space-y-6">
      {/* Header */}
      <div>
        <Link
          href="/campaigns/email"
          className="inline-flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-800 transition mb-3"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Email Campaigns
        </Link>
        <div className="flex items-center gap-3">
          <div className="p-2 bg-[#eff2f0] rounded-lg">
            <Mail className="w-6 h-6 text-[#24422e]" />
          </div>
          <h1 className="text-2xl font-black text-gray-900 tracking-tight">
            New Email Campaign
          </h1>
        </div>
      </div>

      {/* Step Indicator */}
      <div className="flex items-center gap-2">
        {STEPS.map((s, i) => (
          <div key={s} className="flex items-center gap-2">
            <div
              className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold transition ${
                i <= step ? "text-white shadow-md" : "bg-gray-100 text-gray-400"
              }`}
              style={i <= step ? { background: BRAND_GRADIENT } : {}}
            >
              {i < step ? <CheckCircle2 className="w-4 h-4" /> : i + 1}
            </div>
            <span
              className={`text-xs font-medium ${i <= step ? "text-gray-900" : "text-gray-400"}`}
            >
              {s}
            </span>
            {i < STEPS.length - 1 && (
              <div
                className={`w-12 h-0.5 mx-1 rounded ${i < step ? "bg-[#24422e]" : "bg-gray-200"}`}
              />
            )}
          </div>
        ))}
      </div>

      {/* Step Content */}
      <div className="bg-white rounded-xl border p-6">
        {/* STEP 0: Select Template */}
        {step === 0 && (
          <div className="space-y-4">
            <h2 className="text-lg font-bold text-gray-900">
              Select Email Template
            </h2>
            <p className="text-sm text-gray-500">
              Choose a template you have created in the Email Templates section.
            </p>

            {loadingTemplates ? (
              <div className="text-center py-12 text-gray-400 text-sm">
                Loading templates...
              </div>
            ) : templates.length === 0 ? (
              <div className="text-center py-12">
                <FileText className="w-10 h-10 text-gray-300 mx-auto mb-3" />
                <p className="text-sm text-gray-500 mb-4">
                  No email templates found.
                </p>
                <Link
                  href="/campaigns/email/templates"
                  className="text-sm font-bold text-white px-4 py-2 rounded-lg"
                  style={{ background: BRAND_GRADIENT }}
                >
                  Create Template
                </Link>
              </div>
            ) : (
              <div className="grid grid-cols-1 lg:grid-cols-[380px,1fr] gap-8 items-start">
                <div className="space-y-3 max-h-[600px] overflow-y-auto pr-2 custom-scrollbar">
                  {templates.map((t) => (
                    <button
                      key={t.id}
                      onClick={() => {
                        setSelectedTemplate(t);
                        setSubject(t.subject);
                        handlePreview(t.id);
                      }}
                      className={`w-full text-left p-4 rounded-xl border-2 transition-all duration-200 block ${
                        selectedTemplate?.id === t.id
                          ? "border-[#24422e] bg-[#24422e]/5 shadow-sm translate-x-1"
                          : "border-gray-100 hover:border-gray-200 bg-white hover:bg-gray-50"
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <div className="min-w-0 pr-4">
                          <p className="font-bold text-gray-900 truncate">{t.name}</p>
                          <p className="text-[10px] uppercase font-black text-gray-400 mt-1 tracking-wider">
                            Version {t.version}
                          </p>
                        </div>
                        <div className="flex-shrink-0">
                          {selectedTemplate?.id === t.id && (
                            <div className="p-1 bg-[#24422e] rounded-full text-white">
                              <CheckCircle2 className="w-3.5 h-3.5" />
                            </div>
                          )}
                        </div>
                      </div>
                    </button>
                  ))}
                </div>

                <div className="border rounded-[2rem] bg-white flex flex-col overflow-hidden min-h-[600px] shadow-xl shadow-gray-200/50 border-gray-100 sticky top-4">
                  <div className="px-6 py-4 bg-gray-50/50 border-b flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <div className="w-2 h-2 rounded-full bg-red-400" />
                      <div className="w-2 h-2 rounded-full bg-amber-400" />
                      <div className="w-2 h-2 rounded-full bg-emerald-400" />
                      <span className="ml-4 text-[10px] font-bold text-gray-400 uppercase tracking-widest flex items-center gap-1.5">
                        <Eye className="w-3 h-3" /> Live Render Engine
                      </span>
                    </div>
                    {selectedTemplate && (
                      <span className="text-[11px] font-bold text-[#24422e] bg-[#24422e]/5 px-3 py-1 rounded-full">
                        {selectedTemplate.name}
                      </span>
                    )}
                  </div>
                  <div className="flex-1 overflow-y-auto p-8 flex items-start justify-center bg-gray-50/30">
                    {(() => {
                      if (!selectedTemplate) {
                        return (
                          <div className="text-center text-gray-400 my-auto">
                            <Eye className="w-12 h-12 opacity-10 mx-auto mb-4" />
                            <p className="text-sm font-medium">Select a template to initialize preview</p>
                          </div>
                        );
                      }
                      if (!previewHtml) {
                        return (
                          <div className="flex flex-col items-center gap-3 my-auto">
                            <Loader2 className="w-8 h-8 animate-spin text-[#24422e]" />
                            <span className="text-xs font-bold text-gray-400 uppercase tracking-tighter">Compiling Template...</span>
                          </div>
                        );
                      }
                      return (
                        <div className="bg-white rounded-xl shadow-2xl border border-gray-100 w-full max-w-[800px] min-h-full overflow-hidden mx-auto">
                          <div
                            className="p-8"
                            dangerouslySetInnerHTML={{ __html: previewHtml }}
                          />
                        </div>
                      );
                    })()}
                  </div>
                </div>
              </div>
            )}

            {selectedTemplate && (
              <div className="space-y-3 pt-4 border-t">
                <div>
                  <label htmlFor="subjectLine" className="text-xs font-semibold text-gray-600 block mb-1">
                    Subject Line (editable)
                  </label>
                  <input
                    id="subjectLine"
                    type="text"
                    value={subject}
                    onChange={(e) => setSubject(e.target.value)}
                    className="w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-[#24422e]/20 focus:border-[#24422e]"
                    placeholder="Enter email subject"
                  />
                </div>
              </div>
            )}

            {/* Preview Modal */}
            {showPreview && previewHtml && (
              <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
                <div className="bg-white rounded-2xl max-w-2xl w-full max-h-[80vh] overflow-hidden shadow-2xl">
                  <div className="px-5 py-3 border-b flex items-center justify-between">
                    <h3 className="text-sm font-bold text-gray-900">
                      Template Preview
                    </h3>
                    <button
                      onClick={() => setShowPreview(false)}
                      className="text-gray-400 hover:text-gray-600 text-sm"
                    >
                      Close
                    </button>
                  </div>
                  <div className="max-h-[70vh]">
                    <iframe
                      title="Template Preview"
                      srcDoc={previewHtml}
                      sandbox=""
                      className="block h-[70vh] w-full border-0 bg-white"
                    />
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* STEP 1: Upload Contacts */}
        {step === 1 && (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-lg font-bold text-gray-900">Add Contacts</h2>
                <p className="text-sm text-gray-500">
                  Upload a file with{" "}
                  <code className="bg-gray-100 px-1.5 py-0.5 rounded text-xs font-mono">
                    email
                  </code>{" "}
                  column, or use your existing members.
                </p>
              </div>
              <a
                href={`${process.env.NEXT_PUBLIC_API_URL}/contacts/template`}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 text-xs font-bold text-[#24422e] hover:underline bg-[#24422e]/5 px-3 py-1.5 rounded-lg"
              >
                <Download className="w-3.5 h-3.5" />
                SAMPLE FILE
              </a>
            </div>

            {!preflight && (
              <>
                {/* File Upload */}
                <div
                  {...getRootProps()}
                  className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition ${
                    isDragActive
                      ? "border-[#24422e] bg-[#24422e]/5"
                      : "border-gray-200 hover:border-gray-300"
                  }`}
                >
                  <input {...getInputProps()} />
                  <Upload className="w-8 h-8 text-gray-300 mx-auto mb-3" />
                  {file ? (
                    <p className="text-sm font-medium text-gray-700">
                      {file.name}
                    </p>
                  ) : (
                    <p className="text-sm text-gray-500">
                      Drop a CSV or Excel file here, or click to browse
                    </p>
                  )}
                </div>

                {file && (
                  <button
                    onClick={uploadFile}
                    disabled={uploading}
                    className="w-full py-2.5 rounded-xl text-white text-sm font-bold transition disabled:opacity-50"
                    style={{ background: BRAND_GRADIENT }}
                  >
                    {uploading ? (
                      <span className="inline-flex items-center gap-2">
                        <Loader2 className="w-4 h-4 animate-spin" />{" "}
                        Uploading...
                      </span>
                    ) : (
                      "Upload & Validate"
                    )}
                  </button>
                )}

                <div className="relative py-3">
                  <div className="absolute inset-0 flex items-center">
                    <div className="w-full border-t" />
                  </div>
                  <div className="relative flex justify-center">
                    <span className="bg-white px-3 text-xs text-gray-400">
                      or use members
                    </span>
                  </div>
                </div>

                {/* Use Members */}
                <div className="grid grid-cols-3 gap-3">
                  {["all", "nfc", "ecard"].map((type) => (
                    <button
                      key={type}
                      onClick={() =>
                        handleUseMembersAsContacts(type as "all" | "nfc" | "ecard")
                      }
                      disabled={loadingMembers}
                      className="flex items-center justify-center gap-2 py-3 rounded-xl border hover:bg-gray-50 transition text-sm font-medium text-gray-700 disabled:opacity-50"
                    >
                      <Users className="w-4 h-4" />
                      {type === "all" ? "All Members" : type.toUpperCase()}
                    </button>
                  ))}
                </div>
              </>
            )}

            {preflight && (
              <div className="space-y-3">
                <div className="grid grid-cols-3 gap-3">
                  <div className="bg-emerald-50 rounded-xl p-4 text-center">
                    <p className="text-2xl font-black text-emerald-700">
                      {preflight.valid_count}
                    </p>
                    <p className="text-xs text-emerald-600 font-medium">
                      Valid
                    </p>
                  </div>
                  <div className="bg-amber-50 rounded-xl p-4 text-center">
                    <p className="text-2xl font-black text-amber-700">
                      {preflight.invalid_count}
                    </p>
                    <p className="text-xs text-amber-600 font-medium">
                      Invalid
                    </p>
                  </div>
                  <div className="bg-gray-50 rounded-xl p-4 text-center">
                    <p className="text-2xl font-black text-gray-700">
                      {preflight.suppressed_count}
                    </p>
                    <p className="text-xs text-gray-500 font-medium">
                      Suppressed
                    </p>
                  </div>
                </div>
                <button
                  onClick={() => setPreflight(null)}
                  className="text-xs text-gray-500 hover:text-gray-700 underline"
                >
                  Re-upload contacts
                </button>
              </div>
            )}
          </div>
        )}

        {/* STEP 2: Review & Launch */}
        {step === 2 && (
          <div className="space-y-5">
            <h2 className="text-lg font-bold text-gray-900">Review & Launch</h2>

            <div>
              <label htmlFor="campaignName" className="text-xs font-semibold text-gray-600 block mb-1">
                Campaign Name *
              </label>
              <input
                id="campaignName"
                type="text"
                value={campaignName}
                onChange={(e) => setCampaignName(e.target.value)}
                placeholder="e.g. April Newsletter"
                className="w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-[#24422e]/20 focus:border-[#24422e]"
              />
            </div>

            <div className="bg-gray-50 rounded-xl p-5 space-y-3">
              <div className="flex justify-between text-sm">
                <span className="text-gray-500">Template</span>
                <span className="font-medium text-gray-900">
                  {selectedTemplate?.name}
                </span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-gray-500">Subject</span>
                <span className="font-medium text-gray-900">{subject}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-gray-500">Recipients</span>
                <span className="font-bold text-emerald-600">
                  {preflight?.valid_count ?? 0}
                </span>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Navigation */}
      <div className="flex justify-between">
        <button
          onClick={() => setStep((s) => s - 1)}
          disabled={step === 0}
          className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-[#24422e] disabled:opacity-30 transition"
        >
          <ChevronLeft className="w-4 h-4" /> Back
        </button>
        {step < 2 ? (
          <button
            onClick={() => setStep((s) => s + 1)}
            disabled={!canNext}
            className="inline-flex items-center gap-1.5 text-white text-sm font-bold px-5 py-2.5 rounded-xl transition disabled:opacity-40 hover:scale-[1.02] active:scale-[0.98]"
            style={{ background: BRAND_GRADIENT }}
          >
            Next <ChevronRight className="w-4 h-4" />
          </button>
        ) : (
          <button
            onClick={() => createMutation.mutate()}
            disabled={createMutation.isPending || !campaignName}
            className="inline-flex items-center gap-1.5 text-white text-sm font-bold px-6 py-2.5 rounded-xl transition disabled:opacity-40 hover:scale-[1.02] active:scale-[0.98]"
            style={{ background: BRAND_GRADIENT }}
          >
            {createMutation.isPending ? (
              <span className="inline-flex items-center gap-2">
                <Loader2 className="w-4 h-4 animate-spin" /> Creating...
              </span>
            ) : (
              "Launch Campaign"
            )}
          </button>
        )}
      </div>
    </div>
  );
}
