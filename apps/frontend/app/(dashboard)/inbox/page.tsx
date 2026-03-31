"use client";
import { useState, useEffect, useRef, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useUIStore } from "@/lib/ui-store";
import { toast } from "sonner";
import { parseApiError } from "@/lib/errors";
import type { Conversation, InboundMessage } from "@/types";
import { Send, ArrowLeft, Search } from "lucide-react";
import { cn } from "@/lib/utils";
import { MessageBubble } from "@/components/inbox/atoms/MessageBubble";
import { ConversationItem } from "@/components/inbox/molecules/ConversationItem";
import { QuickReplies } from "@/components/inbox/molecules/QuickReplies";
import { ReplyBar } from "@/components/inbox/molecules/ReplyBar";

const BRAND_GRADIENT = "linear-gradient(135deg, #24422e, #3a6b47)";

function initials(name: string | null, phone: string): string {
  if (!name) return phone.slice(-2);
  return name
    .split(" ")
    .map((w) => w[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

function DateSeparator({ date }: { date: string }) {
  const dStr = String(date);
  const d = new Date(dStr.endsWith("Z") ? dStr : dStr + "Z");
  const now = new Date();
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);

  let label = d.toLocaleDateString("en-IN", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
  if (d.toDateString() === now.toDateString()) label = "Today";
  else if (d.toDateString() === yesterday.toDateString()) label = "Yesterday";

  return (
    <div className="flex justify-center my-6 sticky top-2 z-10">
      <span className="px-4 py-1.5 bg-[#eff2f0] text-[#24422e] text-[10px] font-black uppercase tracking-widest rounded-full shadow-sm border border-[#24422e]/5">
        {label}
      </span>
    </div>
  );
}

export default function InboxPage() {
  const qc = useQueryClient();
  const [selected, setSelected] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
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

  const filteredConvs = useMemo(() => {
    if (!searchQuery.trim()) return convs;
    const q = searchQuery.toLowerCase();
    return convs.filter(
      (c) =>
        (c.sender_name?.toLowerCase() || "").includes(q) ||
        c.from_phone.includes(q),
    );
  }, [convs, searchQuery]);

  useEffect(() => {
    setInboxUnread(convs.reduce((sum, c) => sum + c.unread_count, 0));
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

  const thread = messages ? [...messages].reverse() : [];

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [thread.length, selected]);

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
      api.post(
        `/inbox/conversations/${encodeURIComponent(selected ?? "")}/reply`,
        { body },
      ),
    onSuccess: () => {
      setReply("");
      qc.invalidateQueries({ queryKey: ["inbox-messages", selected] });
      qc.invalidateQueries({ queryKey: ["inbox-conversations"] });
    },
    onError: (e: unknown) => toast.error(parseApiError(e).message),
  });

  const activeConv = convs.find((c) => c.from_phone === selected) ?? null;

  return (
    <div className="h-full flex bg-white overflow-hidden">
      {/* Conversation list */}
      <div
        className={cn(
          "w-full sm:w-80 border-r border-gray-100 flex flex-col shrink-0 bg-[#eff2f0]/20",
          selected ? "hidden sm:flex" : "flex",
        )}
      >
        <div className="px-6 py-5 border-b border-gray-100 bg-white/50 backdrop-blur-sm">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-[#eff2f0] rounded-lg">
              <Send className="w-5 h-5 text-[#24422e]" />
            </div>
            <h2 className="text-xl font-black text-gray-900 tracking-tight">
              Inbox
            </h2>
          </div>
          <div className="mt-4 relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              placeholder="Search by name or number..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-[#eff2f0]/50 border-none rounded-xl pl-9 pr-4 py-2.5 text-sm font-medium text-gray-900 placeholder:text-gray-400 focus:ring-2 focus:ring-[#24422e]/20 transition-all outline-none"
            />
          </div>
          <div className="flex items-center justify-between mt-4">
            <p className="text-[10px] font-black text-[#24422e]/40 uppercase tracking-widest">
              Recent Chats
            </p>
            <span className="px-2 py-0.5 bg-[#eff2f0] text-[#24422e] text-[10px] font-bold rounded-full">
              {convs.filter((c) => c.unread_count > 0).length} UNREAD
            </span>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto custom-scrollbar">
          {filteredConvs.length === 0 && (
            <div className="flex flex-col items-center justify-center h-40 text-center px-4">
              <p className="text-xs font-bold text-gray-400 uppercase tracking-widest">
                No conversations found
              </p>
            </div>
          )}
          {filteredConvs.map((c) => (
            <ConversationItem
              key={c.from_phone}
              conv={c}
              selected={selected === c.from_phone}
              onClick={() => selectConv(c.from_phone)}
            />
          ))}
        </div>
      </div>

      {/* Chat thread */}
      <div
        className={cn(
          "flex-1 flex flex-col bg-white",
          selected ? "flex" : "hidden sm:flex",
        )}
      >
        {activeConv ? (
          <>
            <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between bg-white/80 backdrop-blur-md z-20">
              <div className="flex items-center gap-4">
                <button
                  onClick={() => setSelected(null)}
                  className="sm:hidden p-2 hover:bg-[#eff2f0] rounded-xl transition-colors"
                >
                  <ArrowLeft className="w-5 h-5 text-[#24422e]" />
                </button>
                <div
                  className="w-10 h-10 rounded-2xl flex items-center justify-center text-sm font-black text-white shrink-0 shadow-lg shadow-green-900/10 transition-transform active:scale-95"
                  style={{ background: BRAND_GRADIENT }}
                >
                  {initials(activeConv.sender_name, activeConv.from_phone)}
                </div>
                <div>
                  <p className="text-sm font-black text-gray-900 tracking-tight">
                    {activeConv.sender_name ?? activeConv.from_phone}
                  </p>
                  <p className="text-[10px] font-bold text-[#24422e]/40 uppercase tracking-widest">
                    {activeConv.from_phone}
                  </p>
                </div>
              </div>
            </div>
            <div className="flex-1 overflow-y-auto px-6 py-4 bg-gray-50/30 custom-scrollbar">
              {thread.map((msg, i) => {
                const prev = thread[i - 1];
                const dStr = String(msg.received_at);
                const currentMsgDate = new Date(
                  dStr.endsWith("Z") ? dStr : dStr + "Z",
                );
                let showDate = !prev;
                if (prev) {
                  const pStr = String(prev.received_at);
                  const prevMsgDate = new Date(
                    pStr.endsWith("Z") ? pStr : pStr + "Z",
                  );
                  showDate =
                    currentMsgDate.toDateString() !==
                    prevMsgDate.toDateString();
                }

                return (
                  <div key={msg.id} className="space-y-1">
                    {showDate && <DateSeparator date={msg.received_at} />}
                    <MessageBubble msg={msg} />
                  </div>
                );
              })}
              <div ref={bottomRef} />
            </div>
            <div className="border-t bg-white">
              <QuickReplies
                lastMessage={thread.at(-1)}
                onSelect={(s) => replyMutation.mutate(s)}
                disabled={replyMutation.isPending}
              />
              <ReplyBar
                value={reply}
                onChange={setReply}
                onSend={() => {
                  if (reply.trim()) replyMutation.mutate(reply.trim());
                }}
                disabled={replyMutation.isPending}
              />
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
