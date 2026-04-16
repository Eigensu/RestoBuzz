"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { BRAND_GRADIENT } from "@/lib/brand";
import type {
  ReserveGoGuest,
  ReserveGoBill,
  ReserveGoListResponse,
} from "@/types";
import {
  Search,
  ChevronLeft,
  ChevronRight,
  CalendarDays,
  Users,
  Phone,
  Mail,
  Clock,
  Hash,
  Banknote,
  Download,
} from "lucide-react";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 50;

// ── Helpers ──────────────────────────────────────────────────────────────────

function fmt(date: string | null | undefined) {
  if (!date) return "—";
  return new Date(date).toLocaleDateString(undefined, {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function fmtDateTime(date: string | null | undefined) {
  if (!date) return "—";
  return new Date(date).toLocaleString(undefined, {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function statusColor(status: string | null) {
  if (!status) return "bg-gray-100 text-gray-500";
  const s = status.toLowerCase();
  if (s.includes("seated") || s.includes("complete"))
    return "bg-green-100 text-green-700";
  if (s.includes("cancel") || s.includes("delet"))
    return "bg-red-100 text-red-600";
  if (s.includes("reserv") || s.includes("confirm"))
    return "bg-blue-100 text-blue-700";
  return "bg-gray-100 text-gray-600";
}

// ── Guest Table ───────────────────────────────────────────────────────────────

function GuestTable({ guests }: { guests: ReserveGoGuest[] }) {
  if (guests.length === 0) {
    return (
      <div className="bg-white rounded-xl border text-center py-16">
        <p className="text-gray-400 text-sm">No guests found.</p>
      </div>
    );
  }
  return (
    <div className="bg-white rounded-3xl border border-gray-100 overflow-hidden shadow-sm">
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-gray-50 bg-[#eff2f0]/30">
              {[
                "Guest",
                "Phone",
                "Email",
                "Visits",
                "Source",
                "Last Visit",
                "Birthday",
                "Anniversary",
              ].map((h) => (
                <th
                  key={h}
                  className="px-5 py-4 text-[11px] font-bold text-gray-400 uppercase tracking-widest whitespace-nowrap"
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {guests.map((g) => (
              <tr
                key={g.id}
                className="hover:bg-[#eff2f0]/20 transition-colors"
              >
                <td className="px-5 py-3 font-semibold text-gray-900 whitespace-nowrap">
                  {g.guest_name}
                </td>
                <td className="px-5 py-3 text-gray-600 whitespace-nowrap">
                  <span className="flex items-center gap-1.5">
                    <Phone className="w-3 h-3 text-gray-400" />
                    {g.phone || "—"}
                  </span>
                </td>
                <td className="px-5 py-3 text-gray-600 whitespace-nowrap">
                  <span className="flex items-center gap-1.5">
                    <Mail className="w-3 h-3 text-gray-400" />
                    {g.email || "—"}
                  </span>
                </td>
                <td className="px-5 py-3 text-center">
                  <span className="inline-flex items-center justify-center w-7 h-7 rounded-full bg-[#eff2f0] text-[#24422e] text-xs font-bold">
                    {g.total_visits ?? 0}
                  </span>
                </td>
                <td className="px-5 py-3 text-gray-500 whitespace-nowrap">
                  {g.source || "—"}
                </td>
                <td className="px-5 py-3 text-gray-500 whitespace-nowrap">
                  {fmt(g.last_visited_date)}
                </td>
                <td className="px-5 py-3 text-gray-500 whitespace-nowrap">
                  {fmt(g.birthday)}
                </td>
                <td className="px-5 py-3 text-gray-500 whitespace-nowrap">
                  {fmt(g.anniversary)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Bill Table ────────────────────────────────────────────────────────────────

function BillTable({ bills }: { bills: ReserveGoBill[] }) {
  if (bills.length === 0) {
    return (
      <div className="bg-white rounded-xl border text-center py-16">
        <p className="text-gray-400 text-sm">No bill records found.</p>
      </div>
    );
  }
  return (
    <div className="bg-white rounded-3xl border border-gray-100 overflow-hidden shadow-sm">
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-gray-50 bg-[#eff2f0]/30">
              {[
                "Guest",
                "Phone",
                "Booking Time",
                "Pax",
                "Tables",
                "Status",
                "Bill #",
                "Bill Amount",
              ].map((h) => (
                <th
                  key={h}
                  className="px-5 py-4 text-[11px] font-bold text-gray-400 uppercase tracking-widest whitespace-nowrap"
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {bills.map((b) => (
              <tr
                key={b.id}
                className="hover:bg-[#eff2f0]/20 transition-colors"
              >
                <td className="px-5 py-3 font-semibold text-gray-900 whitespace-nowrap">
                  {b.guest_name}
                </td>
                <td className="px-5 py-3 text-gray-600 whitespace-nowrap">
                  <span className="flex items-center gap-1.5">
                    <Phone className="w-3 h-3 text-gray-400" />
                    {b.guest_number || "—"}
                  </span>
                </td>
                <td className="px-5 py-3 text-gray-500 whitespace-nowrap">
                  <span className="flex items-center gap-1.5">
                    <Clock className="w-3 h-3 text-gray-400" />
                    {fmtDateTime(b.booking_time)}
                  </span>
                </td>
                <td className="px-5 py-3 text-center">
                  <span className="inline-flex items-center justify-center w-7 h-7 rounded-full bg-[#eff2f0] text-[#24422e] text-xs font-bold">
                    {b.pax ?? "—"}
                  </span>
                </td>
                <td className="px-5 py-3 text-gray-500 whitespace-nowrap">
                  {b.tables || "—"}
                </td>
                <td className="px-5 py-3 whitespace-nowrap">
                  <span
                    className={cn(
                      "px-2 py-0.5 rounded-full text-[11px] font-bold uppercase tracking-wide",
                      statusColor(b.booking_status),
                    )}
                  >
                    {b.booking_status || "—"}
                  </span>
                </td>
                <td className="px-5 py-3 text-gray-500 whitespace-nowrap">
                  <span className="flex items-center gap-1.5">
                    <Hash className="w-3 h-3 text-gray-400" />
                    {b.bill_number || "—"}
                  </span>
                </td>
                <td className="px-5 py-3 font-semibold text-gray-900 whitespace-nowrap">
                  <span className="flex items-center gap-1.5">
                    <Banknote className="w-3 h-3 text-gray-400" />
                    {b.bill_amount != null
                      ? b.bill_amount.toLocaleString()
                      : "—"}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

const BILL_TAB = "__bills__";

export default function ReservationsPage() {
  const { restaurant } = useAuthStore();
  const [activeTab, setActiveTab] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);

  // Fetch available guest sheets
  const { data: sheetsData } = useQuery({
    queryKey: ["reservego-sheets", restaurant?.id],
    queryFn: () =>
      api
        .get(`/reservego/guests/sheets?restaurant_id=${restaurant!.id}`)
        .then((r) => r.data as { sheets: string[] }),
    enabled: !!restaurant,
  });

  const sheets = sheetsData?.sheets ?? [];
  const currentTab = activeTab ?? (sheets.length > 0 ? sheets[0] : BILL_TAB);
  const isBillTab = currentTab === BILL_TAB;

  // Guest query
  const guestQuery = useQuery<ReserveGoListResponse<ReserveGoGuest>>({
    queryKey: ["reservego-guests", restaurant?.id, currentTab, search, page],
    queryFn: () => {
      const params = new URLSearchParams({
        restaurant_id: restaurant!.id,
        sheet: currentTab,
        page: String(page),
        page_size: String(PAGE_SIZE),
      });
      if (search) params.set("search", search);
      return api.get(`/reservego/guests?${params}`).then((r) => r.data);
    },
    enabled: !!restaurant && !isBillTab,
  });

  // Bill query
  const billQuery = useQuery<ReserveGoListResponse<ReserveGoBill>>({
    queryKey: ["reservego-bills", restaurant?.id, search, page],
    queryFn: () => {
      const params = new URLSearchParams({
        restaurant_id: restaurant!.id,
        page: String(page),
        page_size: String(PAGE_SIZE),
      });
      if (search) params.set("search", search);
      return api.get(`/reservego/bills?${params}`).then((r) => r.data);
    },
    enabled: !!restaurant && isBillTab,
  });

  const activeQuery = isBillTab ? billQuery : guestQuery;
  const total = activeQuery.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const from = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const to = Math.min(page * PAGE_SIZE, total);

  function switchTab(tab: string) {
    setActiveTab(tab);
    setPage(1);
    setSearch("");
  }

  const [downloading, setDownloading] = useState(false);

  async function handleDownload() {
    if (!restaurant) return;
    setDownloading(true);
    try {
      const params = new URLSearchParams({ restaurant_id: restaurant.id });
      if (search) params.set("search", search);
      const endpoint = isBillTab
        ? `/reservego/bills/export?${params}`
        : `/reservego/guests/export?${params}&sheet=${encodeURIComponent(currentTab)}`;

      const res = await api.get(endpoint, { responseType: "blob" });
      const url = URL.createObjectURL(res.data as Blob);
      const a = document.createElement("a");
      a.href = url;
      const slug = isBillTab
        ? "bills"
        : currentTab.toLowerCase().replace(/\s+/g, "_");
      a.download = `reservego_${slug}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } finally {
      setDownloading(false);
    }
  }

  if (!restaurant) return null;

  const allTabs = [...sheets, BILL_TAB];

  return (
    <div className="space-y-8 pb-20 max-w-[1600px] mx-auto p-4 md:p-8">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <div className="p-2 bg-[#eff2f0] rounded-lg">
              <CalendarDays className="w-6 h-6 text-[#24422e]" />
            </div>
            <h1 className="text-2xl font-black text-gray-900 tracking-tight">
              Reservations
            </h1>
          </div>
          <p className="text-sm text-gray-500 mt-1 ml-11 font-medium">
            Guest profiles and bill data imported from ReserveGo
          </p>
        </div>
        <button
          onClick={handleDownload}
          disabled={downloading || activeQuery.isLoading || total === 0}
          className="flex items-center gap-2 border border-[#24422e]/40 text-[#24422e] hover:bg-[#eff2f0] text-[11px] font-black uppercase tracking-widest px-4 py-2 rounded-xl disabled:opacity-50 transition-all duration-300 whitespace-nowrap"
        >
          <Download className="w-3.5 h-3.5" />
          {downloading ? "Exporting..." : "Export Excel"}
        </button>
      </div>

      {/* Tabs + Search */}
      <div className="flex flex-col xl:flex-row gap-4">
        <div className="flex p-1 bg-[#eff2f0] rounded-xl flex-wrap gap-0.5">
          {allTabs.map((tab) => {
            const label = tab === BILL_TAB ? "Bill Amount" : tab;
            const Icon = tab === BILL_TAB ? Banknote : Users;
            const active = currentTab === tab;
            return (
              <button
                key={tab}
                onClick={() => switchTab(tab)}
                className={cn(
                  "flex items-center gap-2 px-4 py-2 text-[11px] font-black uppercase tracking-widest transition-all rounded-lg whitespace-nowrap",
                  active
                    ? "text-white shadow-sm"
                    : "text-[#24422e]/60 hover:text-[#24422e]",
                )}
                style={active ? { background: BRAND_GRADIENT } : undefined}
              >
                <Icon className="w-3.5 h-3.5" />
                {label}
              </button>
            );
          })}
        </div>

        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            aria-label="Search reservations"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            placeholder={
              isBillTab
                ? "Search guest, phone, bill #..."
                : "Search name, phone, email..."
            }
            className="w-full border-gray-100 border bg-white rounded-xl pl-11 pr-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-[#24422e]/10 focus:border-[#24422e]/30 shadow-sm"
          />
        </div>
      </div>

      {/* Table */}
      {activeQuery.isLoading ? (
        <div className="bg-white rounded-xl border p-12 text-center text-sm text-gray-400">
          Loading...
        </div>
      ) : activeQuery.isError ? (
        <div className="bg-white rounded-xl border p-12 text-center text-sm">
          <p className="text-red-500 font-medium mb-3">Failed to load data</p>
          <button
            onClick={() => activeQuery.refetch()}
            className="px-4 py-2 border rounded-lg text-sm font-medium hover:bg-gray-50"
          >
            Retry
          </button>
        </div>
      ) : isBillTab ? (
        <BillTable bills={(billQuery.data?.items ?? []) as ReserveGoBill[]} />
      ) : (
        <GuestTable
          guests={(guestQuery.data?.items ?? []) as ReserveGoGuest[]}
        />
      )}

      {/* Pagination */}
      {!activeQuery.isLoading && !activeQuery.isError && total > 0 && (
        <div className="flex items-center justify-between bg-white rounded-xl border px-4 py-3">
          <p className="text-[11px] font-bold text-gray-400 uppercase tracking-widest">
            Showing {from}–{to} of {total}
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
