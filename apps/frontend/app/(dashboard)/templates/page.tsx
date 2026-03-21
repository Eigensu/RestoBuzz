"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Template } from "@/types";
import { toast } from "sonner";
import { RefreshCw } from "lucide-react";

export default function TemplatesPage() {
  const qc = useQueryClient();
  const { data: templates, isLoading } = useQuery<Template[]>({
    queryKey: ["templates"],
    queryFn: () => api.get("/templates").then((r) => r.data),
  });

  const syncMutation = useMutation({
    mutationFn: () => api.post("/templates/sync"),
    onSuccess: () => {
      toast.success("Sync queued — templates will update shortly");
      setTimeout(() => qc.invalidateQueries({ queryKey: ["templates"] }), 3000);
    },
    onError: () => toast.error("Sync failed"),
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Templates</h1>
        <button
          onClick={() => syncMutation.mutate()}
          disabled={syncMutation.isPending}
          className="flex items-center gap-2 border text-sm px-3 py-1.5 rounded-lg hover:bg-gray-50 transition disabled:opacity-50"
        >
          <RefreshCw className={`w-4 h-4 ${syncMutation.isPending ? "animate-spin" : ""}`} />
          Sync Templates
        </button>
      </div>

      {isLoading ? (
        <p className="text-sm text-gray-400">Loading...</p>
      ) : (templates ?? []).length === 0 ? (
        <div className="bg-white rounded-xl border p-12 text-center">
          <p className="text-gray-400 text-sm">No templates found. Click "Sync Templates" to fetch from Meta.</p>
        </div>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {(templates ?? []).map((t) => (
            <div key={t.name} className="bg-white rounded-xl border p-4 space-y-2">
              <div className="flex items-start justify-between gap-2">
                <p className="font-medium text-sm">{t.name}</p>
                <span className={`text-xs px-2 py-0.5 rounded-full flex-shrink-0 ${
                  t.status === "APPROVED" ? "bg-green-100 text-green-700" : "bg-yellow-100 text-yellow-700"
                }`}>
                  {t.status}
                </span>
              </div>
              <div className="flex gap-2">
                <span className={`text-xs px-2 py-0.5 rounded-full ${t.category === "UTILITY" ? "bg-blue-50 text-blue-600" : "bg-purple-50 text-purple-600"}`}>
                  {t.category}
                </span>
                <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-500">{t.language}</span>
              </div>
              <p className="text-xs text-gray-400 line-clamp-2">
                {t.components.find((c) => c.type === "BODY")?.text ?? "No body text"}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
