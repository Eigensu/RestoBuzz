import { cn } from "@/lib/utils";
import type { Template, PreflightResult } from "@/types";

const INPUT_CLS =
  "w-full border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#24422e]/30";

interface Step3ReviewProps {
  campaignName: string;
  setCampaignName: (s: string) => void;
  priority: "MARKETING" | "UTILITY";
  setPriority: (p: "MARKETING" | "UTILITY") => void;
  includeUnsub: boolean;
  setIncludeUnsub: (b: boolean) => void;
  selectedTemplate: Template | null;
  preflight: PreflightResult | null;
}

export function Step3Review({
  campaignName,
  setCampaignName,
  priority,
  setPriority,
  includeUnsub,
  setIncludeUnsub,
  selectedTemplate,
  preflight,
}: Step3ReviewProps) {
  return (
    <div className="space-y-5">
      <h2 className="font-medium">Schedule & Review</h2>
      <div className="grid sm:grid-cols-2 gap-4">
        <div>
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
        <fieldset className="space-y-2">
          <legend className="text-sm font-medium text-[#24422e]">
            Priority
          </legend>
          <div className="flex gap-2">
            {(["MARKETING", "UTILITY"] as const).map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => setPriority(p)}
                className={cn(
                  "flex-1 py-2 rounded-lg text-sm font-medium border transition focus:ring-2 focus:ring-[#24422e]/20",
                  priority === p
                    ? "text-[#24422e] border-[#24422e] bg-[#24422e]/5 font-bold"
                    : "border-gray-200 text-gray-500 hover:border-[#24422e]/30",
                )}
              >
                {p}
              </button>
            ))}
          </div>
        </fieldset>
      </div>

      {priority === "MARKETING" && (
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={includeUnsub}
            onChange={(e) => setIncludeUnsub(e.target.checked)}
            className="w-4 h-4 accent-[#24422e] cursor-pointer"
          />
          <span className="text-sm">Include unsubscribe footer</span>
        </label>
      )}

      <div className="border rounded-xl overflow-hidden">
        <div className="px-4 py-2 text-xs font-semibold text-gray-500 uppercase tracking-wide border-b bg-gray-50">
          Summary
        </div>
        <div className="divide-y text-sm">
          {[
            ["Campaign Name", campaignName || "—"],
            ["Template", selectedTemplate?.name ?? "—"],
            ["Priority", priority],
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
