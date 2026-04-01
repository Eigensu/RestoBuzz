import type { Campaign } from "@/types";
import { CampaignRow } from "@/components/campaigns/molecules/CampaignRow";

interface CampaignTableProps {
  campaigns: Campaign[];
  onDelete: (id: string) => void;
}

export function CampaignTable({ campaigns, onDelete }: Readonly<CampaignTableProps>) {
  return (
    <div className="bg-white rounded-3xl border border-gray-100 overflow-hidden shadow-sm">
      <table className="w-full text-left">
        <thead>
          <tr className="border-b border-gray-50 bg-[#eff2f0]/30">
            {["Name", "Status", "Progress", "Priority", "Created", ""].map(
              (h) => (
                <th
                  key={h}
                  className="px-6 py-4 text-[11px] font-bold text-gray-400 uppercase tracking-widest"
                >
                  {h}
                </th>
              ),
            )}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {campaigns.map((c) => (
            <CampaignRow key={c.id} campaign={c} onDelete={onDelete} />
          ))}
        </tbody>
      </table>
    </div>
  );
}
