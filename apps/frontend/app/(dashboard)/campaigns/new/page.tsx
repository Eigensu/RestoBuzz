"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { toast } from "sonner";
import type { PreflightResult, Template } from "@/types";
import { useDropzone } from "react-dropzone";
import { Upload, CheckCircle, XCircle, AlertCircle, ChevronRight, ChevronLeft } from "lucide-react";

const STEPS = ["Upload", "Preflight", "Template", "Schedule", "Review"];

export default function NewCampaignPage() {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [file, setFile] = useState<File | null>(null);
  const [preflight, setPreflight] = useState<PreflightResult | null>(null);
  const [selectedTemplate, setSelectedTemplate] = useState<Template | null>(null);
  const [variables, setVariables] = useState<Record<string, string>>({});
  const [mediaUrl, setMediaUrl] = useState("");
  const [priority, setPriority] = useState<"MARKETING" | "UTILITY">("MARKETING");
  const [includeUnsub, setIncludeUnsub] = useState(true);
  const [campaignName, setCampaignName] = useState("");
  const [uploading, setUploading] = useState(false);

  const { data: templates } = useQuery<Template[]>({
    queryKey: ["templates"],
    queryFn: () => api.get("/templates").then((r) => r.data),
    enabled: step === 2,
  });

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept: { "text/csv": [".csv"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"] },
    maxFiles: 1,
    onDrop: (files) => setFile(files[0] ?? null),
  });

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
      setStep(1);
    } catch {
      toast.error("Failed to parse file");
    } finally {
      setUploading(false);
    }
  };

  const createMutation = useMutation({
    mutationFn: () =>
      api.post("/campaigns", {
        name: campaignName,
        template_id: selectedTemplate?.name ?? "",
        template_name: selectedTemplate?.name ?? "",
        template_variables: variables,
        media_url: mediaUrl || null,
        priority,
        include_unsubscribe: includeUnsub,
        contact_file_ref: preflight?.file_ref,
      }),
    onSuccess: (res) => {
      toast.success("Campaign created");
      router.push(`/campaigns/${res.data.id}`);
    },
    onError: () => toast.error("Failed to create campaign"),
  });

  // Extract body variables from template
  const bodyVars = selectedTemplate?.components
    .find((c) => c.type === "BODY")
    ?.text?.match(/\{\{(\d+)\}\}/g)
    ?.map((v) => v.replace(/[{}]/g, "")) ?? [];

  return (
    <div className="max-w-2xl space-y-6">
      <h1 className="text-xl font-semibold">New Campaign</h1>

      {/* Step indicator */}
      <div className="flex items-center gap-1">
        {STEPS.map((s, i) => (
          <div key={s} className="flex items-center gap-1">
            <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-medium transition ${
              i < step ? "bg-green-500 text-white" : i === step ? "bg-green-100 text-green-700 border-2 border-green-500" : "bg-gray-100 text-gray-400"
            }`}>
              {i < step ? <CheckCircle className="w-4 h-4" /> : i + 1}
            </div>
            <span className={`text-xs hidden sm:block ${i === step ? "text-green-700 font-medium" : "text-gray-400"}`}>{s}</span>
            {i < STEPS.length - 1 && <div className="w-6 h-px bg-gray-200 mx-1" />}
          </div>
        ))}
      </div>

      <div className="bg-white rounded-xl border p-6">
        {/* Step 0: Upload */}
        {step === 0 && (
          <div className="space-y-4">
            <h2 className="font-medium">Upload Contacts</h2>
            <div
              {...getRootProps()}
              className={`border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition ${
                isDragActive ? "border-green-400 bg-green-50" : "border-gray-200 hover:border-gray-300"
              }`}
            >
              <input {...getInputProps()} />
              <Upload className="w-8 h-8 text-gray-300 mx-auto mb-3" />
              <p className="text-sm text-gray-500">Drop a CSV or XLSX file here, or click to browse</p>
              <p className="text-xs text-gray-400 mt-1">Max 50MB · First row must be headers</p>
            </div>
            {file && (
              <div className="flex items-center gap-2 text-sm bg-green-50 text-green-700 px-3 py-2 rounded-lg">
                <CheckCircle className="w-4 h-4" />
                {file.name} ({(file.size / 1024).toFixed(1)} KB)
              </div>
            )}
            <button
              onClick={uploadFile}
              disabled={!file || uploading}
              className="w-full bg-green-500 hover:bg-green-600 text-white font-medium py-2 rounded-lg transition disabled:opacity-50"
            >
              {uploading ? "Parsing..." : "Parse & Continue"}
            </button>
          </div>
        )}

        {/* Step 1: Preflight */}
        {step === 1 && preflight && (
          <div className="space-y-4">
            <h2 className="font-medium">Pre-flight Check</h2>
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-green-50 rounded-lg p-3 text-center">
                <p className="text-2xl font-bold text-green-600">{preflight.valid_count}</p>
                <p className="text-xs text-green-600">Valid</p>
              </div>
              <div className="bg-red-50 rounded-lg p-3 text-center">
                <p className="text-2xl font-bold text-red-500">{preflight.invalid_count}</p>
                <p className="text-xs text-red-500">Invalid</p>
              </div>
              <div className="bg-yellow-50 rounded-lg p-3 text-center">
                <p className="text-2xl font-bold text-yellow-600">{preflight.duplicate_count}</p>
                <p className="text-xs text-yellow-600">Duplicates</p>
              </div>
              <div className="bg-gray-50 rounded-lg p-3 text-center">
                <p className="text-2xl font-bold text-gray-500">{preflight.suppressed_count}</p>
                <p className="text-xs text-gray-500">Suppressed</p>
              </div>
            </div>
            {preflight.invalid_rows.length > 0 && (
              <div className="border rounded-lg overflow-hidden">
                <div className="bg-red-50 px-3 py-2 text-xs font-medium text-red-600 flex items-center gap-1">
                  <XCircle className="w-3.5 h-3.5" /> Invalid rows
                </div>
                <div className="max-h-40 overflow-y-auto divide-y">
                  {preflight.invalid_rows.slice(0, 20).map((r) => (
                    <div key={r.row_number} className="px-3 py-1.5 text-xs flex gap-3">
                      <span className="text-gray-400">Row {r.row_number}</span>
                      <span className="font-mono">{r.raw_phone || "(empty)"}</span>
                      <span className="text-red-500">{r.reason}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {preflight.valid_count === 0 && (
              <div className="flex items-center gap-2 text-sm text-red-500 bg-red-50 px-3 py-2 rounded-lg">
                <AlertCircle className="w-4 h-4" /> No valid contacts found. Please fix your file.
              </div>
            )}
          </div>
        )}

        {/* Step 2: Template */}
        {step === 2 && (
          <div className="space-y-4">
            <h2 className="font-medium">Select Template</h2>
            <div className="grid gap-2 max-h-60 overflow-y-auto">
              {(templates ?? []).map((t) => (
                <button
                  key={t.name}
                  onClick={() => { setSelectedTemplate(t); setVariables({}); }}
                  className={`text-left border rounded-lg px-4 py-3 transition ${
                    selectedTemplate?.name === t.name ? "border-green-500 bg-green-50" : "hover:border-gray-300"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium">{t.name}</span>
                    <span className={`text-xs px-2 py-0.5 rounded-full ${t.category === "UTILITY" ? "bg-blue-50 text-blue-600" : "bg-purple-50 text-purple-600"}`}>
                      {t.category}
                    </span>
                  </div>
                  <p className="text-xs text-gray-400 mt-0.5">{t.language} · {t.status}</p>
                </button>
              ))}
            </div>
            {selectedTemplate && bodyVars.length > 0 && (
              <div className="space-y-2">
                <p className="text-sm font-medium">Template Variables</p>
                {bodyVars.map((v) => (
                  <div key={v}>
                    <label className="text-xs text-gray-500 mb-0.5 block">{`{{${v}}}`}</label>
                    <input
                      value={variables[v] ?? ""}
                      onChange={(e) => setVariables((prev) => ({ ...prev, [v]: e.target.value }))}
                      className="w-full border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
                      placeholder={`Value for {{${v}}}`}
                    />
                  </div>
                ))}
              </div>
            )}
            {selectedTemplate && (
              <div>
                <label className="text-xs text-gray-500 mb-0.5 block">Media URL (optional)</label>
                <input
                  value={mediaUrl}
                  onChange={(e) => setMediaUrl(e.target.value)}
                  className="w-full border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
                  placeholder="https://res.cloudinary.com/..."
                />
              </div>
            )}
          </div>
        )}

        {/* Step 3: Schedule */}
        {step === 3 && (
          <div className="space-y-4">
            <h2 className="font-medium">Campaign Settings</h2>
            <div>
              <label className="text-sm font-medium mb-1 block">Campaign Name</label>
              <input
                value={campaignName}
                onChange={(e) => setCampaignName(e.target.value)}
                className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
                placeholder="e.g. Summer Promo 2026"
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-1 block">Priority</label>
              <div className="flex gap-2">
                {(["MARKETING", "UTILITY"] as const).map((p) => (
                  <button
                    key={p}
                    onClick={() => setPriority(p)}
                    className={`flex-1 py-2 rounded-lg text-sm font-medium border transition ${
                      priority === p ? "border-green-500 bg-green-50 text-green-700" : "border-gray-200 text-gray-500 hover:border-gray-300"
                    }`}
                  >
                    {p}
                  </button>
                ))}
              </div>
            </div>
            {priority === "MARKETING" && (
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={includeUnsub}
                  onChange={(e) => setIncludeUnsub(e.target.checked)}
                  className="w-4 h-4 accent-green-500"
                />
                <span className="text-sm">Include unsubscribe footer</span>
              </label>
            )}
          </div>
        )}

        {/* Step 4: Review */}
        {step === 4 && (
          <div className="space-y-4">
            <h2 className="font-medium">Review & Launch</h2>
            <div className="space-y-2 text-sm">
              {[
                ["Campaign Name", campaignName],
                ["Template", selectedTemplate?.name],
                ["Priority", priority],
                ["Recipients", `${preflight?.valid_count} contacts`],
                ["Unsubscribe Footer", includeUnsub ? "Yes" : "No"],
              ].map(([label, value]) => (
                <div key={label} className="flex justify-between py-2 border-b last:border-0">
                  <span className="text-gray-500">{label}</span>
                  <span className="font-medium">{value}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Navigation */}
        <div className="flex justify-between mt-6">
          <button
            onClick={() => setStep((s) => s - 1)}
            disabled={step === 0}
            className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-700 disabled:opacity-30 transition"
          >
            <ChevronLeft className="w-4 h-4" /> Back
          </button>

          {step < 4 ? (
            <button
              onClick={() => setStep((s) => s + 1)}
              disabled={
                (step === 0 && !preflight) ||
                (step === 1 && (preflight?.valid_count ?? 0) === 0) ||
                (step === 2 && !selectedTemplate) ||
                (step === 3 && !campaignName)
              }
              className="flex items-center gap-1.5 bg-green-500 hover:bg-green-600 text-white text-sm font-medium px-4 py-2 rounded-lg transition disabled:opacity-50"
            >
              Next <ChevronRight className="w-4 h-4" />
            </button>
          ) : (
            <button
              onClick={() => createMutation.mutate()}
              disabled={createMutation.isPending}
              className="bg-green-500 hover:bg-green-600 text-white text-sm font-medium px-6 py-2 rounded-lg transition disabled:opacity-50"
            >
              {createMutation.isPending ? "Creating..." : "Launch Campaign"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
