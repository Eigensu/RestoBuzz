import type { Member } from "@/types";
import { MemberRow } from "@/components/members/molecules/MemberRow";

interface MembersTableProps {
  members: Member[];
  total: number;
  onEdit: (m: Member) => void;
  onDelete: (m: Member) => void;
  onAddFirst: () => void;
}

const HEADERS = [
  { key: "member", label: "Member" },
  { key: "type", label: "Type" },
  { key: "card_id", label: "Card ID" },
  { key: "visits", label: "Visits" },
  { key: "joined", label: "Joined" },
  { key: "actions", label: "" },
];

export function MembersTable({
  members,
  total,
  onEdit,
  onDelete,
  onAddFirst,
}: Readonly<MembersTableProps>) {
  if (members.length === 0) {
    return (
      <div className="bg-white rounded-xl border text-center py-16">
        <p className="text-gray-400 text-sm">No members found.</p>
        <button
          onClick={onAddFirst}
          className="mt-3 text-sm font-medium text-[#24422e] hover:underline"
        >
          Add the first member
        </button>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-3xl border border-gray-100 overflow-hidden shadow-sm">
      <table className="w-full text-left">
        <thead>
          <tr className="border-b border-gray-50 bg-[#eff2f0]/30">
            {HEADERS.map((h) => (
              <th
                key={h.key}
                className="px-6 py-4 text-[11px] font-bold text-gray-400 uppercase tracking-widest"
              >
                {h.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {members.map((m) => (
            <MemberRow
              key={m.id}
              member={m}
              onEdit={onEdit}
              onDelete={onDelete}
            />
          ))}
        </tbody>
      </table>
      <div className="px-4 py-3 border-t text-xs text-gray-400">
        {total} member{total !== 1 ? "s" : ""} total
      </div>
    </div>
  );
}
