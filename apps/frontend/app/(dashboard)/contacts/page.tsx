"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { parseApiError } from "@/lib/errors";
import { AddSuppressionForm } from "@/components/contacts/molecules/AddSuppressionForm";
import { SuppressionRow } from "@/components/contacts/molecules/SuppressionRow";

import { ShieldAlert } from "lucide-react";
 
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
    <div className="space-y-8 pb-20 max-w-[1600px] mx-auto p-4 md:p-8">
       <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
         <div>
           <div className="flex items-center gap-3">
             <div className="p-2 bg-[#eff2f0] rounded-lg">
               <ShieldAlert className="w-6 h-6 text-[#24422e]" />
             </div>
             <h1 className="text-2xl font-black text-gray-900 tracking-tight">
               Suppression List
             </h1>
           </div>
           <p className="text-sm text-gray-500 mt-1 ml-11 font-medium">
             Manage blacklisted phone numbers to prevent accidental messaging
           </p>
         </div>
       </div>
 
       <AddSuppressionForm
        phone={phone}
        reason={reason}
        onPhoneChange={setPhone}
        onReasonChange={setReason}
        onAdd={() => addMutation.mutate()}
        isPending={addMutation.isPending}
      />

      <div className="bg-white rounded-3xl border border-gray-100 overflow-hidden shadow-sm">
        <div className="px-6 py-4 border-b border-gray-50 bg-[#eff2f0]/30 text-[11px] font-bold text-gray-400 uppercase tracking-widest">
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
