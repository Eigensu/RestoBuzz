import { Pencil, Trash2 } from "lucide-react";
import type { Member } from "@/types";
import { relativeIST } from "@/lib/date";
import { MemberTypeBadge } from "@/components/members/atoms/MemberTypeBadge";
import { DormancyBadge } from "@/components/members/atoms/DormancyBadge";

interface MemberRowProps {
  member: Member;
  onEdit: (m: Member) => void;
  onDelete: (m: Member) => void;
}

export function MemberRow({
  member: m,
  onEdit,
  onDelete,
}: Readonly<MemberRowProps>) {
  return (
    <tr className="group hover:bg-[#eff2f0]/50 transition-colors">
      {/* Member Identity */}
      <td className="px-6 py-4">
        <p className="font-bold text-gray-900">{m.name}</p>
        <p className="text-[10px] text-gray-400 font-medium uppercase mt-0.5 tracking-wider">
          {m.phone}
        </p>
        {m.email && (
          <p className="text-[10px] text-gray-400 font-medium mt-0.5 whitespace-nowrap">
            {m.email}
          </p>
        )}
      </td>

      {/* Member Type */}
      <td className="px-6 py-4">
        <MemberTypeBadge type={m.type} />
      </td>

      {/* Last Visit */}
      <td className="px-6 py-4 text-[11px] font-medium text-gray-500">
        {m.last_visit ? relativeIST(m.last_visit) : (
          <span className="text-gray-300 italic">No visit recorded</span>
        )}
      </td>

      {/* Dormancy Status — rendered 100% from backend value, no frontend logic */}
      <td className="px-6 py-4">
        <DormancyBadge
          status={m.activity_status ?? "unknown"}
          source={m.activity_source}
        />
      </td>

      {/* Card ID */}
      <td className="px-6 py-4">
        <span className="font-mono text-[10px] text-gray-500 bg-[#eff2f0]/20 rounded px-1.5 py-0.5 inline-block">
          {m.type === "nfc" ? m.card_uid : m.ecard_code}
        </span>
      </td>

      {/* Visit Count */}
      <td className="px-6 py-4 text-gray-700 font-black text-sm">
        {m.visit_count}
      </td>

      {/* Joined */}
      <td className="px-6 py-4 text-[11px] font-medium text-gray-500">
        {relativeIST(m.joined_at)}
      </td>

      {/* Actions */}
      <td className="px-6 py-4">
        <div className="flex items-center gap-1.5 justify-end opacity-0 group-hover:opacity-100 transition-opacity">
          <button
            onClick={() => onEdit(m)}
            className="p-2 text-gray-400 hover:text-[#24422e] hover:bg-[#eff2f0] rounded-xl transition-all"
          >
            <Pencil className="w-4 h-4" />
          </button>
          <button
            onClick={() => onDelete(m)}
            className="p-2 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-xl transition-all"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </td>
    </tr>
  );
}
