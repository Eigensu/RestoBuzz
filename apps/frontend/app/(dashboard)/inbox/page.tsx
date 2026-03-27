"use client";
import { useState, useEffect, useRef } from "react";
import { useUIStore } from "@/lib/ui-store";
import { Send, ArrowLeft, MapPin, FileText, Image, CheckCheck, Check } from "lucide-react";
import { cn } from "@/lib/utils";

/* ─── Mock data ────────────────────────────────────────────── */

type MsgType = "text" | "image" | "document" | "location";

interface MockMsg {
  id: string;
  direction: "inbound" | "outbound";
  message_type: MsgType;
  body?: string;
  media_url?: string;
  location?: { lat: number; lng: number; name?: string };
  time: string;
  seen?: boolean; // outbound read receipt
}

interface MockConv {
  id: string;
  name: string;
  phone: string;
  avatar: string;
  last_at: string;
  unread: number;
  messages: MockMsg[];
}

function getPreview(conv: MockConv): string {
  const last = conv.messages[conv.messages.length - 1];
  if (!last) return "";
  const prefix = last.direction === "outbound" ? "You: " : "";
  if (last.message_type === "text") return prefix + (last.body ?? "");
  if (last.message_type === "image") return prefix + "🖼️ Photo";
  if (last.message_type === "document") return prefix + "📎 " + (last.body ?? "Document");
  if (last.message_type === "location") return prefix + "📍 Location";
  return prefix + "[message]";
}

const MOCK_CONVS: MockConv[] = [
  {
    id: "1",
    name: "Arjun Mehta",
    phone: "+91 98201 34567",
    avatar: "AM",
    last_at: "2m ago",
    unread: 3,
    messages: [
      { id: "m1", direction: "outbound", message_type: "text", body: "Hi Arjun! Your table at Gigi West End is confirmed for tonight 🎉", time: "7:30 PM", seen: true },
      { id: "m2", direction: "inbound",  message_type: "text", body: "Amazing, thank you so much!", time: "7:31 PM" },
      { id: "m3", direction: "outbound", message_type: "text", body: "We've attached the menu for your preview.", time: "7:32 PM", seen: true },
      { id: "m4", direction: "outbound", message_type: "document", body: "Gigi_Menu.pdf", media_url: "#", time: "7:32 PM", seen: true },
      { id: "m5", direction: "inbound",  message_type: "text", body: "Got it! The tasting menu looks fantastic.", time: "7:45 PM" },
      { id: "m6", direction: "inbound",  message_type: "text", body: "Thanks! Will be there at 8pm 🙌", time: "7:46 PM" },
    ],
  },
  {
    id: "2",
    name: "Priya Kaur",
    phone: "+91 91234 56789",
    avatar: "PK",
    last_at: "15m ago",
    unread: 1,
    messages: [
      { id: "m1", direction: "inbound",  message_type: "text", body: "Hi, I'm trying to find the restaurant. Can you help?", time: "6:50 PM" },
      { id: "m2", direction: "outbound", message_type: "text", body: "Of course! We're right on Marine Drive, opposite the fountain.", time: "6:51 PM", seen: true },
      { id: "m3", direction: "inbound",  message_type: "location", location: { lat: 18.9548, lng: 72.8234, name: "Marine Drive, Mumbai" }, time: "6:53 PM" },
      { id: "m4", direction: "outbound", message_type: "text", body: "Perfect, I can see you're just 2 minutes away!", time: "6:54 PM", seen: false },
    ],
  },
  {
    id: "3",
    name: "Ravi Shankar",
    phone: "+91 77001 22334",
    avatar: "RS",
    last_at: "1h ago",
    unread: 0,
    messages: [
      { id: "m1", direction: "inbound",  message_type: "text", body: "Hey, quick question — is the kitchen still open?", time: "5:15 PM" },
      { id: "m2", direction: "outbound", message_type: "text", body: "Hi Ravi! Yes, kitchen closes at 10:30 PM tonight.", time: "5:17 PM", seen: true },
      { id: "m3", direction: "inbound",  message_type: "text", body: "Great, we'll be there by 9!", time: "5:18 PM" },
      { id: "m4", direction: "outbound", message_type: "text", body: "Wonderful! Shall I reserve a table for you?", time: "5:19 PM", seen: true },
      { id: "m5", direction: "inbound",  message_type: "text", body: "Yes please — 4 people.", time: "5:20 PM" },
      { id: "m6", direction: "outbound", message_type: "text", body: "Done! Table for 4 at 9 PM. See you soon 🙂", time: "5:21 PM", seen: true },
    ],
  },
  {
    id: "4",
    name: "Nisha D'Souza",
    phone: "+91 88990 11223",
    avatar: "ND",
    last_at: "3h ago",
    unread: 0,
    messages: [
      { id: "m1", direction: "outbound", message_type: "text", body: "Hi Nisha! How was your dinner experience with us last night?", time: "11:00 AM", seen: true },
      { id: "m2", direction: "inbound",  message_type: "image", body: "Photo from dinner", media_url: "#", time: "11:05 AM" },
      { id: "m3", direction: "inbound",  message_type: "text", body: "❤️ Loved the experience! The ambience was gorgeous.", time: "11:06 AM" },
      { id: "m4", direction: "outbound", message_type: "text", body: "That makes us so happy to hear! Thank you 🙌", time: "11:08 AM", seen: true },
    ],
  },
  {
    id: "5",
    name: "Farukh Tashkentov",
    phone: "+91 99887 76655",
    avatar: "FT",
    last_at: "Yesterday",
    unread: 2,
    messages: [
      { id: "m1", direction: "inbound",  message_type: "text", body: "Hi, I had a corporate dinner last Friday. Can I get the invoice?", time: "Yesterday 4:00 PM" },
      { id: "m2", direction: "outbound", message_type: "text", body: "Of course Farukh! Let me pull that up for you.", time: "Yesterday 4:05 PM", seen: true },
      { id: "m3", direction: "outbound", message_type: "document", body: "Invoice_Corporate_March.pdf", media_url: "#", time: "Yesterday 4:07 PM", seen: false },
      { id: "m4", direction: "inbound",  message_type: "text", body: "Thanks! But can you also send the itemised breakdown?", time: "Yesterday 5:00 PM" },
      { id: "m5", direction: "inbound",  message_type: "text", body: "Please send me the invoice", time: "Yesterday 5:01 PM" },
    ],
  },
];

