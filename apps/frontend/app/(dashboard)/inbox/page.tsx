"use client";
import { useState, useEffect, useRef, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useUIStore } from "@/lib/ui-store";
import { toast } from "sonner";
import { parseApiError } from "@/lib/errors";
import type { Conversation, InboundMessage } from "@/types";
import {
  Send,
  ArrowLeft,
  MapPin,
  FileText,
  Image as ImageIcon,
  CheckCheck,
  Check,
} from "lucide-react";
import { cn } from "@/lib/utils";

const BRAND_GRADIENT = "linear-gradient(135deg, #24422e, #3a6b47)";

/* ─── Helpers ────────────────────────────────────────────── */

function getPreview(conv: Conversation): string {
  const t = conv.last_message_type;
  if (t === "image") return "🖼️ Photo";
  if (t === "document") return "📎 Document";
  if (t === "location") return "📍 Location";
  return conv.last_message ?? "";
}

/* ─── Quick reply suggestions ─────────────────────────────── */

function getQuickReplies(lastMsg: InboundMessage | undefined): string[] {
  if (lastMsg?.direction !== "inbound") return [];

  if (lastMsg.message_type === "location")
    return [
      "I can see you! Head to the main entrance 🚪",
      "We're just 2 minutes from your location!",
      "Our team is on the way to guide you.",
    ];
  if (lastMsg.message_type === "image")
    return [
      "Thank you for sharing! Looks amazing 😍",
      "We'd love to repost this — may we?",
      "So glad you caught that moment with us!",
    ];
  if (lastMsg.message_type === "document")
    return [
      "Got it, we'll review this shortly!",
      "Thanks for sending the document.",
      "We'll get back to you within 24 hours.",
    ];

  const body = (lastMsg.body ?? "").toLowerCase();
  if (/table|reserv|book|seat/.test(body))
    return [
      "Yes, table confirmed! ✅",
      "Sorry, we're fully booked tonight.",
      "How many guests would you like?",
      "What time works best for you?",
    ];
  if (/menu|food|dish|eat|veg|allergi/.test(body))
    return [
      "Here's our menu 📄",
      "We have great vegetarian options!",
      "Our chef's special tonight is the tasting menu.",
      "Any dietary requirements I should note?",
    ];
  if (/invoice|bill|receipt|payment/.test(body))
    return [
      "Sending the invoice right away! 📎",
      "Can you share the visit date?",
      "Your bill has been emailed to you.",
    ];
  if (/thank|great|love|amazing|perfect|happy/.test(body))
    return [
      "So glad you enjoyed it! 🙏",
      "You're always welcome with us!",
      "Do leave us a review — it helps a lot 🌟",
    ];
  if (/open|close|timing|time|hour/.test(body))
    return [
      "We're open 12 PM – 11 PM daily.",
      "Kitchen closes at 10:30 PM.",
      "We're open 7 days a week!",
    ];
  if (/location|where|address|find|direction/.test(body))
    return [
      "We're at Marine Drive, opposite the fountain.",
      "I'll share the Google Maps link!",
      "Nearest landmark is the Metro Station.",
    ];

  return [
    "Sure, let me check that for you!",
    "Thanks for reaching out 🙏",
    "We'll get back to you shortly.",
    "Happy to help!",
  ];
}

