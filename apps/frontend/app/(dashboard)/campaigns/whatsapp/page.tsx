"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import type { Campaign } from "@/types";
import { BRAND_GRADIENT } from "@/lib/brand";
import Link from "next/link";
import { Plus, Send, IdCard } from "lucide-react";
import { toast } from "sonner";
import { parseApiError } from "@/lib/errors";
import { CampaignTable } from "@/components/campaigns/organisms/CampaignTable";
import { EmptyState } from "@/components/ui/EmptyState";
import { Pagination } from "@/components/ui/Pagination";
import { CampaignStatus } from "@/types/common/enums";

const ACTIVE_STATUSES = new Set([
  CampaignStatus.QUEUED,
  CampaignStatus.RUNNING,
  CampaignStatus.PAUSED,
]);

// Root campaigns per page. Retry children ride along with their root and do not
// count against this, so a page always shows exactly this many campaign rows.
const PAGE_SIZE = 20;

export default function CampaignsPage() {
  const qc = useQueryClient();
  const { restaurant } = useAuthStore();
  const [page, setPage] = useState(1);

  // Page numbers are meaningless across restaurants — start over on switch.
  // Adjusted during render rather than in an effect, per the React docs on
  // resetting state when a prop changes.
  const [pagedRestaurantId, setPagedRestaurantId] = useState(restaurant?.id);
  if (restaurant?.id !== pagedRestaurantId) {
    setPagedRestaurantId(restaurant?.id);
    setPage(1);
  }

  const { data, isLoading } = useQuery({
    queryKey: ["campaigns", restaurant?.id, page],
    queryFn: () =>
      api
        .get(
          `/campaigns?restaurant_id=${restaurant!.id}&page=${page}&page_size=${PAGE_SIZE}&roots_only=true`,
        )
        .then((r) => r.data),
    enabled: !!restaurant,
    placeholderData: (prev) => prev,
    refetchInterval: (query) => {
      const campaigns: Campaign[] = query.state.data?.items ?? [];
      const hasActive = campaigns.some((c) =>
        ACTIVE_STATUSES.has(c.status),
      );
      return hasActive ? 5000 : false;
    },
  });

  const campaigns: Campaign[] = data?.items ?? [];
  const total: number = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  // Only roots occupy a row; retry children are nested inside one.
  const rootCount = campaigns.filter((c) => !c.parent_campaign_id).length;

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/campaigns/${id}`),
    onSuccess: (_data, deletedId) => {
      // Deleting the last root on a trailing page leaves it empty, so fall back
      // a page rather than showing a blank table. Retries are nested inside a
      // root's row, so deleting one never empties the page.
      const deletedRoot = campaigns.some(
        (c) => c.id === deletedId && !c.parent_campaign_id,
      );
      if (deletedRoot && rootCount === 1 && page > 1) setPage((p) => p - 1);
      qc.invalidateQueries({ queryKey: ["campaigns", restaurant?.id] });
      toast.success("Campaign deleted");
    },
    onError: (e: unknown) => toast.error(parseApiError(e).message),
  });

  return (
    <div className="space-y-8 pb-20 max-w-[1600px] mx-auto p-4 md:p-8">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <div className="p-2 bg-[#eff2f0] rounded-lg">
              <Send className="w-6 h-6 text-[#24422e]" />
            </div>
            <h1 className="text-2xl font-black text-gray-900 tracking-tight">
              Campaigns
            </h1>
          </div>
          <p className="text-sm text-gray-500 mt-1 ml-11 font-medium">
            Manage and monitor your automated messaging performance
          </p>
        </div>
        <div className="flex items-center gap-3">
          {restaurant?.ecard_config && (
            <Link
              href="/campaigns/whatsapp/new?type=ecard"
              className="inline-flex items-center gap-2 text-[#24422e] text-sm font-bold px-6 py-3 rounded-xl border-2 border-[#24422e]/20 bg-white transition hover:scale-[1.02] active:scale-[0.98] hover:border-[#24422e]/40"
            >
              <IdCard className="w-4 h-4" />
              NEW E-CARD CAMPAIGN
            </Link>
          )}
          <Link
            href="/campaigns/whatsapp/new"
            className="inline-flex items-center gap-2 text-white text-sm font-bold px-6 py-3 rounded-xl transition hover:scale-[1.02] active:scale-[0.98] shadow-lg shadow-green-900/10"
            style={{ background: BRAND_GRADIENT }}
          >
            <Plus className="w-4 h-4" />
            NEW CAMPAIGN
          </Link>
        </div>
      </div>

      {isLoading ? (
        <div className="bg-white rounded-xl border p-12 text-center text-sm text-gray-400">
          Loading...
        </div>
      ) : campaigns.length === 0 ? (
        <div className="bg-white rounded-xl border">
          <EmptyState
            icon={Send}
            title="No campaigns yet"
            description="Create your first campaign to start messaging your audience."
          />
        </div>
      ) : (
        <div className="rounded-3xl border border-gray-100 shadow-sm bg-white overflow-hidden">
          <div className="overflow-x-auto custom-scrollbar">
            <CampaignTable
              campaigns={campaigns}
              onDelete={(id) => deleteMutation.mutate(id)}
            />
          </div>
          <Pagination
            page={page}
            totalPages={totalPages}
            onPageChange={setPage}
            label={`Page ${page} of ${totalPages} · ${total} campaign${total === 1 ? "" : "s"}`}
          />
        </div>
      )}
    </div>
  );
}
