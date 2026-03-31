interface ProgressBarProps {
  sent: number;
  total: number;
}

export function ProgressBar({ sent, total }: ProgressBarProps) {
  const pct = total > 0 ? Math.round((sent / total) * 100) : 0;
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 bg-gray-100 rounded-full h-1.5">
        <div
          className="bg-[#24422e] h-1.5 rounded-full"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-gray-500 w-10 text-right">
        {sent}/{total}
      </span>
    </div>
  );
}
