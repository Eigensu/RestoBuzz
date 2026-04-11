"use client";
import { useState, Fragment } from "react";
import type { Campaign } from "@/types";
import { ChevronDown, ChevronRight } from "lucide-react";
import { CampaignStatusBadge } from "@/components/campaigns/atoms/CampaignStatusBadge";

interface CampaignGroup {
  root: Campaign;
  retries: Campaign[];
}

function groupCampaigns(campaigns: Campaign[]): CampaignGroup[] {
  const roots: Campaign[] = [];
  const retryMap: Record<string, Campaign[]> = {};

  for (const c of campaigns) {
    if (c.parent_campaign_id) {
      if (!retryMap[c.parent_campaign_id]) retryMap[c.parent_campaign_id] = [];
      retryMap[c.parent_campaign_id].push(c);
    } else {
      roots.push(c);
    }
  }

  // Sort retries oldest-first within each group
  return roots.map((root) => ({
    root,
    retries: (retryMap[root.id] ?? []).sort(
      (a, b) =>
        new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
    ),
  }));
}

function effectiveStats(group: CampaignGroup) {
  const originalTotal = group.root.total_count;
  const last =
    group.retries.length > 0
      ? group.retries.at(-1)!
      : group.root;
  const effectiveSent = Math.max(0, originalTotal - last.failed_count);
  const pct =
    originalTotal > 0 ? Math.round((effectiveSent / originalTotal) * 100) : 0;
  return { originalTotal, effectiveSent, pct };
}

interface CampaignTableProps {
  campaigns: Campaign[];
  onDelete: (id: string) => void;
}

