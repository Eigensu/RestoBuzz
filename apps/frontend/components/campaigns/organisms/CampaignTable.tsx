import type { Campaign } from "@/types";
import { CampaignRow } from "@/components/campaigns/molecules/CampaignRow";

interface CampaignTableProps {
  campaigns: Campaign[];
  onDelete: (id: string) => void;
}

export function CampaignTable({ campaigns, onDelete }: CampaignTableProps) {
  return (
    <div className="bg-white rounded-xl border overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-gray-50 border-b">
          <tr>
            {["Name", "Status", "Progress", "Priority", "Created", ""].map(
              (h) => (
                <th
                  key={h}
                  className="text-left px-4 py-3 font-medium text-gray-500"
                >
                  {h}
                </th>
              ),
            )}
          </tr>
        </thead>
        <tbody className="divide-y">
          {campaigns.map((c) => (
            <CampaignRow key={c.id} campaign={c} onDelete={onDelete} />
          ))}
        </tbody>
      </table>
    </div>
  );
}
