import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Campaign } from "@/types";
import { DashboardAnalytics, TTRStat, HourlyStat } from "../types";
import { GREEN as GREEN_PALETTE } from "@/lib/brand";

export function useDashboardAnalytics(restaurantId?: string) {
  const [activeChannel, setActiveChannel] = useState<"whatsapp" | "email">("whatsapp");

  const { data, isLoading: campaignsLoading } = useQuery({
    queryKey: ["dashboard-campaigns", restaurantId],
    queryFn: () =>
      api
        .get(`/campaigns?restaurant_id=${restaurantId}&page=1&page_size=100`)
        .then((r) => r.data),
    enabled: !!restaurantId,
  });

  const {
    data: analyticsData,
    isLoading: analyticsLoading,
    isError: analyticsError,
  } = useQuery({
    queryKey: ["dashboard-analytics-wa", restaurantId],
    queryFn: () =>
      api
        .get(`/campaigns/analytics?restaurant_id=${restaurantId}`)
        .then((r) => r.data),
    enabled: !!restaurantId,
  });

  const { data: emailAnalyticsData, isLoading: emailLoading } = useQuery({
    queryKey: ["dashboard-analytics-email", restaurantId],
    queryFn: () =>
      api
        .get(`/email-campaigns/analytics?restaurant_id=${restaurantId}`)
        .then((r) => r.data),
    enabled: !!restaurantId,
  });

  const campaigns: Campaign[] = useMemo(() => data?.items ?? [], [data?.items]);

  const waAnalytics: DashboardAnalytics | null = useMemo(() => {
    if (!campaigns.length) return null;

    const rootCampaigns = campaigns.filter((c) => !c.parent_campaign_id);
    const retryCampaigns = campaigns.filter((c) => c.parent_campaign_id);

    const retryMap = new Map<string, Campaign[]>();
    retryCampaigns.forEach((c) => {
      const parentId = c.parent_campaign_id!;
      if (!retryMap.has(parentId)) {
        retryMap.set(parentId, []);
      }
      retryMap.get(parentId)!.push(c);
    });

    let totalAudience = 0;
    let totalSent = 0;
    let totalDelivered = 0;
    let totalRead = 0;
    let totalFailed = 0;
    let totalReplies = 0;

    rootCampaigns.forEach((root) => {
      const retries = retryMap.get(root.id) || [];
      const allInChain = [root, ...retries].sort(
        (a, b) =>
          new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
      );

      totalAudience += root.total_count;

      allInChain.forEach((c) => {
        totalSent += c.sent_count;
        totalDelivered += c.delivered_count;
        totalRead += c.read_count;
        totalReplies += c.replies_count || 0;
      });

      const lastCampaign = allInChain.at(-1)!;
      totalFailed += lastCampaign.failed_count;
    });

    const totals = {
      total: totalAudience,
      sent: totalSent,
      delivered: totalDelivered,
      read: totalRead,
      failed: totalFailed,
      replies: totalReplies,
      reservego_members: analyticsData?.totals?.reservego_members || 0,
    };

    // failure_breakdown is from message_logs (individual-level). Compute the ecosystem
    // error *proportion* from there, then apply to campaign-level failed count so both
    // sides of the formula are on the same scale.
    const rawFailureBreakdown: { reason: string; count: number }[] =
      analyticsData?.failure_breakdown ?? [];
    const totalFailedFromLogs = rawFailureBreakdown.reduce(
      (acc, f) => acc + f.count,
      0,
    );
    const ecosystemFromLogs = rawFailureBreakdown
      .filter((f) => f.reason.toLowerCase().includes("ecosystem"))
      .reduce((acc, f) => acc + f.count, 0);
    const ecosystemRatio =
      totalFailedFromLogs > 0 ? ecosystemFromLogs / totalFailedFromLogs : 0;
    const metaEcosystemErrors = Math.round(totals.failed * ecosystemRatio);

    const deliveryRate =
      totals.sent > 0 ? (totals.delivered / totals.sent) * 100 : 0;
    const openRate =
      totals.delivered > 0 ? (totals.read / totals.delivered) * 100 : 0;
    const effectiveReach =
      totals.sent - metaEcosystemErrors > 0
        ? Math.min(100, (totals.delivered / (totals.sent - metaEcosystemErrors)) * 100)
        : 0;
    const failureRate =
      totals.total > 0
        ? Math.max(0, ((totals.failed - metaEcosystemErrors) / totals.total) * 100)
        : 0;

    const funnelData = [
      {
        name: "Total Audience",
        display: `Total Audience: ${totals.total.toLocaleString()}`,
        value: totals.total,
        drop: 0,
        fill: GREEN_PALETTE.light,
      },
      {
        name: "Sent",
        display: `Sent: ${totals.sent.toLocaleString()}`,
        value: totals.sent,
        drop:
          totals.total > 0
            ? ((totals.total - totals.sent) / totals.total) * 100
            : 0,
        fill: GREEN_PALETTE.medium,
      },
      {
        name: "Delivered",
        display: `Delivered: ${totals.delivered.toLocaleString()}`,
        value: totals.delivered,
        drop:
          totals.sent > 0
            ? ((totals.sent - totals.delivered) / totals.sent) * 100
            : 0,
        fill: GREEN_PALETTE.dark,
      },
      {
        name: "Opened",
        display: `Opened: ${totals.read.toLocaleString()}`,
        value: totals.read,
        drop:
          totals.delivered > 0
            ? ((totals.delivered - totals.read) / totals.delivered) * 100
            : 0,
        fill: GREEN_PALETTE.darkest,
      },
    ];

    const templateMap: Record<string, { opened: number; delivered: number; sent: number; count: number }> = {};
    campaigns.forEach((c) => {
      const name = c.template_name || "Unknown";
      if (!templateMap[name]) templateMap[name] = { opened: 0, delivered: 0, sent: 0, count: 0 };
      templateMap[name].opened += c.read_count;
      templateMap[name].delivered += c.delivered_count;
      templateMap[name].sent += c.sent_count;
      templateMap[name].count += 1;
    });

    const templateLeaderboard = Object.entries(templateMap)
      .map(([name, stats]) => {
        const rate = stats.delivered > 0 ? (stats.opened / stats.delivered) * 100 : 0;
        const score = rate * Math.log10(stats.sent + 1);
        return { name, openRate: rate, sent: stats.sent, score };
      })
      .sort((a, b) => b.score - a.score)
      .slice(0, 5);

    const failureBreakdown = analyticsData?.failure_breakdown ?? [];

    const hourlyPerformance: HourlyStat[] = analyticsError
      ? []
      : (analyticsData?.hourly_performance ??
        Array.from({ length: 24 }, (_, i) => {
          const period = i >= 12 ? "PM" : "AM";
          const displayHour = i % 12 || 12;
          return { hour: `${displayHour} ${period}`, rate: 0, delivered: 0 };
        }));

    const ttrDistribution: TTRStat[] = analyticsError
      ? []
      : (analyticsData?.ttr_distribution ?? [
          { range: "0-5 min", count: 0 },
          { range: "5-30 min", count: 0 },
          { range: "30-120 min", count: 0 },
          { range: "2h+", count: 0 },
        ]);

    const pieData = [
      {
        name: "Sent (no delivery)",
        value: Math.max(0, totals.sent - totals.delivered),
        fill: GREEN_PALETTE.light,
      },
      {
        name: "Delivered (unread)",
        value: Math.max(0, totals.delivered - ((totals as any).read || 0)),
        fill: GREEN_PALETTE.medium,
      },
      {
        name: "Opened (no reply)",
        value: Math.max(0, ((totals as any).read || 0) - totals.replies),
        fill: GREEN_PALETTE.dark,
      },
      { name: "Replied", value: totals.replies, fill: GREEN_PALETTE.darkest },
    ];

    const timeSeriesMap: Record<string, { date: string; sortKey: number; sent: number; delivered: number; read: number; failed: number }> = {};

    for (let i = 6; i >= 0; i--) {
      const d = new Date();
      d.setDate(d.getDate() - i);
      const dateKey = d.toISOString().slice(0, 10);
      const dateLabel = d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
      timeSeriesMap[dateKey] = { date: dateLabel, sortKey: d.getTime(), sent: 0, delivered: 0, read: 0, failed: 0 };
    }

    campaigns.forEach((c) => {
      if (!c.created_at) return;
      const createdAt = new Date(c.created_at);
      const dateKey = createdAt.toISOString().slice(0, 10);

      if (timeSeriesMap[dateKey]) {
        timeSeriesMap[dateKey].sent += c.sent_count;
        timeSeriesMap[dateKey].delivered += c.delivered_count;
        timeSeriesMap[dateKey].read += c.read_count;
        timeSeriesMap[dateKey].failed += c.failed_count;
      }
    });

    const timeSeriesData = Object.values(timeSeriesMap).sort((a, b) => a.sortKey - b.sortKey);

    return {
      totals,
      rates: { deliveryRate, openRate, effectiveReach, failureRate },
      funnelData,
      templateLeaderboard,
      failureBreakdown,
      hourlyPerformance,
      ttrDistribution,
      pieData,
      timeSeriesData,
    };
  }, [campaigns, analyticsData, analyticsError]);

  const emailAnalytics: DashboardAnalytics | null = useMemo(() => {
    if (!emailAnalyticsData || !emailAnalyticsData.totals) return null;

    const {
      totals,
      delivery_rate,
      open_rate,
      click_rate,
      bounce_rate,
      failure_breakdown,
    } = emailAnalyticsData;

    return {
      totals: {
        total: (totals?.sent ?? 0) + (totals?.failed ?? 0),
        sent: totals?.sent ?? 0,
        delivered: totals?.delivered ?? 0,
        read: totals?.opened ?? 0,
        replies: 0,
        opened: totals?.opened ?? 0,
        clicked: totals?.clicked ?? 0,
        bounced: totals?.bounced ?? 0,
        failed: totals?.failed ?? 0,
        reservego_members: totals?.reservego_members ?? 0,
      },
      rates: {
        deliveryRate: delivery_rate ?? 0,
        openRate: open_rate ?? 0,
        clickRate: click_rate ?? 0,
        bounceRate: bounce_rate ?? 0,
        effectiveReach: open_rate ?? 0,
        failureRate:
          ((totals?.failed ?? 0) / ((totals?.sent ?? 0) + (totals?.failed ?? 0) || 1)) * 100,
      },
      funnelData: [
        {
          name: "Sent",
          display: `Sent: ${totals.sent.toLocaleString()}`,
          value: totals.sent,
          drop: 0,
          fill: GREEN_PALETTE.light,
        },
        {
          name: "Delivered",
          display: `Delivered: ${totals.delivered.toLocaleString()}`,
          value: totals.delivered,
          drop: totals.sent > 0 ? ((totals.sent - totals.delivered) / totals.sent) * 100 : 0,
          fill: GREEN_PALETTE.medium,
        },
        {
          name: "Opened",
          display: `Opened: ${totals.opened.toLocaleString()}`,
          value: totals.opened,
          drop: totals.delivered > 0 ? ((totals.delivered - totals.opened) / totals.delivered) * 100 : 0,
          fill: GREEN_PALETTE.dark,
        },
        {
          name: "Clicked",
          display: `Clicked: ${totals.clicked.toLocaleString()}`,
          value: totals.clicked,
          drop: totals.opened > 0 ? ((totals.opened - totals.clicked) / totals.opened) * 100 : 0,
          fill: GREEN_PALETTE.darkest,
        },
      ],
      templateLeaderboard: [],
      failureBreakdown: failure_breakdown ?? [],
      hourlyPerformance: [],
      ttrDistribution: [],
      pieData: [],
      timeSeriesData: [],
    };
  }, [emailAnalyticsData]);

  const isLoading = campaignsLoading || analyticsLoading || emailLoading;
  const analytics = activeChannel === "whatsapp" ? waAnalytics : emailAnalytics;

  return {
    analytics,
    waAnalytics,
    emailAnalytics,
    isLoading,
    activeChannel,
    setActiveChannel,
    campaigns,
    emailAnalyticsData
  };
}
