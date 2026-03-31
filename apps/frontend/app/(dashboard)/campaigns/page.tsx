"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import type { Campaign } from "@/types";
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
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Campaigns</h1>
        <Link
          href="/campaigns/new"
          className="flex items-center gap-2 bg-gradient-to-r from-[#24422e] to-[#2a5038] hover:from-[#1a3022] hover:to-[#24422e] text-white text-sm font-medium px-4 py-2 rounded-lg transition-all duration-300 shadow-sm hover:shadow-md"
        >
          <Plus className="w-4 h-4" /> New Campaign
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
        <CampaignTable
          campaigns={campaigns}
          onDelete={(id) => deleteMutation.mutate(id)}
        />
      )}
    </div>
  );
}
