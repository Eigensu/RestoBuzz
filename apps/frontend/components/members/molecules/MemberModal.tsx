"use client";
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { parseApiError } from "@/lib/errors";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";
import { BRAND_GRADIENT } from "@/lib/brand";
import type { Member } from "@/types";

interface MemberModalProps {
  restaurantId: string;
  memberCategories: string[];
  editing: Member | null;
  defaultType: string;
  onClose: () => void;
}

export function MemberModal({
  restaurantId,
  memberCategories,
  editing,
  defaultType,
  onClose,
}: Readonly<MemberModalProps>) {
  const qc = useQueryClient();
  const fallbackCat = memberCategories.length > 0 ? memberCategories[0] : "nfc";
  const [form, setForm] = useState({
    type: editing?.type ?? (defaultType === "all" ? fallbackCat : defaultType),
    isTypeLocked: !editing && defaultType !== "all",
    name: editing?.name ?? "",
    phone: editing?.phone ?? "",
    email: editing?.email ?? "",
    card_uid: editing?.card_uid ?? "",
    ecard_code: editing?.ecard_code ?? "",
    notes: editing?.notes ?? "",
  });

  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }));

  const mutation = useMutation({
    mutationFn: () => {
      const isNfc = form.type === "nfc";
      const isEcard = form.type === "ecard";
      const payload = {
        restaurant_id: restaurantId,
        type: form.type,
        name: form.name,
        phone: form.phone,
        email: form.email || null,
        // NFC → card_uid, ecard → ecard_code, custom → card_uid as reference
        card_uid: (isNfc || (!isNfc && !isEcard)) ? form.card_uid || null : null,
        ecard_code: isEcard ? form.ecard_code || null : null,
        notes: form.notes || null,
        tags: [],
      };
      return editing
        ? api.patch(`/members/${editing.id}`, payload)
        : api.post("/members", payload);
    },
    onSuccess: () => {
      toast.success(editing ? "Member updated" : "Member added");
      qc.invalidateQueries({ queryKey: ["members", restaurantId] });
      onClose();
    },
    onError: (e: unknown) => toast.error(parseApiError(e).message),
  });

  const inputCls =
    "w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#24422e]/40 border-gray-200 focus:border-[#24422e]";

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md">
        <div className="flex items-center justify-between px-5 py-4 border-b">
          <h2 className="font-semibold">
            {editing ? "Edit Member" : "Add Member"}
          </h2>
          <button onClick={onClose}>
            <X className="w-4 h-4 text-gray-400" />
          </button>
        </div>
        <div className="p-5 space-y-4">
          {!editing && !form.isTypeLocked && (
            <div className="flex rounded-lg border overflow-hidden bg-gray-50 flex-wrap">
              {memberCategories.map((t) => (
                <button
                  key={t}
                  onClick={() => set("type", t)}
                  className={cn(
                    "flex-1 min-w-[30%] flex items-center justify-center gap-2 py-2.5 text-xs uppercase font-bold transition",
                    form.type === t
                      ? "text-white shadow-sm"
                      : "text-[#24422e]/60 hover:text-[#24422e] hover:bg-[#24422e]/5 border-r last:border-0",
                  )}
                  style={
                    form.type === t ? { background: BRAND_GRADIENT } : undefined
                  }
                >
                  {t}
                </button>
              ))}
            </div>
          )}
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2">
              <label
                htmlFor="member-name"
                className="block text-xs font-medium text-gray-600 mb-1"
              >
                Full Name *
              </label>
              <input
                id="member-name"
                value={form.name}
                onChange={(e) => set("name", e.target.value)}
                className={inputCls}
                placeholder="Jane Doe"
              />
            </div>
            <div>
              <label
                htmlFor="member-phone"
                className="block text-xs font-medium text-gray-600 mb-1"
              >
                Phone *
              </label>
              <input
                id="member-phone"
                value={form.phone}
                onChange={(e) => set("phone", e.target.value)}
                className={inputCls}
                placeholder="+1234567890"
              />
            </div>
            <div>
              <label
                htmlFor="member-email"
                className="block text-xs font-medium text-gray-600 mb-1"
              >
                Email
              </label>
              <input
                id="member-email"
                value={form.email}
                onChange={(e) => set("email", e.target.value)}
                className={inputCls}
                placeholder="optional"
              />
            </div>
            <div className="col-span-2">
              <label
                htmlFor="member-card"
                className="block text-xs font-medium text-gray-600 mb-1"
              >
                {form.type === "nfc"
                  ? "NFC Card UID"
                  : form.type === "ecard"
                    ? "E-Card Code"
                    : "Card/Reference Code"}
              </label>
              <input
                id="member-card"
                value={form.type === "ecard" ? form.ecard_code : form.card_uid}
                onChange={(e) =>
                  set(
                    form.type === "ecard" ? "ecard_code" : "card_uid",
                    e.target.value,
                  )
                }
                className={cn(inputCls, "font-mono")}
                placeholder={
                  form.type === "nfc"
                    ? "A3F2B1C4..."
                    : form.type === "ecard"
                      ? "EC-0042"
                      : "Optional Reference"
                }
              />
            </div>
            <div className="col-span-2">
              <label
                htmlFor="member-notes"
                className="block text-xs font-medium text-gray-600 mb-1"
              >
                Notes
              </label>
              <textarea
                id="member-notes"
                value={form.notes}
                onChange={(e) => set("notes", e.target.value)}
                rows={2}
                className={cn(inputCls, "resize-none")}
                placeholder="Optional notes..."
              />
            </div>
          </div>
        </div>
        <div className="flex gap-2 px-5 py-4 border-t">
          <button
            onClick={onClose}
            className="flex-1 border rounded-lg py-2 text-sm hover:bg-gray-50 transition"
          >
            Cancel
          </button>
          <button
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending || !form.name || !form.phone}
            className="flex-1 bg-linear-to-r from-[#24422e] to-[#2a5038] text-white rounded-lg py-2 text-sm font-medium transition disabled:opacity-50"
          >
            {mutation.isPending
              ? "Saving..."
              : editing
                ? "Save Changes"
                : "Add Member"}
          </button>
        </div>
      </div>
    </div>
  );
}
