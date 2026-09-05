"use client";
import { useState, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { BRAND_GRADIENT } from "@/lib/brand";
import type {
  Member,
  MemberListResponse,
  MemberSegmentsResponse,
} from "@/types";
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
  Moon,
  Heart,
  Sparkles,
  AlertTriangle,
  UserMinus,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { MemberModal } from "@/components/members/molecules/MemberModal";
import { MembersTable } from "@/components/members/organisms/MembersTable";
import { BulkAddMemberModal } from "@/components/members/molecules/BulkAddMemberModal";

const PAGE_SIZE = 25;

/**
 * Members are filtered on two independent axes:
 *   category — the restaurant's configurable card type (nfc, ecard, vip, …)
 *   segment  — a backend-defined behavioural view (inactive, interested, …)
 *
 * They used to share one `tab` string, which is why a custom category silently
 * showed every member and why "Add member" broke on the Inactive tab. Keeping
 * them separate also lets them compose: VIP members who have gone dormant.
 */
const ICON_BY_SEGMENT: Record<string, LucideIcon> = {
  interested: Heart,
  inactive: Moon,
  active: Sparkles,
  at_risk: AlertTriangle,
  dormant: Moon,
  lost: UserMinus,
};

/** True when the selected category no longer exists after a categories update. */
function activeCategoryRemoved(
  categories: string[],
  category: string | null,
): boolean {
  return category !== null && !categories.includes(category);
}

export default function MembersPage() {
  const { restaurant, user, setRestaurant } = useAuthStore();
  const qc = useQueryClient();
  const [category, setCategory] = useState<string | null>(null);
  const [segment, setSegment] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [modal, setModal] = useState<{ open: boolean; editing: Member | null }>(
    { open: false, editing: null },
  );
  const [bulkModal, setBulkModal] = useState(false);
  const [catModal, setCatModal] = useState(false);
  const [ecardConfirm, setEcardConfirm] = useState<Member | null>(null);

  const [newCat, setNewCat] = useState("");

  const memberCategories = restaurant?.member_categories ?? ["nfc", "ecard"];
  // What "Add member" and Excel import default to when no category tab is
  // active. Always a real configured category — never the selected segment.
  const importFallbackCategory = memberCategories[0] ?? "nfc";

  const fileInputRef = useRef<HTMLInputElement>(null);

  const importMutation = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      // The import type is a category. Sending the active tab used to stamp
      // rows with a segment name ("inactive"), creating members no tab shows.
      const importType = category ?? importFallbackCategory;
      return api.post(
        `/members/import?restaurant_id=${restaurant!.id}&type=${encodeURIComponent(importType)}`,
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
    onError: (e: unknown) => {
      console.error("Import Error:", e);
      toast.error(parseApiError(e).message);
    },
  });

  const catMutation = useMutation({
    mutationFn: (cats: string[]) =>
      api.put(`/restaurants/${restaurant!.id}/categories`, {
        member_categories: cats,
      }),
    onSuccess: (res) => {
      toast.success("Categories updated");
      if (restaurant) {
        setRestaurant({
          ...restaurant,
          member_categories: res.data.member_categories,
        });
      }

      setCatModal(false);
      setNewCat("");
      if (activeCategoryRemoved(res.data.member_categories, category)) {
        setCategory(null);
      }
    },
    onError: (e: unknown) => {
      console.error("Category Update Error:", e);
      toast.error(parseApiError(e).message);
    },
  });

  // Segments come from the backend so this page and the campaign audience
  // picker never drift from the filters the API actually implements.
  const { data: segmentData } = useQuery<MemberSegmentsResponse>({
    queryKey: ["member-segments"],
    queryFn: () => api.get("/members/segments").then((r) => r.data),
    staleTime: Infinity,
  });
  const segments = segmentData?.segments ?? [];

  const { data, isLoading, isError, error, refetch } =
    useQuery<MemberListResponse>({
      queryKey: ["members", restaurant?.id, category, segment, search, page],
      queryFn: () => {
        const params = new URLSearchParams({
          restaurant_id: restaurant!.id,
          page: String(page),
          page_size: String(PAGE_SIZE),
        });
        if (category) params.set("category", category);
        if (segment) params.set("segment", segment);
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
    onError: (e: unknown) => {
      console.error("Delete Error:", e);
      toast.error(parseApiError(e).message);
    },
  });

  const bulkDeleteMutation = useMutation({
    mutationFn: ({
      source,
      deleteAll,
    }: {
      source?: string;
      deleteAll?: boolean;
    }) => {
      const params = new URLSearchParams({ restaurant_id: restaurant!.id });
      if (source) params.set("source", source);
      if (deleteAll) params.set("deleteAll", "true");
      return api.delete(`/members/bulk?${params}`);
    },
    onSuccess: () => {
      toast.success("Bulk deletion successful");
      qc.invalidateQueries({ queryKey: ["members", restaurant?.id] });
    },
    onError: (e: unknown) => {
      console.error("Bulk Delete Error:", e);
      toast.error(parseApiError(e).message);
    },
  });

  const sendEcardMutation = useMutation({
    mutationFn: (id: string) => api.post(`/members/${id}/send-ecard`),
    onSuccess: () => {
      toast.success("E-card sent");
      setEcardConfirm(null);
    },
    onError: (e: unknown) => toast.error(parseApiError(e).message),
  });

  const members = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  // `from`/`to` describe the page that was actually fetched. They used to be
  // derived from a clamped page number while the query used the raw one, so a
  // stale/over-counted total produced "Showing 1-25 of 900" over an empty table.
  const from = members.length === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const to = (page - 1) * PAGE_SIZE + members.length;
  if (!restaurant) return null;

  return (
    <div className="space-y-8 pb-20 max-w-[1600px] mx-auto p-4 md:p-8">
      {importMutation.isPending && (
        <div className="fixed inset-0 z-[100] flex flex-col items-center justify-center bg-white/60 backdrop-blur-md">
          <div className="bg-white p-8 rounded-3xl shadow-2xl border border-gray-100 flex flex-col items-center gap-4 scale-up-center">
            <div className="relative">
              <div className="w-16 h-16 border-4 border-[#24422e]/10 border-t-[#24422e] rounded-full animate-spin" />
              <Upload className="w-6 h-6 text-[#24422e] absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 animate-pulse" />
            </div>
            <div className="text-center">
              <h3 className="text-lg font-black text-gray-900 uppercase tracking-tight">
                Processing Excel
              </h3>
              <p className="text-sm text-gray-500 font-medium">
                Please wait while we sync your members...
              </p>
            </div>
          </div>
        </div>
      )}

      {modal.open && (
        <MemberModal
          restaurantId={restaurant.id}
          memberCategories={memberCategories}
          editing={modal.editing}
          defaultCategory={category}
          onClose={() => setModal({ open: false, editing: null })}
        />
      )}

      {bulkModal && (
        <BulkAddMemberModal
          restaurantId={restaurant.id}
          memberCategories={memberCategories}
          defaultCategory={category}
          onClose={() => setBulkModal(false)}
        />
      )}

      {catModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="bg-white rounded-2xl w-full max-w-sm overflow-hidden shadow-2xl relative">
            <button
              onClick={() => {
                setCatModal(false);
                setNewCat("");
              }}
              className="absolute right-4 top-4 text-gray-400 hover:text-gray-600 transition"
            >
              <X className="w-5 h-5" />
            </button>
            <div className="p-6 space-y-6">
              <div>
                <h3 className="text-xl font-bold text-gray-900">
                  Manage Categories
                </h3>
                <p className="text-sm text-gray-500 mt-1">
                  Add or remove member categories
                </p>
              </div>
              <div className="space-y-3">
                <div className="flex flex-wrap gap-2">
                  {memberCategories.map(
                    (c) => (
                      <div
                        key={c}
                        className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-100 rounded-full text-sm font-medium"
                      >
                        {c.toUpperCase()}
                        <button
                          title="Remove category"
                          onClick={() => {
                            const cats = memberCategories.filter(
                              (x) => x !== c,
                            );

                            catMutation.mutate(cats);
                          }}
                          className="text-gray-400 hover:text-red-500"
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    ),
                  )}
                </div>
                <div className="flex gap-2">
                  <input
                    value={newCat}
                    onChange={(e) => setNewCat(e.target.value)}
                    placeholder="New category..."
                    className="flex-1 w-full border-gray-200 border rounded-xl px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-900/10 focus:border-green-900/30"
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        if (newCat.trim()) {
                          const cats = [...memberCategories, newCat.trim()];
                          catMutation.mutate(cats);
                        }
                      }
                    }}
                  />
                  <button
                    disabled={!newCat.trim() || catMutation.isPending}
                    onClick={() => {
                      const cats = [...memberCategories, newCat.trim()];
                      catMutation.mutate(cats);
                    }}
                    className="bg-[#24422e] text-white px-4 py-2 rounded-xl text-[11px] font-black uppercase tracking-widest hover:bg-[#3a6b47] disabled:opacity-50"
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
            className="flex items-center gap-2 border border-[#24422e]/40 text-[#24422e] hover:bg-[#eff2f0] text-[11px] font-black uppercase tracking-widest px-4 py-2 rounded-xl transition-all duration-300 whitespace-nowrap"
          >
            <Download className="w-3.5 h-3.5" /> DOWNLOAD TEMPLATE
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
            className="flex items-center gap-2 border border-[#24422e]/40 text-[#24422e] hover:bg-[#eff2f0] text-[11px] font-black uppercase tracking-widest px-4 py-2 rounded-xl disabled:opacity-50 transition-all duration-300 whitespace-nowrap"
          >
            <Upload className="w-3.5 h-3.5" />
            {importMutation.isPending ? "IMPORTING..." : "IMPORT EXCEL"}
          </button>

          <button
            onClick={() => setBulkModal(true)}
            className="flex items-center gap-2 border border-[#24422e]/40 text-[#24422e] hover:bg-[#eff2f0] text-[11px] font-black uppercase tracking-widest px-4 py-2 rounded-xl transition-all duration-300 whitespace-nowrap"
          >
            <Users className="w-3.5 h-3.5" /> BULK ADD
          </button>

          <button
            onClick={() => setModal({ open: true, editing: null })}
            className="flex items-center gap-2 text-white text-[11px] font-black uppercase tracking-widest px-4 py-2 rounded-xl transition hover:scale-[1.02] active:scale-[0.98] shadow-lg shadow-green-900/10 whitespace-nowrap"
            style={{ background: BRAND_GRADIENT }}
          >
            <Plus className="w-3.5 h-3.5" /> ADD MEMBER
          </button>
        </div>
      </div>

      <div className="space-y-3">
        {/* Axis 1 — category. Rendered from the restaurant's configured
            categories, so adding one here is all it takes for it to work. */}
        <div className="flex flex-col xl:flex-row gap-4">
          <div className="flex p-1 bg-[#eff2f0] rounded-xl flex-wrap">
            <button
              onClick={() => {
                setCategory(null);
                setPage(1);
              }}
              className={cn(
                "flex items-center gap-2 px-4 py-2 text-[11px] font-black uppercase tracking-widest transition-all rounded-lg",
                category === null
                  ? "text-white shadow-sm"
                  : "text-[#24422e]/60 hover:text-[#24422e]",
              )}
              style={category === null ? { background: BRAND_GRADIENT } : undefined}
            >
              <Users className="w-3.5 h-3.5" />
              All Types
            </button>

            {memberCategories.map((c) => (
              <button
                key={c}
                onClick={() => {
                  setCategory(c);
                  setPage(1);
                }}
                className={cn(
                  "flex items-center gap-2 px-4 py-2 text-[11px] font-black uppercase tracking-widest transition-all rounded-lg",
                  category === c
                    ? "text-white shadow-sm"
                    : "text-[#24422e]/60 hover:text-[#24422e]",
                )}
                style={category === c ? { background: BRAND_GRADIENT } : undefined}
              >
                {c.replaceAll("-", " ").toUpperCase()}
              </button>
            ))}

            {(user?.role === "super_admin" || user?.role === "admin") && (
              <button
                onClick={() => setCatModal(true)}
                className="flex items-center gap-2 px-4 py-2 text-[11px] font-black uppercase tracking-widest transition-all rounded-lg text-[#24422e]/60 hover:text-[#24422e] hover:bg-white/50 border border-transparent"
              >
                <Settings className="w-3.5 h-3.5" />
                Manage
              </button>
            )}
          </div>

          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              aria-label="Search members"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
              placeholder="Search name, phone, email..."
              className="w-full border-gray-100 border bg-white rounded-xl pl-11 pr-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-[#24422e]/10 focus:border-[#24422e]/30 shadow-sm"
            />
          </div>
        </div>

        {/* Axis 2 — segment. Independent of category, so the two compose:
            "VIP members who have gone dormant". Click an active chip to clear. */}
        {segments.length > 0 && (
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[10px] font-black uppercase tracking-widest text-gray-400">
              Segment
            </span>
            {segments.map((s) => {
              const Icon = ICON_BY_SEGMENT[s.id] ?? Users;
              const isActive = segment === s.id;
              return (
                <button
                  key={s.id}
                  title={s.description}
                  aria-pressed={isActive}
                  onClick={() => {
                    setSegment(isActive ? null : s.id);
                    setPage(1);
                  }}
                  className={cn(
                    "flex items-center gap-1.5 px-3 py-1.5 text-[11px] font-black uppercase tracking-widest transition-all rounded-lg border",
                    isActive
                      ? "bg-[#24422e] text-white border-[#24422e] shadow-sm"
                      : "bg-white text-gray-500 border-gray-200 hover:text-[#24422e] hover:border-[#24422e]/40",
                  )}
                >
                  <Icon className="w-3.5 h-3.5" />
                  {s.label}
                  {isActive && <X className="w-3 h-3 opacity-70" />}
                </button>
              );
            })}
          </div>
        )}
      </div>

      {isLoading ? (
        <div className="bg-white rounded-xl border p-12 text-center text-sm text-gray-400">
          Loading...
        </div>
      ) : isError ? (
        <div className="bg-white rounded-xl border p-12 text-center text-sm">
          <p className="text-red-500 font-medium mb-3">
            Failed to load members:{" "}
            {(error as Error)?.message || "Unknown error"}
          </p>
          <button
            onClick={() => refetch()}
            className="px-4 py-2 border rounded-lg text-sm font-medium hover:bg-gray-50"
          >
            Retry
          </button>
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
            onSendEcard={
              restaurant.ecard_config ? (m) => setEcardConfirm(m) : undefined
            }
          />
        </div>
      )}

      {ecardConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-sm rounded-2xl bg-white p-6 shadow-xl">
            <h3 className="text-base font-bold text-gray-900">Send e-card?</h3>
            <p className="mt-2 text-sm text-gray-600">
              A personalized WhatsApp e-card will be sent to{" "}
              <span className="font-semibold text-gray-900">
                {ecardConfirm.name || "this member"}
              </span>{" "}
              at{" "}
              <span className="font-semibold text-gray-900">
                {ecardConfirm.phone}
              </span>
              {"."}
            </p>
            <div className="mt-5 flex justify-end gap-2">
              <button
                onClick={() => setEcardConfirm(null)}
                disabled={sendEcardMutation.isPending}
                className="rounded-lg border px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={() => sendEcardMutation.mutate(ecardConfirm.id)}
                disabled={sendEcardMutation.isPending}
                className="rounded-lg px-4 py-2 text-sm font-bold text-white disabled:opacity-60"
                style={{ background: BRAND_GRADIENT }}
              >
                {sendEcardMutation.isPending ? "Sending…" : "Send e-card"}
              </button>
            </div>
          </div>
        </div>
      )}

      {!isLoading && !isError && total > 0 && (
        <div className="flex items-center justify-between bg-white rounded-xl border px-4 py-3">
          <p className="text-[11px] font-bold text-gray-400 uppercase tracking-widest">
            Showing {from}-{to} of {total}
          </p>
          <div className="flex items-center gap-2">
            <button
              aria-label="Previous page"
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
