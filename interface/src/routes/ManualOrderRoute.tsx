import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import {
  ArrowLeft,
  Play,
  Radar,
  WalletCards,
  TrendingUp,
  TrendingDown,
  AlertTriangle,
  Target,
  Zap,
  FileText,
} from "lucide-react";
import { toast } from "sonner";

import { AnimatedRoute } from "../components/ui/AnimatedRoute";
import {
  fetchJobsForScope,
  fetchPortfolioForScope,
  createManualOrder,
} from "../lib/api";
import { useProfileScopeOptions } from "../hooks/useProfileScopeOptions";
import { normalizeProfileScope } from "../lib/profileScope";
import { formatNumber } from "../lib/format";
import type { JsonRecord } from "../lib/types";

const ESTIMATED_FEE_RATE = 0.0005;

function SectionHeader({
  label,
  title,
  icon: Icon,
}: {
  label: string;
  title: string;
  icon?: React.ElementType;
}) {
  return (
    <div className="mb-5 flex items-center gap-3">
      {Icon && (
        <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-stone-950/[0.04]">
          <Icon className="h-4 w-4 text-stone-500" />
        </div>
      )}
      <div>
        <p className="text-[10px] font-semibold uppercase tracking-widest text-stone-400">
          {label}
        </p>
        <h2 className="text-sm font-semibold text-stone-800">{title}</h2>
      </div>
    </div>
  );
}

function MetricCard({
  label,
  value,
  sub,
  tone = "neutral",
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: "neutral" | "good" | "bad" | "warn";
}) {
  const valueClass =
    tone === "good"
      ? "text-teal-700"
      : tone === "bad"
        ? "text-red-600"
        : tone === "warn"
          ? "text-amber-600"
          : "text-stone-900";

  return (
    <div className="rounded-xl bg-stone-950/[0.025] p-3.5">
      <p className="text-[10px] font-semibold uppercase tracking-widest text-stone-400">
        {label}
      </p>
      <p
        className={`mt-1.5 text-base font-semibold tabular-nums ${valueClass}`}
      >
        {value}
      </p>
      {sub && <p className="mt-0.5 text-xs text-stone-400">{sub}</p>}
    </div>
  );
}

