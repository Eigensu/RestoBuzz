"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { toast } from "sonner";
import { parseApiError } from "@/lib/errors";
import type { PreflightResult, Template } from "@/types";
import { useDropzone } from "react-dropzone";
import {
  Upload,
  CheckCircle,
  XCircle,
  AlertCircle,
  ChevronRight,
  ChevronLeft,
  RefreshCw,
  ImageIcon,
  X,
  FileSpreadsheet,
  Smartphone,
  ExternalLink,
} from "lucide-react";
import { cn } from "@/lib/utils";

/* ─── Shared constants ───────────────────────────────────── */
const BRAND_GRADIENT = "linear-gradient(135deg, #24422e, #3a6b47)";
const INPUT_CLS =
  "w-full border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#24422e]/30";

/* ─── Stat card ──────────────────────────────────────────── */
function StatCard({
  value,
  label,
  colorCls,
  bgCls,
}: {
  readonly value: number;
  readonly label: string;
  readonly colorCls: string;
  readonly bgCls: string;
}) {
  return (
    <div className={cn("rounded-lg p-3 text-center", bgCls)}>
      <p className={cn("text-2xl font-bold", colorCls)}>{value}</p>
      <p className={cn("text-xs", colorCls)}>{label}</p>
    </div>
  );
}

interface SavedFile {
  id: string;
  filename: string;
  valid_count: number;
  invalid_count: number;
  file_ref: string;
  uploaded_at: string;
}

/* ─── Step config ────────────────────────────────────────── */
const STEPS = ["Template", "Upload", "Preflight", "Schedule & Review"];

/* ─── Gradient button helper ─────────────────────────────── */
const GradBtn = ({
  children,
  onClick,
  disabled,
  className = "",
  type = "button",
}: {
  readonly children: React.ReactNode;
  readonly onClick?: () => void;
  readonly disabled?: boolean;
  readonly className?: string;
  readonly type?: "button" | "submit";
}) => (
  <button
    type={type}
    onClick={onClick}
    disabled={disabled}
    className={cn(
      "flex items-center justify-center gap-1.5 text-white font-medium rounded-lg transition disabled:opacity-50 hover:opacity-90",
      className,
    )}
    style={{ background: BRAND_GRADIENT }}
  >
    {children}
  </button>
);

