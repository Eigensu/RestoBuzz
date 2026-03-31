"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { parseApiError } from "@/lib/errors";
import { AddSuppressionForm } from "@/components/contacts/molecules/AddSuppressionForm";
import { SuppressionRow } from "@/components/contacts/molecules/SuppressionRow";

type Reason = "opt_out" | "blocked" | "bounce";

export default function SuppressionPage() {
  const qc = useQueryClient();
  const [phone, setPhone] = useState("");
  const [reason, setReason] = useState<Reason>("blocked");

  const { data, isLoading } = useQuery({
    queryKey: ["suppression"],
    queryFn: () =>
      api.get("/settings/suppression?page=1&page_size=100").then((r) => r.data),
  });

  const addMutation = useMutation({
    mutationFn: () => api.post("/settings/suppression", { phone, reason }),
    onSuccess: () => {
      toast.success("Added to suppression list");
      setPhone("");
      qc.invalidateQueries({ queryKey: ["suppression"] });
    },
    onError: (e: unknown) => toast.error(parseApiError(e).message),
  });

  const removeMutation = useMutation({
    mutationFn: (p: string) =>
      api.delete(`/settings/suppression/${encodeURIComponent(p)}`),
    onSuccess: () => {
      toast.success("Removed from suppression list");
      qc.invalidateQueries({ queryKey: ["suppression"] });
    },
  });

  const items = data?.items ?? [];

  return (
    <div className="space-y-4 max-w-2xl">
      <h1 className="text-xl font-semibold">Suppression List</h1>

      <AddSuppressionForm
        phone={phone}
        reason={reason}
        onPhoneChange={setPhone}
        onReasonChange={setReason}
        onAdd={() => addMutation.mutate()}
        isPending={addMutation.isPending}
      />

      <div className="bg-white rounded-xl border overflow-hidden">
        <div className="px-4 py-3 border-b text-sm font-medium">
          {data?.total ?? 0} suppressed numbers
        </div>
        {isLoading ? (
          <p className="text-sm text-gray-400 text-center py-8">Loading...</p>
        ) : items.length === 0 ? (
          <p className="text-sm text-gray-400 text-center py-8">
            No suppressed numbers
          </p>
        ) : (
          <div className="divide-y">
            {items.map(
              (item: {
                id: string;
                phone: string;
                reason: string;
                added_at: string;
              }) => (
                <SuppressionRow
                  key={item.id}
                  item={item}
                  onRemove={(p) => removeMutation.mutate(p)}
                />
              ),
            )}
          </div>
        )}
      </div>
    </div>
  );
}
