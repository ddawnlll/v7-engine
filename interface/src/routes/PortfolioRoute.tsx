import { useState } from "react";

import { useSearchParams } from "react-router-dom";

import { useMutation, useQuery } from "@tanstack/react-query";
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  BriefcaseBusiness,
  Clock3,
  TrendingDown,
  TrendingUp,
} from "lucide-react";

import { toast } from "sonner";

import { ProfileScopeBar } from "../components/profile/ProfileScopeBar";
import { AnimatedRoute } from "../components/ui/AnimatedRoute";
import { EmptyState } from "../components/ui/EmptyState";
import { Panel } from "../components/ui/Panel";
import { StatusBadge } from "../components/ui/StatusBadge";
import { useSettings } from "../contexts/SettingsContext";
import { fetchPortfolioForScope, syncRuntimeProfileReadOnly } from "../lib/api";
import {
  formatNumber,
  formatPercent,
  formatTime,
  toNumber,
} from "../lib/format";
import { useProfileScopeOptions } from "../hooks/useProfileScopeOptions";
import {
  DEFAULT_PROFILE_SCOPE,
  normalizeProfileScope,
  profileScopeToApiProfileId,
} from "../lib/profileScope";
import type {
  JsonRecord,
  PortfolioPayload,
  ProfileScopeValue,
} from "../lib/types";
import { OpenPositionsTable } from "../modules/portfolio/OpenPositionsTable";

type TradeBucket = {
  label: string;
  count: number;
  avgR: number;
  netR: number;
  tone: "good" | "bad" | "warn";
};

type SymbolMetric = {
  symbol: string;
  trades: number;
  winRate: number;
  netR: number;
  avgR: number;
};

type SortKey = keyof SymbolMetric;
type PortfolioTab = "open" | "closed";
type WindowKey = "7d" | "30d" | "all";
type StreakTone = "neutral" | "good" | "warn" | "bad";

type SparklinePoint = {
  value: number;
};

function formatTooltipR(value: unknown) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? `${numeric.toFixed(2)}R` : "--";
}

function formatTooltipTrades(value: unknown) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? `${numeric} trades` : "--";
}

function getOutcomeBucket(realizedR: number): "wins" | "losses" | "scratch" {
  if (realizedR > 0) return "wins";
  if (realizedR < 0) return "losses";
  return "scratch";
}

function computeDrawdownSeries(equityCurve: JsonRecord[]) {
  let peak = Number.NEGATIVE_INFINITY;
  let maxDrawdown = 0;

  const series = equityCurve.map((point) => {
    const netR = toNumber(point.net_r);
    peak = Math.max(peak, netR);
    const drawdown = peak - netR;
    maxDrawdown = Math.max(maxDrawdown, drawdown);

    return {
      time: formatTime(point.time),
      net_r: netR,
      drawdown,
    };
  });

  return { series, maxDrawdown };
}

function computeDelta(
  dailyBuckets: JsonRecord[],
  accessor: (bucket: JsonRecord) => number,
) {
  const ordered = [...dailyBuckets].sort((left, right) =>
    String(left.date ?? "").localeCompare(String(right.date ?? "")),
  );
  const recent = ordered.slice(-7);
  const previous = ordered.slice(-14, -7);

  const recentValue = recent.reduce((sum, item) => sum + accessor(item), 0);
  const previousValue = previous.reduce((sum, item) => sum + accessor(item), 0);
  const diff = recentValue - previousValue;

  return {
    diff,
    recentValue,
    previousValue,
  };
}

function computeStreakMetrics(closedTrades: JsonRecord[]) {
  const ordered = [...closedTrades].sort((left, right) =>
    String(left.close_timestamp ?? "").localeCompare(
      String(right.close_timestamp ?? ""),
    ),
  );

  let currentWin = 0;
  let currentLoss = 0;
  let longestWin = 0;
  let longestLoss = 0;
  let maxConsecutiveLoss = 0;
  let runningWin = 0;
  let runningLoss = 0;

  for (const trade of ordered) {
    const realized = toNumber(trade.realized_r);
    if (realized > 0) {
      runningWin += 1;
      runningLoss = 0;
      longestWin = Math.max(longestWin, runningWin);
    } else if (realized < 0) {
      runningLoss += 1;
      runningWin = 0;
      longestLoss = Math.max(longestLoss, runningLoss);
      maxConsecutiveLoss = Math.max(maxConsecutiveLoss, runningLoss);
    } else {
      runningWin = 0;
      runningLoss = 0;
    }
  }

  for (let index = ordered.length - 1; index >= 0; index -= 1) {
    const realized = toNumber(ordered[index].realized_r);
    if (realized > 0) {
      currentWin += 1;
      if (currentLoss > 0) break;
    } else if (realized < 0) {
      currentLoss += 1;
      if (currentWin > 0) break;
    } else {
      break;
    }
  }

  return {
    currentWin,
    currentLoss,
    longestWin,
    longestLoss,
    maxConsecutiveLoss,
  };
}

function computeDistribution(closedTrades: JsonRecord[]) {
  const buckets: Record<"wins" | "losses" | "scratch", TradeBucket> = {
    wins: { label: "Wins", count: 0, avgR: 0, netR: 0, tone: "good" },
    losses: { label: "Losses", count: 0, avgR: 0, netR: 0, tone: "bad" },
    scratch: { label: "Scratch", count: 0, avgR: 0, netR: 0, tone: "warn" },
  };

  for (const trade of closedTrades) {
    const hasPct =
      trade.realized_pnl_pct !== null && trade.realized_pnl_pct !== undefined;
    const pnlPct = toNumber(trade.realized_pnl_pct);
    const hasR = trade.realized_r !== null && trade.realized_r !== undefined;
    const realizedR = toNumber(trade.realized_r);

    let bucketKey: "wins" | "losses" | "scratch" = "scratch";
    if (hasPct) {
      if (pnlPct > 0) bucketKey = "wins";
      else if (pnlPct < 0) bucketKey = "losses";
    } else {
      if (realizedR > 0) bucketKey = "wins";
      else if (realizedR < 0) bucketKey = "losses";
    }

    const bucket = buckets[bucketKey];
    bucket.count += 1;
    if (hasR) {
      bucket.netR += realizedR;
    }
  }

  Object.values(buckets).forEach((bucket) => {
    bucket.avgR = bucket.count ? bucket.netR / bucket.count : 0;
  });

  return Object.values(buckets);
}

function computeSymbolMetrics(closedTrades: JsonRecord[]) {
  const grouped = new Map<
    string,
    { trades: number; wins: number; rTrades: number; netR: number }
  >();

  for (const trade of closedTrades) {
    const symbol = String(trade.symbol ?? "--");
    const hasR = trade.realized_r !== null && trade.realized_r !== undefined;
    const realizedR = toNumber(trade.realized_r);
    const hasPct =
      trade.realized_pnl_pct !== null && trade.realized_pnl_pct !== undefined;
    const pnlPct = toNumber(trade.realized_pnl_pct);

    const isWin = hasPct ? pnlPct > 0 : realizedR > 0;
    const current = grouped.get(symbol) ?? {
      trades: 0,
      wins: 0,
      rTrades: 0,
      netR: 0,
    };

    current.trades += 1;
    if (isWin) current.wins += 1;

    if (hasR) {
      current.rTrades += 1;
      current.netR += realizedR;
    }

    grouped.set(symbol, current);
  }

  return [...grouped.entries()].map(([symbol, value]) => ({
    symbol,
    trades: value.trades,
    winRate: value.trades ? (value.wins / value.trades) * 100 : 0,
    netR: value.netR,
    avgR: value.rTrades ? value.netR / value.rTrades : 0,
  }));
}

