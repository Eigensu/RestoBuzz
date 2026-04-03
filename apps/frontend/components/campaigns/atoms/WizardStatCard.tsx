import { cn } from "@/lib/utils";

interface WizardStatCardProps {
  value: number;
  label: string;
  colorCls: string;
  bgCls: string;
}

export function WizardStatCard({
  value,
  label,
  colorCls,
  bgCls,
}: Readonly<WizardStatCardProps>) {
  return (
    <div className={cn("rounded-lg p-3 text-center", bgCls)}>
      <p className={cn("text-2xl font-bold", colorCls)}>{value}</p>
      <p className={cn("text-xs", colorCls)}>{label}</p>
    </div>
  );
}
