"use client";
import { useState, useEffect, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useSSE } from "@/lib/sse";
import type { Conversation, InboundMessage } from "@/types";
import { formatDistanceToNow } from "date-fns";
import { Send, ArrowLeft, MapPin, FileText, Image } from "lucide-react";
import { cn } from "@/lib/utils";

export default function InboxPage() {
  const [selected, setSelected] = useState<string | null>(null);
  const [reply, setReply] = useState("");
  const qc = useQueryClient();
  const bottomRef = useRef<HTMLDivElement>(null);

  const { data: convsData } = useQuery({
    queryKey: ["conversations"],
    queryFn: () => api.get("/inbox/conversations?page=1&page_size=50").then((r) => r.data),
    refetchInterval: 5000,
  });

  const { data: messages } = useQuery<InboundMessage[]>({
    queryKey: ["thread", selected],
    queryFn: () => api.get(`/inbox/conversations/${selected}?page=1&page_size=100`).then((r) => r.data),
    enabled: !!selected,
  });

  // SSE for new messages
  const { data: newMsg } = useSSE<{ from_phone: string }>("/inbox/stream");
  useEffect(() => {
    if (newMsg) {
      qc.invalidateQueries({ queryKey: ["conversations"] });
      if (newMsg.from_phone === selected) {
        qc.invalidateQueries({ queryKey: ["thread", selected] });
      }
    }
  }, [newMsg, selected, qc]);

  // Mark as read when opening thread
  useEffect(() => {
    if (selected) {
      api.post(`/inbox/conversations/${selected}/read`).then(() => {
        qc.invalidateQueries({ queryKey: ["conversations"] });
      });
    }
  }, [selected, qc]);

  // Scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const replyMutation = useMutation({
    mutationFn: () => api.post(`/inbox/conversations/${selected}/reply`, { body: reply }),
    onSuccess: () => {
      setReply("");
      qc.invalidateQueries({ queryKey: ["thread", selected] });
    },
  });

  const convs: Conversation[] = convsData?.items ?? [];
  const sorted = [...(messages ?? [])].reverse();

  return (
    <div className="h-[calc(100vh-8rem)] flex rounded-xl border bg-white overflow-hidden">
      {/* Conversation list */}
      <div className={cn(
        "w-full sm:w-72 border-r flex flex-col flex-shrink-0",
        selected ? "hidden sm:flex" : "flex"
      )}>
        <div className="px-4 py-3 border-b">
          <h2 className="font-semibold text-sm">Inbox</h2>
        </div>
        <div className="flex-1 overflow-y-auto divide-y">
          {convs.length === 0 && (
            <p className="text-xs text-gray-400 text-center py-8">No messages yet</p>
          )}
          {convs.map((c) => (
            <button
              key={c.from_phone}
              onClick={() => setSelected(c.from_phone)}
              className={cn(
                "w-full text-left px-4 py-3 hover:bg-gray-50 transition",
                selected === c.from_phone && "bg-green-50"
              )}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">{c.sender_name || c.from_phone}</p>
                  <p className="text-xs text-gray-400 truncate">{c.last_message || `[${c.last_message_type}]`}</p>
                </div>
                <div className="flex flex-col items-end gap-1 flex-shrink-0">
                  <span className="text-xs text-gray-400">
                    {formatDistanceToNow(new Date(c.last_received_at), { addSuffix: false })}
                  </span>
                  {c.unread_count > 0 && (
                    <span className="w-5 h-5 bg-green-500 text-white text-xs rounded-full flex items-center justify-center">
                      {c.unread_count}
                    </span>
                  )}
                </div>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Chat thread */}
      <div className={cn(
        "flex-1 flex flex-col",
        !selected ? "hidden sm:flex" : "flex"
      )}>
        {!selected ? (
          <div className="flex-1 flex items-center justify-center text-gray-400 text-sm">
            Select a conversation
          </div>
        ) : (
          <>
            <div className="px-4 py-3 border-b flex items-center gap-3">
              <button onClick={() => setSelected(null)} className="sm:hidden">
                <ArrowLeft className="w-4 h-4" />
              </button>
              <div>
                <p className="text-sm font-medium">
                  {convs.find((c) => c.from_phone === selected)?.sender_name || selected}
                </p>
                <p className="text-xs text-gray-400">{selected}</p>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto p-4 space-y-2">
              {sorted.map((msg) => (
                <MessageBubble key={msg.id} msg={msg} />
              ))}
              <div ref={bottomRef} />
            </div>

            <div className="px-4 py-3 border-t flex gap-2">
              <input
                value={reply}
                onChange={(e) => setReply(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && reply.trim() && replyMutation.mutate()}
                placeholder="Type a message..."
                className="flex-1 border rounded-full px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
              />
              <button
                onClick={() => replyMutation.mutate()}
                disabled={!reply.trim() || replyMutation.isPending}
                className="w-9 h-9 bg-green-500 hover:bg-green-600 text-white rounded-full flex items-center justify-center transition disabled:opacity-50"
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

function MessageBubble({ msg }: { msg: InboundMessage }) {
  return (
    <div className="flex justify-start">
      <div className="max-w-xs lg:max-w-md bg-gray-100 rounded-2xl rounded-tl-sm px-4 py-2.5">
        {msg.message_type === "text" && (
          <p className="text-sm">{msg.body}</p>
        )}
        {msg.message_type === "image" && (
          <div className="flex items-center gap-2 text-sm text-gray-600">
            <Image className="w-4 h-4" />
            {msg.body || "Image"}
            {msg.media_url && (
              <a href={msg.media_url} target="_blank" rel="noreferrer" className="text-green-600 underline text-xs">View</a>
            )}
          </div>
        )}
        {msg.message_type === "document" && (
          <div className="flex items-center gap-2 text-sm text-gray-600">
            <FileText className="w-4 h-4" />
            {msg.body || "Document"}
            {msg.media_url && (
              <a href={msg.media_url} target="_blank" rel="noreferrer" className="text-green-600 underline text-xs">Download</a>
            )}
          </div>
        )}
        {msg.message_type === "location" && msg.location && (
          <div className="flex items-center gap-2 text-sm text-gray-600">
            <MapPin className="w-4 h-4 text-red-500" />
            <a
              href={`https://maps.google.com/?q=${msg.location.lat},${msg.location.lng}`}
              target="_blank"
              rel="noreferrer"
              className="text-green-600 underline"
            >
              {msg.location.name || `${msg.location.lat}, ${msg.location.lng}`}
            </a>
          </div>
        )}
        {!["text", "image", "document", "location"].includes(msg.message_type) && (
          <p className="text-sm text-gray-400 italic">[{msg.message_type}]</p>
        )}
        <p className="text-xs text-gray-400 mt-1">
          {formatDistanceToNow(new Date(msg.received_at), { addSuffix: true })}
        </p>
      </div>
    </div>
  );
}
