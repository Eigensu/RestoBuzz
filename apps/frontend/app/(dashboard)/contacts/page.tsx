"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { parseApiError } from "@/lib/errors";
import { Plus, Trash2 } from "lucide-react";
import { relativeIST } from "@/lib/date";

export default function SuppressionPage() {
  const qc = useQueryClient();
  const [phone, setPhone] = useState("");
  const [reason, setReason] = useState<"opt_out" | "blocked" | "bounce">(
    "blocked",
  );

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

      <div className="bg-white rounded-xl border p-4 space-y-3">
        <h2 className="text-sm font-medium">Add Number</h2>
        <div className="flex gap-2">
          <input
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            placeholder="+12125551234"
            className="flex-1 border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#24422e]/40 border-gray-200 focus:border-[#24422e]"
          />
          <select
            value={reason}
            onChange={(e) => setReason(e.target.value as typeof reason)}
            className="border rounded-lg px-3 py-2 text-sm focus:outline-none"
          >
            <option value="blocked">Blocked</option>
            <option value="opt_out">Opt-out</option>
            <option value="bounce">Bounce</option>
          </select>
          <button
            onClick={() => addMutation.mutate()}
            disabled={!phone || addMutation.isPending}
            className="flex items-center gap-1.5 bg-gradient-to-r from-[#24422e] to-[#1a3022] hover:from-[#1a3022] hover:to-[#24422e] text-white text-sm px-4 py-2 rounded-lg transition-all duration-300 shadow-sm hover:shadow-md disabled:opacity-50"
          >
            <Plus className="w-4 h-4" /> Add
          </button>
        </div>
      </div>

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
            {items.map((item: any) => (
              <div
                key={item.id}
                className="flex items-center gap-3 px-4 py-2.5"
              >
                <span className="font-mono text-sm flex-1">{item.phone}</span>
                <span
                  className={`text-xs px-2 py-0.5 rounded-full ${
                    item.reason === "opt_out"
                      ? "bg-yellow-100 text-yellow-700"
                      : item.reason === "bounce"
                        ? "bg-orange-100 text-orange-700"
                        : "bg-red-100 text-red-700"
                  }`}
                >
                  {item.reason}
                </span>
                <span className="text-xs text-gray-400">
                  {relativeIST(item.added_at)}
                </span>
                <button
                  onClick={() => removeMutation.mutate(item.phone)}
                  className="text-gray-400 hover:text-red-500 transition"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
