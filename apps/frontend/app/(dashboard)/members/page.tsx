"use client";
import { useState, useRef, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { BRAND_GRADIENT } from "@/lib/brand";
import type { Member, MemberListResponse } from "@/types";
import { toast } from "sonner";
import { parseApiError } from "@/lib/errors";
import {
  Plus,
  Search,
  Upload,
  Download,
  ChevronLeft,
  ChevronRight,
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

const PAGE_SIZE = 25;

export default function MembersPage() {
  const { restaurant } = useAuthStore();
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>("all");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [modal, setModal] = useState<{ open: boolean; editing: Member | null }>(
    { open: false, editing: null },
  );
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setPage(1);
  }, [tab, search, restaurant?.id]);

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
    queryKey: ["members", restaurant?.id, tab, search, page],
    queryFn: () => {
      const params = new URLSearchParams({
        restaurant_id: restaurant!.id,
        page: String(page),
        page_size: String(PAGE_SIZE),
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
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const from = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const to = Math.min(page * PAGE_SIZE, total);
  if (!restaurant) return null;

  return (
    <div className="space-y-8 pb-20 max-w-[1600px] mx-auto p-4 md:p-8">
      {modal.open && (
        <MemberModal
          restaurantId={restaurant.id}
          editing={modal.editing}
          defaultType={tab}
          onClose={() => setModal({ open: false, editing: null })}
        />
      )}

      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <div className="p-2 bg-[#eff2f0] rounded-lg">
              <CheckCircle2 className="w-6 h-6 text-[#24422e]" />
            </div>
            <h1 className="text-2xl font-black text-gray-900 tracking-tight">
              Members
            </h1>
          </div>
          <p className="text-sm text-gray-500 mt-1 ml-11 font-medium">
            Manage your restaurant&apos;s loyalty database and membership types
          </p>
        </div>
        <div className="flex gap-2">
          <a
            href="/downloads/member-import-template.xlsx"
            download
            className="flex items-center gap-2 border border-gray-300 text-gray-700 hover:bg-gray-50 text-sm font-medium px-4 py-2 rounded-lg transition-all duration-300"
          >
            <Download className="w-4 h-4" /> Download Template
          </a>
          <input
            ref={fileInputRef}
            type="file"
            accept=".xlsx"
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
            className="flex items-center gap-2 border border-[#24422e]/40 text-[#24422e] hover:bg-[#eff2f0] text-sm font-bold px-6 py-3 rounded-xl disabled:opacity-50 transition-all duration-300"
          >
            <Upload className="w-4 h-4" />
            {importMutation.isPending ? "Importing..." : "IMPORT EXCEL"}
          </button>
          <button
            onClick={() => setModal({ open: true, editing: null })}
            className="flex items-center gap-2 text-white text-sm font-bold px-6 py-3 rounded-xl transition hover:scale-[1.02] active:scale-[0.98] shadow-lg shadow-green-900/10"
            style={{ background: BRAND_GRADIENT }}
          >
            <Plus className="w-4 h-4" /> ADD MEMBER
          </button>
        </div>
      </div>

      <div className="flex flex-col sm:flex-row gap-4">
        <div className="flex p-1 bg-[#eff2f0] rounded-xl">
          {TABS.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={cn(
                "flex items-center gap-2 px-6 py-2.5 text-xs font-black uppercase tracking-widest transition-all rounded-lg",
                tab === key
                  ? "text-white shadow-sm"
                  : "text-[#24422e]/60 hover:text-[#24422e]",
              )}
              style={tab === key ? { background: BRAND_GRADIENT } : undefined}
            >
              <Icon className="w-3.5 h-3.5" />
              {label}
            </button>
          ))}
        </div>
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search name, phone, email..."
            className="w-full border-gray-100 border bg-white rounded-xl pl-11 pr-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-[#24422e]/10 focus:border-[#24422e]/30 shadow-sm"
          />
        </div>
      </div>

      {isLoading ? (
        <div className="bg-white rounded-xl border p-12 text-center text-sm text-gray-400">
          Loading...
        </div>
      ) : (
        <div className="overflow-x-auto rounded-3xl border border-gray-100 shadow-sm custom-scrollbar">
          <MembersTable
            members={members}
            total={total}
            onEdit={(m) => setModal({ open: true, editing: m })}
            onDelete={(m) => {
              if (confirm(`Remove ${m.name}?`)) deleteMutation.mutate(m.id);
            }}
            onAddFirst={() => setModal({ open: true, editing: null })}
          />
        </div>
      )}

      {!isLoading && total > 0 && (
        <div className="flex items-center justify-between bg-white rounded-xl border px-4 py-3">
          <p className="text-xs text-gray-500">
            Showing {from}-{to} of {total}
          </p>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg border text-sm text-gray-700 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50"
            >
              <ChevronLeft className="w-4 h-4" /> Prev
            </button>
            <span className="text-sm text-gray-600 min-w-20 text-center">
              Page {page} / {totalPages}
            </span>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
              className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg border text-sm text-gray-700 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50"
            >
              Next <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