export function ManualOrderRoute() {
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { options: profileScopeOptions } = useProfileScopeOptions();
  const profileScope = normalizeProfileScope(
    searchParams.get("profile"),
    profileScopeOptions,
  );

  // Passed signal data if navigated from ScansRoute
  const signal = location.state?.signal as JsonRecord | undefined;
  const defaultEntry = signal
    ? (signal.entry_price ?? signal.entry ?? signal.entry_zone_low)
    : "";
  const defaultSl = signal ? (signal.stop_loss ?? signal.sl) : "";
  const defaultTp = signal ? (signal.take_profit ?? signal.tp) : "";

  const [symbol, setSymbol] = useState(
    signal?.symbol ? String(signal.symbol) : "",
  );
  const [interval, setInterval] = useState(
    signal?.interval ? String(signal.interval) : "15m",
  );
  const [mode, setMode] = useState(
    signal?.mode ? String(signal.mode) : "SCALP",
  );
  const [direction, setDirection] = useState(
    signal?.direction ? String(signal.direction) : "BUY",
  );
  const [entry, setEntry] = useState<string>(
    defaultEntry ? String(defaultEntry) : "",
  );
  const [sl, setSl] = useState<string>(defaultSl ? String(defaultSl) : "");
  const [tp, setTp] = useState<string>(defaultTp ? String(defaultTp) : "");
  const [balancePct, setBalancePct] = useState<string>("100");
  const [leverage, setLeverage] = useState<string>("1");
  const [orderType, setOrderType] = useState("MARKET");
  const [tif, setTif] = useState("GTC");
  const [notes, setNote] = useState("");

  useEffect(() => {
    document.title = "Create Manual Order";
  }, []);

  const portfolioQuery = useQuery({
    queryKey: ["manual-order-portfolio", profileScope],
    queryFn: () => fetchPortfolioForScope(profileScope),
    enabled: Boolean(profileScope),
  });

  const jobsQuery = useQuery({
    queryKey: ["manual-order-jobs", profileScope],
    queryFn: () => fetchJobsForScope(25, profileScope),
    enabled: Boolean(profileScope),
  });

  const createMutation = useMutation({
    mutationFn: (payload: JsonRecord) => createManualOrder(payload),
    onSuccess: () => {
      toast.success("Manual order submitted");
      navigate(`/trade/trades?profile=${profileScope}`);
    },
    onError: (e) =>
      toast.error("Failed to create manual order", {
        description: e instanceof Error ? e.message : "Unknown error",
      }),
  });

  const portfolioAccount = (portfolioQuery.data?.account ??
    portfolioQuery.data?.paper_account ??
    {}) as JsonRecord;
  const portfolioSummary = (portfolioQuery.data?.summary ?? {}) as JsonRecord;
  const portfolioState = (portfolioQuery.data?.portfolio ?? {}) as JsonRecord;
  const resolvedProfileId = String(
    portfolioQuery.data?.profile_id ?? profileScope ?? "",
  );
  const executionMode = String(
    portfolioState.execution_mode ??
      (resolvedProfileId.startsWith("paper-") ? "PAPER" : "LIVE"),
  ).toUpperCase();
  const venue = String(
    portfolioState.venue ??
      (resolvedProfileId.startsWith("paper-") ? "paper" : "binance_usdm"),
  ).toLowerCase();
  const balanceSourceLabel =
    executionMode === "LIVE" && venue === "binance_usdm"
      ? "Binance Futures"
      : executionMode === "PAPER"
        ? "Paper account"
        : executionMode === "LIVE"
          ? "Live account"
          : "Scoped account";
  const balanceCurrency = String(portfolioAccount.balance_ccy ?? "USDT");
  const availableBalanceRaw =
    portfolioAccount.available_balance ?? portfolioSummary.paper_balance;
  const availableBalance =
    availableBalanceRaw == null || Number.isNaN(Number(availableBalanceRaw))
      ? null
      : Number(availableBalanceRaw);

  const riskMetrics = useMemo(() => {
    const e = Number(entry);
    const s = Number(sl);
    const t = Number(tp);
    if (!e || !s) return null;
    const slDist = Math.abs((e - s) / e) * 100;
    const tpDist = t ? Math.abs((t - e) / e) * 100 : null;
    const rr = tpDist ? tpDist / slDist : null;
    const estimatedFee = e * ESTIMATED_FEE_RATE;
    const breakeven = direction === "BUY" ? e + estimatedFee : e - estimatedFee;
    return { slDist, tpDist, rr, breakeven, estimatedFee };
  }, [entry, sl, tp, direction]);

  const riskBar = useMemo(() => {
    if (!riskMetrics) return null;
    const rawSl = riskMetrics.slDist;
    const rawTp = riskMetrics.tpDist ?? 0;
    const total = rawSl + rawTp;
    const slWidth = Math.min(total ? (rawSl / total) * 100 : 70, 70);
    const tpWidth = Math.min(total ? (rawTp / total) * 100 : 0, 70);
    return { slWidth, tpWidth, entryLeft: slWidth };
  }, [riskMetrics]);

  const orderSummary = useMemo(() => {
    const e = Number(entry);
    const s = Number(sl);
    const t = Number(tp);
    const lev = Number(leverage);
    const pct = Number(balancePct);
    if (!e || availableBalance == null) return null;
    const notional = ((availableBalance * pct) / 100) * lev;
    const qty = notional / e;
    const maxLoss = s ? Math.abs(qty * (e - s)) : null;
    const pnlTarget = t ? Math.abs(qty * (t - e)) : null;
    const fee = notional * ESTIMATED_FEE_RATE;
    return { notional, qty, maxLoss, pnlTarget, fee };
  }, [entry, sl, tp, balancePct, leverage, availableBalance]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!symbol || !entry || !sl) {
      toast.error("Symbol, Entry, and SL are required");
      return;
    }

    const payload = {
      profile_id: profileScope,
      symbol,
      interval,
      mode,
      direction,
      entry: Number(entry),
      sl: Number(sl),
      tp: tp ? Number(tp) : null,
      use_balance_pct: Number(balancePct),
      leverage: Number(leverage),
      order_type: orderType,
      tif,
      notes,
    };

    createMutation.mutate(payload);
  };

  const isBuy = direction === "BUY";

  return (
    <AnimatedRoute>
      <div className="mx-auto mt-8 flex max-w-5xl flex-col gap-5 pb-12">
        {/* ── Header ─────────────────────────────────────────────── */}
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => navigate(-1)}
              className="rounded-full p-2 text-stone-500 transition hover:bg-stone-900/5 hover:text-stone-800"
            >
              <ArrowLeft className="h-4 w-4" />
            </button>
            <div>
              <h1 className="text-lg font-bold text-stone-900">
                Create Manual Order
              </h1>
              <p className="text-xs text-stone-400">
                Deploy explicit position sizes based on balance
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 text-xs text-stone-400">
            <span
              className={`inline-block h-1.5 w-1.5 rounded-full ${portfolioQuery.isSuccess ? "bg-teal-500" : portfolioQuery.isLoading ? "bg-amber-400" : "bg-stone-300"}`}
            />
            <span>
              {portfolioQuery.isSuccess
                ? "Portfolio connected"
                : portfolioQuery.isLoading
                  ? "Connecting…"
                  : "Portfolio offline"}
            </span>
            <span className="text-stone-200">·</span>
            <span>{jobsQuery.data?.items?.length ?? 0} scanner jobs</span>
            <span className="text-stone-200">·</span>
            <span className="rounded-md bg-stone-100 px-2 py-0.5 font-medium text-stone-500">
              {balanceSourceLabel} · Profile {profileScope}
            </span>
          </div>
        </div>

        {/* ── Signal banner ──────────────────────────────────────── */}
        {signal && (
          <div className="flex flex-wrap items-center gap-3 rounded-xl border border-teal-200 bg-teal-50 px-4 py-3">
            <Radar className="h-3.5 w-3.5 flex-shrink-0 text-teal-600" />
            <p className="text-xs font-medium text-teal-700">
              Pre-filled from scanner signal —{" "}
              <span className="font-bold">
                {String(signal.symbol ?? symbol ?? "--")}
              </span>
              {" · "}
              {String(signal.interval ?? interval)}
              {" · "}
              {String(signal.mode ?? mode)}
            </p>
            <span className="ml-auto rounded-full bg-teal-100 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-widest text-teal-700">
              from scanner
            </span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          {/* ── Card 1: Instrument & direction ─────────────────────── */}
          <div className="rounded-2xl border border-stone-900/8 bg-white p-6 shadow-sm">
            <SectionHeader
              label="Step 1"
              title="Instrument & direction"
              icon={Zap}
            />

            <div className="grid gap-4 md:grid-cols-[1fr_auto]">
              {/* Symbol */}
              <div>
                <label className="mb-1.5 block text-[10px] font-semibold uppercase tracking-widest text-stone-400">
                  Symbol
                </label>
                <input
                  value={symbol}
                  onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                  className="w-full rounded-lg border border-stone-200 px-3 py-2 text-sm font-medium text-stone-900 placeholder-stone-300 outline-none transition focus:border-teal-500 focus:ring-1 focus:ring-teal-500"
                  placeholder="BTCUSDT"
                />
              </div>

              {/* Direction toggle */}
              <div>
                <label className="mb-1.5 block text-[10px] font-semibold uppercase tracking-widest text-stone-400">
                  Direction
                </label>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setDirection("BUY")}
                    className={`flex items-center gap-1.5 rounded-lg border px-5 py-2 text-sm font-semibold transition ${
                      isBuy
                        ? "border-teal-300 bg-teal-50 text-teal-700"
                        : "border-stone-200 bg-white text-stone-400 hover:border-stone-300 hover:text-stone-600"
                    }`}
                  >
                    <TrendingUp className="h-3.5 w-3.5" />
                    Long
                  </button>
                  <button
                    type="button"
                    onClick={() => setDirection("SELL")}
                    className={`flex items-center gap-1.5 rounded-lg border px-5 py-2 text-sm font-semibold transition ${
                      !isBuy
                        ? "border-red-200 bg-red-50 text-red-700"
                        : "border-stone-200 bg-white text-stone-400 hover:border-stone-300 hover:text-stone-600"
                    }`}
                  >
                    <TrendingDown className="h-3.5 w-3.5" />
                    Short
                  </button>
                </div>
              </div>
            </div>

            {/* Row 2: selects */}
            <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
              {[
                {
                  label: "Mode",
                  value: mode,
                  onChange: setMode,
                  options: ["SCALP", "SWING", "POSITION"],
                },
                {
                  label: "Interval",
                  value: interval,
                  onChange: setInterval,
                  options: ["1m", "5m", "15m", "1h", "4h", "1d"],
                },
                {
                  label: "Order type",
                  value: orderType,
                  onChange: setOrderType,
                  options: ["MARKET", "LIMIT", "STOP_MARKET", "STOP_LIMIT"],
                  display: {
                    MARKET: "Market",
                    LIMIT: "Limit",
                    STOP_MARKET: "Stop market",
                    STOP_LIMIT: "Stop limit",
                  } as Record<string, string>,
                },
                {
                  label: "TIF",
                  value: tif,
                  onChange: setTif,
                  options: ["GTC", "IOC", "FOK"],
                },
              ].map(({ label, value, onChange, options, display }) => (
                <div key={label}>
                  <label className="mb-1.5 block text-[10px] font-semibold uppercase tracking-widest text-stone-400">
                    {label}
                  </label>
                  <select
                    value={value}
                    onChange={(e) => onChange(e.target.value)}
                    className="w-full rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm text-stone-800 outline-none transition focus:border-teal-500 focus:ring-1 focus:ring-teal-500"
                  >
                    {options.map((opt) => (
                      <option key={opt} value={opt}>
                        {display ? (display[opt] ?? opt) : opt}
                      </option>
                    ))}
                  </select>
                </div>
              ))}
            </div>
          </div>

          {/* ── Card 2: Price levels ────────────────────────────────── */}
          <div className="rounded-2xl border border-stone-900/8 bg-white p-6 shadow-sm">
            <SectionHeader
              label="Step 2"
              title="Execution framework"
              icon={Target}
            />

            <div className="grid gap-3 md:grid-cols-3">
              <div>
                <label className="mb-1.5 block text-[10px] font-semibold uppercase tracking-widest text-stone-400">
                  Entry price
                </label>
                <input
                  type="number"
                  step="any"
                  value={entry}
                  onChange={(e) => setEntry(e.target.value)}
                  className="w-full rounded-lg border border-stone-200 px-3 py-2 text-sm font-medium tabular-nums text-stone-900 placeholder-stone-300 outline-none transition focus:border-teal-500 focus:ring-1 focus:ring-teal-500"
                  placeholder="0.00"
                />
              </div>
              <div>
                <label className="mb-1.5 block text-[10px] font-semibold uppercase tracking-widest text-stone-400">
                  Stop loss <span className="ml-1 text-red-400">*</span>
                </label>
                <input
                  type="number"
                  step="any"
                  value={sl}
                  onChange={(e) => setSl(e.target.value)}
                  className="w-full rounded-lg border border-stone-200 px-3 py-2 text-sm font-medium tabular-nums text-stone-900 placeholder-stone-300 outline-none transition focus:border-red-400 focus:ring-1 focus:ring-red-300"
                  placeholder="0.00"
                />
              </div>
              <div>
                <label className="mb-1.5 block text-[10px] font-semibold uppercase tracking-widest text-stone-400">
                  Take profit{" "}
                  <span className="ml-1 text-stone-300">optional</span>
                </label>
                <input
                  type="number"
                  step="any"
                  value={tp}
                  onChange={(e) => setTp(e.target.value)}
                  className="w-full rounded-lg border border-stone-200 px-3 py-2 text-sm font-medium tabular-nums text-stone-900 placeholder-stone-300 outline-none transition focus:border-teal-500 focus:ring-1 focus:ring-teal-500"
                  placeholder="Optional"
                />
              </div>
            </div>

            {/* Risk panel */}
            {riskMetrics && riskBar ? (
              <div className="mt-4 space-y-4 rounded-xl border border-stone-900/6 bg-stone-950/[0.025] p-4">
                {/* Risk/Reward bar */}
                <div>
                  <div className="mb-2 flex items-center justify-between text-[10px] font-semibold uppercase tracking-widest text-stone-400">
                    <span>
                      SL {sl ? `$${formatNumber(Number(sl), 2)}` : "--"}
                    </span>
                    <span>Entry ${formatNumber(Number(entry), 2)}</span>
                    <span>
                      {tp ? `TP $${formatNumber(Number(tp), 2)}` : "No TP"}
                    </span>
                  </div>
                  <div className="relative h-2 overflow-hidden rounded-full bg-stone-200">
                    <div
                      className="absolute inset-y-0 left-0 rounded-l-full bg-red-400"
                      style={{ width: `${riskBar.slWidth}%` }}
                    />
                    <div
                      className="absolute inset-y-0 rounded-r-full bg-teal-400"
                      style={{
                        left: `${riskBar.entryLeft}%`,
                        width: `${riskBar.tpWidth}%`,
                      }}
                    />
                    {/* Entry marker */}
                    <div
                      className="absolute top-1/2 h-4 w-0.5 -translate-y-1/2 rounded-full bg-stone-700"
                      style={{ left: `${riskBar.entryLeft}%` }}
                    />
                  </div>
                </div>

                {/* Metrics row */}
                <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                  <MetricCard
                    label="SL distance"
                    value={`${riskMetrics.slDist.toFixed(2)}%`}
                    tone="bad"
                  />
                  <MetricCard
                    label="TP distance"
                    value={
                      riskMetrics.tpDist !== null
                        ? `${riskMetrics.tpDist.toFixed(2)}%`
                        : "--"
                    }
                    tone={riskMetrics.tpDist !== null ? "good" : "neutral"}
                  />
                  <MetricCard
                    label="Risk / Reward"
                    value={
                      riskMetrics.rr !== null
                        ? `1 : ${riskMetrics.rr.toFixed(2)}`
                        : "--"
                    }
                    tone={
                      riskMetrics.rr !== null
                        ? riskMetrics.rr >= 2
                          ? "good"
                          : riskMetrics.rr >= 1
                            ? "warn"
                            : "bad"
                        : "neutral"
                    }
                    sub={
                      riskMetrics.rr !== null
                        ? riskMetrics.rr >= 2
                          ? "Strong"
                          : riskMetrics.rr >= 1
                            ? "Acceptable"
                            : "Weak"
                        : undefined
                    }
                  />
                  <MetricCard
                    label="Breakeven"
                    value={`$${formatNumber(riskMetrics.breakeven, 2)}`}
                    sub="incl. est. fee"
                  />
                </div>
              </div>
            ) : (
              <div className="mt-4 flex items-center gap-2 rounded-xl border border-dashed border-stone-200 px-4 py-3 text-xs text-stone-400">
                <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" />
                Enter entry and stop loss to see risk metrics
              </div>
            )}
          </div>

          {/* ── Card 3: Capital deployment ──────────────────────────── */}
          <div className="rounded-2xl border border-stone-900/8 bg-white p-6 shadow-sm">
            <div className="mb-5 flex items-center justify-between gap-3">
              <SectionHeader
                label="Step 3"
                title="Capital deployment"
                icon={WalletCards}
              />
              <span className="mb-5 rounded-md bg-stone-100 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-widest text-stone-500">
                {balanceSourceLabel} balance {availableBalance == null ? "--" : `${balanceCurrency} ${formatNumber(availableBalance, 2)}`}
              </span>
            </div>

            <div className="grid gap-5">
              {/* Balance % slider */}
              <div>
                <div className="mb-2 flex items-center justify-between">
                  <label className="text-[10px] font-semibold uppercase tracking-widest text-stone-400">
                    Balance %
                  </label>
                  <span className="text-sm font-semibold tabular-nums text-stone-700">
                    {balancePct}%
                  </span>
                </div>
                <input
                  type="range"
                  min="1"
                  max="100"
                  step="1"
                  value={balancePct}
                  onChange={(e) => setBalancePct(e.target.value)}
                  className="w-full accent-teal-600"
                />
                <div className="mt-1 flex justify-between text-[10px] text-stone-300">
                  <span>1%</span>
                  <span>25%</span>
                  <span>50%</span>
                  <span>75%</span>
                  <span>100%</span>
                </div>
              </div>

              {/* Leverage slider */}
              <div>
                <div className="mb-2 flex items-center justify-between">
                  <label className="text-[10px] font-semibold uppercase tracking-widest text-stone-400">
                    Leverage
                  </label>
                  <span
                    className={`text-sm font-semibold tabular-nums ${Number(leverage) > 3 ? "text-amber-600" : "text-stone-700"}`}
                  >
                    {leverage}×
                    {Number(leverage) > 3 && (
                      <span className="ml-1.5 text-[10px] font-medium text-amber-400">
                        high
                      </span>
                    )}
                  </span>
                </div>
                <input
                  type="range"
                  min="1"
                  max="10"
                  step="1"
                  value={leverage}
                  onChange={(e) => setLeverage(e.target.value)}
                  className="w-full accent-teal-600"
                />
                <div className="mt-1 flex justify-between text-[10px] text-stone-300">
                  {[
                    "1×",
                    "2×",
                    "3×",
                    "4×",
                    "5×",
                    "6×",
                    "7×",
                    "8×",
                    "9×",
                    "10×",
                  ].map((l) => (
                    <span key={l}>{l}</span>
                  ))}
                </div>
              </div>
            </div>

            {/* Order summary */}
            <div className="mt-5 border-t border-stone-900/6 pt-5">
              <p className="mb-3 text-[10px] font-semibold uppercase tracking-widest text-stone-400">
                Order summary
              </p>
              <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
                <MetricCard
                  label="Notional"
                  value={
                    orderSummary
                      ? `$${formatNumber(orderSummary.notional, 2)}`
                      : "--"
                  }
                />
                <MetricCard
                  label="Qty (units)"
                  value={
                    orderSummary ? formatNumber(orderSummary.qty, 6) : "--"
                  }
                />
                <MetricCard
                  label="Max loss"
                  value={
                    orderSummary?.maxLoss != null
                      ? `$${formatNumber(orderSummary.maxLoss, 2)}`
                      : "--"
                  }
                  tone={orderSummary?.maxLoss != null ? "bad" : "neutral"}
                />
                <MetricCard
                  label="PnL target"
                  value={
                    orderSummary?.pnlTarget != null
                      ? `$${formatNumber(orderSummary.pnlTarget, 2)}`
                      : "--"
                  }
                  tone={orderSummary?.pnlTarget != null ? "good" : "neutral"}
                />
                <MetricCard
                  label="Est. fee"
                  value={
                    orderSummary
                      ? `$${formatNumber(orderSummary.fee, 2)}`
                      : "--"
                  }
                />
              </div>
            </div>
          </div>

          {/* ── Card 4: Notes ───────────────────────────────────────── */}
          <div className="rounded-2xl border border-stone-900/8 bg-white p-6 shadow-sm">
            <SectionHeader
              label="Step 4 — optional"
              title="Execution rationale"
              icon={FileText}
            />
            <input
              value={notes}
              onChange={(e) => setNote(e.target.value)}
              className="w-full rounded-lg border border-stone-200 px-3 py-2 text-sm text-stone-800 placeholder-stone-300 outline-none transition focus:border-teal-500 focus:ring-1 focus:ring-teal-500"
              placeholder="Trade rationale, catalyst, HTF confluence, or checklist note…"
            />
          </div>

          {/* ── Footer ─────────────────────────────────────────────── */}
          <div className="flex items-center justify-between gap-4 rounded-2xl border border-stone-900/8 bg-white px-6 py-4 shadow-sm">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-stone-400">
              <span
                className={`inline-flex items-center gap-1.5 ${isBuy ? "text-teal-600" : "text-red-500"}`}
              >
                {isBuy ? (
                  <TrendingUp className="h-3 w-3" />
                ) : (
                  <TrendingDown className="h-3 w-3" />
                )}
                <span className="font-medium">{direction}</span>
              </span>
              <span className="text-stone-200">·</span>
              <span>{symbol || "—"}</span>
              <span className="text-stone-200">·</span>
              <span>
                {interval} {mode}
              </span>
              <span className="text-stone-200">·</span>
              <span>
                {orderType} / {tif}
              </span>
              {orderSummary && (
                <>
                  <span className="text-stone-200">·</span>
                  <span>
                    ${formatNumber(orderSummary.notional, 0)} notional
                  </span>
                  <span className="text-stone-200">·</span>
                  <span>{leverage}× leverage</span>
                </>
              )}
            </div>

            <button
              type="submit"
              disabled={createMutation.isPending}
              className="inline-flex flex-shrink-0 items-center gap-2 rounded-lg bg-teal-600 px-5 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-teal-700 active:scale-95 disabled:opacity-50"
            >
              <Play className="h-3.5 w-3.5" />
              {createMutation.isPending ? "Submitting…" : "Submit order"}
            </button>
          </div>
        </form>
      </div>
    </AnimatedRoute>
  );
}