function computeEngineStatus(engine: Record<string, unknown>) {
  const threadAlive = Boolean(engine.thread_alive);
  const lastError = String(
    (engine.last_error as Record<string, unknown> | undefined)?.message ?? "",
  ).trim();
  const lastScanValue = (
    engine.last_scan as Record<string, unknown> | undefined
  )?.timestamp;
  const lastScan = lastScanValue ? new Date(String(lastScanValue)) : null;
  const ageMinutes = lastScan
    ? Math.round((Date.now() - lastScan.getTime()) / 60000)
    : Number.POSITIVE_INFINITY;

  if (!threadAlive) {
    return {
      label: "Degraded",
      tone: "bad" as const,
      message:
        "The engine thread is not alive, so portfolio metrics may be stale.",
    };
  }
  if (lastError) {
    return { label: "Warning", tone: "warn" as const, message: lastError };
  }
  if (ageMinutes > 120) {
    return {
      label: "Stale",
      tone: "warn" as const,
      message: `Last scan was ${ageMinutes} minutes ago.`,
    };
  }
  return {
    label: "Healthy",
    tone: "good" as const,
    message: "Scan cadence and trade monitoring look healthy.",
  };
}

function sortSymbolMetrics(
  metrics: SymbolMetric[],
  sortKey: SortKey,
  descending: boolean,
) {
  return [...metrics].sort((left, right) => {
    const leftValue = left[sortKey];
    const rightValue = right[sortKey];
    const order = leftValue < rightValue ? -1 : leftValue > rightValue ? 1 : 0;
    return descending ? order * -1 : order;
  });
}

function withinWindow(timestamp: unknown, windowKey: WindowKey) {
  if (windowKey === "all") return true;
  const value = String(timestamp ?? "");
  if (!value) return false;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return false;
  const days = windowKey === "7d" ? 7 : 30;
  return Date.now() - date.getTime() <= days * 24 * 60 * 60 * 1000;
}

function computeGroupedNetR(rows: JsonRecord[], field: "mode" | "interval") {
  const groups = new Map<string, { netR: number; trades: number }>();
  for (const row of rows) {
    const key = String(row[field] ?? "--");
    const current = groups.get(key) ?? { netR: 0, trades: 0 };
    current.netR += toNumber(row.realized_r);
    current.trades += 1;
    groups.set(key, current);
  }
  return [...groups.entries()].map(([label, value]) => ({
    label,
    netR: value.netR,
    trades: value.trades,
  }));
}

function buildSparklineSeries(values: number[]) {
  return values
    .filter((value) => Number.isFinite(value))
    .map((value) => ({ value }));
}

function rollingProfitFactor(dailyBuckets: JsonRecord[]) {
  let cumulativeGain = 0;
  let cumulativeLoss = 0;
  return dailyBuckets.map((bucket) => {
    const netR = toNumber(bucket.net_r);
    if (netR >= 0) {
      cumulativeGain += netR;
    } else {
      cumulativeLoss += Math.abs(netR);
    }
    const value =
      cumulativeLoss > 0 ? cumulativeGain / cumulativeLoss : cumulativeGain;
    return { value };
  });
}

function Sparkline({
  data,
  tone = "good",
}: {
  data: SparklinePoint[];
  tone?: "good" | "bad" | "neutral";
}) {
  const stroke =
    tone === "bad" ? "#be123c" : tone === "neutral" ? "#78716c" : "#145c56";
  if (!data.length) return <div className="h-8" />;
  return (
    <div className="h-8">
      <ResponsiveContainer width="99%" height="100%" minWidth={0} minHeight={0}>
        <LineChart data={data}>
          <Line
            type="monotone"
            dataKey="value"
            stroke={stroke}
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

// ─── Small reusable primitives ───────────────────────────────────────────────

function SectionEyebrow({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-[0.68rem] font-semibold uppercase tracking-[0.18em] text-stone-500">
      {children}
    </p>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="text-lg font-semibold tracking-[-0.04em] text-stone-950">
      {children}
    </h2>
  );
}

function Card({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`rounded-[1.4rem] border border-stone-900/8 bg-white/88 ${className}`}
    >
      {children}
    </div>
  );
}

function InnerCard({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={`rounded-[1.1rem] bg-stone-950/[0.03] ${className}`}>
      {children}
    </div>
  );
}

function Chip({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-full bg-stone-950/[0.04] px-3 py-1.5 text-xs text-stone-600">
      {children}
    </span>
  );
}

// ─── Zone 1: Command Strip ────────────────────────────────────────────────────

function CommandStrip({
  resolvedProfileId,
  resolvedAccountId,
  executionMode,
  venue,
  engineStatus,
  windowKey,
  setWindowKey,
  syncLiveMutation,
  engine,
  portfolioPayload,
  profileScopeOptions,
  profileScope,
  handleProfileScopeChange,
}: {
  resolvedProfileId: string;
  resolvedAccountId: string;
  executionMode: string;
  venue: string;
  engineStatus: ReturnType<typeof computeEngineStatus>;
  windowKey: WindowKey;
  setWindowKey: (w: WindowKey) => void;
  syncLiveMutation: any;
  engine: Record<string, unknown>;
  portfolioPayload: PortfolioPayload | null;
  profileScopeOptions: any;
  profileScope: any;
  handleProfileScopeChange: (v: any) => void;
}) {
  const statusColor =
    engineStatus.tone === "good"
      ? "bg-teal-600"
      : engineStatus.tone === "bad"
        ? "bg-rose-600"
        : "bg-amber-500";

  return (
    <Card className="px-4 py-3 shadow-[0_12px_32px_rgba(77,62,40,0.07)]">
      <div className="flex flex-wrap items-center justify-between gap-3">
        {/* Left: identity */}
        <div className="flex flex-wrap items-center gap-3">
          <ProfileScopeBar
            options={profileScopeOptions}
            value={profileScope}
            onChange={handleProfileScopeChange}
          />
          <div className="flex items-center gap-1.5">
            <span className={`h-2 w-2 rounded-full ${statusColor}`} />
            <span className="text-sm font-semibold text-stone-950">
              {engineStatus.label}
            </span>
          </div>
          <div className="hidden flex-wrap items-center gap-2 sm:flex">
            <Chip>{resolvedProfileId}</Chip>
            <Chip>
              {executionMode} · {venue}
            </Chip>
          </div>
        </div>

        {/* Right: controls */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Window toggle */}
          <div className="flex items-center gap-1 rounded-full border border-stone-900/8 bg-stone-950/[0.03] p-1">
            {(["7d", "30d", "all"] as WindowKey[]).map((w) => (
              <button
                key={w}
                type="button"
                onClick={() => setWindowKey(w)}
                className={`rounded-full px-3 py-1 text-xs font-semibold transition ${
                  windowKey === w
                    ? "bg-stone-950 text-stone-50"
                    : "text-stone-500 hover:text-stone-700"
                }`}
              >
                {w === "7d" ? "7D" : w === "30d" ? "30D" : "All"}
              </button>
            ))}
          </div>

          {/* Sync button — only in live mode */}
          {executionMode === "LIVE" && (
            <button
              type="button"
              onClick={() => syncLiveMutation.mutate()}
              disabled={syncLiveMutation.isPending}
              className="flex items-center gap-1.5 rounded-full border border-stone-900/8 bg-white px-3 py-1.5 text-xs font-semibold text-stone-700 hover:bg-stone-50 disabled:opacity-50"
            >
              <RefreshCw
                className={`h-3 w-3 ${syncLiveMutation.isPending ? "animate-spin" : ""}`}
                strokeWidth={2}
              />
              {syncLiveMutation.isPending ? "Syncing…" : "Sync Binance"}
            </button>
          )}

          <Chip>
            Scan{" "}
            {formatTime(
              (engine.last_scan as Record<string, unknown> | undefined)
                ?.timestamp,
            )}
          </Chip>
          <Chip>Gen {formatTime(portfolioPayload?.generated_at)}</Chip>
        </div>
      </div>
    </Card>
  );
}

// ─── Zone 2: Hero KPIs ───────────────────────────────────────────────────────

function HeroKpis({
  summary,
  netRDelta,
  winRateDelta,
  filteredClosed,
}: {
  summary: JsonRecord;
  netRDelta: ReturnType<typeof computeDelta>;
  winRateDelta: ReturnType<typeof computeDelta>;
  filteredClosed: JsonRecord[];
}) {
  const profitFactor = toNumber(summary.profit_factor);

  const items = [
    {
      label: "Net R",
      value: `${formatNumber(summary.net_r)}R`,
      delta: `${netRDelta.diff >= 0 ? "+" : ""}${formatNumber(netRDelta.diff)}R vs prior 7d`,
      positive: netRDelta.diff >= 0,
    },
    {
      label: "Win rate",
      value: formatPercent(summary.win_rate, 1),
      delta: `${winRateDelta.diff >= 0 ? "+" : ""}${formatNumber(winRateDelta.diff, 0)} wins vs prior 7d`,
      positive: winRateDelta.diff >= 0,
    },
    {
      label: "Profit factor",
      value: formatNumber(profitFactor),
      delta: filteredClosed.length
        ? `${filteredClosed.length} closes in view`
        : "No recent closes",
      positive: profitFactor >= 1,
    },
  ];

  return (
    <Card className="overflow-hidden shadow-[0_18px_48px_rgba(77,62,40,0.09)]">
      <div className="grid divide-x divide-stone-900/8 sm:grid-cols-3">
        {items.map((item) => (
          <div key={item.label} className="px-6 py-5">
            <SectionEyebrow>{item.label}</SectionEyebrow>
            <p className="mt-2 text-[2.6rem] font-semibold leading-none tracking-[-0.06em] text-stone-950">
              {item.value}
            </p>
            <p
              className={`mt-2 text-sm ${item.positive ? "text-teal-800" : "text-rose-700"}`}
            >
              {item.delta}
            </p>
          </div>
        ))}
      </div>
    </Card>
  );
}

// ─── Zone 3: Secondary KPI Strip ─────────────────────────────────────────────

function SecondaryKpis({
  kpis,
  settings,
}: {
  kpis: {
    label: string;
    raw: string;
    value: string;
    delta: string;
    tone: string;
    icon: React.ElementType;
    sparkline: SparklinePoint[];
  }[];
  settings: any;
}) {
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
      {kpis.map((item) => (
        <Card key={item.label} className="p-4">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <SectionEyebrow>{item.label}</SectionEyebrow>
              {settings.showRawKeys && (
                <p className="mt-0.5 font-mono text-[0.62rem] text-stone-400">
                  {item.raw}
                </p>
              )}
            </div>
            <item.icon
              className="mt-0.5 h-3.5 w-3.5 shrink-0 text-stone-400"
              strokeWidth={1.8}
            />
          </div>
          <p className="mt-3 text-2xl font-semibold tracking-[-0.04em] text-stone-950">
            {item.value}
          </p>
          <div className="mt-2">
            <Sparkline
              data={item.sparkline}
              tone={
                item.tone === "bad"
                  ? "bad"
                  : item.tone === "warn"
                    ? "neutral"
                    : "good"
              }
            />
          </div>
          <p
            className={`mt-1.5 text-xs ${
              item.tone === "good"
                ? "text-teal-900"
                : item.tone === "bad"
                  ? "text-rose-800"
                  : item.tone === "warn"
                    ? "text-amber-900"
                    : "text-stone-500"
            }`}
          >
            {item.delta}
          </p>
        </Card>
      ))}
    </div>
  );
}

