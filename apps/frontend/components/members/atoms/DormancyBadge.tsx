interface DormancyBadgeProps {
  status?: "active" | "dormant" | "unknown" | null;
  source?: string | null;
}

const BADGE_CONFIG = {
  active: {
    className: "bg-green-100 text-green-700",
    label: "ACTIVE",
  },
  dormant: {
    className: "bg-red-100 text-red-700",
    label: "DORMANT",
  },
  unknown: {
    className: "bg-gray-100 text-gray-500 border border-gray-200",
    label: "UNKNOWN",
  },
} as const;

export function DormancyBadge({ status, source }: Readonly<DormancyBadgeProps>) {
  const key = (status ?? "unknown") as keyof typeof BADGE_CONFIG;
  const config = BADGE_CONFIG[key] ?? BADGE_CONFIG.unknown;

  const tooltip = source
    ? `Source: ${source.replaceAll("_", " ")}`
    : undefined;

  return (
    <div className="flex flex-col items-start gap-1">
      <span
        title={tooltip}
        className={[
          "inline-flex items-center justify-center",
          "rounded-full px-2.5 py-1",
          "text-xs font-semibold tracking-wide",
          "cursor-default select-none",
          config.className,
        ].join(" ")}
      >
        {config.label}
      </span>
      {source && (
        <span className="text-[9px] text-gray-300 font-medium italic leading-none">
          via {source.replaceAll("_", " ")}
        </span>
      )}
    </div>
  );
}
