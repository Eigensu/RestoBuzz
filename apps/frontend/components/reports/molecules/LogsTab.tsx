import { ChevronRight, Inbox, Search } from "lucide-react";
import { EmptyState } from "../atoms/EmptyState";
import { SectionCard } from "../atoms/SectionCard";
import { StatusBadge } from "../atoms/StatusBadge";
import { TabSkeleton } from "../atoms/TabSkeleton";
import type { LogItem, LogsResponse } from "../types";

export function LogsTab({
  data,
  loading,
  search,
  onSearch,
  status,
  onStatus,
  onLoadMore,
}: {
  readonly data: LogsResponse | null | undefined;
  readonly loading: boolean;
  readonly search: string;
  readonly onSearch: (v: string) => void;
  readonly status: string;
  readonly onStatus: (v: string) => void;
  readonly onLoadMore: () => void;
}) {
  if (loading) {
    return (
      <div className="space-y-6">
        <div className="flex flex-wrap gap-3 items-end">
          <div className="h-10 w-64 bg-gray-100 rounded-xl animate-pulse" />
          <div className="h-10 w-32 bg-gray-100 rounded-xl animate-pulse" />
        </div>
        <TabSkeleton />
      </div>
    );
  }

  const items = data?.items ?? [];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap gap-3 items-end">
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            value={search}
            onChange={(e) => onSearch(e.target.value)}
            placeholder="Search phone or email..."
            className="w-full border border-gray-200 rounded-xl pl-11 pr-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#24422e]/10 focus:border-[#24422e]/30"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label
            htmlFor="log-status"
            className="text-[10px] font-black uppercase tracking-widest text-gray-400"
          >
            Status
          </label>
          <select
            id="log-status"
            value={status}
            onChange={(e) => onStatus(e.target.value)}
            className="border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#24422e]/10 bg-white min-w-[140px]"
          >
            <option value="">All Statuses</option>
            <option value="sent">Sent</option>
            <option value="delivered">Delivered</option>
            <option value="read">Read</option>
            <option value="opened">Opened</option>
            <option value="clicked">Clicked</option>
            <option value="failed">Failed</option>
            <option value="bounced">Bounced</option>
          </select>
        </div>
      </div>

      {items.length === 0 ? (
        <EmptyState
          icon={Inbox}
          message="No delivery logs found for this filter."
        />
      ) : (
        <SectionCard title="Delivery Logs">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100">
                  {[
                    "Channel",
                    "Recipient",
                    "Name",
                    "Campaign",
                    "Status",
                    "Error",
                    "Retries",
                    "Time",
                  ].map((h) => (
                    <th
                      key={h}
                      className="text-[10px] font-black uppercase tracking-widest text-gray-400 text-left pb-3 pr-4"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {items.map((row: LogItem) => (
                  <tr
                    key={row.id}
                    className="border-b border-gray-50 hover:bg-gray-50/50 transition"
                  >
                    <td className="py-3 pr-4">
                      <span className="text-[10px] font-black uppercase tracking-widest bg-gray-100 px-2 py-0.5 rounded-full">
                        {row.channel}
                      </span>
                    </td>
                    <td className="py-3 pr-4 font-mono text-xs text-gray-600 max-w-[140px] truncate">
                      {row.recipient}
                    </td>
                    <td className="py-3 pr-4 text-gray-700 max-w-[100px] truncate">
                      {row.recipient_name || "—"}
                    </td>
                    <td className="py-3 pr-4 text-gray-400 font-mono text-[10px] max-w-[80px] truncate">
                      {row.campaign_id.slice(-8)}
                    </td>
                    <td className="py-3 pr-4">
                      <StatusBadge status={row.status} />
                    </td>
                    <td className="py-3 pr-4 text-xs text-red-400 max-w-[140px] truncate">
                      {row.error_reason || "—"}
                    </td>
                    <td className="py-3 pr-4 text-center text-gray-500">
                      {row.retry_count}
                    </td>
                    <td className="py-3 pr-4 text-xs text-gray-400 whitespace-nowrap">
                      {row.created_at.slice(0, 16).replace("T", " ")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data?.next_cursor && (
            <button
              onClick={onLoadMore}
              className="mt-4 flex items-center gap-2 text-[11px] font-black uppercase tracking-widest text-[#24422e] hover:underline mx-auto"
            >
              Load More <ChevronRight className="w-3.5 h-3.5" />
            </button>
          )}
        </SectionCard>
      )}
    </div>
  );
}
