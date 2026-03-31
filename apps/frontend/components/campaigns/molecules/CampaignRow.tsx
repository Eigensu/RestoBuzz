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

export function CampaignRow({ campaign: c, onDelete }: CampaignRowProps) {
  return (
    <tr className="hover:bg-gray-50 transition">
      <td className="px-4 py-3">
        <Link
          href={`/campaigns/${c.id}`}
          className="font-medium hover:text-[#24422e]"
        >
          {c.name}
        </Link>
        <p className="text-xs text-gray-400">{c.template_name}</p>
      </td>
      <td className="px-4 py-3">
        <CampaignStatusBadge status={c.status} />
      </td>
      <td className="px-4 py-3 w-40">
        <ProgressBar sent={c.sent_count} total={c.total_count} />
      </td>
      <td className="px-4 py-3">
        <PriorityBadge priority={c.priority} />
      </td>
      <td className="px-4 py-3 text-gray-400 text-xs">
        {relativeIST(c.created_at)}
      </td>
      <td className="px-4 py-3 text-right">
        {c.status !== "running" && (
          <button
            onClick={() => {
              if (confirm(`Delete "${c.name}"?`)) onDelete(c.id);
            }}
            className="text-gray-400 hover:text-red-500 transition"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        )}
      </td>
    </tr>
  );
}
