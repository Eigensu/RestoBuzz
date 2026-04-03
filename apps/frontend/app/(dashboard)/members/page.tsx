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
  CheckCircle2,
  Users,
  Settings,
  X,
  Trash2,
  MoreVertical,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { MemberModal } from "@/components/members/molecules/MemberModal";
import { MembersTable } from "@/components/members/organisms/MembersTable";

type Tab = string;

const PAGE_SIZE = 25;

export default function MembersPage() {
  const { restaurant, user, setRestaurant } = useAuthStore();
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>("all");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [modal, setModal] = useState<{ open: boolean; editing: Member | null }>(
    { open: false, editing: null },
  );
  const [catModal, setCatModal] = useState(false);
  const [newCat, setNewCat] = useState("");

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

  const catMutation = useMutation({
    mutationFn: (cats: string[]) => 
      api.put(`/restaurants/${restaurant!.id}/categories`, { categories: cats }),
    onSuccess: (res) => {
      toast.success("Categories updated");
      if (restaurant) {
        setRestaurant({ ...restaurant, member_categories: res.data.categories });
      }
      setCatModal(false);
      setNewCat("");
      if (!res.data.categories.includes(tab) && tab !== "all") {
        setTab("all");
      }
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

  const bulkDeleteMutation = useMutation({
    mutationFn: ({ source, deleteAll }: { source?: string; deleteAll?: boolean }) => {
      const params = new URLSearchParams({ restaurant_id: restaurant!.id });
      if (source) params.set("source", source);
      if (deleteAll) params.set("deleteAll", "true");
      return api.delete(`/members/bulk?${params}`);
    },
    onSuccess: () => {
      toast.success("Bulk deletion successful");
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
          memberCategories={restaurant.member_categories || ["nfc", "ecard"]}
          editing={modal.editing}
          defaultType={tab}
          onClose={() => setModal({ open: false, editing: null })}
        />
      )}

      {catModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="bg-white rounded-2xl w-full max-w-sm overflow-hidden shadow-2xl relative">
            <button
              onClick={() => { setCatModal(false); setNewCat(""); }}
              className="absolute right-4 top-4 text-gray-400 hover:text-gray-600 transition"
            >
              <X className="w-5 h-5" />
            </button>
            <div className="p-6 space-y-6">
              <div>
                <h3 className="text-xl font-bold text-gray-900">Manage Categories</h3>
                <p className="text-sm text-gray-500 mt-1">Add or remove member categories</p>
              </div>
              <div className="space-y-3">
                <div className="flex flex-wrap gap-2">
                  {(restaurant?.member_categories || ["nfc", "ecard"]).map(c => (
                    <div key={c} className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-100 rounded-full text-sm font-medium">
                      {c.toUpperCase()}
                      <button
                        title="Remove category"
                        onClick={() => {
                          const cats = (restaurant?.member_categories || []).filter(x => x !== c);
                          catMutation.mutate(cats);
                        }}
                        className="text-gray-400 hover:text-red-500"
                      >
                        <X className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  ))}
                </div>
                <div className="flex gap-2">
                  <input 
                    value={newCat}
                    onChange={(e) => setNewCat(e.target.value)}
                    placeholder="New category..."
                    className="flex-1 w-full border-gray-200 border rounded-xl px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-900/10 focus:border-green-900/30"
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault();
                        if (newCat.trim()) {
                          const cats = [...(restaurant?.member_categories || ["nfc", "ecard"]), newCat.trim()];
                          catMutation.mutate(cats);
                        }
                      }
                    }}
                  />
                  <button
                    disabled={!newCat.trim() || catMutation.isPending}
                    onClick={() => {
                      const cats = [...(restaurant?.member_categories || ["nfc", "ecard"]), newCat.trim()];
                      catMutation.mutate(cats);
                    }}
                    className="bg-[#24422e] text-white px-4 py-2 rounded-xl text-sm font-bold hover:bg-[#3a6b47] disabled:opacity-50"
                  >
                    ADD
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
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
            className="flex items-center gap-2 border border-[#24422e]/40 text-[#24422e] hover:bg-[#eff2f0] text-sm font-bold px-6 py-3 rounded-xl transition-all duration-300"
          >
            <Download className="w-4 h-4" /> DOWNLOAD TEMPLATE
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
            {importMutation.isPending ? "IMPORTING..." : "IMPORT EXCEL"}
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

      <div className="flex flex-col xl:flex-row gap-4">
        <div className="flex p-1 bg-[#eff2f0] rounded-xl flex-wrap">
          <button
            onClick={() => setTab("all")}
            className={cn(
              "flex items-center gap-2 px-6 py-2.5 text-xs font-black uppercase tracking-widest transition-all rounded-lg",
              tab === "all" ? "text-white shadow-sm" : "text-[#24422e]/60 hover:text-[#24422e]"
            )}
            style={tab === "all" ? { background: BRAND_GRADIENT } : undefined}
          >
            <Users className="w-3.5 h-3.5" />
            All Members
          </button>
          
          {(restaurant?.member_categories || ["nfc", "ecard"]).map((cat) => (
            <button
              key={cat}
              onClick={() => setTab(cat)}
              className={cn(
                "flex items-center gap-2 px-6 py-2.5 text-xs font-black uppercase tracking-widest transition-all rounded-lg",
                tab === cat ? "text-white shadow-sm" : "text-[#24422e]/60 hover:text-[#24422e]"
              )}
              style={tab === cat ? { background: BRAND_GRADIENT } : undefined}
            >
              {cat}
            </button>
          ))}
          {user?.role === "super_admin" && (
            <button
              onClick={() => setCatModal(true)}
              className="flex items-center gap-2 px-6 py-2.5 text-xs font-black uppercase tracking-widest transition-all rounded-lg text-[#24422e]/60 hover:text-[#24422e] hover:bg-white/50 border border-transparent"
            >
              <Settings className="w-3.5 h-3.5" />
              Manage 
            </button>
          )}

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