function initials(name: string | null, phone: string): string {
  if (!name) return phone.slice(-2);
  return name
    .split(" ")
    .map((w) => w[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

/* ─── Component ────────────────────────────────────────────── */

export default function InboxPage() {
  const qc = useQueryClient();
  const [selected, setSelected] = useState<string | null>(null);
  const [reply, setReply] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const setInboxUnread = useUIStore((s) => s.setInboxUnread);

  const { data: convsData } = useQuery<{
    items: Conversation[];
    total: number;
  }>({
    queryKey: ["inbox-conversations"],
    queryFn: () =>
      api.get("/inbox/conversations?page=1&page_size=50").then((r) => r.data),
    refetchInterval: 15_000,
  });

  const convs = useMemo(() => convsData?.items ?? [], [convsData]);

  // Keep global unread count in sync
  useEffect(() => {
    const total = convs.reduce((sum, c) => sum + c.unread_count, 0);
    setInboxUnread(total);
  }, [convs, setInboxUnread]);

  const { data: messages } = useQuery<InboundMessage[]>({
    queryKey: ["inbox-messages", selected],
    queryFn: () =>
      api
        .get(`/inbox/conversations/${encodeURIComponent(selected ?? "")}`)
        .then((r) => r.data),
    enabled: !!selected,
    refetchInterval: 8_000,
  });

  // Sorted oldest-first for display (API returns newest-first)
  const thread = messages ? [...messages].reverse() : [];

  // Auto-scroll on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [thread.length, selected]);

  // Mark read when conversation opened
  const markReadMutation = useMutation({
    mutationFn: (phone: string) =>
      api.post(`/inbox/conversations/${encodeURIComponent(phone)}/read`),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["inbox-conversations"] }),
  });

  const selectConv = (phone: string) => {
    setSelected(phone);
    markReadMutation.mutate(phone);
  };

  const replyMutation = useMutation({
    mutationFn: (body: string) =>
      api.post(`/inbox/conversations/${encodeURIComponent(selected ?? "")}/reply`, {
        body,
      }),
    onSuccess: () => {
      setReply("");
      qc.invalidateQueries({ queryKey: ["inbox-messages", selected] });
      qc.invalidateQueries({ queryKey: ["inbox-conversations"] });
    },
    onError: (e: unknown) => toast.error(parseApiError(e).message),
  });

  const sendReply = () => {
    if (!reply.trim() || !selected) return;
    replyMutation.mutate(reply.trim());
  };

  const activeConv = convs.find((c) => c.from_phone === selected) ?? null;
  const suggestions = getQuickReplies(thread.at(-1));

  return (
    <div className="h-full flex rounded-xl border bg-white overflow-hidden">
      {/* ── Conversation list ── */}
      <div
        className={cn(
          "w-full sm:w-72 border-r flex flex-col shrink-0",
          selected ? "hidden sm:flex" : "flex",
        )}
      >
        <div className="px-4 py-3 border-b">
          <h2 className="font-semibold text-sm text-[#24422e]">Inbox</h2>
          <p className="text-xs text-gray-400 mt-0.5">
            {convs.filter((c) => c.unread_count > 0).length} unread
          </p>
        </div>
        <div className="flex-1 overflow-y-auto divide-y">
          {convs.length === 0 && (
            <p className="text-xs text-gray-400 text-center py-10">
              No conversations yet
            </p>
          )}
          {convs.map((c) => (
            <button
              key={c.from_phone}
              onClick={() => selectConv(c.from_phone)}
              className={cn(
                "w-full text-left px-4 py-3 transition flex items-start gap-3",
                selected === c.from_phone
                  ? "bg-[#24422e]/10"
                  : "hover:bg-[#24422e]/5",
              )}
            >
              <div
                className="w-9 h-9 rounded-full flex items-center justify-center text-xs font-bold text-white shrink-0 mt-0.5"
                style={{ background: BRAND_GRADIENT }}
              >
                {initials(c.sender_name, c.from_phone)}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-1">
                  <p
                    className={cn(
                      "text-sm truncate",
                      c.unread_count > 0 ? "font-semibold" : "font-medium",
                    )}
                  >
                    {c.sender_name ?? c.from_phone}
                  </p>
                  <span className="text-[10px] text-gray-400 shrink-0">
                    {new Date(c.last_received_at).toLocaleTimeString("en-IN", {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </span>
                </div>
                <div className="flex items-center justify-between gap-1 mt-0.5">
                  <p
                    className={cn(
                      "text-xs truncate",
                      c.unread_count > 0 ? "text-gray-700" : "text-gray-400",
                    )}
                  >
                    {getPreview(c)}
                  </p>
                  {c.unread_count > 0 && (
                    <span
                      className="w-5 h-5 text-white text-[10px] rounded-full flex items-center justify-center shrink-0 font-semibold"
                      style={{ background: BRAND_GRADIENT }}
                    >
                      {c.unread_count}
                    </span>
                  )}
                </div>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* ── Chat thread ── */}
      <div
        className={cn(
          "flex-1 flex flex-col",
          selected ? "flex" : "hidden sm:flex",
        )}
      >
      {activeConv ? (
        <>
          {/* Header */}
          <div className="px-4 py-3 border-b flex items-center gap-3">
            <button onClick={() => setSelected(null)} className="sm:hidden">
              <ArrowLeft className="w-4 h-4" />
            </button>
            <div
              className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold text-white shrink-0"
              style={{ background: BRAND_GRADIENT }}
            >
              {initials(activeConv.sender_name, activeConv.from_phone)}
            </div>
            <div>
              <p className="text-sm font-semibold text-[#24422e]">
                {activeConv.sender_name ?? activeConv.from_phone}
              </p>
              <p className="text-xs text-gray-400">{activeConv.from_phone}</p>
            </div>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-4 space-y-2 bg-gray-50/40">
            {thread.map((msg) => (
              <MessageBubble key={msg.id} msg={msg} />
            ))}
            <div ref={bottomRef} />
          </div>

          {/* Quick reply suggestions + reply bar — unified bottom panel */}
          <div className="border-t bg-white">
            {suggestions.length > 0 && (
              <div className="px-4 pt-3 pb-2 flex flex-wrap gap-1.5">
                {suggestions.map((s) => (
                  <button
                    key={s}
                    onClick={() => replyMutation.mutate(s)}
                    disabled={replyMutation.isPending}
                    className="text-xs px-3 py-1.5 rounded-full bg-[#24422e]/5 border border-[#24422e]/15 text-[#24422e] hover:bg-[#24422e] hover:text-white hover:border-transparent transition-all font-medium disabled:opacity-50"
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}
            <div className="px-4 py-3 flex gap-2 items-center">
              <input
                value={reply}
                onChange={(e) => setReply(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey && reply.trim()) {
                    e.preventDefault();
                    sendReply();
                  }
                }}
                placeholder="Type a message…"
                className="flex-1 bg-gray-50 border border-gray-200 rounded-full px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#24422e]/25 focus:border-[#24422e]/40 transition"
              />
              <button
                onClick={sendReply}
                disabled={!reply.trim() || replyMutation.isPending}
                className="w-9 h-9 text-white rounded-full flex items-center justify-center transition-all disabled:opacity-30 hover:scale-105"
                style={{ background: BRAND_GRADIENT }}
              >
                <Send className="w-4 h-4" />
              </button>
            </div>
          </div>
        </>
      ) : (
        <div className="flex-1 flex flex-col items-center justify-center text-gray-400 gap-2">
          <div className="w-12 h-12 rounded-full bg-[#24422e]/10 flex items-center justify-center">
            <Send className="w-5 h-5 text-[#24422e]" />
          </div>
          <p className="text-sm">Select a conversation to start</p>
        </div>
      )}
      </div>
    </div>
  );
}

/* ─── Message bubble ───────────────────────────────────────── */
function MessageBubble({ msg }: { msg: InboundMessage }) {
  const out = msg.direction === "outbound";
  return (
    <div className={cn("flex", out ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-xs lg:max-w-md rounded-2xl px-4 py-2.5 shadow-sm",
          out
            ? "text-white rounded-tr-sm"
            : "bg-white border text-gray-900 rounded-tl-sm",
        )}
        style={
          out
            ? { background: "linear-gradient(135deg, #24422e, #3a6b47)" }
            : undefined
        }
      >
        {msg.message_type === "text" && (
          <p className="text-sm leading-relaxed">{msg.body}</p>
        )}
        {msg.message_type === "image" && (
          <div className="flex items-center gap-2 text-sm">
            <ImageIcon className="w-4 h-4 shrink-0" />
            <span>{msg.body || "Image"}</span>
            {msg.media_url && (
              <a
                href={msg.media_url}
                className={cn(
                  "underline text-xs",
                  out ? "text-white/70" : "text-[#24422e]",
                )}
              >
                View
              </a>
            )}
          </div>
        )}
        {msg.message_type === "document" && (
          <div className="flex items-center gap-2 text-sm">
            <FileText className="w-4 h-4 shrink-0" />
            <span className="truncate max-w-[180px]">
              {msg.body || "Document"}
            </span>
            {msg.media_url && (
              <a
                href={msg.media_url}
                className={cn(
                  "underline text-xs shrink-0",
                  out ? "text-white/70" : "text-[#24422e]",
                )}
              >
                Download
              </a>
            )}
          </div>
        )}
        {msg.message_type === "location" && msg.location && (
          <div className="flex items-center gap-2 text-sm">
            <MapPin className="w-4 h-4 shrink-0" />
            <a
              href={`https://maps.google.com/?q=${msg.location.lat},${msg.location.lng}`}
              target="_blank"
              rel="noreferrer"
              className={cn(
                "underline",
                out ? "text-white/70" : "text-[#24422e]",
              )}
            >
              {msg.location.name ?? `${msg.location.lat}, ${msg.location.lng}`}
            </a>
          </div>
        )}
        <div
          className={cn(
            "flex items-center gap-1 mt-1 justify-end",
            out ? "text-white/60" : "text-gray-400",
          )}
        >
          <span className="text-[10px]">
            {new Date(msg.received_at).toLocaleTimeString("en-IN", {
              hour: "2-digit",
              minute: "2-digit",
            })}
          </span>
          {out &&
            (msg.is_read ? (
              <CheckCheck className="w-3 h-3 text-white/80" />
            ) : (
              <Check className="w-3 h-3 text-white/50" />
            ))}
        </div>
      </div>
    </div>
  );
}
