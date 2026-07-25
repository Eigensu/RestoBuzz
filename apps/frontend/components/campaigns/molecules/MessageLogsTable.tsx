"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { MessageLog } from "@/types";
import { MESSAGE_STATUS_COLORS } from "@/types/common/constants";
import { Pagination } from "@/components/ui/Pagination";

const PAGE_SIZE = 50;

interface MessageLogsTableProps {
  campaignId: string;
  pollMs?: number | false;
}

export function MessageLogsTable({
  campaignId,
  pollMs = false,
}: Readonly<MessageLogsTableProps>) {
  const [page, setPage] = useState(1);

  const { data, isLoading } = useQuery<{ items: MessageLog[]; total: number }>({
    queryKey: ["campaign-messages", campaignId, page],
    queryFn: () =>
      api
        .get(
          `/campaigns/${campaignId}/messages?page=${page}&page_size=${PAGE_SIZE}`,
        )
        .then((r) => r.data),
    placeholderData: (prev) => prev,
    refetchInterval: pollMs,
  });

  const logs = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="bg-white rounded-xl border overflow-hidden">
      <div className="px-5 py-4 border-b flex items-center justify-between">
        <h2 className="font-medium text-sm">Message Logs</h2>
        {total > 0 && (
          <span className="text-xs text-gray-400">{total} total</span>
        )}
      </div>
      <table className="w-full text-sm">
        <thead className="bg-gray-50 border-b">
          <tr>
            {["Phone", "Name", "Status", "Retries", "Error"].map((h) => (
              <th
                key={h}
                className="text-left px-4 py-2.5 font-medium text-gray-500"
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y">
          {logs.length === 0 ? (
            <tr>
              <td
                colSpan={5}
                className="px-4 py-8 text-center text-gray-400 text-xs"
              >
                {isLoading ? "Loading…" : "No logs yet"}
              </td>
            </tr>
          ) : (
            logs.map((m) => {
              const errorText = m.error_code
                ? `${m.error_code}: ${m.error_message}`
                : "—";
              return (
                <tr key={m.id} className="hover:bg-gray-50">
                  <td className="px-4 py-2.5 font-mono text-xs">
                    {m.recipient_phone}
                  </td>
                  <td className="px-4 py-2.5 text-gray-600">
                    {m.recipient_name || "—"}
                  </td>
                  <td className="px-4 py-2.5">
                    <span
                      className={`text-xs px-2 py-0.5 rounded-full font-medium ${MESSAGE_STATUS_COLORS[m.status] ?? "bg-gray-100 text-gray-600"}`}
                    >
                      {m.status}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-gray-400">{m.retry_count}</td>
                  <td className="px-4 py-2.5 text-red-500 text-xs">
                    {errorText}
                  </td>
                </tr>
              );
            })
          )}
        </tbody>
      </table>
      <Pagination page={page} totalPages={totalPages} onPageChange={setPage} />
    </div>
  );
}