/* ─── Quick reply suggestions ─────────────────────────────── */
function getQuickReplies(conv: MockConv): string[] {
  // Only show suggestions if the very last message is from the customer
  const lastMsg = conv.messages[conv.messages.length - 1];
  if (!lastMsg || lastMsg.direction !== "inbound") return [];
  const last = lastMsg;
  if (!last) return [];

  if (last.message_type === "location") {
    return [
      "I can see you! Head to the main entrance 🚪",
      "We're just 2 minutes from your location!",
      "Our team is on the way to guide you.",
    ];
  }

  if (last.message_type === "image") {
    return [
      "Thank you for sharing! Looks amazing 😍",
      "We'd love to repost this — may we?",
      "So glad you caught that moment with us!",
    ];
  }

  if (last.message_type === "document") {
    return [
      "Got it, we'll review this shortly!",
      "Thanks for sending the document.",
      "We'll get back to you within 24 hours.",
    ];
  }

  // Text: keyword matching
  const body = (last.body ?? "").toLowerCase();

  if (/table|reserv|book|seat/.test(body)) {
    return [
      "Yes, table confirmed! ✅",
      "Sorry, we're fully booked tonight.",
      "How many guests would you like?",
      "What time works best for you?",
    ];
  }
  if (/menu|food|dish|eat|veg|non-veg|allergi/.test(body)) {
    return [
      "Here's our menu 📄",
      "We have great vegetarian options!",
      "Our chef's special tonight is the tasting menu.",
      "Any dietary requirements I should note?",
    ];
  }
  if (/invoice|bill|receipt|payment|paid/.test(body)) {
    return [
      "Sending the invoice right away! 📎",
      "Can you share the visit date?",
      "Your bill has been emailed to you.",
      "We accept UPI, cards and cash.",
    ];
  }
  if (/thank|great|love|beautiful|amazing|perfect|happy/.test(body)) {
    return [
      "So glad you enjoyed it! 🙏",
      "You're always welcome with us!",
      "We'd love to see you again soon!",
      "Do leave us a review — it helps a lot 🌟",
    ];
  }
  if (/open|close|timing|time|hour/.test(body)) {
    return [
      "We're open 12 PM – 11 PM daily.",
      "Kitchen closes at 10:30 PM.",
      "We're open 7 days a week!",
    ];
  }
  if (/location|where|address|find|direction/.test(body)) {
    return [
      "We're at Marine Drive, opposite the fountain.",
      "I'll share the Google Maps link!",
      "Nearest landmark is the Metro Station.",
    ];
  }

  // Generic fallback
  return [
    "Sure, let me check that for you!",
    "Thanks for reaching out 🙏",
    "We'll get back to you shortly.",
    "Happy to help!",
  ];
}

