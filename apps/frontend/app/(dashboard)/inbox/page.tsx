"use client";
import { useState, useEffect, useRef, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useUIStore } from "@/lib/ui-store";
import { toast } from "sonner";
import { parseApiError } from "@/lib/errors";
import type { Conversation, InboundMessage } from "@/types";
import { Send, ArrowLeft } from "lucide-react";
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
    <div className="h-full flex rounded-xl border bg-white overflow-hidden">
      {/* Conversation list */}
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
          "flex-1 flex flex-col",
          selected ? "flex" : "hidden sm:flex",
        )}
      >
        {activeConv ? (
          <>
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
            <div className="flex-1 overflow-y-auto p-4 space-y-2 bg-gray-50/40">
              {thread.map((msg) => (
                <MessageBubble key={msg.id} msg={msg} />
              ))}
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
