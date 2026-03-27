"use client";
import { useState, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import type { Member, MemberListResponse } from "@/types";
import { relativeIST } from "@/lib/date";
import { toast } from "sonner";
import { parseApiError } from "@/lib/errors";
import {
  Plus,
  Search,
  Trash2,
  Pencil,
  CreditCard,
  Wifi,
  X,
  CheckCircle2,
  Upload,
} from "lucide-react";
import { cn } from "@/lib/utils";

type Tab = "all" | "nfc" | "ecard";

// ── Add/Edit Modal ────────────────────────────────────────────────────────────
function MemberModal({
  restaurantId,
  editing,
  defaultType,
  onClose,
}: {
  restaurantId: string;
  editing: Member | null;
  defaultType: Tab;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [form, setForm] = useState({
    type: (editing?.type ?? (defaultType === "all" ? "nfc" : defaultType)) as
      | "nfc"
      | "ecard",
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
      const payload = {
        restaurant_id: restaurantId,
        type: form.type,
        name: form.name,
        phone: form.phone,
        email: form.email || null,
        card_uid: form.type === "nfc" ? form.card_uid || null : null,
        ecard_code: form.type === "ecard" ? form.ecard_code || null : null,
        notes: form.notes || null,
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
          {/* Type toggle */}
          {!editing && (
            <div className="flex rounded-lg border overflow-hidden">
              {(["nfc", "ecard"] as const).map((t) => (
                <button
                  key={t}
                  onClick={() => set("type", t)}
                  className={cn(
                    "flex-1 flex items-center justify-center gap-2 py-2 text-sm font-medium transition",
                    form.type === t
                      ? "text-white"
                      : "text-[#24422e] hover:bg-[#24422e]/10",
                  )}
                  style={
                    form.type === t
                      ? { background: "linear-gradient(135deg, #24422e, #3a6b47)" }
                      : undefined
                  }
                >
                  {t === "nfc" ? (
                    <Wifi className="w-4 h-4" />
                  ) : (
                    <CreditCard className="w-4 h-4" />
                  )}
                  {t === "nfc" ? "NFC Card" : "E-Card"}
                </button>
              ))}
            </div>
          )}

          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2">
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Full Name *
              </label>
              <input
                value={form.name}
                onChange={(e) => set("name", e.target.value)}
                className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
                placeholder="Jane Doe"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Phone *
              </label>
              <input
                value={form.phone}
                onChange={(e) => set("phone", e.target.value)}
                className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
                placeholder="+1234567890"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Email
              </label>
              <input
                value={form.email}
                onChange={(e) => set("email", e.target.value)}
                className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
                placeholder="optional"
              />
            </div>

            {form.type === "nfc" ? (
              <div className="col-span-2">
                <label className="block text-xs font-medium text-gray-600 mb-1">
                  NFC Card UID *
                </label>
                <input
                  value={form.card_uid}
                  onChange={(e) => set("card_uid", e.target.value)}
                  className="w-full border rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-green-500"
                  placeholder="A3F2B1C4..."
                />
              </div>
            ) : (
              <div className="col-span-2">
                <label className="block text-xs font-medium text-gray-600 mb-1">
                  E-Card Code *
                </label>
                <input
                  value={form.ecard_code}
                  onChange={(e) => set("ecard_code", e.target.value)}
                  className="w-full border rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-green-500"
                  placeholder="EC-0042"
                />
              </div>
            )}

            <div className="col-span-2">
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Notes
              </label>
              <textarea
                value={form.notes}
                onChange={(e) => set("notes", e.target.value)}
                rows={2}
                className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500 resize-none"
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
            className="flex-1 text-white rounded-lg py-2 text-sm font-medium transition disabled:opacity-50 hover:opacity-90"
            style={{ background: "linear-gradient(135deg, #24422e, #3a6b47)" }}
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

// ── Main Page ─────────────────────────────────────────────────────────────────
export default function MembersPage() {
  const { restaurant } = useAuthStore();
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>("all");
  const [search, setSearch] = useState("");
  const [modal, setModal] = useState<{ open: boolean; editing: Member | null }>(
    { open: false, editing: null },
  );
  const fileInputRef = useRef<HTMLInputElement>(null);

  const importMutation = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return api.post(
        `/members/import?restaurant_id=${restaurant!.id}&type=${tab === "all" ? "ecard" : tab}`,
        form,
        { headers: { "Content-Type": "multipart/form-data" } },
      );
    },
    onSuccess: (res) => {
      toast.success(
        `Imported ${res.data.inserted} members, skipped ${res.data.skipped}`,
      );
      qc.invalidateQueries({ queryKey: ["members", restaurant?.id] });
    },
    onError: (e: unknown) => toast.error(parseApiError(e).message),
  });

  const { data, isLoading } = useQuery<MemberListResponse>({
    queryKey: ["members", restaurant?.id, tab, search],
    queryFn: () => {
      const params = new URLSearchParams({
        restaurant_id: restaurant!.id,
        page: "1",
        page_size: "100",
      });
      if (tab !== "all") params.set("type", tab);
      if (search) params.set("search", search);
      return api.get(`/members?${params}`).then((r) => r.data);
    },
    enabled: !!restaurant,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/members/${id}`),
    onSuccess: () => {
      toast.success("Member removed");
      qc.invalidateQueries({ queryKey: ["members", restaurant?.id] });
    },
    onError: (e: unknown) => toast.error(parseApiError(e).message),
  });

  const members = data?.items ?? [];
  const nfcCount = data?.total ?? 0;

  const TABS: { key: Tab; label: string; icon: React.ElementType }[] = [
    { key: "all", label: "All Members", icon: CheckCircle2 },
    { key: "nfc", label: "NFC Card", icon: Wifi },
    { key: "ecard", label: "E-Card", icon: CreditCard },
  ];

  if (!restaurant) return null;

  return (
    <div className="space-y-4">
      {modal.open && (
        <MemberModal
          restaurantId={restaurant.id}
          editing={modal.editing}
          defaultType={tab}
          onClose={() => setModal({ open: false, editing: null })}
        />
      )}

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Members</h1>
          <p className="text-xs text-gray-400 mt-0.5">
            {restaurant.name} · {restaurant.location}
          </p>
        </div>
        <div className="flex gap-2">
          <input
            ref={fileInputRef}
            type="file"
            accept=".xlsx,.xls"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) importMutation.mutate(file);
              e.target.value = "";
            }}
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={importMutation.isPending}
            className="flex items-center gap-2 border border-[#24422e]/40 text-[#24422e] hover:text-white text-sm font-medium px-4 py-2 rounded-lg transition disabled:opacity-50 hover:opacity-90"
            style={{ transition: "background 0.2s" }}
            onMouseEnter={(e) => (e.currentTarget.style.background = "linear-gradient(135deg, #24422e, #3a6b47)")}
            onMouseLeave={(e) => (e.currentTarget.style.background = "")}
          >
            <Upload className="w-4 h-4" />
            {importMutation.isPending ? "Importing..." : "Import Excel"}
          </button>
          <button
            onClick={() => setModal({ open: true, editing: null })}
            className="flex items-center gap-2 text-white text-sm font-medium px-4 py-2 rounded-lg transition hover:opacity-90"
            style={{ background: "linear-gradient(135deg, #24422e, #3a6b47)" }}
          >
            <Plus className="w-4 h-4" /> Add Member
          </button>
        </div>
      </div>

      {/* Tabs + Search */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="flex rounded-lg border bg-white overflow-hidden">
          {TABS.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={cn(
                "flex items-center gap-1.5 px-4 py-2 text-sm font-medium transition",
                tab === key
                  ? "text-white"
                  : "text-[#24422e] hover:bg-[#24422e]/10",
              )}
              style={
                tab === key
                  ? { background: "linear-gradient(135deg, #24422e, #3a6b47)" }
                  : undefined
              }
            >
              <Icon className="w-3.5 h-3.5" />
              {label}
            </button>
          ))}
        </div>
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search name, phone, email..."
            className="w-full border rounded-lg pl-9 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500 bg-white"
          />
        </div>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border overflow-hidden">
        {isLoading ? (
          <p className="text-sm text-gray-400 text-center py-12">Loading...</p>
        ) : members.length === 0 ? (
          <div className="text-center py-16">
            <p className="text-gray-400 text-sm">No members found.</p>
            <button
              onClick={() => setModal({ open: true, editing: null })}
              className="mt-3 text-sm font-medium text-[#24422e] hover:underline"
            >
              Add the first member
            </button>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-gray-500">
                  Member
                </th>
                <th className="text-left px-4 py-3 font-medium text-gray-500">
                  Type
                </th>
                <th className="text-left px-4 py-3 font-medium text-gray-500">
                  Card ID
                </th>
                <th className="text-left px-4 py-3 font-medium text-gray-500">
                  Visits
                </th>
                <th className="text-left px-4 py-3 font-medium text-gray-500">
                  Joined
                </th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y">
              {members.map((m) => (
                <tr key={m.id} className="hover:bg-gray-50 transition">
                  <td className="px-4 py-3">
                    <p className="font-medium">{m.name}</p>
                    <p className="text-xs text-gray-400">{m.phone}</p>
                    {m.email && (
                      <p className="text-xs text-gray-400">{m.email}</p>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={cn(
                        "inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-medium",
                        m.type === "nfc"
                          ? "bg-blue-50 text-blue-600"
                          : "bg-purple-50 text-purple-600",
                      )}
                    >
                      {m.type === "nfc" ? (
                        <Wifi className="w-3 h-3" />
                      ) : (
                        <CreditCard className="w-3 h-3" />
                      )}
                      {m.type === "nfc" ? "NFC" : "E-Card"}
                    </span>
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
                        onClick={() => setModal({ open: true, editing: m })}
                        className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded transition"
                      >
                        <Pencil className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => {
                          if (confirm(`Remove ${m.name}?`))
                            deleteMutation.mutate(m.id);
                        }}
                        className="p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded transition"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {data && data.total > 0 && (
          <div className="px-4 py-3 border-t text-xs text-gray-400">
            {data.total} member{data.total !== 1 ? "s" : ""} total
          </div>
        )}
      </div>
    </div>
  );
}
