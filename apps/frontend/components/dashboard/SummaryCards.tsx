import React from "react";
import {
  Send,
  Eye,
  TrendingUp,
  Megaphone,
  AlertTriangle,
} from "lucide-react";
import { StatCard } from "./ui";
import { DashboardAnalytics } from "@/app/(dashboard)/dashboard/types";

export function SummaryCards({
  analytics,
  activeChannel,
  campaignLength,
  emailAnalyticsData,
  waAnalytics,
}: {
  analytics: DashboardAnalytics;
  activeChannel: "whatsapp" | "email";
  campaignLength: number;
  emailAnalyticsData?: DashboardAnalytics | null;
  waAnalytics?: DashboardAnalytics | null;
}) {
  const { totals, rates } = analytics;

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 md:gap-6">
      {totals.reservego_members != null && totals.reservego_members > 0 ? (
        <StatCard
          label="Total Contacts in DB"
          value={totals.reservego_members.toLocaleString()}
          subtitle="Total Guests Synced"
          icon={TrendingUp}
          color="bg-gray-800"
        />
      ) : (
        <StatCard
          label={activeChannel === "whatsapp" ? "WA Campaigns" : "Emails Sent"}
          value={
            activeChannel === "whatsapp"
              ? campaignLength
              : emailAnalyticsData?.totals.sent || 0
          }
          subtitle="All time"
          icon={Megaphone}
          color="bg-gray-800"
        />
      )}
      <StatCard
        label="Total Sent"
        value={totals.sent.toLocaleString()}
        subtitle="Success broadcasts"
        icon={Send}
        color="bg-[#3a6b47]"
      />
      <StatCard
        label={activeChannel === "whatsapp" ? "Read Rate" : "Open Rate"}
        value={`${(rates.openRate || 0).toFixed(1)}%`}
        subtitle="Interaction velocity"
        icon={Eye}
        color="bg-[#24422e]"
      />
      <StatCard
        label={activeChannel === "whatsapp" ? "Effective Reach" : "Click Rate"}
        value={`${(activeChannel === "whatsapp" ? (rates.effectiveReach ?? 0) : (rates.clickRate ?? 0)).toFixed(1)}%`}
        subtitle={
          activeChannel === "whatsapp" ? "Delivered / Sent" : "Clicks / Sent"
        }
        icon={TrendingUp}
        color="bg-[#6bb97b]"
      />
      <StatCard
        label="Total Replies"
        value={
          activeChannel === "whatsapp"
            ? (waAnalytics?.totals?.replies || 0).toLocaleString()
            : "0"
        }
        subtitle="Direct responses"
        icon={Send}
        color="bg-[#1a2f21]"
      />
      <StatCard
        label={activeChannel === "whatsapp" ? "Failure Rate" : "Bounce Rate"}
        value={`${(activeChannel === "whatsapp" ? rates.failureRate : rates.bounceRate || 0).toFixed(1)}%`}
        subtitle={"Critical drops"}
        icon={AlertTriangle}
        color="bg-red-900/80"
      />
    </div>
  );
}
