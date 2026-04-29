import { cn } from "@/lib/utils";

export function StatCard({
  label,
  value,
  sub,
  highlight,
  icon: Icon,
  className,
}: {
  readonly label: string;
  readonly value: string | number;
  readonly sub?: string;
  readonly highlight?: "green" | "red" | "amber";
  readonly icon?: React.ElementType;
  readonly className?: string;
}) {
  const colorMap = {
    green: "text-emerald-600",
    red: "text-red-500",
    amber: "text-amber-500",
  };
  return (
    <div
      className={cn(
        "bg-white rounded-2xl border border-gray-100 shadow-sm p-5 flex flex-col gap-2",
        className,
      )}
    >
      <div className="flex items-center justify-between">
        <p
          className={cn(
            "text-[10px] font-black uppercase tracking-widest text-gray-400",
            className && "text-inherit text-opacity-60",
          )}
        >
          {label}
        </p>
        {Icon && (
          <div
            className={cn(
              "p-1.5 bg-[#eff2f0] rounded-lg",
              className && "bg-white/50",
            )}
          >
            <Icon className="w-3.5 h-3.5 text-[#24422e]" />
          </div>
        )}
      </div>
      <p
        className={cn(
          "text-2xl font-black tracking-tight truncate",
          highlight ? colorMap[highlight] : "text-gray-900",
        )}
      >
        {value}
      </p>
      {sub && (
        <p
          className={cn(
            "text-xs text-gray-400 font-medium",
            className && "text-inherit text-opacity-60",
          )}
        >
          {sub}
        </p>
      )}
    </div>
  );
}
