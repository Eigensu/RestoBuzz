"use client";
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { parseApiError } from "@/lib/errors";
import { X, Users, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { BRAND_GRADIENT } from "@/lib/brand";

interface BulkAddMemberModalProps {
  restaurantId: string;
  memberCategories: string[];
  defaultType: string;
  onClose: () => void;
}

export function BulkAddMemberModal({
  restaurantId,
  memberCategories,
  defaultType,
  onClose,
}: Readonly<BulkAddMemberModalProps>) {
  const qc = useQueryClient();
  const fallbackCat = memberCategories.length > 0 ? memberCategories[0] : "ecard";
  const [type, setType] = useState(defaultType === "all" ? fallbackCat : defaultType);
  const [text, setText] = useState("");

  const mutation = useMutation({
    mutationFn: async () => {
      // Parse the text: expecting "Name, Phone" or just "Phone" per line
      const lines = text.split("\n").filter(l => l.trim());
      const members = lines.map(line => {
        const parts = line.split(/[,\t]/);
        if (parts.length >= 2) {
          return {
            name: parts[0].trim(),
            phone: parts[1].trim(),
            type,
            restaurant_id: restaurantId
          };
        }
        return {
          name: "Guest",
          phone: parts[0].trim(),
          type,
          restaurant_id: restaurantId
        };
      });

      if (members.length === 0) throw new Error("No valid members found");

      // We'll send them one by one or implement a bulk endpoint if needed.
      // For now, let's look if there's a bulk create endpoint.
      // Backend only has single POST /members. 
      // I'll implement a small loop or use Promise.all
      // Note: Backend has a bulk delete, but no bulk create (except for Excel).
      // I'll use Promise.allSettled to add them.
      const results = await Promise.allSettled(
        members.map(m => api.post("/members", m))
      );
      
      const success = results.filter(r => r.status === "fulfilled").length;
      const failed = results.filter(r => r.status === "rejected").length;
      
      return { success, failed };
    },
    onSuccess: (res) => {
      toast.success(`Imported ${res.success} members. ${res.failed} failures.`);
      qc.invalidateQueries({ queryKey: ["members", restaurantId] });
      if (res.failed === 0) onClose();
    },
    onError: (e: unknown) => {
        console.error("Bulk Add Error:", e);
        toast.error(parseApiError(e).message);
    },
  });

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4 backdrop-blur-sm">
      <div className="bg-white rounded-3xl shadow-2xl w-full max-w-lg overflow-hidden flex flex-col">
        <div className="flex items-center justify-between px-6 py-4 border-b">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-[#eff2f0] rounded-lg">
                <Users className="w-5 h-5 text-[#24422e]" />
            </div>
            <h2 className="text-xl font-bold text-gray-900">Bulk Add Members</h2>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-gray-100 transition">
            <X className="w-5 h-5 text-gray-400" />
          </button>
        </div>

        <div className="p-6 space-y-6">
          <div className="space-y-3">
             <label className="text-xs font-bold text-gray-400 uppercase tracking-widest">Membership Type</label>
             <div className="flex rounded-xl border border-gray-100 overflow-hidden bg-gray-50 p-1">
                {memberCategories.map((t) => (
                    <button
                    key={t}
                    onClick={() => setType(t)}
                    className={cn(
                        "flex-1 py-2 text-[10px] font-black uppercase tracking-tighter transition rounded-lg",
                        type === t ? "text-white shadow-sm" : "text-gray-400 hover:text-gray-600"
                    )}
                    style={type === t ? { background: BRAND_GRADIENT } : undefined}
                    >
                    {t}
                    </button>
                ))}
             </div>
          </div>

          <div className="space-y-2">
            <label className="text-xs font-bold text-gray-400 uppercase tracking-widest flex items-center justify-between">
                Paste Members
                <span className="normal-case font-medium text-[10px]">Name, Phone (one per line)</span>
            </label>
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="John Doe, +1234567890&#10;Jane Smith, +1987654321"
              rows={8}
              className="w-full border rounded-2xl px-4 py-3 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-[#24422e]/10 border-gray-100 focus:border-[#24422e]/30 resize-none bg-gray-50/30"
            />
          </div>

          <div className="bg-amber-50 rounded-2xl p-4 flex gap-3 border border-amber-100">
            <AlertCircle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
            <p className="text-xs text-amber-800 leading-relaxed font-medium">
                Duplicated phone numbers will be automatically skipped. For richer attributes like Card UIDs or Emails, use the <strong>Excel Import</strong> option instead.
            </p>
          </div>
        </div>

        <div className="flex gap-3 px-6 py-5 border-t bg-gray-50/50">
          <button
            onClick={onClose}
            className="flex-1 bg-white border border-gray-200 rounded-xl py-2.5 text-sm font-bold text-gray-500 hover:bg-gray-50 transition"
          >
            CANCEL
          </button>
          <button
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending || !text.trim()}
            className="flex-1 text-white rounded-xl py-2.5 text-sm font-black transition disabled:opacity-50 shadow-lg shadow-green-900/20 active:scale-95"
            style={{ background: BRAND_GRADIENT }}
          >
            {mutation.isPending ? "ADDING..." : "ADD MEMBERS"}
          </button>
        </div>
      </div>
    </div>
  );
}
