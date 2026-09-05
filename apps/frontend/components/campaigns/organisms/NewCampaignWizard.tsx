"use client";
import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { toast } from "sonner";
import { parseApiError } from "@/lib/errors";
import { cloudinaryPublicId, buildEcardPreviewUrl } from "@/lib/cloudinary";
import type {
  PreflightResult,
  Template,
  MemberSegmentsResponse,
} from "@/types";
import { useDropzone } from "react-dropzone";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { StepIndicator } from "@/components/campaigns/molecules/StepIndicator";
import { WizardRightPanel } from "@/components/campaigns/molecules/WizardRightPanel";
import { Step0Template } from "@/components/campaigns/molecules/Step0Template";
import { Step1Upload } from "@/components/campaigns/molecules/Step1Upload";
import { Step2Preflight } from "@/components/campaigns/molecules/Step2Preflight";
import { VariableMappingPanel } from "@/components/campaigns/molecules/VariableMappingPanel";
import { Step3Review } from "@/components/campaigns/molecules/Step3Review";
import { GradientButton } from "@/components/ui/GradientButton";
import {
  extractVariables,
  resolvePreviewValue,
  sourceError,
  suggestSource,
} from "@/lib/templateVariables";
import type { VariableSourceDraft } from "@/lib/templateVariables";

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
  // E-card personalization: render each recipient's name onto the header image.
  const [ecardPersonalize, setEcardPersonalize] = useState(false);
  const [ecardPublicId, setEcardPublicId] = useState("");

  // Step 1
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [reusingFile, setReusingFile] = useState(false);
  const [loadingMembers, setLoadingMembers] = useState(false);

  // Step 2
  const [preflight, setPreflight] = useState<PreflightResult | null>(null);
  const [variableSources, setVariableSources] = useState<
    Record<string, VariableSourceDraft>
  >({});

  // Step 3
  const [campaignName, setCampaignName] = useState("");
  const [includeUnsub, setIncludeUnsub] = useState(true);
  const [testPhone, setTestPhone] = useState("");
  const [sendMode, setSendMode] = useState<"immediate" | "scheduled">(
    "immediate",
  );
  const [scheduledAt, setScheduledAt] = useState<Date | null>(null);
  const [smartRetries, setSmartRetries] = useState(false);
  const [retryUntil, setRetryUntil] = useState<Date | null>(null);

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

  const { data: analytics } = useQuery({
    queryKey: ["campaign-analytics", restaurant?.id],
    queryFn: () => api.get("/campaigns/analytics", { params: { restaurant_id: restaurant?.id } }).then((r) => r.data),
    enabled: step === 1 && !!restaurant?.id,
  });
  const reservegoCount = analytics?.totals?.reservego_members ?? 0;

  // Segments are defined by the backend so the audience picker and the members
  // page always offer exactly the filters the API implements.
  const { data: segmentData } = useQuery<MemberSegmentsResponse>({
    queryKey: ["member-segments"],
    queryFn: () => api.get("/members/segments").then((r) => r.data),
    staleTime: Infinity,
    enabled: step === 1,
  });
  const memberSegments = segmentData?.segments ?? [];

  // E-card campaign entry: when opened via "New E-card campaign" (?type=ecard),
  // lock the configured template + base card and jump straight to contacts.
  const ecardPrefilled = useRef(false);
  useEffect(() => {
    if (ecardPrefilled.current || globalThis.window === undefined) return;
    if (new URLSearchParams(globalThis.location.search).get("type") !== "ecard")
      return;
    const cfg = restaurant?.ecard_config;
    if (!cfg || !apiTemplates) return;
    const tpl = apiTemplates.find((t) => t.name === cfg.template_name);
    if (!tpl) return;
    ecardPrefilled.current = true;
    setSelectedTemplate(tpl);
    setVariables({});
    setMediaUrl(cfg.base_url);
    setEcardPublicId(cfg.base_public_id);
    setEcardPersonalize(true);
    setStep(1);
  }, [apiTemplates, restaurant]);

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

  const loadAudience = async (params: URLSearchParams, emptyMessage: string) => {
    setLoadingMembers(true);
    try {
      const { data } = await api.post(`/members/as-contacts?${params}`);
      if (data.valid_count === 0) {
        toast.error(emptyMessage);
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

  /** Audience is a category and/or a segment — the same axes as the members page. */
  const useMembersAsContacts = async (
    selection: { category?: string | null; segment?: string | null },
    limit?: number,
  ) => {
    const params = new URLSearchParams({ restaurant_id: restaurant!.id });
    if (selection.category) params.set("category", selection.category);
    if (selection.segment) params.set("segment", selection.segment);
    if (limit) params.set("limit", limit.toString());
    await loadAudience(
      params,
      "No active members found for the selected audience.",
    );
  };

  const useReservegoAsContacts = async (limit?: number) => {
    const params = new URLSearchParams({
      restaurant_id: restaurant!.id,
      type: "reservego",
    });
    if (limit) params.set("limit", limit.toString());
    await loadAudience(params, "No ReserveGo guests found.");
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

  // Resolve the base card's public_id (from the upload response, or derived from
  // a Cloudinary URL for template/pasted cards) and whether personalization is
  // actually usable. When active, each recipient's name is rendered server-side.
  const ecardBasePublicId =
    ecardPublicId || (mediaUrl ? cloudinaryPublicId(mediaUrl) : null);
  const ecardActive = ecardPersonalize && !!ecardBasePublicId;
  const personalizationPayload = ecardActive
    ? {
        type: "ecard_name_overlay",
        base_public_id: ecardBasePublicId,
        overlay: {},
      }
    : null;

  const createMutation = useMutation({
    mutationFn: () =>
      api.post("/campaigns", {
        restaurant_id: restaurant?.id ?? "",
        name: campaignName,
        template_id: selectedTemplate?.name ?? "",
        template_name: selectedTemplate?.name ?? "",
        template_variables: variables,
        variable_sources: variableSources,
        media_url: mediaUrl || null,
        personalization: personalizationPayload,
        include_unsubscribe: includeUnsub,
        contact_file_ref: preflight?.file_ref,
        scheduled_at:
          sendMode === "scheduled" && scheduledAt
            ? scheduledAt.toISOString()
            : null,
        smart_retries: smartRetries,
        retry_until: smartRetries && retryUntil ? retryUntil.toISOString() : null,
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
        // Resolved against the first contact so the test message reads exactly
        // as the campaign will, mapping mistakes included.
        template_variables: previewVariables,
        // Personalized test shows a sample name so the operator sees the real card.
        media_url: ecardActive
          ? buildEcardPreviewUrl(mediaUrl, "Aarav Mehta")
          : mediaUrl || null,
      }),
    onSuccess: (res) => {
      toast.success(
        `Test message sent via ${res.data.endpoint_used} (${res.data.wa_message_id})`,
      );
    },
    onError: (e: unknown) => toast.error(parseApiError(e).message),
  });

  const bodyVars = extractVariables(
    selectedTemplate?.components.find((c) => c.type === "BODY")?.text ?? "",
  );

  const sheetHeaders = preflight?.headers ?? [];
  const sampleContact = preflight?.valid_rows?.[0];

  // Values the first contact would receive — drives the phone preview and the
  // test send, so both show what actually goes out rather than raw {{...}}.
  // Blank entries are dropped rather than sent as "": an empty value would
  // override the template's own sample and leave the preview showing the raw
  // {{placeholder}} instead.
  const previewVariables = Object.fromEntries(
    bodyVars
      .map((name) => [
        name,
        resolvePreviewValue(variableSources[name], {
          row: sampleContact?.row,
          contactName: sampleContact?.name,
          restaurant,
        }) || variables[name] || "",
      ])
      .filter(([, value]) => value),
  );

  const mappingProblem = bodyVars
    .map((name) => sourceError(variableSources[name]))
    .find(Boolean);

  // Open the mapping step already filled in. Guessing from the variable's name
  // and the sheet's headers is right most of the time, and a wrong guess is one
  // dropdown to fix — an empty row is a decision for every variable.
  const varSignature = bodyVars.join(",");
  useEffect(() => {
    if (!preflight) return;
    const headers = preflight.headers ?? [];
    setVariableSources((prev) => {
      // Re-seed a variable with no mapping yet, and any column mapping whose
      // column this sheet does not have — swapping the contact file otherwise
      // leaves a mapping pointing at a column that is gone, which resolves
      // blank for every recipient.
      const stale = bodyVars.filter((name) => {
        const source = prev[name];
        if (!source) return true;
        return (
          source.kind === "column" && !headers.includes(source.column ?? "")
        );
      });
      if (stale.length === 0) return prev;
      const next = { ...prev };
      for (const name of stale) {
        next[name] = suggestSource(name, headers);
      }
      return next;
    });
    // bodyVars is rebuilt every render; varSignature tracks its contents.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [preflight, varSignature]);

  const scheduleValid =
    sendMode === "immediate" ||
    (scheduledAt !== null && scheduledAt > new Date());

  const retryValid =
    !smartRetries ||
    (smartRetries && retryUntil !== null && retryUntil > new Date());

  const launchLabel = (() => {
    if (createMutation.isPending) {
      return sendMode === "scheduled" ? "Scheduling..." : "Creating...";
    }
    return sendMode === "scheduled"
      ? "📅 Schedule Campaign"
      : "🚀 Launch Campaign";
  })();

  function getCanNext(): boolean {
    if (step === 0) {
      if (!selectedTemplate) return false;
      // If personalization is toggled on but we can't resolve a Cloudinary base
      // public_id, the payload silently collapses to a static header. Block here
      // (Step0Template shows why) rather than send a non-personalized card.
      if (ecardPersonalize && !ecardBasePublicId) return false;
      return true;
    }
    if (step === 1) return !!preflight;
    if (step === 2) {
      return (preflight?.valid_count ?? 0) > 0 && !mappingProblem;
    }
    return !!campaignName && scheduleValid && retryValid;
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
              variables={previewVariables}
              setVariables={setVariables}
              mediaUrl={mediaUrl}
              setMediaUrl={setMediaUrl}
              fetchingTemplates={fetchingTemplates}
              refetchTemplates={refetchTemplates}
              uploadingMedia={uploadingMedia}
              setUploadingMedia={setUploadingMedia}
              bodyVars={bodyVars}
              ecardPersonalize={ecardPersonalize}
              setEcardPersonalize={setEcardPersonalize}
              setEcardPublicId={setEcardPublicId}
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
              onSelectReservego={useReservegoAsContacts}
              onDeleteFile={deleteFile}
              reservegoCount={reservegoCount}
              memberCategories={restaurant?.member_categories ?? ["nfc", "ecard"]}
              segments={memberSegments}
            />
          )}
          {step === 2 && preflight && (
            <div className="space-y-6">
              <Step2Preflight preflight={preflight} />
              <VariableMappingPanel
                names={bodyVars}
                headers={sheetHeaders}
                sources={variableSources}
                onChange={(name, source) =>
                  setVariableSources((prev) => ({ ...prev, [name]: source }))
                }
                restaurant={restaurant}
                sampleRow={sampleContact}
              />
            </div>
          )}
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
              smartRetries={smartRetries}
              setSmartRetries={setSmartRetries}
              retryUntil={retryUntil}
              setRetryUntil={setRetryUntil}
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
                createMutation.isPending || !campaignName || !scheduleValid || !retryValid
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
