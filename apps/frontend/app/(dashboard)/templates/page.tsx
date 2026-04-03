"use client";
import { useState } from "react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Template } from "@/types";
import { toast } from "sonner";
import { parseApiError } from "@/lib/errors";
import { RefreshCw, LayoutTemplate, Plus } from "lucide-react";
import { TemplateSearchBar } from "@/components/templates/molecules/TemplateSearchBar";
import {
  TemplateGrid,
  TemplateEmptyState,
} from "@/components/templates/organisms/TemplateGrid";

import { GREEN } from "@/lib/brand";

type FilterStatus = "ALL" | "APPROVED" | "PENDING";

export default function TemplatesPage() {
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const [filterStatus, setFilterStatus] = useState<FilterStatus>("ALL");

  const { data: templates = [], isLoading } = useQuery<Template[]>({
    queryKey: ["templates"],
    queryFn: () => api.get("/templates").then((r) => r.data),
  });

  const syncMutation = useMutation({
    mutationFn: () => api.post("/templates/sync"),
    onSuccess: () => {
      toast.success("Sync queued — templates will update shortly");
      setTimeout(() => qc.invalidateQueries({ queryKey: ["templates"] }), 3000);
    },
    onError: (e: unknown) => toast.error(parseApiError(e).message),
  });

  const filtered = templates.filter((t) => {
    const matchesSearch = t.name.toLowerCase().includes(search.toLowerCase());
    const matchesStatus =
      filterStatus === "ALL" ||
      (filterStatus === "APPROVED" && t.status === "APPROVED") ||
      (filterStatus === "PENDING" && t.status !== "APPROVED");
    return matchesSearch && matchesStatus;
  });

  if (isLoading) {
    return (
      <div className="h-[80vh] flex flex-col items-center justify-center text-gray-400 gap-4">
        <div className="w-12 h-12 border-4 border-gray-200 border-t-[#24422e] rounded-full animate-spin" />
        <p className="text-sm font-medium animate-pulse">
          Loading Templates...
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-8 pb-20 max-w-[1600px] mx-auto p-4 md:p-8">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <div className="p-2 bg-[#eff2f0] rounded-lg">
              <LayoutTemplate className="w-6 h-6 text-[#24422e]" />
            </div>
            <h1 className="text-2xl font-black text-gray-900 tracking-tight">
              Message Templates
            </h1>
          </div>
          <p className="text-sm text-gray-500 mt-1 ml-11 font-medium">
            {templates.length} templates synced from Meta
          </p>
        </div>
        <div className="flex gap-3">
          <Link
            href="/templates/new"
            className="inline-flex items-center gap-2 text-sm font-bold px-5 py-3 rounded-xl border-2 border-[#24422e] text-[#24422e] hover:bg-[#24422e] hover:text-white transition"
          >
            <Plus className="w-4 h-4" />
            New Template
          </Link>
          <button
            onClick={() => syncMutation.mutate()}
            disabled={syncMutation.isPending}
            className="inline-flex items-center gap-2 text-white text-sm font-bold px-6 py-3 rounded-xl transition hover:scale-[1.02] active:scale-[0.98] shadow-lg shadow-green-900/10 disabled:opacity-50"
            style={{
              background: `linear-gradient(135deg, ${GREEN.darkest}, ${GREEN.dark})`,
            }}
          >
            <RefreshCw
              className={`w-4 h-4 ${syncMutation.isPending ? "animate-spin" : ""}`}
            />
            Sync Templates
          </button>
        </div>
      </div>

      {/* Search & Filter */}
      <TemplateSearchBar
        search={search}
        onSearchChange={setSearch}
        filterStatus={filterStatus}
        onFilterChange={setFilterStatus}
      />

      {/* Content */}
      {templates.length === 0 ? (
        <TemplateEmptyState />
      ) : (
        <TemplateGrid templates={filtered} />
      )}
    </div>
  );
}
