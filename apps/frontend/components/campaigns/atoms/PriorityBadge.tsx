export function PriorityBadge({ priority }: Readonly<{ priority: string }>) {
  return (
    <span
      className={`text-xs px-2.5 py-1 rounded-full font-bold ${
        priority === "UTILITY"
          ? "bg-blue-50 text-blue-600"
          : "bg-[#eff2f0] text-[#24422e]"
      }`}
    >
      {priority}
    </span>
  );
}
