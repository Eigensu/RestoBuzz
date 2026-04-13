"use client";
import React from "react";
import Link from "next/link";
import { useAuthStore } from "@/store/auth";
import { Send } from "lucide-react";

import { useDashboardAnalytics } from "./hooks/useDashboardAnalytics";
import { DashboardHeader } from "@/components/dashboard/DashboardHeader";
import { SummaryCards } from "@/components/dashboard/SummaryCards";
import { ConversionFunnel } from "@/components/dashboard/ConversionFunnel";
import { EngagementPie } from "@/components/dashboard/EngagementPie";
import { TemplateLeaderboard } from "@/components/dashboard/TemplateLeaderboard";
import { TimePerformanceCharts } from "@/components/dashboard/TimePerformanceCharts";

export default function DashboardPage() {
  const { restaurant } = useAuthStore();
  
  const {
    analytics,
    waAnalytics,
    emailAnalyticsData,
    isLoading,
    activeChannel,
    setActiveChannel,
    campaigns,
  } = useDashboardAnalytics(restaurant?.id);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="relative w-16 h-16">
          <div className="absolute inset-0 rounded-full border-[3px] border-gray-100"></div>
          <div className="absolute inset-0 rounded-full border-[3px] border-[#24422e] border-t-transparent animate-spin"></div>
        </div>
      </div>
    );
  }

  // Handle empty state gracefully
  if (!campaigns?.length && activeChannel === "whatsapp") {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] max-w-md mx-auto text-center px-4">
        <div className="w-20 h-20 rounded-[2rem] bg-[#eff2f0] flex items-center justify-center mb-6">
          <Send className="w-8 h-8 text-[#24422e]" />
        </div>
        <h2 className="text-2xl font-black text-gray-900 mb-3 tracking-tight">
          Awaiting First Transmission
        </h2>
        <p className="text-gray-500 mb-8 leading-relaxed font-medium">
          Your analytics suite activates once your first WhatsApp campaign is
          dispatched. Launch a campaign to ignite performance tracking.
        </p>
        <Link
          href="/campaigns/whatsapp/new"
          className="inline-flex items-center justify-center h-12 px-8 rounded-full bg-[#24422e] text-white font-bold hover:bg-[#1a2f21] transition-all hover:-translate-y-0.5 shadow-lg shadow-[#24422e]/20"
        >
          Launch Your First Campaign
        </Link>
      </div>
    );
  }

  if (!analytics) return null;

  return (
    <div className="space-y-8 pb-20 max-w-[1800px] mx-auto p-4 md:p-8">
      <DashboardHeader 
        restaurantName={restaurant?.name} 
        activeChannel={activeChannel} 
        setActiveChannel={setActiveChannel} 
        campaignCount={
          activeChannel === "whatsapp"
            ? campaigns.length
            : emailAnalyticsData?.totals?.sent || 0
        }
      />

      <SummaryCards 
        analytics={analytics} 
        activeChannel={activeChannel}
        campaignLength={campaigns.length}
        waAnalytics={waAnalytics}
        emailAnalyticsData={emailAnalyticsData}
      />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <ConversionFunnel data={analytics.funnelData} />
        <EngagementPie data={analytics.pieData} />
      </div>

      <TemplateLeaderboard data={analytics.templateLeaderboard} />

      <TimePerformanceCharts 
        analytics={analytics} 
        activeChannel={activeChannel} 
      />
    </div>
  );
}