// ─── Zone 4: Analytics Canvas ────────────────────────────────────────────────

function EquityAndDrawdown({
  equityData,
}: {
  equityData: { time: string; net_r: number; drawdown: number }[];
}) {
  return (
    <Card className="p-4 shadow-[0_12px_32px_rgba(77,62,40,0.06)]">
      <SectionEyebrow>Equity &amp; drawdown</SectionEyebrow>
      <SectionTitle>Performance and pain on one timeline</SectionTitle>
      <p className="mt-1 mb-3 text-xs text-stone-500">
        Equity above · drawdown below · shared x-axis
      </p>

      <InnerCard className="min-h-[200px] h-[200px] p-3">
        {equityData.length ? (
          <ResponsiveContainer
            width="99%"
            height="100%"
            minWidth={0}
            minHeight={0}
          >
            <AreaChart data={equityData} syncId="portfolio">
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="rgba(69,58,44,0.08)"
              />
              <XAxis dataKey="time" hide />
              <YAxis
                tickFormatter={(v) => `${v}R`}
                tickLine={false}
                axisLine={false}
                tick={{ fontSize: 11 }}
              />
              <Tooltip formatter={formatTooltipR} />
              <defs>
                <linearGradient id="eqGrad" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0%" stopColor="rgba(20,92,86,0.28)" />
                  <stop offset="100%" stopColor="rgba(20,92,86,0.02)" />
                </linearGradient>
              </defs>
              <Area
                type="monotone"
                dataKey="net_r"
                stroke="#145c56"
                fill="url(#eqGrad)"
                strokeWidth={2.5}
              />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <EmptyState message="Equity curve will appear as settled trades accumulate." />
        )}
      </InnerCard>

      <div className="my-3 h-px bg-stone-900/8" />

      <InnerCard className="min-h-[110px] h-[110px] p-3">
        {equityData.length ? (
          <ResponsiveContainer
            width="99%"
            height="100%"
            minWidth={0}
            minHeight={0}
          >
            <AreaChart data={equityData} syncId="portfolio">
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="rgba(69,58,44,0.08)"
              />
              <XAxis
                dataKey="time"
                tickLine={false}
                axisLine={false}
                tick={{ fill: "#78716c", fontSize: 10 }}
              />
              <YAxis
                tickFormatter={(v) => `${v}R`}
                tickLine={false}
                axisLine={false}
                tick={{ fontSize: 11 }}
              />
              <Tooltip formatter={formatTooltipR} />
              <defs>
                <linearGradient id="ddGrad" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0%" stopColor="rgba(161,98,7,0.24)" />
                  <stop offset="100%" stopColor="rgba(161,98,7,0.02)" />
                </linearGradient>
              </defs>
              <Area
                type="monotone"
                dataKey="drawdown"
                stroke="#a16207"
                fill="url(#ddGrad)"
                strokeWidth={2}
              />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <EmptyState message="Drawdown appears once equity points exist." />
        )}
      </InnerCard>
    </Card>
  );
}

