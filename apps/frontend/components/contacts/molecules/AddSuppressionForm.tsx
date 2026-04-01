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
    <div className="bg-[#eff2f0]/50 rounded-2xl border border-[#24422e]/10 p-6 space-y-4 shadow-sm">
      <div className="flex items-center gap-2">
        <Plus className="w-4 h-4 text-[#24422e]" />
        <h2 className="text-sm font-black text-[#24422e] uppercase tracking-widest">
          Add Number
        </h2>
      </div>
      <div className="flex flex-col sm:flex-row gap-3">
        <input
          value={phone}
          onChange={(e) => onPhoneChange(e.target.value)}
          placeholder="+12125551234"
          className="flex-1 border-gray-100 border bg-white rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-[#24422e]/10 shadow-sm"
        />
        <select
          value={reason}
          onChange={(e) => onReasonChange(e.target.value as Reason)}
          className="sm:w-40 border-gray-100 border bg-white rounded-xl px-4 py-3 text-sm focus:outline-none shadow-sm"
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
          {isPending ? "ADDING..." : "ADD"}
        </button>
      </div>
    </div>
  );
}
