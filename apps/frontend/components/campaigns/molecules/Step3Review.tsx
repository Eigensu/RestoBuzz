import { cn } from "@/lib/utils";
import type { Template, PreflightResult } from "@/types";

const INPUT_CLS =
  "w-full border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#24422e]/30";

interface Step3ReviewProps {
  campaignName: string;
  setCampaignName: (s: string) => void;
  includeUnsub: boolean;
  setIncludeUnsub: (b: boolean) => void;
  selectedTemplate: Template | null;
  preflight: PreflightResult | null;
}

export function Step3Review({
  campaignName,
  setCampaignName,
  includeUnsub,
  setIncludeUnsub,
  selectedTemplate,
  preflight,
}: Readonly<Step3ReviewProps>) {
  return (
    <div className="space-y-5">
      <h2 className="font-medium">Schedule & Review</h2>
      <div className="max-w-md">
        <label
          htmlFor="campaign-name"
          className="text-sm font-medium mb-1 block"
        >
          Campaign Name
        </label>
        <input
          id="campaign-name"
          value={campaignName}
          onChange={(e) => setCampaignName(e.target.value)}
          className={cn(INPUT_CLS, "py-2")}
          placeholder="e.g. Summer Promo 2026"
        />
      </div>

      <label className="flex items-center gap-2 cursor-pointer">
        <input
          type="checkbox"
          checked={includeUnsub}
          onChange={(e) => setIncludeUnsub(e.target.checked)}
          className="w-4 h-4 accent-[#24422e] cursor-pointer"
        />
        <span className="text-sm">Include unsubscribe footer</span>
      </label>

      <div className="border rounded-xl overflow-hidden">
        <div className="px-4 py-2 text-xs font-semibold text-gray-500 uppercase tracking-wide border-b bg-gray-50">
          Summary
        </div>
        <div className="divide-y text-sm">
          {[
            ["Campaign Name", campaignName || "—"],
            ["Template", selectedTemplate?.name ?? "—"],
            [
              "Recipients",
              preflight ? `${preflight.valid_count} contacts` : "—",
            ],
            ["Unsubscribe Footer", includeUnsub ? "Yes" : "No"],
          ].map(([label, value]) => (
            <div key={label} className="flex justify-between px-4 py-2.5">
              <span className="text-gray-500">{label}</span>
              <span className="font-medium">{value}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
