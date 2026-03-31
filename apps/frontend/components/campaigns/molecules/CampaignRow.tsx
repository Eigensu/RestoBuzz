import Link from "next/link";
import { Trash2 } from "lucide-react";
import type { Campaign } from "@/types";
import { relativeIST } from "@/lib/date";
import { CampaignStatusBadge } from "@/components/campaigns/atoms/CampaignStatusBadge";
import { PriorityBadge } from "@/components/campaigns/atoms/PriorityBadge";
import { ProgressBar } from "@/components/campaigns/atoms/ProgressBar";

interface CampaignRowProps {
  campaign: Campaign;
  onDelete: (id: string) => void;
}

export function CampaignRow({ campaign: c, onDelete }: Readonly<CampaignRowProps>) {
  return (
    <tr className="group hover:bg-[#eff2f0]/50 transition-colors">
      <td className="px-6 py-4 font-bold text-gray-900">
        <Link
          href={`/campaigns/${c.id}`}
          className="hover:text-[#24422e] transition-colors"
        >
          {c.name}
        </Link>
        <p className="text-[10px] text-gray-400 font-medium uppercase mt-0.5 tracking-wider">
          {c.template_name}
        </p>
      </td>
      <td className="px-6 py-4">
        <CampaignStatusBadge status={c.status} />
      </td>
      <td className="px-6 py-4 w-48">
        <ProgressBar sent={c.sent_count} total={c.total_count} />
      </td>
      <td className="px-6 py-4">
        <PriorityBadge priority={c.priority} />
      </td>
      <td className="px-6 py-4 text-gray-500 text-[11px] font-medium">
        {relativeIST(c.created_at)}
      </td>
      <td className="px-6 py-4 text-right">
        {c.status !== "running" && (
          <button
            onClick={() => {
              if (confirm(`Delete "${c.name}"?`)) onDelete(c.id);
            }}
            className="text-gray-300 hover:text-red-500 transition-colors bg-[#eff2f0] p-2 rounded-lg opacity-0 group-hover:opacity-100"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        )}
      </td>
    </tr>
  );
}
