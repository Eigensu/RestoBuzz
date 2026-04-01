import type { Member } from "@/types";
import { MemberRow } from "@/components/members/molecules/MemberRow";

interface MembersTableProps {
  members: Member[];
  total: number;
  onEdit: (m: Member) => void;
  onDelete: (m: Member) => void;
  onAddFirst: () => void;
}

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
    <div className="bg-white rounded-xl border overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-gray-50 border-b">
          <tr>
            {["Member", "Type", "Card ID", "Visits", "Joined", ""].map((h) => (
              <th
                key={h}
                className="text-left px-4 py-3 font-medium text-gray-500"
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y">
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
