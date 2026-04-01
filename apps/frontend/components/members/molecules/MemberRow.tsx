import { Pencil, Trash2 } from "lucide-react";
import type { Member } from "@/types";
import { relativeIST } from "@/lib/date";
import { MemberTypeBadge } from "@/components/members/atoms/MemberTypeBadge";

interface MemberRowProps {
  member: Member;
  onEdit: (m: Member) => void;
  onDelete: (m: Member) => void;
}

export function MemberRow({ member: m, onEdit, onDelete }: Readonly<MemberRowProps>) {
  return (
    <tr className="hover:bg-gray-50 transition">
      <td className="px-4 py-3">
        <p className="font-medium">{m.name}</p>
        <p className="text-xs text-gray-400">{m.phone}</p>
        {m.email && <p className="text-xs text-gray-400">{m.email}</p>}
      </td>
      <td className="px-4 py-3">
        <MemberTypeBadge type={m.type} />
      </td>
      <td className="px-4 py-3 font-mono text-xs text-gray-500">
        {m.type === "nfc" ? m.card_uid : m.ecard_code}
      </td>
      <td className="px-4 py-3 text-gray-600">{m.visit_count}</td>
      <td className="px-4 py-3 text-xs text-gray-400">
        {relativeIST(m.joined_at)}
      </td>
      <td className="px-4 py-3">
        <div className="flex items-center gap-1 justify-end">
          <button
            onClick={() => onEdit(m)}
            className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded transition"
          >
            <Pencil className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => onDelete(m)}
            className="p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded transition"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </td>
    </tr>
  );
}
