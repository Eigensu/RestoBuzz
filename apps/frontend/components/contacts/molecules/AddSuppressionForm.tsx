import { Plus } from "lucide-react";

type Reason = "opt_out" | "blocked" | "bounce";

interface AddSuppressionFormProps {
  phone: string;
  reason: Reason;
  onPhoneChange: (v: string) => void;
  onReasonChange: (v: Reason) => void;
  onAdd: () => void;
  isPending: boolean;
}

export function AddSuppressionForm({
  phone,
  reason,
  onPhoneChange,
  onReasonChange,
  onAdd,
  isPending,
}: Readonly<AddSuppressionFormProps>) {
  return (
    <div className="bg-white rounded-xl border p-4 space-y-3">
      <h2 className="text-sm font-medium">Add Number</h2>
      <div className="flex gap-2">
        <input
          value={phone}
          onChange={(e) => onPhoneChange(e.target.value)}
          placeholder="+12125551234"
          className="flex-1 border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#24422e]/40 border-gray-200 focus:border-[#24422e]"
        />
        <select
          value={reason}
          onChange={(e) => onReasonChange(e.target.value as Reason)}
          className="border rounded-lg px-3 py-2 text-sm focus:outline-none"
        >
          <option value="blocked">Blocked</option>
          <option value="opt_out">Opt-out</option>
          <option value="bounce">Bounce</option>
        </select>
        <button
          onClick={onAdd}
          disabled={!phone || isPending}
          className="flex items-center gap-1.5 bg-linear-to-r from-[#24422e] to-[#1a3022] text-white text-sm px-4 py-2 rounded-lg transition disabled:opacity-50"
        >
          <Plus className="w-4 h-4" /> Add
        </button>
      </div>
    </div>
  );
}