/* ─── Component ────────────────────────────────────────────── */

export default function InboxPage() {
  const [selected, setSelected] = useState<string | null>(null);
  const [reply, setReply] = useState("");
  const [convs, setConvs] = useState(MOCK_CONVS);
  const bottomRef = useRef<HTMLDivElement>(null);
  const setInboxUnread = useUIStore((s) => s.setInboxUnread);

  // Keep global unread count in sync
  useEffect(() => {
    const total = convs.reduce((sum, c) => sum + c.unread, 0);
    setInboxUnread(total);
  }, [convs, setInboxUnread]);

  const activeConv = convs.find((c) => c.id === selected) ?? null;

  // Auto-scroll on open/new message
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [activeConv?.messages.length, selected]);

  // Mark as read when opened
  useEffect(() => {
    if (selected) {
      setConvs((prev) =>
        prev.map((c) => (c.id === selected ? { ...c, unread: 0 } : c))
      );
    }
  }, [selected]);

  const sendReply = () => {
    if (!reply.trim() || !selected) return;
    const newMsg: MockMsg = {
      id: `m${Date.now()}`,
      direction: "outbound",
      message_type: "text",
      body: reply.trim(),
      time: new Date().toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" }),
      seen: false,
    };
    setConvs((prev) =>
      prev.map((c) =>
        c.id === selected
          ? { ...c, messages: [...c.messages, newMsg], last_message: reply.trim(), last_at: "just now" }
          : c
      )
    );
    setReply("");
  };

  return (
    <div className="h-full flex rounded-xl border bg-white overflow-hidden">
      {/* ── Conversation list ── */}
      <div
        className={cn(
          "w-full sm:w-72 border-r flex flex-col flex-shrink-0",
          selected ? "hidden sm:flex" : "flex"
        )}
      >
        <div className="px-4 py-3 border-b">
          <h2 className="font-semibold text-sm text-[#24422e]">Inbox</h2>
          <p className="text-xs text-gray-400 mt-0.5">{convs.filter((c) => c.unread > 0).length} unread</p>
        </div>
        <div className="flex-1 overflow-y-auto divide-y">
          {convs.map((c) => (
            <button
              key={c.id}
              onClick={() => setSelected(c.id)}
              className={cn(
                "w-full text-left px-4 py-3 transition flex items-start gap-3",
                selected === c.id
                  ? "bg-[#24422e]/10"
                  : "hover:bg-[#24422e]/5"
              )}
            >
              {/* Avatar */}
              <div
                className="w-9 h-9 rounded-full flex items-center justify-center text-xs font-bold text-white shrink-0 mt-0.5"
                style={{ background: "linear-gradient(135deg, #24422e, #3a6b47)" }}
              >
                {c.avatar}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-1">
                  <p className={cn("text-sm truncate", c.unread > 0 ? "font-semibold" : "font-medium")}>
                    {c.name}
                  </p>
                  <span className="text-[10px] text-gray-400 shrink-0">{c.last_at}</span>
                </div>
                <div className="flex items-center justify-between gap-1 mt-0.5">
                   <p className={cn("text-xs truncate", c.unread > 0 ? "text-gray-700" : "text-gray-400")}>
                    {getPreview(c)}
                  </p>
                  {c.unread > 0 && (
                    <span
                      className="w-5 h-5 text-white text-[10px] rounded-full flex items-center justify-center shrink-0 font-semibold"
                      style={{ background: "linear-gradient(135deg, #24422e, #3a6b47)" }}
                    >
                      {c.unread}
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
          !selected ? "hidden sm:flex" : "flex"
        )}
      >
        {!activeConv ? (
          <div className="flex-1 flex flex-col items-center justify-center text-gray-400 gap-2">
            <div className="w-12 h-12 rounded-full bg-[#24422e]/10 flex items-center justify-center">
              <Send className="w-5 h-5 text-[#24422e]" />
            </div>
            <p className="text-sm">Select a conversation to start</p>
          </div>
        ) : (
          <>
            {/* Header */}
            <div className="px-4 py-3 border-b flex items-center gap-3">
              <button onClick={() => setSelected(null)} className="sm:hidden">
                <ArrowLeft className="w-4 h-4" />
              </button>
              <div
                className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold text-white shrink-0"
                style={{ background: "linear-gradient(135deg, #24422e, #3a6b47)" }}
              >
                {activeConv.avatar}
              </div>
              <div>
                <p className="text-sm font-semibold text-[#24422e]">{activeConv.name}</p>
                <p className="text-xs text-gray-400">{activeConv.phone}</p>
              </div>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-4 space-y-2 bg-gray-50/40">
              {activeConv.messages.map((msg) => (
                <MessageBubble key={msg.id} msg={msg} />
              ))}
              <div ref={bottomRef} />
            </div>

            {/* Quick reply suggestions */}
            {(() => {
              const suggestions = activeConv ? getQuickReplies(activeConv) : [];
              if (!suggestions.length) return null;
              return (
                <div className="px-4 pt-2 pb-1 flex flex-wrap gap-2 border-t bg-white">
                  {suggestions.map((s) => (
                    <button
                      key={s}
                      onClick={() => {
                        setReply(s);
                        setTimeout(() => {
                          const newMsg: MockMsg = {
                            id: `m${Date.now()}`,
                            direction: "outbound",
                            message_type: "text",
                            body: s,
                            time: new Date().toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" }),
                            seen: false,
                          };
                          setConvs((prev) =>
                            prev.map((c) =>
                              c.id === selected
                                ? { ...c, messages: [...c.messages, newMsg], last_at: "just now" }
                                : c
                            )
                          );
                          setReply("");
                        }, 0);
                      }}
                      className="text-xs px-3 py-1.5 rounded-full border border-[#24422e]/30 text-[#24422e] hover:bg-[#24422e] hover:text-white transition font-medium"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              );
            })()}

            {/* Reply bar */}
            <div className="px-4 py-3 border-t flex gap-2 bg-white">
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
                className="flex-1 border border-[#24422e]/30 rounded-full px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#24422e]/30"
              />
              <button
                onClick={sendReply}
                disabled={!reply.trim()}
                className="w-9 h-9 text-white rounded-full flex items-center justify-center transition disabled:opacity-40 hover:opacity-90"
                style={{ background: "linear-gradient(135deg, #24422e, #3a6b47)" }}
              >
                <Send className="w-4 h-4" />
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

/* ─── Message bubble ───────────────────────────────────────── */
function MessageBubble({ msg }: { msg: MockMsg }) {
  const out = msg.direction === "outbound";
  return (
    <div className={cn("flex", out ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-xs lg:max-w-md rounded-2xl px-4 py-2.5 shadow-sm",
          out
            ? "text-white rounded-tr-sm"
            : "bg-white border text-gray-900 rounded-tl-sm"
        )}
        style={out ? { background: "linear-gradient(135deg, #24422e, #3a6b47)" } : undefined}
      >
        {/* Text */}
        {msg.message_type === "text" && <p className="text-sm leading-relaxed">{msg.body}</p>}

        {/* Image */}
        {msg.message_type === "image" && (
          <div className="flex items-center gap-2 text-sm">
            <Image className="w-4 h-4 shrink-0" />
            <span>{msg.body || "Image"}</span>
            {msg.media_url && (
              <a href={msg.media_url} className={cn("underline text-xs", out ? "text-white/70" : "text-[#24422e]")}>
                View
              </a>
            )}
          </div>
        )}

        {/* Document */}
        {msg.message_type === "document" && (
          <div className="flex items-center gap-2 text-sm">
            <FileText className="w-4 h-4 shrink-0" />
            <span className="truncate max-w-[180px]">{msg.body || "Document"}</span>
            {msg.media_url && (
              <a href={msg.media_url} className={cn("underline text-xs shrink-0", out ? "text-white/70" : "text-[#24422e]")}>
                Download
              </a>
            )}
          </div>
        )}

        {/* Location */}
        {msg.message_type === "location" && msg.location && (
          <div className="flex items-center gap-2 text-sm">
            <MapPin className="w-4 h-4 shrink-0" />
            <a
              href={`https://maps.google.com/?q=${msg.location.lat},${msg.location.lng}`}
              target="_blank"
              rel="noreferrer"
              className={cn("underline", out ? "text-white/70" : "text-[#24422e]")}
            >
              {msg.location.name || `${msg.location.lat}, ${msg.location.lng}`}
            </a>
          </div>
        )}

        {/* Timestamp + read receipt */}
        <div className={cn("flex items-center gap-1 mt-1 justify-end", out ? "text-white/60" : "text-gray-400")}>
          <span className="text-[10px]">{msg.time}</span>
          {out && (
            msg.seen
              ? <CheckCheck className="w-3 h-3 text-white/80" />
              : <Check className="w-3 h-3 text-white/50" />
          )}
        </div>
      </div>
    </div>
  );
}
