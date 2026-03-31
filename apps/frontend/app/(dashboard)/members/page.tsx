"use client";
import { useState, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import type { Member, MemberListResponse } from "@/types";
import { toast } from "sonner";
import { parseApiError } from "@/lib/errors";
import {
  Plus,
  Search,
  Upload,
  Wifi,
  CreditCard,
  CheckCircle2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { MemberModal } from "@/components/members/molecules/MemberModal";
import { MembersTable } from "@/components/members/organisms/MembersTable";

type Tab = "all" | "nfc" | "ecard";

const TABS: { key: Tab; label: string; icon: React.ElementType }[] = [
  { key: "all", label: "All Members", icon: CheckCircle2 },
  { key: "nfc", label: "NFC Card", icon: Wifi },
  { key: "ecard", label: "E-Card", icon: CreditCard },
];

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
              const f = e.target.files?.[0];
              if (f) importMutation.mutate(f);
              e.target.value = "";
            }}
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={importMutation.isPending}
            className="flex items-center gap-2 border border-[#24422e]/40 text-[#24422e] hover:bg-gradient-to-r hover:from-[#24422e] hover:to-[#3a6b47] hover:text-white text-sm font-medium px-4 py-2 rounded-lg disabled:opacity-50 transition-all duration-300"
          >
            <Upload className="w-4 h-4" />
            {importMutation.isPending ? "Importing..." : "Import Excel"}
          </button>
          <button
            onClick={() => setModal({ open: true, editing: null })}
            className="flex items-center gap-2 bg-gradient-to-r from-[#24422e] to-[#2a5038] text-white text-sm font-medium px-4 py-2 rounded-lg transition-all duration-300 shadow-sm hover:shadow-md"
          >
            <Plus className="w-4 h-4" /> Add Member
          </button>
        </div>
      </div>

      <div className="flex flex-col sm:flex-row gap-3">
        <div className="flex rounded-lg border bg-white overflow-hidden">
          {TABS.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={cn(
                "flex items-center gap-1.5 px-4 py-2 text-sm font-medium transition",
                tab === key
                  ? "text-white bg-gradient-to-r from-[#24422e] to-[#3a6b47]"
                  : "text-[#24422e] hover:bg-[#24422e]/10",
              )}
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
            className="w-full border rounded-lg pl-9 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#24422e]/40 border-gray-200 focus:border-[#24422e] bg-white"
          />
        </div>
      </div>

      {isLoading ? (
        <div className="bg-white rounded-xl border p-12 text-center text-sm text-gray-400">
          Loading...
        </div>
      ) : (
        <MembersTable
          members={members}
          total={data?.total ?? 0}
          onEdit={(m) => setModal({ open: true, editing: m })}
          onDelete={(m) => {
            if (confirm(`Remove ${m.name}?`)) deleteMutation.mutate(m.id);
          }}
          onAddFirst={() => setModal({ open: true, editing: null })}
        />
      )}
    </div>
  );
}
