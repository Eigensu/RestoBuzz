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
import { ChevronLeft, ChevronRight } from "lucide-react";
import { StepIndicator } from "@/components/campaigns/molecules/StepIndicator";
import { WizardRightPanel } from "@/components/campaigns/molecules/WizardRightPanel";
import { Step0Template } from "@/components/campaigns/molecules/Step0Template";
import { Step1Upload } from "@/components/campaigns/molecules/Step1Upload";
import { Step2Preflight } from "@/components/campaigns/molecules/Step2Preflight";
import { Step3Review } from "@/components/campaigns/molecules/Step3Review";
import { GradientButton } from "@/components/ui/GradientButton";

interface SavedFile {
  id: string;
  filename: string;
  valid_count: number;
  invalid_count: number;
  file_ref: string;
  uploaded_at: string;
}

export function NewCampaignWizard() {
  const { restaurant } = useAuthStore();
  const router = useRouter();
  const [step, setStep] = useState(0);

  // Step 0
  const [selectedTemplate, setSelectedTemplate] = useState<Template | null>(
    null,
  );
  const [variables, setVariables] = useState<Record<string, string>>({});
  const [mediaUrl, setMediaUrl] = useState("");
  const [uploadingMedia, setUploadingMedia] = useState(false);

  // Step 1
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [reusingFile, setReusingFile] = useState(false);
  const [loadingMembers, setLoadingMembers] = useState(false);

  // Step 2
  const [preflight, setPreflight] = useState<PreflightResult | null>(null);

  // Step 3
  const [campaignName, setCampaignName] = useState("");
  const [includeUnsub, setIncludeUnsub] = useState(true);
  const [testPhone, setTestPhone] = useState("");
  const [sendMode, setSendMode] = useState<"immediate" | "scheduled">(
    "immediate",
  );
  const [scheduledAt, setScheduledAt] = useState<Date | null>(null);

  const {
    data: apiTemplates,
    refetch: refetchTemplates,
    isFetching: fetchingTemplates,
  } = useQuery<Template[]>({
    queryKey: ["templates"],
    queryFn: () => api.get("/templates").then((r) => r.data),
    enabled: step === 0,
  });

  const { data: savedFiles, refetch: refetchSavedFiles } = useQuery<
    SavedFile[]
  >({
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

  const useMembersAsContacts = async (type: "all" | "nfc" | "ecard") => {
    setLoadingMembers(true);
    try {
      const params = new URLSearchParams({ restaurant_id: restaurant!.id });
      if (type !== "all") params.set("type", type);
      const { data } = await api.post(`/members/as-contacts?${params}`);
      if (data.valid_count === 0) {
        toast.error("No active members found for the selected type.");
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

  const deleteFile = async (fileRef: string) => {
    try {
      await api.delete(`/contacts/files/${fileRef}`);
      toast.success("File deleted");
      refetchSavedFiles();
    } catch (e) {
      toast.error(parseApiError(e).message);
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
        include_unsubscribe: includeUnsub,
        contact_file_ref: preflight?.file_ref,
        scheduled_at:
          sendMode === "scheduled" && scheduledAt
            ? scheduledAt.toISOString()
            : null,
      }),
    onSuccess: (res) => {
      toast.success(
        sendMode === "scheduled" ? "Campaign scheduled" : "Campaign created",
      );
      router.push(`/campaigns/whatsapp/${res.data.id}`);
    },
    onError: (e: unknown) => toast.error(parseApiError(e).message),
  });

  const sendTestMutation = useMutation({
    mutationFn: () =>
      api.post("/campaigns/test-message", {
        restaurant_id: restaurant?.id ?? "",
        to_phone: testPhone.trim(),
        template_name: selectedTemplate?.name ?? "",
        template_variables: variables,
        media_url: mediaUrl || null,
      }),
    onSuccess: (res) => {
      toast.success(
        `Test message sent via ${res.data.endpoint_used} (${res.data.wa_message_id})`,
      );
    },
    onError: (e: unknown) => toast.error(parseApiError(e).message),
  });

  const bodyVars =
    selectedTemplate?.components
      .find((c) => c.type === "BODY")
      ?.text?.match(/\{\{(\d+)\}\}/g)
      ?.map((v) => v.replaceAll("{", "").replaceAll("}", "")) ?? [];

  const scheduleValid =
    sendMode === "immediate" ||
    (scheduledAt !== null && scheduledAt > new Date());

  const launchLabel = (() => {
    if (createMutation.isPending) {
      return sendMode === "scheduled" ? "Scheduling..." : "Creating...";
    }
    return sendMode === "scheduled"
      ? "📅 Schedule Campaign"
      : "🚀 Launch Campaign";
  })();

  function getCanNext(): boolean {
    if (step === 0) return !!selectedTemplate;
    if (step === 1) return !!preflight;
    if (step === 2) return (preflight?.valid_count ?? 0) > 0;
    return !!campaignName && scheduleValid;
  }

  const canNext = getCanNext();

  if (!restaurant) return null;

  return (
    <div className="w-full space-y-6 p-4 md:p-8 pb-20">
      <h1 className="text-xl font-semibold text-[#24422e]">New Campaign</h1>

      <StepIndicator currentStep={step} />

      {/* Two-column layout */}
      <div className="flex gap-6 items-start">
        <div className="flex-1 min-w-0 bg-white rounded-xl border p-6">
          {step === 0 && (
            <Step0Template
              templates={apiTemplates ?? []}
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
              loadingMembers={loadingMembers}
              onSelectMembers={useMembersAsContacts}
              onDeleteFile={deleteFile}
            />
          )}
          {step === 2 && preflight && <Step2Preflight preflight={preflight} />}
          {step === 3 && (
            <Step3Review
              campaignName={campaignName}
              setCampaignName={setCampaignName}
              includeUnsub={includeUnsub}
              setIncludeUnsub={setIncludeUnsub}
              selectedTemplate={selectedTemplate}
              preflight={preflight}
              sendMode={sendMode}
              setSendMode={setSendMode}
              scheduledAt={scheduledAt}
              setScheduledAt={setScheduledAt}
            />
          )}
        </div>

        {step > 0 && <WizardRightPanel step={step} preflight={preflight} />}
      </div>

      {/* Navigation */}
      <div className="space-y-4">
        {step === 3 && (
          <div className="rounded-xl border border-[#24422e]/20 bg-[#f7fbf8] p-4">
            <p className="text-sm font-medium text-[#24422e]">
              Send Test Message
            </p>
            <p className="mt-1 text-xs text-gray-600">
              Send a test to one phone number before launching the full
              campaign.
            </p>
            <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center">
              <input
                value={testPhone}
                onChange={(e) => setTestPhone(e.target.value)}
                placeholder="Enter test phone number"
                className="h-10 w-full flex-1 rounded-lg border border-gray-300 px-3 text-sm outline-none ring-0 transition focus:border-[#24422e]"
              />
              <GradientButton
                onClick={() => sendTestMutation.mutate()}
                disabled={
                  sendTestMutation.isPending ||
                  !testPhone.trim() ||
                  !selectedTemplate
                }
                className="h-10 min-w-[120px] whitespace-nowrap px-4 text-sm"
              >
                {sendTestMutation.isPending ? "Sending..." : "Send Test"}
              </GradientButton>
            </div>
          </div>
        )}

        <div className="flex justify-between">
          <button
            onClick={() => setStep((s) => s - 1)}
            disabled={step === 0}
            className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-[#24422e] disabled:opacity-30 transition"
          >
            <ChevronLeft className="w-4 h-4" /> Back
          </button>
          {step < 3 ? (
            <GradientButton
              onClick={() => setStep((s) => s + 1)}
              disabled={!canNext}
              className="px-4 py-2 text-sm"
            >
              Next <ChevronRight className="w-4 h-4" />
            </GradientButton>
          ) : (
            <GradientButton
              onClick={() => createMutation.mutate()}
              disabled={
                createMutation.isPending || !campaignName || !scheduleValid
              }
              className="px-6 py-2 text-sm"
            >
              {launchLabel}
            </GradientButton>
          )}
        </div>
      </div>
    </div>
  );
}