/* ─── Template preview ───────────────────────────────────── */
function TemplatePreview({
  template,
  variables,
  mediaUrl,
}: {
  readonly template: Template | null;
  readonly variables: Record<string, string>;
  readonly mediaUrl: string;
}) {
  if (!template) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-gray-400 gap-3">
        <Smartphone className="w-10 h-10 opacity-30" />
        <p className="text-sm">Select a template to preview</p>
      </div>
    );
  }

  const header = template.components.find((c) => c.type === "HEADER");
  const body = template.components.find((c) => c.type === "BODY");
  const footer = template.components.find((c) => c.type === "FOOTER");
  const buttons = template.components.find((c) => c.type === "BUTTONS") as
    | { type: string; buttons?: { type: string; text: string }[] }
    | undefined;

  const resolveBody = (text: string) =>
    text.replaceAll(/\{\{(\d+)\}\}/g, (_, k) => variables[k] ?? `{{${k}}}`);

  return (
    <div className="flex flex-col items-center justify-center h-full px-4">
      <p className="text-xs text-gray-400 mb-3 font-medium tracking-wide uppercase">
        WhatsApp Preview
      </p>
      {/* Phone frame */}
      <div className="w-64 bg-[#e5ddd5] rounded-2xl overflow-hidden shadow-xl border border-gray-200">
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

        {/* Chat area */}
        <div className="p-3">
          <div className="bg-white rounded-xl rounded-tl-sm shadow-sm overflow-hidden max-w-[85%]">
            {/* Header */}
            {header?.format === "IMAGE" && (
              <div className="bg-gray-100 h-28 flex items-center justify-center">
                {mediaUrl ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={mediaUrl}
                    alt="header"
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <ImageIcon className="w-8 h-8 text-gray-300" />
                )}
              </div>
            )}
            {header?.text && (
              <div className="px-3 pt-2.5">
                <p className="text-xs font-bold text-gray-900">{header.text}</p>
              </div>
            )}

            {/* Body */}
            {body?.text && (
              <div className="px-3 py-2">
                <p className="text-xs text-gray-800 leading-relaxed whitespace-pre-wrap">
                  {resolveBody(body.text)}
                </p>
              </div>
            )}

            {/* Footer */}
            {footer?.text && (
              <div className="px-3 pb-2">
                <p className="text-[10px] text-gray-400">{footer.text}</p>
              </div>
            )}

            {/* Timestamp */}
            <div className="px-3 pb-1.5 flex justify-end">
              <span className="text-[9px] text-gray-400">10:30 AM ✓✓</span>
            </div>

            {/* Buttons */}
            {buttons?.buttons && buttons.buttons.length > 0 && (
              <div className="border-t divide-y">
                {buttons.buttons.map((btn) => (
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
  );
}

/* ─── Step 0: Template ───────────────────────────────────── */
function Step0Template({
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
}: {
  readonly templates: Template[];
  readonly selectedTemplate: Template | null;
  readonly setSelectedTemplate: (t: Template | null) => void;
  readonly variables: Record<string, string>;
  readonly setVariables: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  readonly mediaUrl: string;
  readonly setMediaUrl: (url: string) => void;
  readonly fetchingTemplates: boolean;
  readonly refetchTemplates: () => void;
  readonly uploadingMedia: boolean;
  readonly setUploadingMedia: (b: boolean) => void;
  readonly bodyVars: string[];
}) {
  return (
    <div className="flex gap-6">
      <div className="flex-1 min-w-0 space-y-3 overflow-y-auto max-h-[65vh] pr-1">
        <div className="flex items-center justify-between">
          <h2 className="font-medium">Select Template</h2>
          <button
            onClick={refetchTemplates}
            disabled={fetchingTemplates}
            className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-[#24422e] disabled:opacity-50 transition"
          >
            <RefreshCw className={cn("w-3.5 h-3.5", fetchingTemplates && "animate-spin")} />
            Refresh
          </button>
        </div>
        <div className="grid gap-2 max-h-64 overflow-y-auto pr-1">
          {templates.map((t) => (
            <button
              key={t.name}
              onClick={() => {
                setSelectedTemplate(t);
                setVariables({});
              }}
              className={cn(
                "text-left border rounded-lg px-4 py-3 transition",
                selectedTemplate?.name === t.name
                  ? "border-[#24422e] bg-[#24422e]/5"
                  : "hover:border-[#24422e]/30"
              )}
            >
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">{t.name}</span>
                <span className={cn(
                  "text-xs px-2 py-0.5 rounded-full",
                  t.category === "UTILITY" ? "bg-[#24422e]/10 text-[#24422e]" : "bg-[#3a6b47]/10 text-[#3a6b47]"
                )}>
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
                <label htmlFor={`var-${v}`} className="text-xs text-gray-500 mb-0.5 block">{`{{${v}}}`}</label>
                <input
                  id={`var-${v}`}
                  value={variables[v] ?? ""}
                  onChange={(e) => setVariables(prev => ({ ...prev, [v]: e.target.value }))}
                  className={INPUT_CLS}
                  placeholder={`Value for {{${v}}}`}
                />
              </div>
            ))}
          </div>
        )}

        {selectedTemplate && (
          <div className="space-y-1.5">
            <label htmlFor="media-upload-input" className="text-xs text-gray-500 block">Media Image (optional)</label>
            {mediaUrl ? (
              <div className="relative w-full rounded-lg overflow-hidden border">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={mediaUrl} alt="media preview" className="w-full max-h-36 object-cover" />
                <button
                  onClick={() => setMediaUrl("")}
                  className="absolute top-2 right-2 bg-black/50 hover:bg-black/70 text-white rounded-full p-1 transition"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            ) : (
              <label className={cn(
                "flex flex-col items-center justify-center gap-2 border-2 border-dashed rounded-lg p-4 cursor-pointer transition",
                uploadingMedia ? "opacity-50 pointer-events-none" : "hover:border-[#24422e]/40 hover:bg-[#24422e]/5"
              )}>
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
                {uploadingMedia ? <RefreshCw className="w-5 h-5 text-gray-400 animate-spin" /> : <ImageIcon className="w-5 h-5 text-gray-300" />}
                <span className="text-xs text-gray-400">{uploadingMedia ? "Uploading…" : "Click to upload · JPG, PNG, WEBP · max 5MB"}</span>
              </label>
            )}
            <input
              value={mediaUrl}
              onChange={(e) => setMediaUrl(e.target.value)}
              className={INPUT_CLS}
              placeholder="Or paste a URL directly…"
            />
          </div>
        )}
      </div>
      <div className="hidden lg:flex w-72 border-l pl-6 flex-col sticky top-0 self-start">
        <TemplatePreview template={selectedTemplate} variables={variables} mediaUrl={mediaUrl} />
      </div>
    </div>
  );
}

/* ─── Step 1: Upload ─────────────────────────────────────── */
function Step1Upload({
  getRootProps,
  getInputProps,
  isDragActive,
  file,
  uploading,
  uploadFile,
  savedFiles,
  reusingFile,
  reuseFile,
}: {
  readonly getRootProps: any;
  readonly getInputProps: any;
  readonly isDragActive: boolean;
  readonly file: File | null;
  readonly uploading: boolean;
  readonly uploadFile: () => void;
  readonly savedFiles: SavedFile[] | undefined;
  readonly reusingFile: boolean;
  readonly reuseFile: (ref: string) => void;
}) {
  return (
    <div className="space-y-4">
      <h2 className="font-medium">Upload Contacts</h2>
      <div {...getRootProps()} className={cn(
        "border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition",
        isDragActive ? "border-[#24422e]/60 bg-[#24422e]/5" : "border-gray-200 hover:border-[#24422e]/40"
      )}>
        <input {...getInputProps()} />
        <Upload className="w-8 h-8 text-gray-300 mx-auto mb-3" />
        <p className="text-sm text-gray-500">Drop a CSV or XLSX file here, or click to browse</p>
        <p className="text-xs text-gray-400 mt-1">Max 50MB · First row must be headers</p>
      </div>
      {file && (
        <div className="flex items-center gap-2 text-sm px-3 py-2 rounded-lg" style={{ background: "#24422e14", color: "#24422e" }}>
          <CheckCircle className="w-4 h-4" />
          {file.name} ({(file.size / 1024).toFixed(1)} KB)
        </div>
      )}
      <GradBtn onClick={uploadFile} disabled={!file || uploading} className="w-full py-2">
        {uploading ? "Parsing..." : "Parse & Continue"}
      </GradBtn>
      {savedFiles && savedFiles.length > 0 && (
        <>
          <div className="relative">
            <div className="absolute inset-0 flex items-center"><div className="w-full border-t border-gray-200" /></div>
            <div className="relative flex justify-center text-xs"><span className="bg-white px-2 text-gray-400">Or use a previously parsed file</span></div>
          </div>
          <div className="max-h-48 overflow-y-auto space-y-2">
            {savedFiles.map((f) => (
              <button
                key={f.id}
                onClick={() => reuseFile(f.file_ref)}
                disabled={reusingFile}
                className="w-full flex items-center gap-3 p-3 border rounded-lg hover:border-[#24422e]/40 hover:bg-[#24422e]/5 transition text-left disabled:opacity-50"
              >
                <FileSpreadsheet className="w-5 h-5 text-gray-400 shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">{f.filename}</p>
                  <p className="text-xs text-gray-400">{f.valid_count} valid · {new Date(f.uploaded_at).toLocaleDateString()}</p>
                </div>
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

/* ─── Step 2: Preflight ───────────────────────────────────── */
function Step2Preflight({ preflight }: { readonly preflight: PreflightResult }) {
  return (
    <div className="space-y-4">
      <h2 className="font-medium">Pre-flight Check</h2>
      <div className="grid grid-cols-2 gap-3">
        <StatCard value={preflight.valid_count} label="Valid" colorCls="text-[#24422e]" bgCls="bg-[#24422e]/[0.08]" />
        <StatCard value={preflight.invalid_count} label="Invalid" colorCls="text-red-500" bgCls="bg-red-50" />
        <StatCard value={preflight.duplicate_count} label="Duplicates" colorCls="text-amber-600" bgCls="bg-amber-50" />
        <StatCard value={preflight.suppressed_count} label="Suppressed" colorCls="text-gray-500" bgCls="bg-gray-50" />
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
  );
}

/* ─── Step 3: Review ──────────────────────────────────────── */
function Step3Review({
  campaignName,
  setCampaignName,
  priority,
  setPriority,
  includeUnsub,
  setIncludeUnsub,
  selectedTemplate,
  preflight,
}: {
  readonly campaignName: string;
  readonly setCampaignName: (s: string) => void;
  readonly priority: "MARKETING" | "UTILITY";
  readonly setPriority: (p: "MARKETING" | "UTILITY") => void;
  readonly includeUnsub: boolean;
  readonly setIncludeUnsub: (b: boolean) => void;
  readonly selectedTemplate: Template | null;
  readonly preflight: PreflightResult | null;
}) {
  return (
    <div className="space-y-5">
      <h2 className="font-medium">Schedule & Review</h2>
      <div className="grid sm:grid-cols-2 gap-4">
        <div>
          <label htmlFor="campaign-name" className="text-sm font-medium mb-1 block">Campaign Name</label>
          <input
            id="campaign-name"
            value={campaignName}
            onChange={(e) => setCampaignName(e.target.value)}
            className={cn(INPUT_CLS, "py-2")}
            placeholder="e.g. Summer Promo 2026"
          />
        </div>
        <fieldset className="space-y-2">
          <legend className="text-sm font-medium text-[#24422e]">Priority</legend>
          <div className="flex gap-2">
            {(["MARKETING", "UTILITY"] as const).map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => setPriority(p)}
                className={cn(
                  "flex-1 py-2 rounded-lg text-sm font-medium border transition focus:ring-2 focus:ring-[#24422e]/20",
                  priority === p
                    ? "text-[#24422e] border-[#24422e] bg-[#24422e]/5 font-bold"
                    : "border-gray-200 text-gray-500 hover:border-[#24422e]/30"
                )}
              >
                {p}
              </button>
            ))}
          </div>
        </fieldset>
      </div>

      {priority === "MARKETING" && (
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={includeUnsub}
            onChange={(e) => setIncludeUnsub(e.target.checked)}
            className="w-4 h-4 accent-[#24422e] cursor-pointer"
          />
          <span className="text-sm">Include unsubscribe footer</span>
        </label>
      )}

      <div className="border rounded-xl overflow-hidden">
        <div className="px-4 py-2 text-xs font-semibold text-gray-500 uppercase tracking-wide border-b bg-gray-50">Summary</div>
        <div className="divide-y text-sm">
          {[
            ["Campaign Name", campaignName || "—"],
            ["Template", selectedTemplate?.name ?? "—"],
            ["Priority", priority],
            ["Recipients", preflight ? `${preflight.valid_count} contacts` : "—"],
            ["Unsubscribe Footer", includeUnsub ? "Yes" : "No"],
          ].map(([label, value]) => (
            <div key={label} className="flex justify-between px-4 py-2.5">
              <span className="text-gray-500">{label}</span>
              <span className="font-medium">{value}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ─── Main page ──────────────────────────────────────────── */

function stepCircleClass(i: number, step: number) {
  if (i < step) return "text-white";
  if (i === step) return "border-2 text-[#24422e]";
  return "bg-gray-100 text-gray-400";
}

function stepCircleStyle(
  i: number,
  step: number,
): React.CSSProperties | undefined {
  if (i < step) return { background: BRAND_GRADIENT };
  if (i === step) return { borderColor: "#24422e", background: "#24422e14" };
  return undefined;
}

export default function NewCampaignPage() {
  const { restaurant } = useAuthStore();
  const router = useRouter();
  const [step, setStep] = useState(0);

  // Step 0: Template
  const [selectedTemplate, setSelectedTemplate] = useState<Template | null>(
    null,
  );
  const [variables, setVariables] = useState<Record<string, string>>({});
  const [mediaUrl, setMediaUrl] = useState("");
  const [uploadingMedia, setUploadingMedia] = useState(false);

  // Step 1: Upload
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [reusingFile, setReusingFile] = useState(false);

  // Step 2: Preflight
  const [preflight, setPreflight] = useState<PreflightResult | null>(null);

  // Step 3: Schedule & Review
  const [campaignName, setCampaignName] = useState("");
  const [priority, setPriority] = useState<"MARKETING" | "UTILITY">(
    "MARKETING",
  );
  const [includeUnsub, setIncludeUnsub] = useState(true);

  const {
    data: apiTemplates,
    refetch: refetchTemplates,
    isFetching: fetchingTemplates,
  } = useQuery<Template[]>({
    queryKey: ["templates"],
    queryFn: () => api.get("/templates").then((r) => r.data),
    enabled: step === 0,
  });

  const templates = apiTemplates ?? [];

  const { data: savedFiles } = useQuery<SavedFile[]>({
    queryKey: ["contact-files"],
    queryFn: () => api.get("/contacts/files").then((r) => r.data),
    enabled: step === 1,
  });

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

  const reuseFile = async (fileRef: string) => {
    setReusingFile(true);
    try {
      const { data } = await api.post(`/contacts/files/${fileRef}/use`);
      setPreflight(data);
      setStep(2);
    } catch (e) {
      toast.error(parseApiError(e).message);
    } finally {
      setReusingFile(false);
    }
  };

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

  const createMutation = useMutation({
    mutationFn: () =>
      api.post("/campaigns", {
        restaurant_id: restaurant?.id ?? "",
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
    onError: (e: unknown) => toast.error(parseApiError(e).message),
  });

  const bodyVars =
    selectedTemplate?.components
      .find((c) => c.type === "BODY")
      ?.text?.match(/\{\{(\d+)\}\}/g)
      ?.map((v) => v.replace(/[{}]/g, "")) ?? [];

  const getCanNext = () => {
    switch (step) {
      case 0:
        return !!selectedTemplate;
      case 1:
        return !!preflight;
      case 2:
        return (preflight?.valid_count ?? 0) > 0;
      case 3:
        return !!campaignName;
      default:
        return false;
    }
  };

  const canNext = getCanNext();

  if (!restaurant) return null;

  return (
    <div className="max-w-4xl space-y-6">
      <h1 className="text-xl font-semibold text-[#24422e]">New Campaign</h1>

      {/* Step indicator */}
      <div className="flex items-center gap-1">
        {STEPS.map((s, i) => (
          <div key={s} className="flex items-center gap-1">
            <div
              className={cn(
                "w-7 h-7 rounded-full flex items-center justify-center text-xs font-medium transition",
                stepCircleClass(i, step),
              )}
              style={stepCircleStyle(i, step)}
            >
              {i < step ? <CheckCircle className="w-4 h-4" /> : i + 1}
            </div>
            <span
              className={cn(
                "text-xs hidden sm:block",
                i === step ? "font-medium" : "text-gray-400",
              )}
              style={i === step ? { color: "#24422e" } : undefined}
            >
              {s}
            </span>
            {i < STEPS.length - 1 && (
              <div className="w-6 h-px bg-gray-200 mx-1" />
            )}
          </div>
        ))}
      </div>

      {/* Step content */}
      <div className="bg-white rounded-xl border p-6">
        {step === 0 && (
          <Step0Template
            templates={templates}
            selectedTemplate={selectedTemplate}
            setSelectedTemplate={setSelectedTemplate}
            variables={variables}
            setVariables={setVariables}
            mediaUrl={mediaUrl}
            setMediaUrl={setMediaUrl}
            fetchingTemplates={fetchingTemplates}
            refetchTemplates={refetchTemplates}
            uploadingMedia={uploadingMedia}
            setUploadingMedia={setUploadingMedia}
            bodyVars={bodyVars}
          />
        )}

        {step === 1 && (
          <Step1Upload
            getRootProps={getRootProps}
            getInputProps={getInputProps}
            isDragActive={isDragActive}
            file={file}
            uploading={uploading}
            uploadFile={uploadFile}
            savedFiles={savedFiles}
            reusingFile={reusingFile}
            reuseFile={reuseFile}
          />
        )}

        {step === 2 && preflight && <Step2Preflight preflight={preflight} />}

        {step === 3 && (
          <Step3Review
            campaignName={campaignName}
            setCampaignName={setCampaignName}
            priority={priority}
            setPriority={setPriority}
            includeUnsub={includeUnsub}
            setIncludeUnsub={setIncludeUnsub}
            selectedTemplate={selectedTemplate}
            preflight={preflight}
          />
        )}
      </div>

      {/* Navigation */}
      <div className="flex justify-between mt-6">
        <button
          onClick={() => setStep((s) => s - 1)}
          disabled={step === 0}
          className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-[#24422e] disabled:opacity-30 transition"
        >
          <ChevronLeft className="w-4 h-4" /> Back
        </button>

        {step < 3 ? (
          <GradBtn
            onClick={() => setStep((s) => s + 1)}
            disabled={!canNext}
            className="px-4 py-2 text-sm"
          >
            Next <ChevronRight className="w-4 h-4" />
          </GradBtn>
        ) : (
          <GradBtn
            onClick={() => createMutation.mutate()}
            disabled={createMutation.isPending || !campaignName}
            className="px-6 py-2 text-sm"
          >
            {createMutation.isPending ? "Creating..." : "🚀 Launch Campaign"}
          </GradBtn>
        )}
      </div>
    </div>
  );
}
