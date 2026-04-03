import { Send } from "lucide-react";
import { EmptyState } from "@/components/ui/EmptyState";

export default function SmsCampaignsPage() {
  return (
    <div className="space-y-8 pb-20 max-w-[1600px] mx-auto p-4 md:p-8">
      <div>
        <div className="flex items-center gap-3">
          <div className="p-2 bg-[#eff2f0] rounded-lg">
            <Send className="w-6 h-6 text-[#24422e]" />
          </div>
          <h1 className="text-2xl font-black text-gray-900 tracking-tight">
            SMS Campaigns
          </h1>
        </div>
        <p className="text-sm text-gray-500 mt-1 ml-11 font-medium">
          Send target SMS broadcasts to your audience
        </p>
      </div>

      <div className="bg-white rounded-xl border p-12">
        <EmptyState
          icon={Send}
          title="SMS Campaigns Coming Soon"
          description="We are currently building the SMS campaign engine. Stay tuned!"
        />
      </div>
    </div>
  );
}
