import { MessageSquare, TrendingUp, Users } from "lucide-react";
import { EmptyState } from "../atoms/EmptyState";
import { SectionCard } from "../atoms/SectionCard";
import { StatCard } from "../atoms/StatCard";
import { TabSkeleton } from "../atoms/TabSkeleton";
import type { EngagedCustomer, InboxData } from "../types";

export function InboxTab({
  data,
  loading,
}: {
  readonly data: InboxData | null | undefined;
  readonly loading: boolean;
}) {
  if (loading) return <TabSkeleton />;
  if (!data)
    return (
      <EmptyState icon={MessageSquare} message="No inbox data available." />
    );

  const { summary, engaged_customers } = data;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          icon={MessageSquare}
          label="Incoming Messages"
          value={summary.total_incoming_messages.toLocaleString()}
          sub="Total customer responses"
          highlight="green"
        />
        <StatCard
          icon={Users}
          label="Unique Senders"
          value={summary.unique_engaged_senders.toLocaleString()}
          sub="Individual customers"
        />
        <StatCard
          icon={TrendingUp}
          label="Avg Engagement"
          value={`${summary.avg_messages_per_sender}`}
          sub="Messages per sender"
        />
        {summary.top_engaged_customer && (
          <StatCard
            label="Top Customer"
            value={
              summary.top_engaged_customer.name ||
              summary.top_engaged_customer._id
            }
            sub={`${summary.top_engaged_customer.message_count} messages sent`}
            icon={Users}
            className="bg-[#eff2f0] text-[#24422e]"
          />
        )}
      </div>

      <SectionCard title="Most Engaged Customers">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100">
                {[
                  "Name",
                  "Phone",
                  "Last Message",
                  "Messages Sent",
                  "Last Active",
                ].map((h) => (
                  <th
                    key={h}
                    className="text-[10px] font-black uppercase tracking-widest text-gray-400 text-left pb-3 pr-4"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {engaged_customers.slice(0, 15).map((c: EngagedCustomer) => (
                <tr
                  key={c.phone}
                  className="border-b border-gray-50 hover:bg-gray-50/50 transition"
                >
                  <td className="py-3 pr-4 font-medium text-gray-900">
                    {c.name}
                  </td>
                  <td className="py-3 pr-4 text-gray-500 font-mono text-xs">
                    {c.phone}
                  </td>
                  <td className="py-3 pr-4 text-gray-600 italic text-xs max-w-[200px] truncate">
                    {c.last_message}
                  </td>
                  <td className="py-3 pr-4 font-black text-[#24422e]">
                    {c.message_count.toLocaleString()}
                  </td>
                  <td className="py-3 pr-4 text-gray-400 text-xs">
                    {c.last_received_at.slice(0, 16).replace("T", " ")}
                  </td>
                </tr>
              ))}
              {engaged_customers.length === 0 && (
                <tr>
                  <td
                    colSpan={4}
                    className="py-12 text-center text-sm text-gray-400 font-medium"
                  >
                    No engagement data for this period
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </SectionCard>
    </div>
  );
}
