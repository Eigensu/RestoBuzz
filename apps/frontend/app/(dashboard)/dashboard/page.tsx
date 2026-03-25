"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Campaign } from "@/types";
import { Send, CheckCheck, Eye, XCircle } from "lucide-react";
import { relativeIST } from "@/lib/date";
import Link from "next/link";

function StatCard({
  label,
  value,
  icon: Icon,
  color,
}: {
  label: string;
  value: number;
  icon: React.ElementType;
  color: string;
}) {
  return (
    <div className="bg-white rounded-xl border p-5">
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm text-gray-500">{label}</span>
        <div
          className={`w-8 h-8 rounded-lg flex items-center justify-center ${color}`}
        >
          <Icon className="w-4 h-4 text-white" />
        </div>
      </div>
      <p className="text-2xl font-bold">{value.toLocaleString()}</p>
    </div>
  );
}

const STATUS_COLORS: Record<string, string> = {
  draft: "bg-gray-100 text-gray-600",
  queued: "bg-blue-100 text-blue-700",
  running: "bg-yellow-100 text-yellow-700",
  paused: "bg-orange-100 text-orange-700",
  completed: "bg-green-100 text-green-700",
  failed: "bg-red-100 text-red-700",
  cancelled: "bg-gray-100 text-gray-500",
};

export default function DashboardPage() {
  const { data } = useQuery({
    queryKey: ["campaigns"],
    queryFn: () => api.get("/campaigns?page=1&page_size=5").then((r) => r.data),
  });

  const campaigns: Campaign[] = data?.items ?? [];
  const totals = campaigns.reduce(
    (acc, c) => ({
      sent: acc.sent + c.sent_count,
      delivered: acc.delivered + c.delivered_count,
      read: acc.read + c.read_count,
      failed: acc.failed + c.failed_count,
    }),
    { sent: 0, delivered: 0, read: 0, failed: 0 },
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Dashboard</h1>
        <Link
          href="/campaigns/new"
          className="bg-green-500 hover:bg-green-600 text-white text-sm font-medium px-4 py-2 rounded-lg transition"
        >
          New Campaign
        </Link>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Sent"
          value={totals.sent}
          icon={Send}
          color="bg-blue-500"
        />
        <StatCard
          label="Delivered"
          value={totals.delivered}
          icon={CheckCheck}
          color="bg-green-500"
        />
        <StatCard
          label="Read"
          value={totals.read}
          icon={Eye}
          color="bg-purple-500"
        />
        <StatCard
          label="Failed"
          value={totals.failed}
          icon={XCircle}
          color="bg-red-500"
        />
      </div>

      <div className="bg-white rounded-xl border">
        <div className="px-5 py-4 border-b flex items-center justify-between">
          <h2 className="font-medium">Recent Campaigns</h2>
          <Link
            href="/campaigns"
            className="text-sm text-green-600 hover:underline"
          >
            View all
          </Link>
        </div>
        <div className="divide-y">
          {campaigns.length === 0 && (
            <p className="text-sm text-gray-400 text-center py-8">
              No campaigns yet
            </p>
          )}
          {campaigns.map((c) => (
            <Link
              key={c.id}
              href={`/campaigns/${c.id}`}
              className="flex items-center gap-4 px-5 py-3 hover:bg-gray-50 transition"
            >
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate">{c.name}</p>
                <p className="text-xs text-gray-400">
                  {relativeIST(c.created_at)}
                </p>
              </div>
              <span
                className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_COLORS[c.status]}`}
              >
                {c.status}
              </span>
              <div className="text-xs text-gray-500 text-right">
                <p>
                  {c.sent_count}/{c.total_count} sent
                </p>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
