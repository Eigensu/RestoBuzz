import { StepCircle } from "@/components/campaigns/atoms/StepCircle";

const STEPS = ["Template", "Upload", "Preflight", "Schedule & Review"];

export function StepIndicator({ currentStep }: Readonly<{ currentStep: number }>) {
  return (
    <div className="flex items-center gap-1">
      {STEPS.map((label, i) => (
        <StepCircle
          key={label}
          index={i}
          label={label}
          currentStep={currentStep}
          isLast={i === STEPS.length - 1}
        />
      ))}
    </div>
  );
}