export function CampaignTable({ campaigns, onDelete }: Readonly<CampaignTableProps>) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const groups = groupCampaigns(campaigns);

  return (
    <div className="bg-white rounded-3xl overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-gray-50 border-b">
          <tr>
            {["Campaign", "Status", "Progress", "Replies", "Created", ""].map(
              (h) => (
                <th
                  key={h}
                  className="text-left px-4 py-3 font-medium text-gray-500 text-xs uppercase tracking-wider"
                >
                  {h}
                </th>
              ),
            )}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {groups.map(({ root, retries }) => {
            const hasRetries = retries.length > 0;
            const isOpen = expanded[root.id];
            const { originalTotal, effectiveSent, pct } = effectiveStats({
              root,
              retries,
            });

            return (
              <Fragment key={root.id}>
                {/* Root row */}
                <tr
                  key={root.id}
                  className={`hover:bg-gray-50/80 transition ${hasRetries ? "bg-[#eff2f0]/30" : ""}`}
                >
                  {/* Expand toggle + name */}
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      {hasRetries ? (
                        <button
                          onClick={() =>
                            setExpanded((e) => ({
                              ...e,
                              [root.id]: !e[root.id],
                            }))
                          }
                          className="p-0.5 rounded hover:bg-gray-200 transition shrink-0"
                        >
                          {isOpen ? (
                            <ChevronDown className="w-3.5 h-3.5 text-gray-400" />
                          ) : (
                            <ChevronRight className="w-3.5 h-3.5 text-gray-400" />
                          )}
                        </button>
                      ) : (
                        <span className="w-5 shrink-0" />
                      )}
                      <div>
                        <a
                          href={`/campaigns/whatsapp/${root.id}`}
                          className="font-semibold text-gray-900 hover:text-[#24422e]"
                        >
                          {root.name}
                        </a>
                        <p className="text-xs text-gray-400">
                          {root.template_name}
                        </p>
                        {hasRetries && (
                          <p className="text-[10px] font-bold text-[#24422e] mt-0.5">
                            Effective reach: {effectiveSent.toLocaleString()}/
                            {originalTotal.toLocaleString()} ({pct}%) ·{" "}
                            {retries.length} retr
                            {retries.length === 1 ? "y" : "ies"}
                          </p>
                        )}
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <CampaignStatusBadge status={root.status} />
                      {root.status === "draft" && root.scheduled_at && (
                        <span
                          title={new Date(root.scheduled_at).toLocaleString(
                            "en-IN",
                            {
                              timeZone: "Asia/Kolkata",
                              dateStyle: "medium",
                              timeStyle: "short",
                            },
                          ) + " IST"}
                          className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-semibold text-amber-700 border border-amber-200"
                        >
                          📅 Scheduled
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3 w-40">
                    <div className="flex items-center gap-2">
                      <div className="flex-1 bg-gray-100 rounded-full h-1.5">
                        <div
                          className="bg-[#24422e] h-1.5 rounded-full"
                          style={{
                            width: `${root.total_count > 0 ? Math.round((root.sent_count / root.total_count) * 100) : 0}%`,
                          }}
                        />
                      </div>
                      <span className="text-xs text-gray-500 w-16 text-right shrink-0">
                        {root.sent_count}/{root.total_count}
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-center w-24">
                    <span className="inline-flex items-center justify-center px-2.5 py-0.5 rounded-full bg-green-50 text-green-700 text-xs font-bold border border-green-200" title="Actual Replies Received">
                      {root.replies_count ?? 0}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-400 text-xs">
                    {root.scheduled_at && root.status === "draft" ? (
                      <span
                        title="Scheduled send time (IST)"
                        className="text-amber-600 font-medium"
                      >
                        {new Date(root.scheduled_at).toLocaleString("en-IN", {
                          timeZone: "Asia/Kolkata",
                          month: "short",
                          day: "numeric",
                          hour: "numeric",
                          minute: "2-digit",
                          hour12: true,
                        })}{" "}
                        IST
                      </span>
                    ) : (
                      new Date(root.created_at).toLocaleDateString()
                    )}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {root.status !== "running" && (
                      <button
                        onClick={() => {
                          if (confirm(`Delete "${root.name}"?`))
                            onDelete(root.id);
                        }}
                        className="text-gray-300 hover:text-red-500 transition p-1"
                      >
                        ×
                      </button>
                    )}
                  </td>
                </tr>

                {/* Retry rows — shown when expanded */}
                {hasRetries &&
                  isOpen &&
                  retries.map((retry, idx) => (
                    <tr
                      key={retry.id}
                      className="bg-gray-50/60 hover:bg-gray-50 transition"
                    >
                      <td className="px-4 py-2.5 pl-12">
                        <div className="flex items-center gap-2">
                          <div className="w-px h-4 bg-gray-200 shrink-0" />
                          <div>
                            <a
                              href={`/campaigns/whatsapp/${retry.id}`}
                              className="text-xs font-medium text-gray-600 hover:text-[#24422e]"
                            >
                              ↳ Retry {idx + 1}
                            </a>
                            <p className="text-[10px] text-gray-400">
                              {retry.name}
                            </p>
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-2.5">
                        <CampaignStatusBadge status={retry.status} />
                      </td>
                      <td className="px-4 py-2.5 w-40">
                        <div className="flex items-center gap-2">
                          <div className="flex-1 bg-gray-100 rounded-full h-1.5">
                            <div
                              className="bg-[#3a6b47] h-1.5 rounded-full"
                              style={{
                                width: `${retry.total_count > 0 ? Math.round((retry.sent_count / retry.total_count) * 100) : 0}%`,
                              }}
                            />
                          </div>
                          <span className="text-xs text-gray-400 w-16 text-right shrink-0">
                            {retry.sent_count}/{retry.total_count}
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-2.5 text-center w-24">
                        <span className="text-xs font-medium text-gray-500">
                          {retry.replies_count ?? 0}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-gray-400 text-xs">
                        {new Date(retry.created_at).toLocaleDateString()}
                      </td>
                      <td className="px-4 py-2.5 text-right">
                        {retry.status !== "running" && (
                          <button
                            onClick={() => {
                              if (confirm(`Delete "${retry.name}"?`))
                                onDelete(retry.id);
                            }}
                            className="text-gray-300 hover:text-red-500 transition p-1"
                          >
                            ×
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
