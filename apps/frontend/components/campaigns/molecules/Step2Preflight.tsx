import { XCircle, AlertCircle } from "lucide-react";
import type { PreflightResult } from "@/types";
import { WizardStatCard } from "@/components/campaigns/atoms/WizardStatCard";

export function Step2Preflight({ preflight }: Readonly<{ preflight: PreflightResult }>) {
  return (
    <div className="space-y-4">
      <h2 className="font-medium">Pre-flight Check</h2>
      <div className="grid grid-cols-2 gap-3">
        <WizardStatCard
          value={preflight.valid_count}
          label="Valid"
          colorCls="text-[#24422e]"
          bgCls="bg-[#24422e]/[0.08]"
        />
        <WizardStatCard
          value={preflight.invalid_count}
          label="Invalid"
          colorCls="text-red-500"
          bgCls="bg-red-50"
        />
        <WizardStatCard
          value={preflight.duplicate_count}
          label="Duplicates"
          colorCls="text-amber-600"
          bgCls="bg-amber-50"
        />
        <WizardStatCard
          value={preflight.suppressed_count}
          label="Suppressed"
          colorCls="text-gray-500"
          bgCls="bg-gray-50"
        />
      </div>

      {preflight.invalid_rows.length > 0 && (
        <div className="border rounded-lg overflow-hidden">
          <div className="bg-red-50 px-3 py-2 text-xs font-medium text-red-600 flex items-center gap-1">
            <XCircle className="w-3.5 h-3.5" /> Invalid rows
          </div>
          <div className="max-h-40 overflow-y-auto divide-y">
            {preflight.invalid_rows.slice(0, 20).map((r) => (
              <div
                key={r.row_number}
                className="px-3 py-1.5 text-xs flex gap-3"
              >
                <span className="text-gray-400">Row {r.row_number}</span>
                <span className="font-mono">{r.raw_phone || "(empty)"}</span>
                <span className="text-red-500">{r.reason}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {preflight.valid_count === 0 && (
        <div className="flex items-center gap-2 text-sm text-red-500 bg-red-50 px-3 py-2 rounded-lg">
          <AlertCircle className="w-4 h-4" /> No valid contacts found. Please
          fix your file.
        </div>
      )}
    </div>
  );
}
