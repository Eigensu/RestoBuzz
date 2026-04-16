"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { parseApiError } from "@/lib/errors";
import { BRAND_GRADIENT } from "@/lib/brand";
import {
  ArrowLeft,
  Smartphone,
  Plus,
  X,
  Loader2,
  RefreshCw,
  Image as ImageIcon,
  Phone,
  MoreVertical,
  Send as SendIcon,
  Smile,
  Paperclip,
  Camera,
  Bold,
  Italic,
  Strikethrough,
  Code as CodeIcon,
  Sparkles,
} from "lucide-react";
import { useRef } from "react";

const LANGUAGES = [
  { code: "en", label: "English" },
  { code: "en_US", label: "English (US)" },
  { code: "hi", label: "Hindi" },
  { code: "ar", label: "Arabic" },
  { code: "es", label: "Spanish" },
  { code: "fr", label: "French" },
  { code: "pt_BR", label: "Portuguese (BR)" },
  { code: "id", label: "Indonesian" },
];

type HeaderType = "none" | "text" | "image" | "video" | "document";

export default function NewTemplatePage() {
  const router = useRouter();
  const qc = useQueryClient();
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Form state
  const [name, setName] = useState("");
  const [language, setLanguage] = useState("en");
  const [headerType, setHeaderType] = useState<HeaderType>("none");
  const [headerText, setHeaderText] = useState("");
  const [headerImageUrl, setHeaderImageUrl] = useState("");
  const [body, setBody] = useState("");
  const [footer, setFooter] = useState("");
  const [uploadingImage, setUploadingImage] = useState(false);

  // Variable tracking
  const variableMatches = body.match(/\{\{\d+\}\}/g) || [];
  const uniqueVars = [...new Set(variableMatches)];

  const addVariable = () => {
    const indices = (body.match(/\{\{(\d+)\}\}/g) ?? [])
      .map((m) => parseInt(m.replace(/\{\{|\}\}/g, ""), 10))
      .filter((n) => !isNaN(n));
    const nextIndex = indices.length > 0 ? Math.max(...indices) + 1 : 1;
    setBody((prev) => prev + `{{${nextIndex}}}`);
  };

  const applyFormat = (type: "bold" | "italic" | "strikethrough" | "code") => {
    const el = textareaRef.current;
    if (!el) return;

    const start = el.selectionStart;
    const end = el.selectionEnd;
    const text = body;
    const selected = text.substring(start, end);

    let prefix = "";
    let suffix = "";

    switch (type) {
      case "bold":
        prefix = suffix = "*";
        break;
      case "italic":
        prefix = suffix = "_";
        break;
      case "strikethrough":
        prefix = suffix = "~";
        break;
      case "code":
        prefix = suffix = "```";
        break;
    }

    const newText =
      text.substring(0, start) +
      prefix +
      selected +
      suffix +
      text.substring(end);
    setBody(newText.slice(0, 1024));

    setTimeout(() => {
      el.focus();
      el.setSelectionRange(start + prefix.length, end + prefix.length);
    }, 0);
  };

  const escapeHtml = (str: string) =>
    str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");

  const renderPreviewText = (text: string) => {
    if (!text) return "";
    const escaped = escapeHtml(text);
    return escaped
      .replace(/\*([^*]+)\*/g, "<strong>$1</strong>")
      .replace(/_([^_]+)_/g, "<em>$1</em>")
      .replace(/~([^~]+)~/g, "<del>$1</del>")
      .replace(/```([\s\S]+?)```/g, "<code>$1</code>")
      .replace(/\n/g, "<br />");
  };

  // Build components payload
  const buildComponents = () => {
    const comps: Array<{
      type: string;
      text?: string;
      format?: string;
      example?: Record<string, unknown>;
    }> = [];

    if (headerType === "text" && headerText.trim()) {
      comps.push({ type: "HEADER", format: "TEXT", text: headerText });
    } else if (headerType === "image" && headerImageUrl.trim()) {
      comps.push({
        type: "HEADER",
        format: "IMAGE",
        text: "",
        example: { media_url: headerImageUrl },
      });
    }

    if (body.trim()) {
      comps.push({ type: "BODY", text: body });
    }

    if (footer.trim()) {
      comps.push({ type: "FOOTER", text: footer });
    }

    return comps;
  };

  const mutation = useMutation({
    mutationFn: () =>
      api.post("/templates", {
        name: name.toLowerCase().replace(/\s+/g, "_"),
        category: "MARKETING",
        language,
        components: buildComponents(),
      }),
    onSuccess: () => {
      toast.success("Template created — pending Meta review");
      qc.invalidateQueries({ queryKey: ["templates"] });
      router.push("/templates");
    },
    onError: (e: unknown) => toast.error(parseApiError(e).message),
  });

  const canSubmit =
    !!name.trim() && !!body.trim() && body.length <= 1024 && !uploadingImage;

  const selectedLang = LANGUAGES.find((l) => l.code === language);

  return (
    <div className="min-h-screen pb-20 max-w-[1600px] mx-auto p-4 md:p-8">
      {/* Top Bar */}
      <div className="flex items-center justify-between mb-8">
        <div className="flex items-center gap-4">
          <button
            onClick={() => router.push("/templates")}
            className="inline-flex items-center gap-2 text-sm text-gray-500 hover:text-gray-800 font-medium transition"
          >
            <ArrowLeft className="w-4 h-4" />
            Create New Template
          </button>

          <div className="h-5 w-px bg-gray-200" />

          <div className="flex items-center gap-2 text-sm font-bold text-[#24422e]">
            <Smartphone className="w-4 h-4" />
            WhatsApp
          </div>
        </div>

        <button
          onClick={() => mutation.mutate()}
          disabled={!canSubmit || mutation.isPending}
          className="inline-flex items-center gap-2 text-white text-sm font-black px-8 py-3 rounded-xl transition hover:scale-[1.02] active:scale-[0.98] disabled:opacity-40 shadow-lg shadow-green-900/20"
          style={{ background: BRAND_GRADIENT }}
        >
          {mutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
          Submit
        </button>
      </div>

      {/* Main Layout: Form + Preview */}
      <div className="grid grid-cols-1 xl:grid-cols-[1fr_380px] gap-8 items-start">
        {/* Left: Form */}
        <div className="space-y-6">
          {/* Template Name + Language */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <label className="block text-xs font-black text-gray-500 uppercase tracking-wider mb-2">
                Template Name
              </label>
              <input
                value={name}
                onChange={(e) =>
                  setName(
                    e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ""),
                  )
                }
                className="w-full border border-gray-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-[#24422e]/20 focus:border-[#24422e]"
                placeholder="Enter template name..."
              />
              <p className="text-[10px] text-gray-400 mt-1.5 font-medium">
                Lowercase letters, numbers, underscores only
              </p>
            </div>

            <div>
              <label className="block text-xs font-black text-gray-500 uppercase tracking-wider mb-2">
                Select Language
              </label>
              <div className="flex items-center gap-2">
                <span className="inline-flex items-center gap-1.5 text-xs font-bold px-3 py-1.5 bg-[#eff2f0] text-[#24422e] rounded-lg border border-[#24422e]/10">
                  {selectedLang?.label ?? language}
                  <button
                    onClick={() => setLanguage("en")}
                    className="text-[#24422e]/40 hover:text-[#24422e] transition"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </span>
                <select
                  value={language}
                  onChange={(e) => setLanguage(e.target.value)}
                  className="flex-1 border border-gray-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-[#24422e]/20 focus:border-[#24422e] bg-white"
                >
                  {LANGUAGES.map((l) => (
                    <option key={l.code} value={l.code}>
                      {l.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          {/* Header Section */}
          <div className="bg-white rounded-2xl border border-gray-100 p-6 shadow-sm">
            <h3 className="text-sm font-black text-gray-900">
              Header (Optional)
            </h3>
            <p className="text-xs text-gray-500 mt-1 font-medium">
              Add a title, or select the media type you want to get approved for
              this template&apos;s header.
            </p>

            <div className="flex items-center gap-6 mt-4">
              {(
                [
                  ["none", "None"],
                  ["text", "Text"],
                  ["image", "Image"],
                  ["video", "Video"],
                  ["document", "Document"],
                ] as const
              ).map(([value, label]) => (
                <label
                  key={value}
                  className="flex items-center gap-2 cursor-pointer"
                >
                  <input
                    type="radio"
                    name="headerType"
                    value={value}
                    checked={headerType === value}
                    onChange={() => setHeaderType(value)}
                    disabled={value === "video" || value === "document"}
                    className="w-4 h-4 accent-[#24422e]"
                  />
                  <span
                    className={`text-sm font-medium ${
                      value === "video" || value === "document"
                        ? "text-gray-300"
                        : "text-gray-700"
                    }`}
                  >
                    {label}
                  </span>
                </label>
              ))}
            </div>

            {headerType === "text" && (
              <input
                value={headerText}
                onChange={(e) => setHeaderText(e.target.value)}
                className="w-full border border-gray-200 rounded-xl px-4 py-3 text-sm mt-4 focus:outline-none focus:ring-2 focus:ring-[#24422e]/20 focus:border-[#24422e]"
                placeholder="Enter header text..."
              />
            )}

            {headerType === "image" && (
              <div className="mt-4 space-y-3">
                {headerImageUrl ? (
                  <div className="relative w-full rounded-xl overflow-hidden border bg-white">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={headerImageUrl}
                      alt="header preview"
                      className="w-full max-h-40 object-cover"
                    />
                    <button
                      onClick={() => setHeaderImageUrl("")}
                      className="absolute top-2 right-2 bg-black/50 hover:bg-black/70 text-white rounded-full p-1 transition"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ) : (
                  <label
                    className={`flex flex-col items-center justify-center gap-2 border-2 border-dashed rounded-xl p-6 cursor-pointer transition ${
                      uploadingImage
                        ? "opacity-50 pointer-events-none"
                        : "hover:border-[#24422e]/40 hover:bg-[#24422e]/5"
                    }`}
                  >
                    <input
                      type="file"
                      accept="image/jpeg,image/png,image/webp,image/gif"
                      className="sr-only"
                      onChange={async (e) => {
                        const image = e.target.files?.[0];
                        if (!image) return;
                        setUploadingImage(true);
                        try {
                          const form = new FormData();
                          form.append("file", image);
                          const { data } = await api.post(
                            "/media/upload",
                            form,
                            {
                              headers: {
                                "Content-Type": "multipart/form-data",
                              },
                            },
                          );
                          setHeaderImageUrl(data.url);
                        } catch (err) {
                          toast.error(parseApiError(err).message);
                        } finally {
                          setUploadingImage(false);
                        }
                      }}
                    />
                    {uploadingImage ? (
                      <RefreshCw className="w-5 h-5 text-gray-400 animate-spin" />
                    ) : (
                      <ImageIcon className="w-5 h-5 text-gray-300" />
                    )}
                    <span className="text-xs text-gray-400 font-medium">
                      {uploadingImage
                        ? "Uploading..."
                        : "Click to upload — JPG, PNG, WEBP, GIF (max 5MB)"}
                    </span>
                  </label>
                )}
                <input
                  value={headerImageUrl}
                  onChange={(e) => setHeaderImageUrl(e.target.value)}
                  className="w-full border border-gray-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-[#24422e]/20 focus:border-[#24422e]"
                  placeholder="Or paste an image URL"
                />
              </div>
            )}
          </div>

          {/* Body Section */}
          <div className="bg-white rounded-2xl border border-gray-100 p-6 shadow-sm">
            <h3 className="text-sm font-black text-gray-900">Body</h3>
            <p className="text-xs text-gray-500 mt-1 font-medium">
              The WhatsApp message in the language you have selected
            </p>

            <textarea
              ref={textareaRef}
              value={body}
              onChange={(e) => setBody(e.target.value.slice(0, 1024))}
              rows={6}
              className="w-full border border-gray-200 rounded-xl px-4 py-3 text-sm mt-4 focus:outline-none focus:ring-2 focus:ring-[#24422e]/20 focus:border-[#24422e] resize-none pb-12"
              placeholder="Type your message here. Use {{1}}, {{2}} for variables..."
            />

            <div className="flex items-center justify-between mt-2">
              <div className="flex items-center gap-1">
                <button
                  onClick={addVariable}
                  className="inline-flex items-center gap-1.5 text-xs font-bold text-[#24422e] hover:bg-[#eff2f0] px-2 py-1 rounded-lg transition"
                >
                  <Plus className="w-3.5 h-3.5" />
                  Add variable
                </button>
              </div>

              <div className="flex items-center gap-1 bg-gray-50 p-1 rounded-xl border border-gray-100">
                <button
                  onClick={() => toast.info("AI assistant coming soon!")}
                  className="p-1.5 hover:bg-white hover:shadow-sm rounded-lg transition text-[#24422e] group"
                  title="Generate with AI"
                >
                  <Sparkles className="w-4 h-4" />
                </button>
                <div className="w-px h-4 bg-gray-200 mx-1" />
                <button
                  onClick={() => toast.info("Emoji picker coming soon!")}
                  className="p-1.5 hover:bg-white hover:shadow-sm rounded-lg transition text-gray-500"
                  title="Insert Emoji"
                >
                  <Smile className="w-4 h-4" />
                </button>
                <button
                  onClick={() => applyFormat("bold")}
                  className="p-1.5 hover:bg-white hover:shadow-sm rounded-lg transition text-gray-600 font-bold"
                  title="Bold"
                >
                  <Bold className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={() => applyFormat("italic")}
                  className="p-1.5 hover:bg-white hover:shadow-sm rounded-lg transition text-gray-600 italic"
                  title="Italic"
                >
                  <Italic className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={() => applyFormat("strikethrough")}
                  className="p-1.5 hover:bg-white hover:shadow-sm rounded-lg transition text-gray-600 line-through"
                  title="Strikethrough"
                >
                  <Strikethrough className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={() => applyFormat("code")}
                  className="p-1.5 hover:bg-white hover:shadow-sm rounded-lg transition text-gray-600"
                  title="Monospace"
                >
                  <CodeIcon className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>

            <div className="flex justify-end mt-1">
              <span
                className={`text-[11px] font-medium ${
                  body.length >= 1024 ? "text-amber-600" : "text-gray-400"
                }`}
              >
                {body.length}/1024
              </span>
            </div>

            {uniqueVars.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-3">
                {uniqueVars.map((v) => (
                  <span
                    key={v}
                    className="text-[10px] font-black px-2.5 py-1 bg-[#eff2f0] text-[#24422e] rounded-full tracking-wide"
                  >
                    {v}
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* Footer Section */}
          <div className="bg-white rounded-2xl border border-gray-100 p-6 shadow-sm">
            <h3 className="text-sm font-black text-gray-900">
              Footer (Optional)
            </h3>
            <p className="text-xs text-gray-500 mt-1 font-medium">
              Add a short line of text to the bottom of your message template.
            </p>

            <div className="relative mt-4">
              <input
                value={footer}
                onChange={(e) => setFooter(e.target.value.slice(0, 60))}
                className="w-full border border-gray-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-[#24422e]/20 focus:border-[#24422e]"
                placeholder="e.g. Reply STOP to unsubscribe"
                maxLength={60}
              />
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[11px] text-gray-400 font-medium">
                {footer.length}/60
              </span>
            </div>
          </div>

          {/* Info notice */}
          <div className="p-4 rounded-xl flex items-start gap-3 bg-[#eff2f0] border border-[#24422e]/10">
            <span className="text-[11px] leading-relaxed text-[#24422e] font-medium">
              <span className="font-bold uppercase tracking-wider">Note:</span>{" "}
              Templates are submitted to Meta for review and may take up to 24
              hours to be approved before they can be used in campaigns.
            </span>
          </div>
        </div>

        {/* Right: WhatsApp Phone Preview */}
        <aside className="hidden xl:block sticky top-6">
          <div className="rounded-2xl border border-gray-100 bg-white shadow-sm overflow-hidden">
            <div className="px-4 py-3 border-b bg-[#f8faf9] flex items-center justify-between">
              <p className="text-xs font-bold tracking-wide text-gray-500 uppercase">
                Actual Preview
              </p>
              <div className="flex items-center gap-2">
                <Smartphone className="w-4 h-4 text-[#24422e]" />
              </div>
            </div>

            {/* Phone Frame */}
            <div className="p-4">
              <div className="mx-auto w-[280px] rounded-4xl border-4 border-gray-800 bg-gray-800 overflow-hidden shadow-xl">
                {/* Status bar */}
                <div className="bg-gray-800 text-white text-[10px] flex justify-between items-center px-4 py-1">
                  <span className="font-medium">9:42</span>
                  <div className="flex gap-1 items-center">
                    <div className="w-3 h-3 rounded-full border border-white/30" />
                    <div className="w-3 h-3 rounded-full border border-white/30" />
                  </div>
                </div>

                {/* WhatsApp Header Bar */}
                <div className="bg-[#24422e] text-white px-3 py-2.5 flex items-center gap-2">
                  <ArrowLeft className="w-4 h-4" />
                  <div className="w-8 h-8 rounded-full bg-white/20 flex items-center justify-center text-xs font-bold">
                    {name ? name[0]?.toUpperCase() : "T"}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-bold truncate">
                      {name
                        ? name
                            .replace(/_/g, " ")
                            .replace(/\b\w/g, (c) => c.toUpperCase())
                        : "Template Preview"}
                    </p>
                  </div>
                  <Phone className="w-4 h-4" />
                  <MoreVertical className="w-4 h-4" />
                </div>

                {/* Chat Background */}
                <div className="bg-[#e5ddd5] min-h-[360px] flex flex-col px-2 py-3">
                  {/* Date pill */}
                  <div className="text-center mb-3">
                    <span className="text-[9px] bg-white/80 rounded-full px-3 py-0.5 text-gray-500 font-medium shadow-sm">
                      Today
                    </span>
                  </div>

                  {/* Message bubble */}
                  <div className="max-w-[90%] self-start">
                    <div className="bg-white rounded-xl rounded-tl-sm shadow-sm overflow-hidden">
                      {/* Header image */}
                      {headerType === "image" && headerImageUrl && (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={headerImageUrl}
                          alt="Header"
                          className="w-full h-28 object-cover"
                        />
                      )}

                      <div className="px-2.5 py-2">
                        {/* Header text */}
                        {headerType === "text" && headerText && (
                          <p className="text-[11px] font-bold text-gray-900 mb-1">
                            {headerText}
                          </p>
                        )}

                        {/* Body */}
                        <p
                          className="text-[11px] text-gray-800 leading-relaxed wrap-break-word preview-whatsapp-message"
                          dangerouslySetInnerHTML={{
                            __html:
                              renderPreviewText(body) ||
                              '<span class="text-gray-400 italic">Your message body will appear here...</span>',
                          }}
                        />

                        {/* Footer */}
                        {footer && (
                          <p className="text-[9px] text-gray-400 mt-1.5">
                            {footer}
                          </p>
                        )}

                        {/* Timestamp */}
                        <p className="text-[8px] text-gray-400 text-right mt-1">
                          9:42 AM
                        </p>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Input bar */}
                <div className="bg-[#f0f0f0] px-2 py-2 flex items-center gap-1.5">
                  <Smile className="w-4 h-4 text-gray-400 shrink-0" />
                  <div className="flex-1 bg-white rounded-full px-3 py-1.5 text-[10px] text-gray-400">
                    Type a message
                  </div>
                  <Paperclip className="w-4 h-4 text-gray-400 shrink-0" />
                  <Camera className="w-4 h-4 text-gray-400 shrink-0" />
                  <div className="w-6 h-6 rounded-full bg-[#24422e] flex items-center justify-center shrink-0">
                    <SendIcon className="w-3 h-3 text-white" />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
