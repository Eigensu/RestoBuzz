import { cn } from "@/lib/utils";

import { BRAND_GRADIENT } from "@/lib/brand";

interface GradientButtonProps {
  children: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  className?: string;
  type?: "button" | "submit";
}

export function GradientButton({
  children,
  onClick,
  disabled,
  className = "",
  type = "button",
}: Readonly<GradientButtonProps>) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "flex items-center justify-center gap-1.5 text-white font-medium rounded-lg transition disabled:opacity-50 hover:opacity-90",
        className,
      )}
      style={{ background: BRAND_GRADIENT }}
    >
      {children}
    </button>
  );
}
