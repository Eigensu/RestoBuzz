export function PriorityBadge({ priority }: Readonly<{ priority: string }>) {
  return (
    <span
      className={`text-xs px-2 py-0.5 rounded-full ${priority === "UTILITY" ? "bg-blue-50 text-blue-600" : "bg-purple-50 text-purple-600"}`}
    >
      {priority}
    </span>
  );
}
