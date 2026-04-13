export interface TemplateStat {
  name: string;
  openRate: number;
  sent: number;
  score: number;
}

export interface HourlyStat {
  hour: string;
  rate: number;
  delivered: number;
}

export interface TTRStat {
  range: string;
  count: number;
}

export interface DashboardAnalytics {
  totals: {
    total: number;
    sent: number;
    delivered: number;
    read: number;
    replies: number;
    opened?: number;
    clicked?: number;
    bounced?: number;
    failed: number;
    reservego_members?: number;
  };
  rates: {
    deliveryRate: number;
    openRate: number;
    clickRate?: number;
    bounceRate?: number;
    effectiveReach: number;
    failureRate: number;
  };
  funnelData: {
    name: string;
    display: string;
    value: number;
    drop: number;
    fill: string;
  }[];
  templateLeaderboard: TemplateStat[];
  failureBreakdown: { reason: string; count: number }[];
  hourlyPerformance: HourlyStat[];
  ttrDistribution: TTRStat[];
  pieData: { name: string; value: number; fill?: string }[];
  timeSeriesData: {
    date: string;
    sortKey: number;
    sent: number;
    delivered: number;
    read: number;
    failed: number;
  }[];
}
