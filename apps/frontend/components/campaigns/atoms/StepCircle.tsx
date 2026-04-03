import { CheckCircle } from "lucide-react";
import { cn } from "@/lib/utils";

import { BRAND_GRADIENT } from "@/lib/brand";

interface StepCircleProps {
  index: number;
  label: string;
  currentStep: number;
  isLast: boolean;
}

export function StepCircle({
  index: i,
  label,
  currentStep: step,
  isLast,
}: Readonly<StepCircleProps>) {
  let circleClass = "bg-gray-100 text-gray-400";
  if (i < step) circleClass = "text-white";
  else if (i === step) circleClass = "border-2 text-[#24422e]";

  let circleStyle: React.CSSProperties | undefined;
  if (i < step) circleStyle = { background: BRAND_GRADIENT };
  else if (i === step) circleStyle = { borderColor: "#24422e", background: "#24422e14" };

  return (
    <div className="flex items-center gap-1">
      <div
        className={cn(
          "w-7 h-7 rounded-full flex items-center justify-center text-xs font-medium transition",
          circleClass,
        )}
        style={circleStyle}
      >
        {i < step ? <CheckCircle className="w-4 h-4" /> : i + 1}
      </div>
      <span
        className={cn(
          "text-xs hidden sm:block",
          i === step ? "font-medium" : "text-gray-400",
        )}
        style={i === step ? { color: "#24422e" } : undefined}
      >
        {label}
      </span>
      {!isLast && <div className="w-6 h-px bg-gray-200 mx-1" />}
    </div>
  );
}
