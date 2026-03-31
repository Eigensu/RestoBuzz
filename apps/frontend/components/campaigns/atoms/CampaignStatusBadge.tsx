const STATUS_COLORS: Record<string, string> = {
  draft: "bg-gray-100 text-gray-600",
  queued: "bg-blue-100 text-blue-700",
  running: "bg-yellow-100 text-yellow-700",
  paused: "bg-orange-100 text-orange-700",
  completed: "bg-green-100 text-green-700",
  failed: "bg-red-100 text-red-700",
  cancelled: "bg-gray-100 text-gray-500",
};

export function CampaignStatusBadge({ status }: { status: string }) {
  return (
    <span
      className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_COLORS[status] ?? "bg-gray-100 text-gray-600"}`}
    >
      {status}
    </span>
  );
}