function OutcomeMix({
  distribution,
  summary,
  streaks,
}: {
  distribution: TradeBucket[];
  summary: JsonRecord;
  streaks: ReturnType<typeof computeStreakMetrics>;
}) {
  const total = distribution.reduce((s, b) => s + b.count, 0);

  return (
    <Card className="p-4 shadow-[0_12px_32px_rgba(77,62,40,0.06)]">
      <SectionEyebrow>Outcome mix</SectionEyebrow>
      <SectionTitle>Win, loss &amp; scratch</SectionTitle>

      {/* Donut */}
      <InnerCard className="mt-3 min-h-[180px] h-[180px] p-2">
        {distribution.some((b) => b.count > 0) ? (
          <div className="relative h-full">
            <ResponsiveContainer
              width="99%"
              height="100%"
              minWidth={0}
              minHeight={0}
            >
              <PieChart>
                <Pie
                  data={distribution}
                  dataKey="count"
                  nameKey="label"
                  innerRadius={46}
                  outerRadius={72}
                  paddingAngle={3}
                >
                  {distribution.map((entry) => (
                    <Cell
                      key={entry.label}
                      fill={
                        entry.tone === "good"
                          ? "#145c56"
                          : entry.tone === "bad"
                            ? "#be123c"
                            : "#a16207"
                      }
                    />
                  ))}
                </Pie>
                <Tooltip formatter={formatTooltipTrades} />
              </PieChart>
            </ResponsiveContainer>
            <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
              <div className="text-center">
                <p className="text-[0.62rem] uppercase tracking-[0.18em] text-stone-500">
                  Trades
                </p>
                <p className="text-3xl font-semibold tracking-[-0.05em] text-stone-950">
                  {formatNumber(total, 0)}
                </p>
                <p className="text-xs text-stone-500">
                  {formatPercent(summary.win_rate, 1)} wins
                </p>
              </div>
            </div>
          </div>
        ) : (
          <EmptyState message="Distribution appears when trades settle." />
        )}
      </InnerCard>

      {/* Bars */}
      <div className="mt-3 grid gap-2">
        {distribution.map((bucket) => {
          const pct = total ? (bucket.count / total) * 100 : 0;
          return (
            <div key={bucket.label}>
              <div className="flex items-center justify-between gap-2 mb-1">
                <div className="flex items-center gap-2">
                  <StatusBadge label={bucket.label} tone={bucket.tone} />
                  <span className="text-xs text-stone-500">{bucket.count}</span>
                </div>
                <span className="text-xs font-semibold text-stone-950">
                  {formatNumber(bucket.avgR)}R avg
                </span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-stone-950/[0.06]">
                <div
                  className={`h-full rounded-full ${bucket.tone === "good" ? "bg-teal-700" : bucket.tone === "bad" ? "bg-rose-700" : "bg-amber-700"}`}
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>

      {/* Streaks */}
      <div className="mt-4 border-t border-stone-900/8 pt-4">
        <SectionEyebrow>Consistency</SectionEyebrow>
        <div className="mt-2 grid grid-cols-3 gap-2">
          {[
            {
              label: "Current",
              value:
                streaks.currentWin > 0
                  ? `${streaks.currentWin}W`
                  : streaks.currentLoss > 0
                    ? `${streaks.currentLoss}L`
                    : "Flat",
              tone: (streaks.currentWin > 0
                ? "good"
                : streaks.currentLoss > 0
                  ? "bad"
                  : "neutral") as StreakTone,
            },
            {
              label: "Best win",
              value: String(streaks.longestWin),
              tone: "good" as const,
            },
            {
              label: "Max loss",
              value: String(streaks.maxConsecutiveLoss),
              tone: "bad" as const,
            },
          ].map((item) => (
            <InnerCard key={item.label} className="p-3">
              <p className="text-[0.62rem] uppercase tracking-[0.14em] text-stone-500">
                {item.label}
              </p>
              <p
                className={`mt-1.5 text-xl font-semibold tracking-tight ${item.tone === "good" ? "text-teal-900" : item.tone === "bad" ? "text-rose-800" : "text-stone-700"}`}
              >
                {item.value}
              </p>
            </InnerCard>
          ))}
        </div>
      </div>
    </Card>
  );
}

function PortfolioSnapshot({
  portfolio,
  availableBalance,
  equityBalance,
  marginUsed,
  balanceCurrency,
  summary,
  latestCloseTimestamp,
  engineStatus,
}: {
  portfolio: JsonRecord;
  availableBalance: number;
  equityBalance: number;
  marginUsed: number;
  balanceCurrency: string;
  summary: JsonRecord;
  latestCloseTimestamp: string;
  engineStatus: ReturnType<typeof computeEngineStatus>;
}) {
  const rows = [
    ["Open positions", formatNumber(portfolio.open_orders, 0)],
    ["Total orders", formatNumber(portfolio.total_orders, 0)],
    ["Equity", `${balanceCurrency} ${formatNumber(equityBalance, 2)}`],
    ["Margin used", `${balanceCurrency} ${formatNumber(marginUsed, 2)}`],
    [
      "Today change",
      `$${formatNumber(summary.today_pnl, 2)} (${formatPercent(summary.today_pnl_pct, 2)})`,
    ],
    [
      "3-day change",
      `$${formatNumber(summary.three_day_pnl, 2)} (${formatPercent(summary.three_day_pnl_pct, 2)})`,
    ],
    [
      "Available balance",
      `${balanceCurrency} ${formatNumber(availableBalance, 2)}`,
    ],
    ["Latest close", latestCloseTimestamp],
  ];

  return (
    <Card className="p-4 shadow-[0_12px_32px_rgba(77,62,40,0.06)]">
      <SectionEyebrow>Snapshot</SectionEyebrow>
      <SectionTitle>Position &amp; account context</SectionTitle>

      <div className="mt-3 grid grid-cols-2 gap-2">
        {rows.map(([label, value]) => (
          <InnerCard key={label} className="p-3">
            <p className="text-[0.62rem] uppercase tracking-[0.14em] text-stone-500">
              {label}
            </p>
            <p className="mt-1 text-sm font-semibold leading-snug text-stone-950">
              {value}
            </p>
          </InnerCard>
        ))}
      </div>

      <div
        className={`mt-3 rounded-[1.1rem] border p-3 ${
          engineStatus.tone === "good"
            ? "border-teal-900/10 bg-teal-700/6"
            : engineStatus.tone === "bad"
              ? "border-rose-900/10 bg-rose-700/6"
              : "border-amber-900/10 bg-amber-700/6"
        }`}
      >
        <div className="flex items-start gap-2.5">
          <ShieldCheck
            className="mt-0.5 h-4 w-4 shrink-0 text-teal-900"
            strokeWidth={1.8}
          />
          <div>
            <p className="text-sm font-semibold text-stone-950">
              {engineStatus.label}
            </p>
            <p className="text-xs text-stone-600">{engineStatus.message}</p>
          </div>
        </div>
      </div>
    </Card>
  );
}

// ─── Zone 5: Attribution Row ─────────────────────────────────────────────────

function DailyCadence({
  cadenceData,
}: {
  cadenceData: { date: string; trades: number; net_r: number }[];
}) {
  return (
    <Card className="p-4">
      <SectionEyebrow>Daily cadence</SectionEyebrow>
      <SectionTitle>P&amp;L by day</SectionTitle>
      <InnerCard className="mt-3 min-h-[200px] h-[200px] p-3">
        {cadenceData.length ? (
          <ResponsiveContainer
            width="99%"
            height="100%"
            minWidth={0}
            minHeight={0}
          >
            <BarChart data={cadenceData}>
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="rgba(69,58,44,0.08)"
              />
              <XAxis
                dataKey="date"
                tickLine={false}
                axisLine={false}
                tick={{ fontSize: 10 }}
              />
              <YAxis
                tickLine={false}
                axisLine={false}
                tickFormatter={(v) => `${v}R`}
                tick={{ fontSize: 11 }}
              />
              <Tooltip />
              <Bar dataKey="net_r" radius={[6, 6, 0, 0]}>
                {cadenceData.map((item) => (
                  <Cell
                    key={item.date}
                    fill={item.net_r >= 0 ? "#145c56" : "#be123c"}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <EmptyState message="Daily cadence appears once enough daily buckets exist." />
        )}
      </InnerCard>
    </Card>
  );
}

function HorizontalBarPanel({
  eyebrow,
  title,
  data,
}: {
  eyebrow: string;
  title: string;
  data: { label: string; netR: number; trades: number }[];
}) {
  return (
    <Card className="p-4">
      <SectionEyebrow>{eyebrow}</SectionEyebrow>
      <SectionTitle>{title}</SectionTitle>
      <InnerCard className="mt-3 min-h-[200px] h-[200px] p-3">
        {data.length ? (
          <ResponsiveContainer
            width="99%"
            height="100%"
            minWidth={0}
            minHeight={0}
          >
            <BarChart
              data={data}
              layout="vertical"
              margin={{ left: 8, right: 12 }}
            >
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="rgba(69,58,44,0.08)"
              />
              <XAxis
                type="number"
                tickLine={false}
                axisLine={false}
                tickFormatter={(v) => `${v}R`}
                tick={{ fontSize: 11 }}
              />
              <YAxis
                type="category"
                dataKey="label"
                width={88}
                tickLine={false}
                axisLine={false}
                tick={{ fontSize: 11 }}
              />
              <Tooltip formatter={formatTooltipR} />
              <Bar dataKey="netR" radius={[0, 6, 6, 0]}>
                {data.map((item) => (
                  <Cell
                    key={item.label}
                    fill={item.netR >= 0 ? "#145c56" : "#be123c"}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <EmptyState message="Appears when the selected window has closed trades." />
        )}
      </InnerCard>
    </Card>
  );
}

// ─── Zone 6: Symbol Attribution ───────────────────────────────────────────────

function SymbolAttribution({
  sortedSymbolMetrics,
  sortKey,
  setSortKey,
  sortDescending,
  setSortDescending,
}: {
  sortedSymbolMetrics: SymbolMetric[];
  sortKey: SortKey;
  setSortKey: (k: SortKey) => void;
  sortDescending: boolean;
  setSortDescending: (fn: (prev: boolean) => boolean) => void;
}) {
  const columns: [SortKey, string][] = [
    ["symbol", "Symbol"],
    ["trades", "Trades"],
    ["winRate", "Win rate"],
    ["netR", "Net R"],
    ["avgR", "Avg R"],
  ];

  return (
    <Card className="overflow-hidden shadow-[0_12px_32px_rgba(77,62,40,0.06)]">
      <div className="px-5 pt-4 pb-3">
        <SectionEyebrow>Symbol attribution</SectionEyebrow>
        <SectionTitle>Which tickers are carrying the portfolio</SectionTitle>
      </div>

      {/* Header */}
      <div className="hidden grid-cols-[1.15fr_0.55fr_0.7fr_0.7fr_0.7fr] gap-3 border-y border-stone-900/8 bg-stone-950/[0.02] px-5 py-2.5 lg:grid">
        {columns.map(([key, label]) => (
          <button
            key={key}
            type="button"
            className={`inline-flex items-center gap-1 text-left text-[0.68rem] font-semibold uppercase tracking-[0.14em] transition hover:text-stone-950 ${sortKey === key ? "text-stone-950" : "text-stone-500"}`}
            onClick={() => {
              if (sortKey === key) setSortDescending((c) => !c);
              else {
                setSortKey(key);
                setSortDescending(() => true);
              }
            }}
          >
            {label}
            {sortKey === key ? (
              sortDescending ? (
                <ArrowDown className="h-3 w-3" strokeWidth={2} />
              ) : (
                <ArrowUp className="h-3 w-3" strokeWidth={2} />
              )
            ) : (
              <ArrowUpDown className="h-3 w-3 opacity-40" strokeWidth={2} />
            )}
          </button>
        ))}
      </div>

      {/* Rows */}
      <div className="divide-y divide-stone-900/6">
        {sortedSymbolMetrics.length ? (
          sortedSymbolMetrics.map((metric) => (
            <div
              key={metric.symbol}
              className="px-5 py-3 transition hover:bg-stone-950/[0.02]"
            >
              {/* Desktop */}
              <div className="hidden grid-cols-[1.15fr_0.55fr_0.7fr_0.7fr_0.7fr] gap-3 items-center lg:grid">
                <span className="font-semibold text-stone-950">
                  {metric.symbol}
                </span>
                <span className="text-sm text-stone-600">{metric.trades}</span>
                <span className="text-sm text-stone-600">
                  {formatPercent(metric.winRate, 1)}
                </span>
                <span
                  className={`font-mono text-sm font-semibold ${metric.netR >= 0 ? "text-teal-900" : "text-rose-800"}`}
                >
                  {formatNumber(metric.netR)}R
                </span>
                <span className="font-mono text-sm text-stone-600">
                  {formatNumber(metric.avgR)}R
                </span>
              </div>
              {/* Mobile */}
              <div className="grid gap-2 lg:hidden">
                <div className="flex items-center justify-between">
                  <strong className="font-semibold text-stone-950">
                    {metric.symbol}
                  </strong>
                  <span
                    className={`font-mono text-sm font-semibold ${metric.netR >= 0 ? "text-teal-900" : "text-rose-800"}`}
                  >
                    {formatNumber(metric.netR)}R
                  </span>
                </div>
                <div className="grid grid-cols-3 gap-2">
                  {[
                    ["Trades", String(metric.trades)],
                    ["Win rate", formatPercent(metric.winRate, 1)],
                    ["Avg R", `${formatNumber(metric.avgR)}R`],
                  ].map(([l, v]) => (
                    <InnerCard key={l} className="p-2">
                      <p className="text-[0.6rem] uppercase tracking-[0.14em] text-stone-500">
                        {l}
                      </p>
                      <p className="mt-1 text-sm font-semibold text-stone-950">
                        {v}
                      </p>
                    </InnerCard>
                  ))}
                </div>
              </div>
            </div>
          ))
        ) : (
          <div className="px-5 py-6">
            <EmptyState message="Symbol attribution appears once closed trades accumulate." />
          </div>
        )}
      </div>
    </Card>
  );
}

// ─── Zone 7: Positions Drawer ─────────────────────────────────────────────────

function PositionsDrawer({
  activeTab,
  setActiveTab,
  openOrders,
  recentClosed,
}: {
  activeTab: PortfolioTab;
  setActiveTab: (t: PortfolioTab) => void;
  openOrders: JsonRecord[];
  recentClosed: JsonRecord[];
}) {
  return (
    <Card className="overflow-hidden shadow-[0_12px_32px_rgba(77,62,40,0.06)]">
      {/* Header with tabs */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-stone-900/8 px-5 py-4">
        <div>
          <SectionEyebrow>Portfolio detail</SectionEyebrow>
          <SectionTitle>Open &amp; recently closed positions</SectionTitle>
        </div>
        <div className="relative inline-grid grid-cols-2 rounded-full border border-stone-900/8 bg-stone-950/[0.03] p-1">
          <div
            className={`absolute inset-y-1 w-[calc(50%-0.25rem)] rounded-full bg-stone-950 transition-transform duration-300 ${activeTab === "closed" ? "translate-x-full" : "translate-x-0"}`}
          />
          {(["open", "closed"] as PortfolioTab[]).map((tab) => (
            <button
              key={tab}
              type="button"
              onClick={() => setActiveTab(tab)}
              className={`relative z-10 rounded-full px-4 py-1.5 text-sm font-semibold transition ${activeTab === tab ? "text-stone-50" : "text-stone-600"}`}
            >
              {tab === "open"
                ? `Open (${openOrders.length})`
                : `Closed (${Math.min(recentClosed.length, 10)})`}
            </button>
          ))}
        </div>
      </div>

      <div className="p-4">
        {activeTab === "open" && <OpenPositionsTable rows={openOrders} />}

        {activeTab === "closed" && (
          <div className="grid gap-2">
            {recentClosed.length ? (
              recentClosed.slice(0, 10).map((order, index) => {
                const hasR =
                  order.realized_r !== null && order.realized_r !== undefined;
                const realizedR = toNumber(order.realized_r);
                const pnlPct = toNumber(order.realized_pnl_pct);
                const hasPct =
                  order.realized_pnl_pct !== null &&
                  order.realized_pnl_pct !== undefined;
                const pnlUsdt = toNumber(order.realized_pnl);
                const isPositive = (hasPct ? pnlPct : realizedR) >= 0;

                return (
                  <div
                    key={`${String(order.symbol)}-${index}-${String(order.close_timestamp)}`}
                    className="grid items-center gap-3 rounded-2xl bg-white/82 px-4 py-3 shadow-[0_8px_16px_rgba(71,53,29,0.05)] lg:grid-cols-[0.9fr_0.8fr_0.5fr_0.4fr]"
                  >
                    <div>
                      <strong className="text-sm font-semibold text-stone-950">
                        {String(order.symbol ?? "--")}
                      </strong>
                      <p className="text-xs text-stone-500">
                        {String(order.mode ?? "--")} ·{" "}
                        {String(order.interval ?? "--")}
                      </p>
                    </div>
                    <div>
                      <StatusBadge
                        label={String(order.close_reason ?? "--")}
                        tone={isPositive ? "good" : "bad"}
                      />
                      <p className="mt-1 text-xs text-stone-500">
                        {formatTime(order.close_timestamp)}
                      </p>
                    </div>
                    <div>
                      <p
                        className={`font-mono text-sm font-semibold ${isPositive ? "text-teal-900" : "text-rose-800"}`}
                      >
                        {hasPct
                          ? `${pnlPct > 0 ? "+" : ""}${formatNumber(pnlPct, 2)}%`
                          : `${pnlUsdt > 0 ? "+" : ""}$${formatNumber(pnlUsdt, 2)}`}
                      </p>
                      <p className="text-xs text-stone-500">
                        R:{" "}
                        {hasR
                          ? `${realizedR > 0 ? "+" : ""}${formatNumber(realizedR, 2)}R`
                          : "N/A"}
                      </p>
                    </div>
                    <p className="text-xs text-stone-500">
                      {formatNumber(order.hold_minutes, 1)}m hold
                    </p>
                  </div>
                );
              })
            ) : (
              <EmptyState message="Closed trades will appear here as the engine settles them." />
            )}
          </div>
        )}
      </div>
    </Card>
  );
}

// ─── Zone 8: Live Binance Sync (conditional) ──────────────────────────────────

function LiveSyncPanel({
  engine,
  syncLiveMutation,
  executionMode,
  venue,
  balanceCurrency,
  summary,
  availableBalance,
  venueOpenOrders,
  venuePositions,
  pnlAssets,
  resolvedAccountId,
}: {
  engine: Record<string, unknown>;
  syncLiveMutation: any;
  executionMode: string;
  venue: string;
  balanceCurrency: string;
  summary: JsonRecord;
  availableBalance: number;
  venueOpenOrders: JsonRecord[];
  venuePositions: JsonRecord[];
  pnlAssets: JsonRecord[];
  resolvedAccountId: string;
}) {
  return (
    <Card className="p-5 shadow-[0_12px_32px_rgba(77,62,40,0.06)]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <SectionEyebrow>Live Binance sync</SectionEyebrow>
          <SectionTitle>Account, venue orders &amp; PnL assets</SectionTitle>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => syncLiveMutation.mutate()}
            disabled={syncLiveMutation.isPending}
            className="flex items-center gap-1.5 rounded-full border border-stone-900/8 bg-white px-3 py-1.5 text-sm font-semibold text-stone-950 hover:bg-stone-50 disabled:opacity-60"
          >
            <RefreshCw
              className={`h-3.5 w-3.5 ${syncLiveMutation.isPending ? "animate-spin" : ""}`}
              strokeWidth={2}
            />
            {syncLiveMutation.isPending ? "Syncing…" : "Sync now"}
          </button>
          <StatusBadge
            label={
              syncLiveMutation.isPending
                ? "SYNCING"
                : String(engine.sync_status ?? "SYNCED")
            }
            tone={
              syncLiveMutation.isPending
                ? "warn"
                : String(engine.sync_status ?? "").toUpperCase() === "SYNCED"
                  ? "good"
                  : "neutral"
            }
          />
          <Chip>Mode {executionMode}</Chip>
          <Chip>Venue {venue}</Chip>
          <Chip>
            Reconciliation {String(engine.reconciliation_status ?? "--")}
          </Chip>
        </div>
      </div>

      <div className="mt-4 grid gap-2 text-sm text-stone-700 sm:grid-cols-4">
        {[
          [
            "Total balance",
            `${balanceCurrency} ${formatNumber(summary.total_balance, 2)}`,
          ],
          [
            "Available balance",
            `${balanceCurrency} ${formatNumber(availableBalance, 2)}`,
          ],
          ["Venue open orders", formatNumber(venueOpenOrders.length, 0)],
          ["Venue positions", formatNumber(venuePositions.length, 0)],
        ].map(([label, value]) => (
          <div key={label}>
            {label}:{" "}
            <span className="font-semibold text-stone-950">{value}</span>
          </div>
        ))}
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        {/* PnL assets */}
        <InnerCard className="p-4">
          <p className="text-sm font-semibold text-stone-950">
            Assets with active PnL
          </p>
          <div className="mt-3 space-y-2">
            {pnlAssets.length ? (
              pnlAssets.map((asset, i) => (
                <div
                  key={`${String(asset.asset)}-${i}`}
                  className="flex items-center justify-between rounded-xl bg-white/80 px-3 py-2 text-sm"
                >
                  <span className="text-stone-700">
                    {String(asset.asset ?? "--")}
                  </span>
                  <span className="font-semibold text-stone-950">
                    {formatNumber(asset.cross_unrealized_pnl, 4)}
                  </span>
                </div>
              ))
            ) : (
              <p className="text-sm text-stone-500">
                No assets carry unrealized PnL.
              </p>
            )}
          </div>
        </InnerCard>

        {/* Venue orders */}
        <InnerCard className="p-4">
          <p className="text-sm font-semibold text-stone-950">
            Venue open orders
          </p>
          <div className="mt-3 space-y-2">
            {venueOpenOrders.length ? (
              venueOpenOrders.map((order, i) => (
                <div
                  key={`${String(order.symbol)}-${i}`}
                  className="rounded-xl bg-white/80 px-3 py-2 text-sm"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-semibold text-stone-950">
                      {String(order.symbol ?? "--")}
                    </span>
                    <span className="text-stone-600">
                      {String(order.status ?? "--")}
                    </span>
                  </div>
                  <p className="mt-0.5 text-xs text-stone-500">
                    {String(order.order_type ?? "--")} · qty{" "}
                    {formatNumber(order.quantity, 4)} · price{" "}
                    {formatNumber(order.price, 4)}
                  </p>
                </div>
              ))
            ) : (
              <p className="text-sm text-stone-500">No open venue orders.</p>
            )}
          </div>
        </InnerCard>

        {/* Today symbols */}
        <InnerCard className="p-4">
          <p className="text-sm font-semibold text-stone-950">
            Today realized symbols
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {((summary.today_symbols as unknown[]) ?? []).length ? (
              ((summary.today_symbols as unknown[]) ?? []).map((symbol, i) => (
                <span
                  key={`${String(symbol)}-${i}`}
                  className="rounded-full bg-white px-3 py-1.5 text-sm text-stone-700"
                >
                  {String(symbol)}
                </span>
              ))
            ) : (
              <p className="text-sm text-stone-500">
                No locally realized symbols today.
              </p>
            )}
          </div>
        </InnerCard>
      </div>
    </Card>
  );
}

// ─── Root Route ───────────────────────────────────────────────────────────────

export function PortfolioRoute() {
  const { settings, term, rawKey } = useSettings();
  const [searchParams, setSearchParams] = useSearchParams();
  const { options: profileScopeOptions } = useProfileScopeOptions();
  const profileScope = normalizeProfileScope(
    searchParams.get("profile"),
    profileScopeOptions,
  );
  const scopedProfileId = profileScopeToApiProfileId(
    profileScope,
    profileScopeOptions,
  );

  const portfolioQuery = useQuery({
    queryKey: ["portfolio", profileScope],
    queryFn: () => fetchPortfolioForScope(profileScope),
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    staleTime: 60_000,
  });

  const syncLiveMutation = useMutation({
    mutationFn: async () => {
      const profileId = profileScopeToApiProfileId(
        profileScope,
        profileScopeOptions,
      );
      if (!profileId || profileId === DEFAULT_PROFILE_SCOPE)
        throw new Error(
          "Live sync is only available for live runtime profiles.",
        );
      return syncRuntimeProfileReadOnly(profileId);
    },
    onSuccess: async () => {
      toast.success("Binance sync completed");
      await portfolioQuery.refetch();
    },
    onError: (error) =>
      toast.error(
        error instanceof Error ? error.message : "Binance sync failed",
      ),
  });

  const portfolioPayload = (portfolioQuery.data ??
    null) as PortfolioPayload | null;
  const summary = portfolioPayload?.summary ?? {};
  const portfolio = portfolioPayload?.portfolio ?? {};
  const account = (portfolioPayload?.account ??
    portfolioPayload?.paper_account ??
    {}) as JsonRecord;
  const paperAccount = account;
  const resolvedProfileId = String(
    portfolioPayload?.profile_id ??
      account.profile_id ??
      scopedProfileId ??
      DEFAULT_PROFILE_SCOPE,
  );
  const resolvedAccountId = String(
    portfolioPayload?.account_id ??
      account.account_id ??
      `${resolvedProfileId}:default`,
  );
  const executionMode = String(
    portfolio.execution_mode ??
      (resolvedProfileId.startsWith("paper-") ? "PAPER" : "LIVE"),
  );
  const venue = String(
    portfolio.venue ??
      (resolvedProfileId.startsWith("paper-") ? "paper" : "binance_usdm"),
  ).toLowerCase();
  const availableBalance = toNumber(
    account.available_balance ?? summary.paper_balance,
  );
  const equityBalance = toNumber(
    account.equity ?? summary.total_equity ?? portfolio.total_equity,
  );
  const marginUsed = toNumber(account.margin_used ?? summary.margin_used);
  const balanceCurrency = String(account.balance_ccy ?? "USDT");
  const engine = (portfolioPayload?.engine ?? {}) as Record<string, unknown>;
  const performanceWindows = (summary.performance_windows ?? {}) as Record<
    string,
    JsonRecord
  >;
  const todayWindow = (performanceWindows.today ?? {}) as JsonRecord;
  const dailyBuckets = portfolioPayload?.daily ?? [];
  const equityCurve = portfolioPayload?.equity_curve ?? [];
  const openOrders = portfolioPayload?.open_positions ?? [];
  const recentClosed = portfolioPayload?.recent_closed ?? [];
  const pnlAssets = portfolioPayload?.pnl_assets ?? [];
  const venueOpenOrders = portfolioPayload?.venue_open_orders ?? [];
  const venuePositions = portfolioPayload?.venue_positions ?? [];

  const [sortKey, setSortKey] = useState<SortKey>("netR");
  const [sortDescending, setSortDescending] = useState(true);
  const [activeTab, setActiveTab] = useState<PortfolioTab>("open");
  const [windowKey, setWindowKey] = useState<WindowKey>("30d");

  const filteredClosed = recentClosed.filter((trade) =>
    withinWindow(trade.close_timestamp, windowKey),
  );
  const filteredDailyBuckets = dailyBuckets.filter((bucket) =>
    withinWindow(`${String(bucket.date ?? "")}T00:00:00`, windowKey),
  );
  const filteredEquityCurve = equityCurve.filter((point) =>
    withinWindow(point.time, windowKey),
  );

  const { series: equityData, maxDrawdown } =
    computeDrawdownSeries(filteredEquityCurve);
  const symbolMetrics = computeSymbolMetrics(filteredClosed);
  const sortedSymbolMetrics = sortSymbolMetrics(
    symbolMetrics,
    sortKey,
    sortDescending,
  );
  const distribution = computeDistribution(filteredClosed);
  const streaks = computeStreakMetrics(filteredClosed);
  const engineStatus = computeEngineStatus(engine);

  const winRateDelta = computeDelta(filteredDailyBuckets, (b) =>
    toNumber(b.wins),
  );
  const netRDelta = computeDelta(filteredDailyBuckets, (b) =>
    toNumber(b.net_r),
  );
  const tradesDelta = computeDelta(filteredDailyBuckets, (b) =>
    toNumber(b.trades),
  );

  const avgHoldMinutes = toNumber(portfolioPayload?.avg_hold_minutes);
  const avgWinHold = (() => {
    const wins = filteredClosed.filter((t) => toNumber(t.realized_r) > 0);
    if (!wins.length) return 0;
    return wins.reduce((s, t) => s + toNumber(t.hold_minutes), 0) / wins.length;
  })();
  const avgLossHold = (() => {
    const losses = filteredClosed.filter((t) => toNumber(t.realized_r) < 0);
    if (!losses.length) return 0;
    return (
      losses.reduce((s, t) => s + toNumber(t.hold_minutes), 0) / losses.length
    );
  })();

  const cadenceData = [...filteredDailyBuckets]
    .sort((a, b) => String(a.date ?? "").localeCompare(String(b.date ?? "")))
    .slice(-10)
    .map((day) => ({
      date: String(day.date ?? "--"),
      trades: toNumber(day.trades),
      net_r: toNumber(day.net_r),
    }));

  const latestCloseTimestamp = filteredClosed.length
    ? formatTime(filteredClosed[0]?.close_timestamp)
    : "--";

  function handleProfileScopeChange(nextScope: ProfileScopeValue) {
    const nextParams = new URLSearchParams(searchParams);
    if (nextScope === DEFAULT_PROFILE_SCOPE) nextParams.delete("profile");
    else nextParams.set("profile", nextScope);
    setSearchParams(nextParams);
  }

  const modeBreakdown = computeGroupedNetR(filteredClosed, "mode");
  const intervalBreakdown = computeGroupedNetR(filteredClosed, "interval");

  const netRSparkline = buildSparklineSeries(
    filteredEquityCurve.map((p) => toNumber(p.net_r)),
  );
  const winRateSparkline = buildSparklineSeries(
    [...filteredDailyBuckets]
      .sort((a, b) => String(a.date ?? "").localeCompare(String(b.date ?? "")))
      .map((b) => {
        const t = toNumber(b.trades);
        const w = toNumber(b.wins);
        return t > 0 ? (w / t) * 100 : 0;
      }),
  );
  const profitFactorSparkline = rollingProfitFactor(
    [...filteredDailyBuckets].sort((a, b) =>
      String(a.date ?? "").localeCompare(String(b.date ?? "")),
    ),
  );
  const tradeCountSparkline = buildSparklineSeries(
    [...filteredDailyBuckets]
      .sort((a, b) => String(a.date ?? "").localeCompare(String(b.date ?? "")))
      .map((b) => toNumber(b.trades)),
  );

  const kpis = [
    {
      label: "Available balance",
      raw: "available_balance",
      value: `${balanceCurrency} ${formatNumber(availableBalance, 2)}`,
      delta:
        executionMode === "LIVE"
          ? `${resolvedAccountId} · venue ${String(engine.sync_status ?? "--")}`
          : `${resolvedAccountId} · ${formatNumber(paperAccount.default_balance, 2)} seeded`,
      tone: availableBalance > 0 ? "good" : "bad",
      icon: BriefcaseBusiness,
      sparkline: [] as SparklinePoint[],
    },
    {
      label: term("net_r"),
      raw: rawKey("net_r"),
      value: `${formatNumber(summary.net_r)}R`,
      delta: `${netRDelta.diff >= 0 ? "+" : ""}${formatNumber(netRDelta.diff)}R vs prior 7d`,
      tone: netRDelta.diff >= 0 ? "good" : "bad",
      icon: TrendingUp,
      sparkline: netRSparkline,
    },
    {
      label: term("win_rate"),
      raw: rawKey("win_rate"),
      value: formatPercent(summary.win_rate, 1),
      delta: `${winRateDelta.diff >= 0 ? "+" : ""}${formatNumber(winRateDelta.diff, 0)} wins vs prior 7d`,
      tone: winRateDelta.diff >= 0 ? "good" : "bad",
      icon: BriefcaseBusiness,
      sparkline: winRateSparkline,
    },
    {
      label: term("profit_factor"),
      raw: rawKey("profit_factor"),
      value: formatNumber(summary.profit_factor),
      delta: filteredClosed.length
        ? `${filteredClosed.length} closes in view`
        : "No recent closes",
      tone: toNumber(summary.profit_factor) >= 1 ? "good" : "warn",
      icon: TrendingUp,
      sparkline: profitFactorSparkline,
    },
    {
      label: "Total trades",
      raw: rawKey("trades_shown"),
      value: formatNumber(summary.total_trades, 0),
      delta: `${tradesDelta.diff >= 0 ? "+" : ""}${formatNumber(tradesDelta.diff, 0)} vs prior 7d`,
      tone: tradesDelta.diff >= 0 ? "good" : "neutral",
      icon: BriefcaseBusiness,
      sparkline: tradeCountSparkline,
    },
    {
      label: "Today P&L",
      raw: "today_pnl",
      value: `$${formatNumber(summary.today_pnl, 2)}`,
      delta: `${formatPercent(summary.today_pnl_pct, 2)} · ${formatNumber(todayWindow.closed_trades, 0)} closes`,
      tone: toNumber(summary.today_pnl) >= 0 ? "good" : "bad",
      icon: TrendingUp,
      sparkline: [] as SparklinePoint[],
    },
    {
      label: "3-day P&L",
      raw: "three_day_pnl",
      value: `$${formatNumber(summary.three_day_pnl, 2)}`,
      delta: `${formatPercent(summary.three_day_pnl_pct, 2)} over rolling 72h`,
      tone: toNumber(summary.three_day_pnl) >= 0 ? "good" : "bad",
      icon: TrendingUp,
      sparkline: [] as SparklinePoint[],
    },
    {
      label: term("avg_hold"),
      raw: rawKey("avg_hold"),
      value: `${formatNumber(avgHoldMinutes, 1)}m`,
      delta: `W ${formatNumber(avgWinHold, 1)}m / L ${formatNumber(avgLossHold, 1)}m`,
      tone: avgWinHold >= avgLossHold ? "good" : "warn",
      icon: Clock3,
      sparkline: [] as SparklinePoint[],
    },
    {
      label: term("max_drawdown"),
      raw: rawKey("max_drawdown"),
      value: `${formatNumber(maxDrawdown)}R`,
      delta:
        maxDrawdown <= Math.max(Math.abs(toNumber(summary.net_r)) * 0.35, 1)
          ? "Contained relative to equity"
          : "Needs attention",
      tone:
        maxDrawdown <= Math.max(Math.abs(toNumber(summary.net_r)) * 0.35, 1)
          ? "good"
          : "bad",
      icon: TrendingDown,
      sparkline: [] as SparklinePoint[],
    },
  ];

  if (portfolioQuery.isLoading && !portfolioPayload) {
    return (
      <AnimatedRoute>
        <EmptyState message="Loading portfolio analytics…" />
      </AnimatedRoute>
    );
  }

  return (
    <AnimatedRoute>
      <div className="grid gap-4">
        {/* ── Zone 1: Command strip ── */}
        <CommandStrip
          resolvedProfileId={resolvedProfileId}
          resolvedAccountId={resolvedAccountId}
          executionMode={executionMode}
          venue={venue}
          engineStatus={engineStatus}
          windowKey={windowKey}
          setWindowKey={setWindowKey}
          syncLiveMutation={syncLiveMutation}
          engine={engine}
          portfolioPayload={portfolioPayload}
          profileScopeOptions={profileScopeOptions}
          profileScope={profileScope}
          handleProfileScopeChange={handleProfileScopeChange}
        />

        {/* ── Zone 2: Hero KPIs ── */}
        <HeroKpis
          summary={summary}
          netRDelta={netRDelta}
          winRateDelta={winRateDelta}
          filteredClosed={filteredClosed}
        />

        {/* ── Zone 3: Secondary KPI strip ── */}
        <SecondaryKpis kpis={kpis} settings={settings} />

        {/* ── Zone 4: Analytics canvas (equity + outcome mix + snapshot) ── */}
        <div className="grid gap-4 xl:grid-cols-[1.5fr_0.9fr_0.9fr]">
          <EquityAndDrawdown equityData={equityData} />
          <OutcomeMix
            distribution={distribution}
            summary={summary}
            streaks={streaks}
          />
          <PortfolioSnapshot
            portfolio={portfolio}
            availableBalance={availableBalance}
            equityBalance={equityBalance}
            marginUsed={marginUsed}
            balanceCurrency={balanceCurrency}
            summary={summary}
            latestCloseTimestamp={latestCloseTimestamp}
            engineStatus={engineStatus}
          />
        </div>

        {/* ── Zone 5: Attribution row (cadence + mode + interval) ── */}
        <div className="grid gap-4 xl:grid-cols-3">
          <DailyCadence cadenceData={cadenceData} />
          <HorizontalBarPanel
            eyebrow="By mode"
            title="Which styles carry P&L"
            data={modeBreakdown}
          />
          <HorizontalBarPanel
            eyebrow="By interval"
            title="Where timeframe edge comes from"
            data={intervalBreakdown}
          />
        </div>

        {/* ── Zone 6: Symbol attribution ── */}
        <SymbolAttribution
          sortedSymbolMetrics={sortedSymbolMetrics}
          sortKey={sortKey}
          setSortKey={setSortKey}
          sortDescending={sortDescending}
          setSortDescending={setSortDescending}
        />

        {/* ── Zone 7: Positions drawer ── */}
        <PositionsDrawer
          activeTab={activeTab}
          setActiveTab={setActiveTab}
          openOrders={openOrders}
          recentClosed={recentClosed}
        />

        {/* ── Zone 8: Live Binance sync (live mode only) ── */}
        {executionMode === "LIVE" && (
          <LiveSyncPanel
            engine={engine}
            syncLiveMutation={syncLiveMutation}
            executionMode={executionMode}
            venue={venue}
            balanceCurrency={balanceCurrency}
            summary={summary}
            availableBalance={availableBalance}
            venueOpenOrders={venueOpenOrders}
            venuePositions={venuePositions}
            pnlAssets={pnlAssets}
            resolvedAccountId={resolvedAccountId}
          />
        )}
      </div>
    </AnimatedRoute>
  );
}
