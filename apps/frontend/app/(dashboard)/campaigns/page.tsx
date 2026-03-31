"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import type { Campaign } from "@/types";
import { BRAND_GRADIENT } from "@/lib/brand";
import Link from "next/link";
import { Plus, Send } from "lucide-react";
import { toast } from "sonner";
import { parseApiError } from "@/lib/errors";
import { CampaignTable } from "@/components/campaigns/organisms/CampaignTable";
import { EmptyState } from "@/components/ui/EmptyState";

export default function CampaignsPage() {
  const qc = useQueryClient();
  const { restaurant } = useAuthStore();

  const { data, isLoading } = useQuery({
    queryKey: ["campaigns", restaurant?.id],
    queryFn: () =>
      api
        .get(`/campaigns?restaurant_id=${restaurant!.id}&page=1&page_size=50`)
        .then((r) => r.data),
    enabled: !!restaurant,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/campaigns/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["campaigns", restaurant?.id] });
      toast.success("Campaign deleted");
    },
    onError: (e: unknown) => toast.error(parseApiError(e).message),
  });

  const campaigns: Campaign[] = data?.items ?? [];

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
        <Link
          href="/campaigns/new"
          className="inline-flex items-center gap-2 text-white text-sm font-bold px-6 py-3 rounded-xl transition hover:scale-[1.02] active:scale-[0.98] shadow-lg shadow-green-900/10"
          style={{ background: BRAND_GRADIENT }}
        >
          <Plus className="w-4 h-4" />
          NEW CAMPAIGN
        </Link>
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
        <div className="overflow-x-auto rounded-3xl border border-gray-100 shadow-sm custom-scrollbar">
          <CampaignTable
            campaigns={campaigns}
            onDelete={(id) => deleteMutation.mutate(id)}
          />
        </div>
      )}
    </div>
  );
}
