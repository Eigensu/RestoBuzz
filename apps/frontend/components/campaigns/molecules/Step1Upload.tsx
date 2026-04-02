"use client";
import { useState } from "react";
import {
  Upload,
  CheckCircle,
  FileSpreadsheet,
  Users,
  RefreshCw,
  ChevronRight,
  Download,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { GradientButton } from "@/components/ui/GradientButton";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { parseApiError } from "@/lib/errors";
import { BRAND_GRADIENT } from "@/lib/brand";

interface SavedFile {
  id: string;
  filename: string;
  valid_count: number;
  invalid_count: number;
  file_ref: string;
  uploaded_at: string;
}

interface Step1UploadProps {
  getRootProps: () => Record<string, unknown>;
  getInputProps: () => Record<string, unknown>;
  isDragActive: boolean;
  file: File | null;
  uploading: boolean;
  uploadFile: () => void;
  savedFiles: SavedFile[] | undefined;
  reusingFile: boolean;
  reuseFile: (ref: string) => void;
  loadingMembers: boolean;
  onSelectMembers: (type: "all" | "nfc" | "ecard") => void;
}

const MEMBER_TYPES: {
  key: "all" | "nfc" | "ecard";
  label: string;
  desc: string;
}[] = [
  {
    key: "all",
    label: "All Members",
    desc: "Every active member regardless of card type",
  },
  { key: "nfc", label: "NFC Only", desc: "Members with a physical NFC card" },
  { key: "ecard", label: "E-Card Only", desc: "Members with a digital e-card" },
];

export function Step1Upload({
  getRootProps,
  getInputProps,
  isDragActive,
  file,
  uploading,
  uploadFile,
  savedFiles,
  reusingFile,
  reuseFile,
  loadingMembers,
  onSelectMembers,
}: Step1UploadProps) {
  const [source, setSource] = useState<"file" | "members">("file");
  const [downloading, setDownloading] = useState(false);

  const downloadTemplate = async () => {
    setDownloading(true);
    try {
      const res = await api.get("/contacts/template", { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement("a");
      a.href = url;
      a.download = "contacts_template.xlsx";
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      toast.error(parseApiError(e).message);
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="space-y-4">
      <h2 className="font-medium">Select Contacts</h2>

      {/* Source toggle */}
      <div className="flex rounded-xl border overflow-hidden">
        {(["file", "members"] as const).map((s) => (
          <button
            key={s}
            onClick={() => setSource(s)}
            className={cn(
              "flex-1 flex items-center justify-center gap-2 py-2.5 text-sm font-medium transition",
              source === s ? "text-white" : "text-gray-500 hover:bg-gray-50",
            )}
            style={source === s ? { background: BRAND_GRADIENT } : undefined}
          >
            {s === "file" ? (
              <FileSpreadsheet className="w-4 h-4" />
            ) : (
              <Users className="w-4 h-4" />
            )}
            {s === "file" ? "Upload File" : "From Members"}
          </button>
        ))}
      </div>

      {source === "file" ? (
        <>
          {/* Template download */}
          <div className="flex items-center justify-between px-1">
            <p className="text-xs text-gray-400">Need the right format?</p>
            <button
              onClick={downloadTemplate}
              disabled={downloading}
              className="flex items-center gap-1.5 text-xs font-bold text-[#24422e] hover:underline disabled:opacity-50"
            >
              <Download className="w-3.5 h-3.5" />
              {downloading ? "Downloading..." : "Download Template"}
            </button>
          </div>
          <div
            {...getRootProps()}
            className={cn(
              "border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition",
              isDragActive
                ? "border-[#24422e]/60 bg-[#24422e]/5"
                : "border-gray-200 hover:border-[#24422e]/40",
            )}
          >
            <input {...getInputProps()} />
            <Upload className="w-8 h-8 text-gray-300 mx-auto mb-3" />
            <p className="text-sm text-gray-500">
              Drop a CSV or XLSX file here, or click to browse
            </p>
            <p className="text-xs text-gray-400 mt-1">
              Max 50MB · First row must be headers
            </p>
          </div>

          {file && (
            <div
              className="flex items-center gap-2 text-sm px-3 py-2 rounded-lg"
              style={{ background: "#24422e14", color: "#24422e" }}
            >
              <CheckCircle className="w-4 h-4" />
              {file.name} ({(file.size / 1024).toFixed(1)} KB)
            </div>
          )}

          <GradientButton
            onClick={uploadFile}
            disabled={!file || uploading}
            className="w-full py-2"
          >
            {uploading ? "Parsing..." : "Parse & Continue"}
          </GradientButton>

          {savedFiles && savedFiles.length > 0 && (
            <>
              <div className="relative">
                <div className="absolute inset-0 flex items-center">
                  <div className="w-full border-t border-gray-200" />
                </div>
                <div className="relative flex justify-center text-xs">
                  <span className="bg-white px-2 text-gray-400">
                    Or use a previously parsed file
                  </span>
                </div>
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
                      <p className="text-sm font-medium truncate">
                        {f.filename}
                      </p>
                      <p className="text-xs text-gray-400">
                        {f.valid_count} valid ·{" "}
                        {new Date(f.uploaded_at).toLocaleDateString()}
                      </p>
                    </div>
                  </button>
                ))}
              </div>
            </>
          )}
        </>
      ) : (
        <div className="space-y-3">
          <p className="text-xs text-gray-500">
            Choose which members to target. Only active members with a phone
            number are included.
          </p>
          {MEMBER_TYPES.map(({ key, label, desc }) => (
            <button
              key={key}
              onClick={() => onSelectMembers(key)}
              disabled={loadingMembers}
              className="w-full flex items-center gap-4 p-4 border-2 rounded-xl hover:border-[#24422e] hover:bg-[#24422e]/5 transition text-left disabled:opacity-50 group"
            >
              <div className="w-10 h-10 rounded-xl bg-[#eff2f0] flex items-center justify-center shrink-0 group-hover:bg-[#24422e]/10">
                <Users className="w-5 h-5 text-[#24422e]" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-bold text-gray-900">{label}</p>
                <p className="text-xs text-gray-400 mt-0.5">{desc}</p>
              </div>
              {loadingMembers ? (
                <RefreshCw className="w-4 h-4 text-gray-400 animate-spin shrink-0" />
              ) : (
                <ChevronRight className="w-4 h-4 text-gray-300 group-hover:text-[#24422e] shrink-0" />
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
