import { useEffect, useMemo, useRef, useState } from "react";

import { useMutation, useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowUpDown,
  Clock3,
  Copy,
  Link2,
  Radar,
  Search,
  WalletCards,
  X,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { ProfileScopeBar } from "../components/profile/ProfileScopeBar";
import { AnimatedRoute } from "../components/ui/AnimatedRoute";
import { EmptyState } from "../components/ui/EmptyState";
import { StatusBadge } from "../components/ui/StatusBadge";
import { useSettings } from "../contexts/SettingsContext";
import {
  closeAllOpenOrders,
  closeOrder,
  fetchOrdersForScope,
  getFailures,
  getSelfLearningReplays,
  getSignalAudit,
  syncRuntimeProfileReadOnly,
} from "../lib/api";
import { resolveTradeExecutionIdentity } from "../lib/executionIdentity";
import {
  copyToClipboard,
  downloadFile,
  exportAsCSV,
  exportFilename,
} from "../lib/export";
import { formatNumber, formatTime, toNumber } from "../lib/format";
import { useProfileScopeOptions } from "../hooks/useProfileScopeOptions";
import {
  DEFAULT_PROFILE_SCOPE,
  normalizeProfileScope,
  profileScopeToApiProfileId,
} from "../lib/profileScope";
import { queryClient } from "../lib/queryClient";
import type {
  FailureRecord,
  JsonRecord,
  OrderRow,
  OrdersSnapshot,
  ProfileScopeValue,
  SelfLearningReplayPayload,
  SignalAuditTrail,
} from "../lib/types";

type TradeStatusFilter = "ALL" | "OPEN" | "CLOSED";
type TradeResultFilter = "ALL" | "WINNER" | "LOSER";
type SortKey = "time" | "r" | "hold" | "symbol";

const PAGE_SIZE = 100;
const TRADES_REFRESH_INTERVAL_MS = 15_000;
const BINANCE_SYNC_INTERVAL_MS = 30_000;

function toneFromTrade(row: OrderRow): "neutral" | "good" | "warn" | "bad" {
  const status = String(row.status ?? "").toUpperCase();
  const realized = tradeOutcomeValue(row);
  if (status === "OPEN" || status === "PENDING" || status === "ORDERED")
    return "warn";
  if (realized > 0) return "good";
  if (realized < 0) return "bad";
  return "neutral";
}

function tradeLifecycle(row: OrderRow): "OPEN" | "CLOSED" {
  if (row.is_open === true) return "OPEN";
  const lifecycleStatus = String(row.lifecycle_status ?? "").toUpperCase();
  if (lifecycleStatus === "OPEN" || lifecycleStatus === "CLOSED")
    return lifecycleStatus as "OPEN" | "CLOSED";
  if (row.close_timestamp) return "CLOSED";
  const status = String(row.status ?? "").toUpperCase();
  if (
    status === "OPEN" ||
    status === "PENDING" ||
    status === "ORDERED" ||
    status === "NEW" ||
    status === "PARTIALLY_FILLED"
  )
    return "OPEN";
  if (
    status === "FILLED" &&
    String(row.execution_mode ?? "").toUpperCase() === "LIVE"
  )
    return "OPEN";
  return "CLOSED";
}

function tradeTimestamp(row: OrderRow) {
  return String(
    row.close_timestamp ??
      row.open_timestamp ??
      row.last_venue_update_at_utc ??
      ((row.payload as Record<string, unknown>)?.venue_position as Record<string, unknown> | undefined)?.update_time_utc ??
      "",
  );
}

function holdMinutes(row: OrderRow) {
  const opened = row.open_timestamp
    ? new Date(String(row.open_timestamp))
    : null;
  const closed = row.close_timestamp
    ? new Date(String(row.close_timestamp))
    : new Date();
  if (
    !opened ||
    Number.isNaN(opened.getTime()) ||
    Number.isNaN(closed.getTime())
  )
    return 0;
  return Math.max(0, (closed.getTime() - opened.getTime()) / 60000);
}

function buildTradeKey(row: OrderRow) {
  const identity = resolveTradeExecutionIdentity(row);
  return `${identity.profile_id}-${String(row.order_id ?? row.id ?? tradeTimestamp(row))}`;
}

function bucketHold(minutes: number) {
  if (minutes < 60) return "<1h";
  if (minutes < 240) return "1-4h";
  if (minutes < 1440) return "4-24h";
  if (minutes < 4320) return "1-3d";
  return "3d+";
}

function tradeOutcomeValue(row: OrderRow) {
  const realizedR = Number(row.realized_r);
  if (Number.isFinite(realizedR)) return realizedR;
  const realizedPnl = Number(row.realized_pnl);
  if (Number.isFinite(realizedPnl)) return realizedPnl;
  return 0;
}

function hasRealizedR(row: OrderRow) {
  return Number.isFinite(Number(row.realized_r));
}

function realizedDisplay(row: OrderRow) {
  if (tradeLifecycle(row) === "OPEN") {
    return { label: "OPEN", className: "text-amber-800" };
  }
  const realized = tradeOutcomeValue(row);
  return {
    label: hasRealizedR(row)
      ? `${formatNumber(row.realized_r)}R`
      : `$${formatNumber(row.realized_pnl)}`,
    className: realized >= 0 ? "text-teal-900" : "text-rose-800",
  };
}

function sideLabel(row: OrderRow) {
  const side = String(row.position_side ?? "").toUpperCase();
  if (side === "LONG" || side === "SHORT") return side;
  const direction = String(row.direction ?? "").toUpperCase();
  if (direction === "BUY") return "LONG";
  if (direction === "SELL") return "SHORT";
  return "--";
}

function timingProgressPercent(row: OrderRow) {
  return hasTimingProgress(row)
    ? Math.max(0, Math.min(100, toNumber(row.timing_progress?.pct, 0)))
    : null;
}

function hasTradeProgress(row: OrderRow) {
  return Number.isFinite(Number(row.progress?.pct));
}

function tradeProgressPercent(row: OrderRow) {
  return hasTradeProgress(row)
    ? Math.max(0, Math.min(100, toNumber(row.progress?.pct, 0)))
    : null;
}

function hasTimingProgress(row: OrderRow) {
  return Number.isFinite(Number(row.timing_progress?.pct));
}

function hasExpectedR(row: OrderRow) {
  return Number.isFinite(Number(row.expected_r));
}

function isVenueSyncOnlyTrade(row: OrderRow) {
  return String(row.origin ?? "").toUpperCase() === "VENUE_SYNC";
}

function timingStatusTone(row: OrderRow): "neutral" | "good" | "warn" | "bad" {
  const status = String(row.timing_status ?? "").toUpperCase();
  if (status === "TRACKING") return "good";
  if (status === "DUE") return "warn";
  if (status === "OVERDUE") return "bad";
  return "neutral";
}

function tradeProgressTone(row: OrderRow) {
  const side = String(row.progress?.side ?? "").toLowerCase();
  if (side === "tp") return "bg-teal-800";
  if (side === "sl") return "bg-amber-700";
  return "bg-stone-500";
}

function venuePositionPayload(row: OrderRow): JsonRecord {
  return ((row.payload as Record<string, unknown>)?.venue_position ?? {}) as JsonRecord;
}

function venueMetric(row: OrderRow, key: string, fallback?: unknown) {
  const direct = (row as JsonRecord)[key];
  if (direct !== undefined && direct !== null && `${direct}` !== "") return direct;
  const payload = venuePositionPayload(row);
  return payload[key] ?? fallback;
}

function venueInitialMargin(row: OrderRow) {
  const explicit = Number(
    venueMetric(row, "position_initial_margin", venueMetric(row, "initial_margin")),
  );
  if (Number.isFinite(explicit) && explicit > 0) {
    return { value: explicit, estimated: false };
  }
  const notional = Math.abs(Number(venueMetric(row, "notional")));
  const leverage = Number(venueMetric(row, "leverage"));
  if (Number.isFinite(notional) && Number.isFinite(leverage) && leverage > 0) {
    return { value: notional / leverage, estimated: true };
  }
  return { value: null, estimated: false };
}

function venueRoePct(row: OrderRow) {
  const unrealized = Number(venueMetric(row, "unrealized_pnl"));
  const margin = venueInitialMargin(row).value;
  if (!Number.isFinite(unrealized) || margin == null || margin <= 0) {
    return null;
  }
  return (unrealized / margin) * 100;
}

function nullableMetricNumber(value: unknown) {
  const numeric = Number(value);
  return Number.isFinite(numeric) && numeric !== 0 ? numeric : null;
}

function liquidationDistancePct(row: OrderRow) {
  const liq = Number(venueMetric(row, "liquidation_price"));
  const mark = Number(venueMetric(row, "last_price", venueMetric(row, "mark_price")));
  if (!Number.isFinite(liq) || !Number.isFinite(mark) || mark === 0) return null;
  return Math.abs((mark - liq) / mark) * 100;
}

function displayPrice(value: unknown, digits = 4) {
  const numeric = Number(value);
  return Number.isFinite(numeric) && numeric > 0 ? formatNumber(numeric, digits) : "--";
}

function displayHoldMinutes(row: OrderRow) {
  if (!row.open_timestamp) return "--";
  return `${formatNumber(row.holding_minutes ?? holdMinutes(row), 0)}m`;
}

function orderIdentifier(row: OrderRow) {
  return String(row.order_id ?? row.id ?? "");
}

function tradeSummary(row: OrderRow) {
  return String(
    row.signal_payload?.summary ??
      row.signal_payload?.audit_summary ??
      row.signal_payload?.reason_summary ??
      "",
  ).trim();
}

function tradeWhatHappened(row: OrderRow, failure?: FailureRecord | null) {
  if (failure?.explanation) return String(failure.explanation);
  const closeReason = String(row.close_reason ?? "").trim();
  if (closeReason) return closeReason;
  return tradeLifecycle(row) === "OPEN"
    ? "Trade is still open."
    : "No outcome summary available.";
}

function buildTradeExportRow(row: OrderRow, failure?: FailureRecord | null) {
  const identity = resolveTradeExecutionIdentity(row);
  return {
    order_id: orderIdentifier(row),
    signal_id: String(row.signal_id ?? ""),
    profile_id: identity.profile_id,
    execution_mode: identity.execution_mode,
    venue: identity.venue,
    origin: identity.origin,
    account_id: String(identity.account_id ?? ""),
    symbol: String(row.symbol ?? ""),
    side: sideLabel(row),
    direction: String(row.direction ?? ""),
    source: String(row.source ?? ""),
    mode: String(row.mode ?? ""),
    interval: String(row.interval ?? ""),
    status: String(row.status ?? ""),
    open_timestamp: String(row.open_timestamp ?? ""),
    close_timestamp: String(row.close_timestamp ?? ""),
    hold_minutes: toNumber(row.holding_minutes ?? holdMinutes(row)),
    entry: toNumber(row.entry),
    stop_loss: toNumber(row.sl),
    take_profit: toNumber(row.tp),
    last_price: toNumber(row.last_price),
    close_price: toNumber(row.close_price),
    expected_r: toNumber(row.expected_r),
    realized_r: toNumber(row.realized_r),
    confidence_before_learning: toNumber(row.confidence_before_learning),
    confidence_after_learning: toNumber(
      row.confidence_after_learning ?? row.confidence,
    ),
    probability_before_learning: toNumber(row.probability_before_learning),
    probability_after_learning: toNumber(row.probability_after_learning),
    summary: tradeSummary(row),
    regime: String(row.signal_payload?.regime ?? ""),
    trend: String(row.signal_payload?.trend ?? ""),
    factors: Array.isArray(row.signal_payload?.factors)
      ? row.signal_payload?.factors.join(" | ")
      : "",
    close_reason: String(row.close_reason ?? ""),
    what_happened: tradeWhatHappened(row, failure),
    failure_source: String(failure?.failure_source ?? ""),
    blamed_component: String(failure?.blamed_component ?? ""),
    failure_classification: String(failure?.classification ?? ""),
    failure_confidence: toNumber(failure?.confidence),
    improvement: String(failure?.improvement ?? ""),
    learning_reasons: Array.isArray(row.learning_adjustments?.reasons)
      ? row.learning_adjustments.reasons.join(" | ")
      : "",
  };
}

export function TradesRoute() {
  const { settings, term } = useSettings();
  const [searchParams, setSearchParams] = useSearchParams();
  const profileScopeOptionsQuery = useProfileScopeOptions();
  const { options: profileScopeOptions } = profileScopeOptionsQuery;
  const profileScope = normalizeProfileScope(
    searchParams.get("profile"),
    profileScopeOptions,
  );
  const scopedProfileId = profileScopeToApiProfileId(
    profileScope,
    profileScopeOptions,
  );

  const [statusFilter, setStatusFilter] = useState<TradeStatusFilter>("ALL");
  const [resultFilter, setResultFilter] = useState<TradeResultFilter>("ALL");
  const [symbolFilter, setSymbolFilter] = useState("");
  const [modeFilter, setModeFilter] = useState("ALL");
  const [intervalFilter, setIntervalFilter] = useState("ALL");
  const [directionFilter, setDirectionFilter] = useState("ALL");
  const [sortKey, setSortKey] = useState<SortKey>("time");
  const [page, setPage] = useState(1);
  const [selectedTradeKey, setSelectedTradeKey] = useState<string | null>(null);
  // Right panel tab: 'audit' or 'failures'
  const [rightTab, setRightTab] = useState<"audit" | "failures">("audit");

  const scopedRuntimeProfile = useMemo(
    () =>
      (profileScopeOptionsQuery.data?.items ?? []).find(
        (item) => String(item.profile_id ?? "") === scopedProfileId,
      ) ?? null,
    [profileScopeOptionsQuery.data?.items, scopedProfileId],
  );
  const canSyncBinanceProfile =
    String(scopedRuntimeProfile?.execution_mode ?? "").toUpperCase() ===
      "LIVE" &&
    String(scopedRuntimeProfile?.venue ?? "").toUpperCase() ===
      "BINANCE_USDM" &&
    Boolean(scopedRuntimeProfile?.supports_account_reads);
  const scopedProfileReadOnly = Boolean(scopedRuntimeProfile?.read_only);

  const ordersQuery = useQuery({
    queryKey: ["orders-ledger", profileScope],
    queryFn: () => fetchOrdersForScope(1000, profileScope),
    refetchInterval: TRADES_REFRESH_INTERVAL_MS,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    staleTime: 60_000,
  });
  const failuresQuery = useQuery({
    queryKey: ["trade-failures", "trades", profileScope],
    queryFn: () => getFailures({ limit: 1000, profileScope }),
    refetchInterval: TRADES_REFRESH_INTERVAL_MS,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    staleTime: 60_000,
  });
  const syncMutation = useMutation({
    mutationFn: async (_variables: { silent?: boolean }) => {
      if (!scopedProfileId) {
        throw new Error("A profile scope is required before syncing Binance.");
      }
      return syncRuntimeProfileReadOnly(scopedProfileId);
    },
    onSuccess: async (_payload, variables) => {
      if (!variables?.silent) {
        toast.success("Synced orders from Binance.");
      }
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["orders-ledger"] }),
        queryClient.invalidateQueries({
          queryKey: ["trade-failures", "trades"],
        }),
        queryClient.invalidateQueries({ queryKey: ["portfolio"] }),
        queryClient.invalidateQueries({ queryKey: ["portfolio", "app-shell"] }),
      ]);
    },
    onError: (error, variables) => {
      if (variables?.silent) return;
      toast.error(
        error instanceof Error ? error.message : "Failed to sync Binance orders.",
      );
    },
  });
  const closeMutation = useMutation({
    mutationFn: ({
      orderId,
      closePrice,
    }: {
      orderId: string;
      closePrice: number;
    }) => closeOrder(orderId, closePrice, "MANUAL_CLOSE"),
    onSuccess: async () => {
      toast.success("Trade closed manually.");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["orders-ledger"] }),
        queryClient.invalidateQueries({
          queryKey: ["trade-failures", "trades"],
        }),
        queryClient.invalidateQueries({ queryKey: ["portfolio", "app-shell"] }),
      ]);
    },
    onError: (error) => {
      toast.error(
        error instanceof Error ? error.message : "Failed to close trade.",
      );
    },
  });
  const closeAllMutation = useMutation({
    mutationFn: () => closeAllOpenOrders("MANUAL_BULK_CLOSE"),
    onSuccess: async (payload) => {
      toast.success(
        `${formatNumber(payload.closed_count, 0)} open trade(s) closed.`,
      );
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["orders-ledger"] }),
        queryClient.invalidateQueries({
          queryKey: ["trade-failures", "trades"],
        }),
        queryClient.invalidateQueries({ queryKey: ["portfolio"] }),
        queryClient.invalidateQueries({ queryKey: ["portfolio", "app-shell"] }),
      ]);
    },
    onError: (error) => {
      toast.error(
        error instanceof Error
          ? error.message
          : "Failed to close all open trades.",
      );
    },
  });

  const snapshot = (ordersQuery.data ?? {}) as OrdersSnapshot;
  const failureRows =
    ((failuresQuery.data?.items ?? []) as FailureRecord[]) ?? [];
  const failuresByOrder = useMemo(
    () =>
      new Map(
        failureRows
          .filter((row) => row.order_id)
          .map((row) => [String(row.order_id), row]),
      ),
    [failureRows],
  );
  const hasLedgerOrders = Boolean(
    (snapshot.open_orders ?? []).length ||
    (snapshot.closed_orders ?? []).length,
  );
  const openTrades = (snapshot.open_orders ?? []) as OrderRow[];
  const closedTrades = (snapshot.closed_orders ?? []) as OrderRow[];
  const openTradeAnalysis = (snapshot.open_trade_analysis ?? {}) as JsonRecord;
  const trades = useMemo(
    () =>
      [...openTrades, ...closedTrades].sort((left, right) =>
        tradeTimestamp(right).localeCompare(tradeTimestamp(left)),
      ),
    [closedTrades, openTrades],
  );

  const modes = useMemo(
    () =>
      Array.from(
        new Set(trades.map((row) => String(row.mode ?? "")).filter(Boolean)),
      ).sort(),
    [trades],
  );
  const intervals = useMemo(
    () =>
      Array.from(
        new Set(
          trades.map((row) => String(row.interval ?? "")).filter(Boolean),
        ),
      ).sort(),
    [trades],
  );

  const filteredTrades = useMemo(() => {
    const query = symbolFilter.trim().toUpperCase();
    const rows = trades.filter((row) => {
      const lifecycle = tradeLifecycle(row);
      const symbol = String(row.symbol ?? "").toUpperCase();
      const matchesStatus =
        statusFilter === "ALL" ? true : lifecycle === statusFilter;
      const matchesSymbol = !query ? true : symbol.includes(query);
      const matchesMode =
        modeFilter === "ALL" ? true : String(row.mode ?? "") === modeFilter;
      const matchesInterval =
        intervalFilter === "ALL"
          ? true
          : String(row.interval ?? "") === intervalFilter;
      const matchesDirection =
        directionFilter === "ALL"
          ? true
          : String(row.direction ?? "") === directionFilter;
      const realized = tradeOutcomeValue(row);
      const matchesResult =
        resultFilter === "ALL"
          ? true
          : resultFilter === "WINNER"
            ? lifecycle === "CLOSED" && realized > 0
            : lifecycle === "CLOSED" && realized < 0;
      return (
        matchesStatus &&
        matchesSymbol &&
        matchesMode &&
        matchesInterval &&
        matchesDirection &&
        matchesResult
      );
    });

    return [...rows].sort((left, right) => {
      if (sortKey === "r")
        return tradeOutcomeValue(right) - tradeOutcomeValue(left);
      if (sortKey === "hold") return holdMinutes(right) - holdMinutes(left);
      if (sortKey === "symbol")
        return String(left.symbol ?? "").localeCompare(
          String(right.symbol ?? ""),
        );
      return tradeTimestamp(right).localeCompare(tradeTimestamp(left));
    });
  }, [
    directionFilter,
    intervalFilter,
    modeFilter,
    resultFilter,
    sortKey,
    statusFilter,
    symbolFilter,
    trades,
  ]);

  useEffect(() => {
    setPage(1);
  }, [
    directionFilter,
    intervalFilter,
    modeFilter,
    resultFilter,
    sortKey,
    statusFilter,
    symbolFilter,
  ]);

  const totalPages = Math.max(1, Math.ceil(filteredTrades.length / PAGE_SIZE));
  const paginatedTrades = useMemo(() => {
    const start = (page - 1) * PAGE_SIZE;
    return filteredTrades.slice(start, start + PAGE_SIZE);
  }, [filteredTrades, page]);

  useEffect(() => {
    if (!filteredTrades.length) {
      setSelectedTradeKey(null);
      return;
    }
    if (
      !selectedTradeKey ||
      !filteredTrades.some((row) => buildTradeKey(row) === selectedTradeKey)
    ) {
      setSelectedTradeKey(buildTradeKey(filteredTrades[0]));
    }
  }, [filteredTrades, selectedTradeKey]);

  const autoSyncInFlightRef = useRef(false);

  useEffect(() => {
    if (!canSyncBinanceProfile || !scopedProfileId) return;

    let cancelled = false;
    const runAutoSync = async () => {
      if (cancelled || autoSyncInFlightRef.current) return;
      autoSyncInFlightRef.current = true;
      try {
        await syncRuntimeProfileReadOnly(scopedProfileId);
        if (!cancelled) {
          await Promise.all([
            queryClient.invalidateQueries({ queryKey: ["orders-ledger"] }),
            queryClient.invalidateQueries({
              queryKey: ["trade-failures", "trades"],
            }),
            queryClient.invalidateQueries({ queryKey: ["portfolio"] }),
            queryClient.invalidateQueries({
              queryKey: ["portfolio", "app-shell"],
            }),
          ]);
        }
      } catch {
        // Silent by design for timer-driven sync.
      } finally {
        autoSyncInFlightRef.current = false;
      }
    };

    void runAutoSync();
    const timer = window.setInterval(() => {
      void runAutoSync();
    }, BINANCE_SYNC_INTERVAL_MS);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [canSyncBinanceProfile, scopedProfileId]);

  const selectedTrade =
    filteredTrades.find((row) => buildTradeKey(row) === selectedTradeKey) ??
    null;
  const selectedSignalId = String(selectedTrade?.signal_id ?? "");

  const auditQuery = useQuery({
    queryKey: ["signal-audit", selectedSignalId],
    queryFn: () => getSignalAudit(selectedSignalId),
    enabled: Boolean(selectedSignalId),
    refetchOnWindowFocus: false,
    staleTime: 60_000,
  });
  const selectedAudit = (auditQuery.data?.audit ??
    null) as SignalAuditTrail | null;

  const replayQuery = useQuery({
    queryKey: ["self-learning-replays", orderIdentifier(selectedTrade ?? {})],
    queryFn: () => getSelfLearningReplays(orderIdentifier(selectedTrade!)),
    enabled: Boolean(
      selectedTrade &&
      tradeLifecycle(selectedTrade) === "CLOSED" &&
      orderIdentifier(selectedTrade),
    ),
    refetchOnWindowFocus: false,
    staleTime: 60_000,
  });
  const replayPayload = (replayQuery.data ?? {}) as SelfLearningReplayPayload;

  const selectedFailure = selectedTrade
    ? (failuresByOrder.get(orderIdentifier(selectedTrade)) ?? null)
    : null;

  const summary = useMemo(() => {
    const closed = filteredTrades.filter(
      (row) => tradeLifecycle(row) === "CLOSED",
    );
    const open = filteredTrades.filter((row) => tradeLifecycle(row) === "OPEN");
    const wins = closed.filter((row) => tradeOutcomeValue(row) > 0).length;
    const netR = closed.reduce(
      (total, row) => total + tradeOutcomeValue(row),
      0,
    );
    const openWithExpectedR = open.filter((row) => hasExpectedR(row));
    const openExpectedR = openWithExpectedR.length
      ? openWithExpectedR.reduce(
          (total, row) => total + toNumber(row.expected_r),
          0,
        )
      : null;
    const avgHold = filteredTrades.length
      ? filteredTrades.reduce((total, row) => total + holdMinutes(row), 0) /
        filteredTrades.length
      : 0;
    return {
      shown: filteredTrades.length,
      open: open.length,
      netR,
      openExpectedR,
      expectedNetR: openExpectedR == null ? null : netR + openExpectedR,
      winRate: closed.length ? (wins / closed.length) * 100 : 0,
      avgHold,
    };
  }, [filteredTrades]);

  const losingTrades = useMemo(
    () =>
      filteredTrades.filter(
        (row) =>
          tradeLifecycle(row) === "CLOSED" && tradeOutcomeValue(row) < 0,
      ),
    [filteredTrades],
  );

  const analyzedLosses = useMemo(
    () =>
      losingTrades.filter((row) => failuresByOrder.has(orderIdentifier(row))),
    [failuresByOrder, losingTrades],
  );

  const rHistogram = useMemo(() => {
    const buckets = new Map<string, number>([
      ["<= -1R", 0],
      ["-1R to 0", 0],
      ["0 to 1R", 0],
      ["1R to 2R", 0],
      ["2R+", 0],
    ]);
    for (const row of filteredTrades.filter(
      (item) => tradeLifecycle(item) === "CLOSED",
    )) {
      const realized = tradeOutcomeValue(row);
      const bucket =
        realized <= -1
          ? "<= -1R"
          : realized < 0
            ? "-1R to 0"
            : realized < 1
              ? "0 to 1R"
              : realized < 2
                ? "1R to 2R"
                : "2R+";
      buckets.set(bucket, (buckets.get(bucket) ?? 0) + 1);
    }
    return Array.from(buckets.entries()).map(([bucket, count]) => ({
      bucket,
      count,
    }));
  }, [filteredTrades]);

  const holdHistogram = useMemo(() => {
    const buckets = new Map<string, number>([
      ["<1h", 0],
      ["1-4h", 0],
      ["4-24h", 0],
      ["1-3d", 0],
      ["3d+", 0],
    ]);
    for (const row of filteredTrades) {
      const bucket = bucketHold(holdMinutes(row));
      buckets.set(bucket, (buckets.get(bucket) ?? 0) + 1);
    }
    return Array.from(buckets.entries()).map(([bucket, count]) => ({
      bucket,
      count,
    }));
  }, [filteredTrades]);

  function handleProfileScopeChange(nextScope: ProfileScopeValue) {
    const nextParams = new URLSearchParams(searchParams);
    if (nextScope === DEFAULT_PROFILE_SCOPE) {
      nextParams.delete("profile");
    } else {
      nextParams.set("profile", nextScope);
    }
    setSearchParams(nextParams);
  }

  async function handleCopyTradeDetails(row: OrderRow | null) {
    if (!row) return;
    const failure = failuresByOrder.get(orderIdentifier(row));
    const audit =
      String(row.signal_id ?? "") === selectedSignalId ? selectedAudit : null;
    await copyToClipboard(
      JSON.stringify(
        { trade: row, failure: failure ?? null, audit: audit ?? null },
        null,
        2,
      ),
    );
    toast.success("Trade details copied.");
  }

  function handleExportTrades(
    format: "csv" | "json",
    scope: "all" | "filtered" = "filtered",
  ) {
    const sourceRows = scope === "all" ? trades : filteredTrades;
    if (!sourceRows.length) {
      toast.error("No trades available to export.");
      return;
    }
    const rows = sourceRows.map((row) =>
      buildTradeExportRow(
        row,
        failuresByOrder.get(orderIdentifier(row)) ?? null,
      ),
    );
    if (format === "json") {
      downloadFile(
        JSON.stringify(rows, null, 2),
        exportFilename(`trade-history-${scope}`, "json"),
        "application/json",
      );
      toast.success(`Trade history JSON downloaded (${scope}).`);
      return;
    }
    downloadFile(
      exportAsCSV(rows as unknown as JsonRecord[]),
      exportFilename(`trade-history-${scope}`, "csv"),
      "text/csv;charset=utf-8",
    );
    toast.success(`Trade history CSV downloaded (${scope}).`);
  }

  function handleManualClose(row: OrderRow | null) {
    if (!row) return;
    const orderId = orderIdentifier(row);
    const closePrice = toNumber(
      row.last_price ?? row.close_price ?? row.entry,
      0,
    );
    if (!orderId || closePrice <= 0) {
      toast.error("No valid market price available for manual close.");
      return;
    }
    closeMutation.mutate({ orderId, closePrice });
  }

  function applySavedView(
    view: "all" | "open" | "winners" | "losers" | "longs" | "shorts",
  ) {
    if (view === "all") {
      setStatusFilter("ALL");
      setResultFilter("ALL");
      setDirectionFilter("ALL");
      return;
    }
    if (view === "open") {
      setStatusFilter("OPEN");
      setResultFilter("ALL");
      setDirectionFilter("ALL");
      return;
    }
    if (view === "winners") {
      setStatusFilter("CLOSED");
      setResultFilter("WINNER");
      setDirectionFilter("ALL");
      setSortKey("r");
      return;
    }
    if (view === "losers") {
      setStatusFilter("CLOSED");
      setResultFilter("LOSER");
      setDirectionFilter("ALL");
      setSortKey("time");
      return;
    }
    if (view === "longs") {
      setResultFilter("ALL");
      setDirectionFilter("BUY");
      return;
    }
    setResultFilter("ALL");
    setDirectionFilter("SELL");
  }

  function resetFilters() {
    setStatusFilter("ALL");
    setResultFilter("ALL");
    setSymbolFilter("");
    setModeFilter("ALL");
    setIntervalFilter("ALL");
    setDirectionFilter("ALL");
    setSortKey("time");
  }

  if (ordersQuery.isLoading && !ordersQuery.data) {
    return (
      <AnimatedRoute>
        <EmptyState message="Loading trade ledger..." />
      </AnimatedRoute>
    );
  }

  return (
    <AnimatedRoute>
      <div className="grid gap-4">
        <ProfileScopeBar
          options={profileScopeOptions}
          value={profileScope}
          onChange={handleProfileScopeChange}
        />

        {/* ── Top summary bar ── */}
        <div className="overflow-hidden rounded-[1.8rem] border border-stone-900/8 bg-white/84 shadow-[0_18px_40px_rgba(77,62,40,0.08)]">
          {!hasLedgerOrders && !ordersQuery.isLoading ? (
            <div className="border-b border-stone-900/8 bg-stone-50/70 px-4 py-3 text-sm text-stone-700">
              No trade ledger is available yet. This usually means there are no
              recorded trades in the current backend data source.
            </div>
          ) : null}

          {/* Summary strip */}
          <div className="flex flex-col gap-3 border-b border-stone-900/8 bg-white px-4 py-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex flex-wrap items-center gap-3 text-sm">
              <span className="font-semibold text-stone-950">Trades</span>
              <span className="text-stone-400">·</span>
              <span className="text-stone-600">
                {formatNumber(summary.shown, 0)} shown
              </span>
              <span className="text-stone-400">·</span>
              <span className="text-stone-600">
                {formatNumber(summary.open, 0)} open
              </span>
              <span className="text-stone-400">·</span>
              <span className="text-stone-600">
                Net{" "}
                <strong
                  className={
                    summary.netR >= 0 ? "text-teal-900" : "text-rose-800"
                  }
                >
                  {formatNumber(summary.netR)}R
                </strong>
              </span>
              <span className="text-stone-400">·</span>
              <span className="text-stone-600">
                Expected{" "}
                <strong
                  className={
                    summary.expectedNetR == null
                      ? "text-stone-500"
                      : summary.expectedNetR >= 0
                        ? "text-teal-900"
                        : "text-rose-800"
                  }
                >
                  {summary.expectedNetR == null
                    ? "--R"
                    : `${formatNumber(summary.expectedNetR)}R`}
                </strong>
              </span>
              <span className="text-stone-400">·</span>
              <span className="text-stone-600">
                Win rate{" "}
                <strong className="text-stone-950">
                  {formatNumber(summary.winRate)}%
                </strong>
              </span>
              <span className="text-stone-400">·</span>
              <span className="text-stone-600">
                Avg hold{" "}
                <strong className="text-stone-950">
                  {formatNumber(summary.avgHold, 0)}m
                </strong>
              </span>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge
                label={`${summary.open} open positions`}
                tone={summary.open > 0 ? "warn" : "neutral"}
              />
              <StatusBadge
                label={`${analyzedLosses.length} analyzed losses`}
                tone={analyzedLosses.length > 0 ? "bad" : "neutral"}
              />
              <StatusBadge
                label={`Scope ${scopedProfileId ?? profileScope}`}
                tone="neutral"
              />
              {canSyncBinanceProfile ? (
                <button
                  type="button"
                  onClick={() => syncMutation.mutate({ silent: false })}
                  disabled={syncMutation.isPending}
                  className="inline-flex items-center gap-2 rounded-full border border-sky-900/10 bg-sky-50 px-3 py-1.5 text-xs font-semibold text-sky-900 transition hover:bg-sky-100 disabled:opacity-60"
                >
                  <Radar className="h-3.5 w-3.5" strokeWidth={1.8} />
                  {syncMutation.isPending ? "Syncing Binance…" : "Sync now"}
                </button>
              ) : null}
              <button
                type="button"
                onClick={() => handleExportTrades("csv", "all")}
                className="inline-flex items-center gap-2 rounded-full border border-stone-900/8 bg-white px-3 py-1.5 text-xs font-semibold text-stone-800 transition hover:bg-stone-950/[0.03]"
              >
                Export all CSV
              </button>
              <button
                type="button"
                onClick={() => handleExportTrades("json", "all")}
                className="inline-flex items-center gap-2 rounded-full border border-stone-900/8 bg-white px-3 py-1.5 text-xs font-semibold text-stone-800 transition hover:bg-stone-950/[0.03]"
              >
                Export all JSON
              </button>
              {summary.open > 0 && !scopedProfileReadOnly ? (
                <button
                  type="button"
                  onClick={() => closeAllMutation.mutate()}
                  disabled={closeAllMutation.isPending}
                  className="inline-flex items-center gap-2 rounded-full border border-amber-900/10 bg-amber-50 px-3 py-1.5 text-xs font-semibold text-amber-900 transition hover:bg-amber-100 disabled:opacity-60"
                >
                  <X className="h-3.5 w-3.5" strokeWidth={1.8} />
                  {closeAllMutation.isPending
                    ? "Closing open trades…"
                    : "Close all open trades"}
                </button>
              ) : null}
            </div>
          </div>

          {/* ── Filter bar ── */}
          <div className="flex flex-wrap items-center gap-2 border-b border-stone-900/8 bg-white/70 px-4 py-2.5">
            {/* Quick-view pills */}
            {(
              ["all", "open", "winners", "losers", "longs", "shorts"] as const
            ).map((view) => {
              const labels: Record<string, string> = {
                all: "All",
                open: "Open",
                winners: "Winners",
                losers: "Losers",
                longs: "Longs",
                shorts: "Shorts",
              };
              const isActive =
                view === "all"
                  ? statusFilter === "ALL" &&
                    resultFilter === "ALL" &&
                    directionFilter === "ALL"
                  : view === "open"
                    ? statusFilter === "OPEN"
                    : view === "winners"
                      ? resultFilter === "WINNER"
                      : view === "losers"
                        ? resultFilter === "LOSER"
                        : view === "longs"
                          ? directionFilter === "BUY"
                          : directionFilter === "SELL";
              return (
                <button
                  key={view}
                  type="button"
                  onClick={() => applySavedView(view)}
                  className={`rounded-full px-3 py-1.5 text-xs font-semibold transition ${isActive ? "bg-stone-950 text-stone-50" : "border border-stone-900/8 bg-white text-stone-600 hover:bg-stone-950/[0.03]"}`}
                >
                  {labels[view]}
                </button>
              );
            })}

            <div className="mx-1 h-4 w-px bg-stone-900/10" />

            {/* Symbol search */}
            <label className="relative">
              <Search
                className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-stone-400"
                strokeWidth={1.8}
              />
              <input
                value={symbolFilter}
                onChange={(e) => setSymbolFilter(e.target.value)}
                placeholder="Symbol…"
                className="h-8 w-36 rounded-2xl border border-stone-900/8 bg-white pl-9 pr-3 text-xs text-stone-900 outline-none transition focus:border-teal-900/20 focus:ring-4 focus:ring-teal-900/6"
              />
            </label>

            {/* Selects */}
            {[
              {
                value: modeFilter,
                setter: setModeFilter,
                options: modes,
                placeholder: "Mode",
              },
              {
                value: intervalFilter,
                setter: setIntervalFilter,
                options: intervals,
                placeholder: "Interval",
              },
            ].map((f) => (
              <select
                key={f.placeholder}
                value={f.value}
                onChange={(e) => f.setter(e.target.value)}
                className="h-8 rounded-2xl border border-stone-900/8 bg-white px-3 text-xs text-stone-900 outline-none"
              >
                <option value="ALL">All {f.placeholder}s</option>
                {f.options.map((o) => (
                  <option key={o} value={o}>
                    {o}
                  </option>
                ))}
              </select>
            ))}
            <select
              value={directionFilter}
              onChange={(e) => setDirectionFilter(e.target.value)}
              className="h-8 rounded-2xl border border-stone-900/8 bg-white px-3 text-xs text-stone-900 outline-none"
            >
              <option value="ALL">All directions</option>
              <option value="BUY">Long</option>
              <option value="SELL">Short</option>
            </select>
            <select
              value={sortKey}
              onChange={(e) => setSortKey(e.target.value as SortKey)}
              className="h-8 rounded-2xl border border-stone-900/8 bg-white px-3 text-xs text-stone-900 outline-none"
            >
              <option value="time">Newest</option>
              <option value="r">Best R</option>
              <option value="hold">Longest hold</option>
              <option value="symbol">Symbol</option>
            </select>

            <button
              type="button"
              onClick={resetFilters}
              className="ml-auto rounded-full border border-rose-900/10 bg-rose-50 px-3 py-1.5 text-xs font-semibold text-rose-900 transition hover:bg-rose-100"
            >
              Reset
            </button>
          </div>

          {/* ── Three-column body ── */}
          <div className="grid min-h-[70vh] grid-cols-1 divide-x divide-stone-900/8 lg:grid-cols-[280px_1fr_320px]">
            {/* ── LEFT: Ledger list ── */}
            <div className="flex flex-col overflow-hidden">
              {/* Column header */}
              <div className="flex items-center justify-between border-b border-stone-900/8 bg-white/60 px-4 py-2.5">
                <span className="text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-stone-500">
                  Ledger
                </span>
                <div className="flex items-center gap-2 text-xs text-stone-400">
                  <span>
                    {(page - 1) * PAGE_SIZE + 1}–
                    {Math.min(page * PAGE_SIZE, filteredTrades.length)} of{" "}
                    {filteredTrades.length}
                  </span>
                  <button
                    type="button"
                    disabled={page === 1}
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    className="rounded px-1.5 py-0.5 text-xs disabled:opacity-30 hover:bg-stone-100"
                  >
                    ‹
                  </button>
                  <button
                    type="button"
                    disabled={page >= totalPages}
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    className="rounded px-1.5 py-0.5 text-xs disabled:opacity-30 hover:bg-stone-100"
                  >
                    ›
                  </button>
                </div>
              </div>

              {/* Export row */}
              <div className="flex items-center gap-2 border-b border-stone-900/8 bg-white/40 px-4 py-2">
                <button
                  type="button"
                  onClick={() => handleExportTrades("csv", "filtered")}
                  className="text-[0.68rem] font-semibold text-stone-500 transition hover:text-stone-900"
                >
                  CSV
                </button>
                <span className="text-stone-300">·</span>
                <button
                  type="button"
                  onClick={() => handleExportTrades("json", "filtered")}
                  className="text-[0.68rem] font-semibold text-stone-500 transition hover:text-stone-900"
                >
                  JSON
                </button>
              </div>

              {/* Scrollable list */}
              <div className="flex-1 overflow-y-auto">
                {paginatedTrades.length ? (
                  paginatedTrades.map((row) => {
                    const key = buildTradeKey(row);
                    const selected = key === selectedTradeKey;
                    const lifecycle = tradeLifecycle(row);
                    const realized = realizedDisplay(row);
                    const identity = resolveTradeExecutionIdentity(row);
                    const failure = failuresByOrder.get(orderIdentifier(row));
                    return (
                      <button
                        key={key}
                        type="button"
                        onClick={() => setSelectedTradeKey(key)}
                        className={`w-full border-b border-stone-900/8 px-4 py-3 text-left transition last:border-0 ${selected ? "bg-stone-950" : "hover:bg-stone-50/80"}`}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <span
                            className={`text-sm font-semibold ${selected ? "text-stone-50" : "text-stone-950"}`}
                          >
                            {String(row.symbol ?? "--")}
                          </span>
                          <span
                            className={`font-mono text-sm font-semibold ${selected ? "text-stone-50" : realized.className}`}
                          >
                            {realized.label}
                          </span>
                        </div>
                        <div
                          className={`mt-1 flex flex-wrap items-center gap-1.5 text-xs ${selected ? "text-stone-300" : "text-stone-500"}`}
                        >
                          <span
                            className={`rounded-full px-2 py-0.5 text-[0.64rem] font-semibold ${selected ? "bg-stone-700 text-stone-200" : "bg-stone-100 text-stone-600"}`}
                          >
                            {sideLabel(row)}
                          </span>
                          <span
                            className={`rounded-full px-2 py-0.5 text-[0.64rem] font-semibold ${lifecycle === "OPEN" ? (selected ? "bg-amber-900 text-amber-100" : "bg-amber-50 text-amber-900") : selected ? "bg-stone-700 text-stone-200" : "bg-stone-100 text-stone-600"}`}
                          >
                            {lifecycle}
                          </span>
                          <span>{identity.execution_mode}</span>
                          <span>·</span>
                          <span>{String(row.interval ?? "--")}</span>
                          {lifecycle === "CLOSED" &&
                          tradeOutcomeValue(row) < 0 &&
                          failure ? (
                            <span
                              className={`rounded-full px-2 py-0.5 text-[0.64rem] font-semibold uppercase ${selected ? "bg-rose-900 text-rose-100" : "bg-rose-50 text-rose-900"}`}
                            >
                              {String(failure.failure_source ?? "LOSS")}
                            </span>
                          ) : lifecycle === "CLOSED" &&
                            tradeOutcomeValue(row) < 0 ? (
                            <span
                              className={`rounded-full px-2 py-0.5 text-[0.64rem] font-semibold ${selected ? "bg-stone-700 text-stone-200" : "bg-stone-100 text-stone-600"}`}
                            >
                              Unanalyzed
                            </span>
                          ) : null}
                        </div>
                        <div
                          className={`mt-1 text-xs ${selected ? "text-stone-400" : "text-stone-400"}`}
                        >
                          {formatTime(tradeTimestamp(row))}
                        </div>
                      </button>
                    );
                  })
                ) : (
                  <EmptyState message="No trades matched the current filters." />
                )}
              </div>
            </div>

            {/* ── CENTER: Trade detail ── */}
            <div className="flex flex-col overflow-hidden">
              <div className="flex items-center justify-between border-b border-stone-900/8 bg-white/60 px-4 py-2.5">
                <span className="text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-stone-500">
                  {selectedTrade
                    ? `${String(selectedTrade.symbol ?? "--")} · ${sideLabel(selectedTrade)} · ${String(selectedTrade.mode ?? "--")} / ${String(selectedTrade.interval ?? "--")}`
                    : "Detail"}
                </span>
                {selectedTrade ? (
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => void handleCopyTradeDetails(selectedTrade)}
                      className="inline-flex items-center gap-1.5 rounded-full border border-stone-900/8 bg-white px-2.5 py-1 text-xs font-semibold text-stone-700 transition hover:bg-stone-50"
                    >
                      <Copy className="h-3 w-3" strokeWidth={1.8} />
                      Copy
                    </button>
                    {tradeLifecycle(selectedTrade) === "OPEN" &&
                    !scopedProfileReadOnly ? (
                      <button
                        type="button"
                        onClick={() => handleManualClose(selectedTrade)}
                        disabled={closeMutation.isPending}
                        className="inline-flex items-center gap-1.5 rounded-full border border-amber-900/10 bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-900 transition hover:bg-amber-100 disabled:opacity-60"
                      >
                        <X className="h-3 w-3" strokeWidth={1.8} />
                        {closeMutation.isPending ? "Closing…" : "Close"}
                      </button>
                    ) : null}
                  </div>
                ) : null}
              </div>

              <div className="flex-1 overflow-y-auto">
                <AnimatePresence mode="wait">
                  <motion.div
                    key={selectedTradeKey ?? "empty"}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: 4 }}
                    transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
                    className="grid gap-0"
                  >
                    {selectedTrade ? (
                      <>
                        {/* Identity badges */}
                        <div className="flex flex-wrap items-center gap-2 border-b border-stone-900/8 bg-white/40 px-4 py-3">
                          {(() => {
                            const identity =
                              resolveTradeExecutionIdentity(selectedTrade);
                            return (
                              <>
                                <StatusBadge
                                  label={String(
                                    selectedTrade.close_reason ??
                                      selectedTrade.status ??
                                      "--",
                                  )}
                                  tone={toneFromTrade(selectedTrade)}
                                />
                                <StatusBadge
                                  label={hasTimingProgress(selectedTrade)
                                    ? String(
                                        selectedTrade.timing_status ??
                                          "UNSPECIFIED",
                                      )
                                    : "UNAVAILABLE"}
                                  tone={timingStatusTone(selectedTrade)}
                                />
                                {isVenueSyncOnlyTrade(selectedTrade) ? (
                                  <>
                                    <span className="rounded-full bg-sky-50 px-2.5 py-1 text-xs font-semibold text-sky-900">
                                      Venue position only
                                    </span>
                                    <span className="rounded-full bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-900">
                                      Protection {String(selectedTrade.protection_status ?? "NONE")}
                                    </span>
                                  </>
                                ) : null}
                                <span className="rounded-full bg-stone-100 px-2.5 py-1 text-xs font-semibold text-stone-700">
                                  {identity.profile_id}
                                </span>
                                <span className="rounded-full bg-teal-50 px-2.5 py-1 text-xs font-semibold text-teal-900">
                                  {identity.execution_mode}
                                </span>
                                <span className="rounded-full bg-sky-50 px-2.5 py-1 text-xs font-semibold text-sky-900">
                                  {identity.venue}
                                </span>
                                <span className="rounded-full bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-900">
                                  {identity.origin}
                                </span>
                                {identity.account_id ? (
                                  <span className="rounded-full bg-violet-50 px-2.5 py-1 text-xs font-semibold text-violet-900">
                                    {identity.account_id}
                                  </span>
                                ) : null}
                              </>
                            );
                          })()}
                          {tradeLifecycle(selectedTrade) === "CLOSED" &&
                          tradeOutcomeValue(selectedTrade) < 0 &&
                          selectedFailure ? (
                            <>
                              <Link
                                to={`/failures?order_id=${encodeURIComponent(orderIdentifier(selectedTrade))}`}
                                className="rounded-full bg-rose-50 px-2.5 py-1 text-xs font-semibold text-rose-900"
                              >
                                {String(selectedFailure.failure_source ?? "--")}
                              </Link>
                              <Link
                                to={`/failures?order_id=${encodeURIComponent(orderIdentifier(selectedTrade))}`}
                                className="rounded-full bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-900"
                              >
                                {String(
                                  selectedFailure.blamed_component ?? "--",
                                )}
                              </Link>
                              <a
                                href={`/api/v3/failures/${encodeURIComponent(String(selectedFailure.order_id ?? orderIdentifier(selectedTrade)))}`}
                                target="_blank"
                                rel="noreferrer"
                                className="inline-flex items-center gap-1 rounded-full border border-stone-900/8 bg-white px-2.5 py-1 text-xs font-semibold text-stone-700"
                              >
                                Failure detail{" "}
                                <Link2 className="h-3 w-3" strokeWidth={1.8} />
                              </a>
                            </>
                          ) : tradeLifecycle(selectedTrade) === "CLOSED" &&
                            tradeOutcomeValue(selectedTrade) < 0 ? (
                            <span className="text-xs text-stone-500">
                              No failure analysis yet.
                            </span>
                          ) : null}
                        </div>

                        {/* Levels */}
                        <div className="grid grid-cols-4 divide-x divide-stone-900/8 border-b border-stone-900/8">
                          {[
                            {
                              label: "Entry",
                              value: formatNumber(selectedTrade.entry, 4),
                            },
                            {
                              label: "Stop",
                              value: displayPrice(selectedTrade.sl, 4),
                              className: "text-rose-800",
                            },
                            {
                              label: "Target",
                              value: displayPrice(selectedTrade.tp, 4),
                              className: "text-teal-900",
                            },
                            {
                              label: "Last",
                              value: formatNumber(
                                selectedTrade.close_price ??
                                  selectedTrade.last_price,
                                4,
                              ),
                            },
                          ].map((item) => (
                            <div key={item.label} className="px-4 py-3">
                              <p className="text-[0.68rem] uppercase tracking-[0.16em] text-stone-400">
                                {item.label}
                              </p>
                              <p
                                className={`mt-1 font-mono text-base font-semibold ${item.className ?? "text-stone-950"}`}
                              >
                                {item.value}
                              </p>
                            </div>
                          ))}
                        </div>

                        {/* Performance */}
                        <div className="grid grid-cols-2 gap-3 border-b border-stone-900/8 p-4 sm:grid-cols-4">
                          {[
                            {
                              label: term("realized_r") ?? "Realized R",
                              value:
                                tradeLifecycle(selectedTrade) === "OPEN"
                                  ? "Open"
                                  : hasRealizedR(selectedTrade)
                                    ? `${formatNumber(selectedTrade.realized_r)}R`
                                    : `$${formatNumber(selectedTrade.realized_pnl)}`,
                              className:
                                tradeLifecycle(selectedTrade) === "OPEN"
                                  ? "text-amber-800"
                                  : tradeOutcomeValue(selectedTrade) >= 0
                                    ? "text-teal-900"
                                    : "text-rose-800",
                            },
                            {
                              label: "Expected R",
                              value: hasExpectedR(selectedTrade)
                                ? `${formatNumber(selectedTrade.expected_r)}R`
                                : "--R",
                              className: hasExpectedR(selectedTrade)
                                ? toNumber(selectedTrade.expected_r) >= 0
                                  ? "text-teal-900"
                                  : "text-rose-800"
                                : "text-stone-500",
                            },
                            {
                              label: term("hold") ?? "Hold",
                              value: displayHoldMinutes(selectedTrade),
                            },
                            {
                              label: "Est. duration",
                              value: String(
                                selectedTrade.estimated_duration ?? "—",
                              ),
                            },
                          ].map((item) => (
                            <div
                              key={String(item.label)}
                              className="rounded-[1rem] bg-stone-950/[0.03] px-3 py-2.5"
                            >
                              <p className="text-[0.68rem] uppercase tracking-[0.16em] text-stone-400">
                                {item.label}
                              </p>
                              {settings.showRawKeys ? (
                                <p className="mt-0.5 font-mono text-[0.6rem] text-stone-300">
                                  {String(item.label)}
                                </p>
                              ) : null}
                              <p
                                className={`mt-1.5 font-mono text-base font-semibold ${item.className ?? "text-stone-950"}`}
                              >
                                {item.value}
                              </p>
                            </div>
                          ))}
                        </div>

                        {isVenueSyncOnlyTrade(selectedTrade) ? (
                          <div className="border-b border-stone-900/8 p-4">
                            <div className="mb-3 flex items-center gap-2 text-xs font-semibold text-stone-700">
                              <WalletCards
                                className="h-3.5 w-3.5 text-sky-800"
                                strokeWidth={1.8}
                              />
                              Binance position metrics
                            </div>
                            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                              {[
                                {
                                  label: "Quantity",
                                  value: formatNumber(selectedTrade.quantity, 4),
                                },
                                {
                                  label: "Break-even",
                                  value: formatNumber(
                                    venueMetric(selectedTrade, "break_even_price"),
                                    4,
                                  ),
                                },
                                {
                                  label: "Notional",
                                  value: formatNumber(
                                    venueMetric(selectedTrade, "notional"),
                                    4,
                                  ),
                                },
                                {
                                  label: "Unrealized PnL",
                                  value: formatNumber(
                                    venueMetric(selectedTrade, "unrealized_pnl"),
                                    4,
                                  ),
                                },
                                {
                                  label: "ROE",
                                  value:
                                    venueRoePct(selectedTrade) == null
                                      ? "--"
                                      : `${formatNumber(venueRoePct(selectedTrade), 2)}%`,
                                },
                                {
                                  label: venueInitialMargin(selectedTrade).estimated
                                    ? "Est. initial margin"
                                    : "Initial margin",
                                  value: venueInitialMargin(selectedTrade).value == null
                                    ? "--"
                                    : formatNumber(venueInitialMargin(selectedTrade).value, 4),
                                },
                                {
                                  label: "Maint. margin",
                                  value: nullableMetricNumber(
                                    venueMetric(selectedTrade, "maint_margin"),
                                  ) == null
                                    ? "--"
                                    : formatNumber(
                                        nullableMetricNumber(
                                          venueMetric(selectedTrade, "maint_margin"),
                                        ),
                                        4,
                                      ),
                                },
                                {
                                  label: "Leverage",
                                  value: `${formatNumber(
                                    venueMetric(selectedTrade, "leverage"),
                                    0,
                                  )}x`,
                                },
                                {
                                  label: "Liq. price",
                                  value: formatNumber(
                                    venueMetric(selectedTrade, "liquidation_price"),
                                    4,
                                  ),
                                },
                                {
                                  label: "Distance to liq.",
                                  value:
                                    liquidationDistancePct(selectedTrade) == null
                                      ? "--"
                                      : `${formatNumber(liquidationDistancePct(selectedTrade), 2)}%`,
                                },
                                {
                                  label: "Margin type",
                                  value: String(venueMetric(selectedTrade, "margin_type", "--")),
                                },
                                {
                                  label: "Last venue update",
                                  value: formatTime(
                                    venueMetric(
                                      selectedTrade,
                                      "last_venue_update_at_utc",
                                      venueMetric(selectedTrade, "update_time_utc"),
                                    ),
                                  ),
                                },
                              ].map((item) => (
                                <div
                                  key={item.label}
                                  className="rounded-[1rem] bg-sky-50/60 px-3 py-2.5"
                                >
                                  <p className="text-[0.68rem] uppercase tracking-[0.16em] text-sky-900/60">
                                    {item.label}
                                  </p>
                                  <p className="mt-1.5 font-mono text-sm font-semibold text-sky-950">
                                    {item.value}
                                  </p>
                                </div>
                              ))}
                            </div>
                            <div className="mt-4 rounded-[1rem] border border-amber-900/10 bg-amber-50/60 p-3">
                              <div className="flex items-center justify-between gap-2">
                                <p className="text-[0.68rem] uppercase tracking-[0.16em] text-amber-900/60">
                                  Protection mapping
                                </p>
                                <StatusBadge
                                  label={String(selectedTrade.protection_status ?? "NONE")}
                                  tone={String(selectedTrade.protection_status ?? "NONE").includes("STOP") || String(selectedTrade.protection_status ?? "").includes("PROTECTED") ? "good" : "warn"}
                                />
                              </div>
                              <p className="mt-1.5 text-xs text-amber-900">
                                {String(selectedTrade.protection_summary ?? "No protective Binance orders matched.")}
                              </p>
                              <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
                                {[
                                  { label: "Stop", value: displayPrice(selectedTrade.sl, 4) },
                                  { label: "Target", value: displayPrice(selectedTrade.tp, 4) },
                                  {
                                    label: "Trailing activation",
                                    value: formatNumber(
                                      ((selectedTrade.payload as Record<string, unknown>)?.trailing_stop as JsonRecord | undefined)
                                        ?.activate_price,
                                      4,
                                    ),
                                  },
                                  {
                                    label: "Trailing callback",
                                    value: (() => {
                                      const callback = Number(
                                        ((selectedTrade.payload as Record<string, unknown>)?.trailing_stop as JsonRecord | undefined)
                                          ?.callback_rate,
                                      );
                                      return Number.isFinite(callback)
                                        ? `${formatNumber(callback, 2)}%`
                                        : "--";
                                    })(),
                                  },
                                ].map((item) => (
                                  <div key={item.label}>
                                    <p className="text-[0.68rem] uppercase tracking-[0.14em] text-amber-900/60">
                                      {item.label}
                                    </p>
                                    <p className="mt-1 font-mono text-sm font-semibold text-amber-950">
                                      {item.value}
                                    </p>
                                  </div>
                                ))}
                              </div>
                            </div>
                          </div>
                        ) : (
                          <div className="grid grid-cols-2 gap-3 border-b border-stone-900/8 p-4">
                            <div className="rounded-[1rem] bg-white p-3 shadow-[0_4px_12px_rgba(71,53,29,0.06)]">
                              <div className="flex items-center justify-between">
                                <p className="text-[0.68rem] uppercase tracking-[0.16em] text-stone-400">
                                  Price progress
                                </p>
                                <span className="text-xs font-semibold text-stone-500">
                                  {tradeProgressPercent(selectedTrade) == null
                                    ? "--"
                                    : `${formatNumber(
                                        tradeProgressPercent(selectedTrade),
                                        0,
                                      )}%`}
                                </span>
                              </div>
                              <div className="mt-2 h-2 overflow-hidden rounded-full bg-stone-100">
                                <div
                                  className={`h-full rounded-full transition-[width] duration-300 ${tradeProgressTone(selectedTrade)}`}
                                  style={{
                                    width: `${tradeProgressPercent(selectedTrade) ?? 0}%`,
                                  }}
                                />
                              </div>
                              <p className="mt-1.5 text-xs text-stone-500">
                                {hasTradeProgress(selectedTrade)
                                  ? `Last move ${formatNumber(selectedTrade.progress?.pnl_pct, 2)}% · ${String(
                                      selectedTrade.progress?.side ?? "--",
                                    ).toUpperCase()}`
                                  : "Progress unavailable for venue-synced positions."}
                              </p>
                            </div>
                            <div className="rounded-[1rem] bg-white p-3 shadow-[0_4px_12px_rgba(71,53,29,0.06)]">
                              <div className="flex items-center justify-between">
                                <p className="text-[0.68rem] uppercase tracking-[0.16em] text-stone-400">
                                  Timing
                                </p>
                                <StatusBadge
                                  label={hasTimingProgress(selectedTrade)
                                    ? String(
                                        selectedTrade.timing_status ?? "UNSPECIFIED",
                                      )
                                    : "UNAVAILABLE"}
                                  tone={timingStatusTone(selectedTrade)}
                                />
                              </div>
                              <div className="mt-2 h-2 overflow-hidden rounded-full bg-stone-100">
                                <div
                                  className={`h-full rounded-full transition-[width] duration-300 ${
                                    String(
                                      selectedTrade.timing_status ?? "",
                                    ).toUpperCase() === "OVERDUE"
                                      ? "bg-rose-700"
                                      : String(
                                            selectedTrade.timing_status ?? "",
                                          ).toUpperCase() === "DUE"
                                        ? "bg-amber-700"
                                        : "bg-teal-800"
                                  }`}
                                  style={{
                                    width: `${timingProgressPercent(selectedTrade) ?? 0}%`,
                                  }}
                                />
                              </div>
                              <p className="mt-1.5 text-xs text-stone-500">
                                {hasTimingProgress(selectedTrade)
                                  ? `${formatNumber(
                                      selectedTrade.timing_progress?.elapsed_candles,
                                      2,
                                    )} / ${formatNumber(
                                      selectedTrade.timing_progress?.expected_candles,
                                      2,
                                    )} candles`
                                  : "Timing unavailable for venue-synced positions."}
                              </p>
                            </div>
                          </div>
                        )}

                        {/* Timestamps + meta */}
                        <div className="grid grid-cols-2 gap-x-4 gap-y-2 border-b border-stone-900/8 px-4 py-3 text-xs sm:grid-cols-3">
                          {[
                            {
                              label: "Opened",
                              value: isVenueSyncOnlyTrade(selectedTrade)
                                ? selectedTrade.open_timestamp
                                  ? formatTime(selectedTrade.open_timestamp)
                                  : "Unavailable — requires trade-history reconstruction"
                                : formatTime(selectedTrade.open_timestamp),
                            },
                            {
                              label: "Closed",
                              value: formatTime(selectedTrade.close_timestamp),
                            },
                            {
                              label: "Direction",
                              value: String(selectedTrade.direction ?? "--"),
                            },
                            {
                              label: "Mode / Interval",
                              value: `${String(selectedTrade.mode ?? "--")} / ${String(selectedTrade.interval ?? "--")}`,
                            },
                            { label: "Side", value: sideLabel(selectedTrade) },
                            {
                              label: isVenueSyncOnlyTrade(selectedTrade)
                                ? "Position source"
                                : "Close reason",
                              value: isVenueSyncOnlyTrade(selectedTrade)
                                ? "Binance read-only venue sync"
                                : String(selectedTrade.close_reason ?? "—"),
                            },
                          ].map((item) => (
                            <div key={item.label}>
                              <p className="text-stone-400">{item.label}</p>
                              <p className="mt-0.5 font-semibold text-stone-700">
                                {item.value}
                              </p>
                            </div>
                          ))}
                        </div>

                        {/* R distribution chart */}
                        <div className="border-b border-stone-900/8 p-4">
                          <div className="mb-3 flex items-center gap-2 text-xs font-semibold text-stone-700">
                            <ArrowUpDown
                              className="h-3.5 w-3.5 text-teal-800"
                              strokeWidth={1.8}
                            />
                            R distribution (filtered set)
                          </div>
                          <div className="h-[160px]">
                            <ResponsiveContainer width="100%" height="100%">
                              <BarChart data={rHistogram}>
                                <CartesianGrid
                                  strokeDasharray="3 3"
                                  stroke="rgba(69,58,44,0.08)"
                                />
                                <XAxis
                                  dataKey="bucket"
                                  tickLine={false}
                                  axisLine={false}
                                  tick={{ fontSize: 10 }}
                                />
                                <YAxis
                                  allowDecimals={false}
                                  tickLine={false}
                                  axisLine={false}
                                  tick={{ fontSize: 10 }}
                                />
                                <Tooltip />
                                <Bar
                                  dataKey="count"
                                  fill="#145c56"
                                  radius={[6, 6, 0, 0]}
                                />
                              </BarChart>
                            </ResponsiveContainer>
                          </div>
                        </div>

                        {/* Hold time chart */}
                        <div className="p-4">
                          <div className="mb-3 flex items-center gap-2 text-xs font-semibold text-stone-700">
                            <Clock3
                              className="h-3.5 w-3.5 text-teal-800"
                              strokeWidth={1.8}
                            />
                            Hold time distribution (filtered set)
                          </div>
                          <div className="h-[160px]">
                            <ResponsiveContainer width="100%" height="100%">
                              <BarChart data={holdHistogram}>
                                <CartesianGrid
                                  strokeDasharray="3 3"
                                  stroke="rgba(69,58,44,0.08)"
                                />
                                <XAxis
                                  dataKey="bucket"
                                  tickLine={false}
                                  axisLine={false}
                                  tick={{ fontSize: 10 }}
                                />
                                <YAxis
                                  allowDecimals={false}
                                  tickLine={false}
                                  axisLine={false}
                                  tick={{ fontSize: 10 }}
                                />
                                <Tooltip />
                                <Bar
                                  dataKey="count"
                                  fill="#3b766f"
                                  radius={[6, 6, 0, 0]}
                                />
                              </BarChart>
                            </ResponsiveContainer>
                          </div>
                        </div>

                        {/* Open trade analysis (if any open) */}
                        {summary.open > 0 && openTradeAnalysis.open_count ? (
                          <div className="border-t border-stone-900/8 p-4">
                            <div className="mb-3 flex items-center gap-2 text-xs font-semibold text-stone-700">
                              <Radar
                                className="h-3.5 w-3.5 text-amber-700"
                                strokeWidth={1.8}
                              />
                              Open positions overview
                            </div>
                            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                              {[
                                {
                                  label: "Projected score",
                                  value: Number.isFinite(Number(openTradeAnalysis.open_expected_r))
                                    ? `${formatNumber(openTradeAnalysis.open_expected_r, 2)}R`
                                    : "--R",
                                },
                                {
                                  label: "Avg progress",
                                  value: Number.isFinite(Number(openTradeAnalysis.avg_progress_pct))
                                    ? `${formatNumber(openTradeAnalysis.avg_progress_pct, 0)}%`
                                    : "--",
                                },
                                {
                                  label: "Near target",
                                  value: `${formatNumber(openTradeAnalysis.near_target_count, 0)}`,
                                },
                                {
                                  label: "Adverse",
                                  value: `${formatNumber(openTradeAnalysis.adverse_count, 0)}`,
                                },
                              ].map((item) => (
                                <div
                                  key={item.label}
                                  className="rounded-[0.9rem] bg-amber-50/70 px-3 py-2"
                                >
                                  <p className="text-[0.68rem] text-amber-900/60">
                                    {item.label}
                                  </p>
                                  <p className="mt-1 text-sm font-semibold text-amber-900">
                                    {item.value}
                                  </p>
                                </div>
                              ))}
                            </div>
                          </div>
                        ) : null}
                      </>
                    ) : (
                      <div className="flex h-64 items-center justify-center">
                        <EmptyState message="Select a trade in the ledger to inspect its details." />
                      </div>
                    )}
                  </motion.div>
                </AnimatePresence>
              </div>
            </div>

            {/* ── RIGHT: Audit + Replay/Failures ── */}
            <div className="flex flex-col overflow-hidden border-l border-stone-900/8">
              {/* Right panel tab bar */}
              <div className="flex border-b border-stone-900/8 bg-white/60">
                {[
                  {
                    id: "audit" as const,
                    label: "Audit",
                    badge:
                      selectedTrade &&
                      (selectedTrade.learning ||
                        selectedAudit ||
                        selectedFailure)
                        ? "Ready"
                        : null,
                  },
                  {
                    id: "failures" as const,
                    label: "Failures",
                    badge:
                      losingTrades.length > 0
                        ? String(losingTrades.length)
                        : null,
                  },
                ].map((tab) => (
                  <button
                    key={tab.id}
                    type="button"
                    onClick={() => setRightTab(tab.id)}
                    className={`flex flex-1 items-center justify-center gap-2 py-2.5 text-xs font-semibold transition ${rightTab === tab.id ? "border-b-2 border-stone-950 text-stone-950" : "text-stone-500 hover:text-stone-700"}`}
                  >
                    {tab.label}
                    {tab.badge ? (
                      <span
                        className={`rounded-full px-2 py-0.5 text-[0.64rem] font-semibold ${rightTab === tab.id ? "bg-stone-950 text-stone-50" : "bg-stone-100 text-stone-600"}`}
                      >
                        {tab.badge}
                      </span>
                    ) : null}
                  </button>
                ))}
              </div>

              <div className="flex-1 overflow-y-auto">
                <AnimatePresence mode="wait">
                  <motion.div
                    key={`${rightTab}-${selectedTradeKey ?? "none"}`}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.15 }}
                  >
                    {/* ── AUDIT TAB ── */}
                    {rightTab === "audit" ? (
                      selectedTrade ? (
                        <div className="grid gap-0">
                          {/* Learning audit */}
                          <div className="border-b border-stone-900/8 p-4">
                            <div className="mb-3 flex items-center gap-2 text-xs font-semibold text-stone-700">
                              <Radar
                                className="h-3.5 w-3.5 text-teal-800"
                                strokeWidth={1.8}
                              />
                              Learning audit
                            </div>
                            {selectedTrade.learning &&
                            Object.keys(selectedTrade.learning).length ? (
                              <div className="grid gap-3">
                                <div className="grid grid-cols-2 gap-2">
                                  {[
                                    [
                                      "Conf before",
                                      `${formatNumber(selectedTrade.confidence_before_learning, 1)}%`,
                                    ],
                                    [
                                      "Conf after",
                                      `${formatNumber(selectedTrade.confidence_after_learning ?? selectedTrade.confidence, 1)}%`,
                                    ],
                                    [
                                      "Prob before",
                                      `${formatNumber(Number(selectedTrade.probability_before_learning ?? 0) * 100, 1)}%`,
                                    ],
                                    [
                                      "Prob after",
                                      `${formatNumber(Number(selectedTrade.probability_after_learning ?? 0) * 100, 1)}%`,
                                    ],
                                  ].map(([label, value]) => (
                                    <div
                                      key={String(label)}
                                      className="rounded-[0.9rem] bg-stone-950/[0.03] px-3 py-2"
                                    >
                                      <p className="text-[0.68rem] uppercase tracking-[0.14em] text-stone-400">
                                        {label}
                                      </p>
                                      <p className="mt-1 text-sm font-semibold text-stone-950">
                                        {value}
                                      </p>
                                    </div>
                                  ))}
                                </div>
                                <div className="grid grid-cols-2 gap-2">
                                  {[
                                    [
                                      "Calibration",
                                      formatNumber(
                                        selectedTrade.learning_adjustments
                                          ?.calibration_multiplier,
                                        3,
                                      ),
                                    ],
                                    [
                                      "Entry penalty",
                                      formatNumber(
                                        selectedTrade.learning_adjustments
                                          ?.entry_penalty,
                                        3,
                                      ),
                                    ],
                                    [
                                      "Stop mult.",
                                      `×${formatNumber(selectedTrade.learning_adjustments?.stop_loss_multiplier ?? 1, 2)}`,
                                    ],
                                    [
                                      "Regime",
                                      `${String(selectedTrade.learning_adjustments?.regime_stability_label ?? "--")} ×${formatNumber(selectedTrade.learning_adjustments?.regime_stability_damping ?? 1, 2)}`,
                                    ],
                                  ].map(([label, value]) => (
                                    <div
                                      key={String(label)}
                                      className="rounded-[0.9rem] bg-stone-950/[0.03] px-3 py-2"
                                    >
                                      <p className="text-[0.68rem] uppercase tracking-[0.14em] text-stone-400">
                                        {label}
                                      </p>
                                      <p className="mt-1 text-sm font-semibold text-stone-950">
                                        {value}
                                      </p>
                                    </div>
                                  ))}
                                </div>
                                <div className="flex items-center justify-between rounded-[0.9rem] bg-stone-950/[0.03] px-3 py-2 text-sm">
                                  <span className="text-stone-500">
                                    Learning state
                                  </span>
                                  <span className="font-semibold text-stone-900">
                                    {selectedTrade.learning_adjustments
                                      ?.hard_reject
                                      ? "Hard reject"
                                      : selectedTrade.learning_adjustments
                                            ?.learning_active
                                        ? "Active"
                                        : "Inactive"}
                                  </span>
                                </div>
                                {Array.isArray(
                                  selectedTrade.learning_adjustments?.reasons,
                                ) &&
                                selectedTrade.learning_adjustments.reasons
                                  .length ? (
                                  <div className="rounded-[0.9rem] border border-stone-900/8 bg-white px-3 py-2.5">
                                    <p className="mb-2 text-[0.68rem] uppercase tracking-[0.14em] text-stone-400">
                                      Execution reasons
                                    </p>
                                    <div className="grid gap-1.5">
                                      {selectedTrade.learning_adjustments.reasons.map(
                                        (reason, idx) => (
                                          <p
                                            key={`${String(reason)}-${idx}`}
                                            className="text-xs leading-5 text-stone-600"
                                          >
                                            {String(reason)}
                                          </p>
                                        ),
                                      )}
                                    </div>
                                  </div>
                                ) : null}
                              </div>
                            ) : (
                              <p className="text-xs text-stone-400">
                                No learning adjustment audit attached to this
                                trade.
                              </p>
                            )}
                          </div>

                          {/* Signal audit trail */}
                          <div className="border-b border-stone-900/8 p-4">
                            <div className="mb-3 flex items-center gap-2 text-xs font-semibold text-stone-700">
                              <Link2
                                className="h-3.5 w-3.5 text-teal-800"
                                strokeWidth={1.8}
                              />
                              Signal audit trail
                            </div>
                            {auditQuery.isLoading && selectedSignalId ? (
                              <p className="text-xs text-stone-400">
                                Loading audit…
                              </p>
                            ) : selectedAudit ? (
                              <div className="grid gap-3">
                                <div className="grid grid-cols-2 gap-2">
                                  {[
                                    [
                                      "Conf before",
                                      `${formatNumber(selectedAudit.confidence_before_learning, 1)}%`,
                                    ],
                                    [
                                      "Conf after",
                                      `${formatNumber(selectedAudit.confidence_after_learning, 1)}%`,
                                    ],
                                    [
                                      "Circuit state",
                                      String(
                                        selectedAudit.circuit_breaker_state ??
                                          "--",
                                      ),
                                    ],
                                    [
                                      "Threshold checks",
                                      formatNumber(
                                        selectedAudit.threshold_checks
                                          ?.length ?? 0,
                                        0,
                                      ),
                                    ],
                                  ].map(([label, value]) => (
                                    <div
                                      key={String(label)}
                                      className="rounded-[0.9rem] bg-stone-950/[0.03] px-3 py-2"
                                    >
                                      <p className="text-[0.68rem] uppercase tracking-[0.14em] text-stone-400">
                                        {label}
                                      </p>
                                      <p className="mt-1 text-sm font-semibold text-stone-950">
                                        {value}
                                      </p>
                                    </div>
                                  ))}
                                </div>
                                {(selectedAudit.threshold_checks ?? [])
                                  .length ? (
                                  <div className="rounded-[0.9rem] border border-stone-900/8 bg-white px-3 py-2.5">
                                    <p className="mb-2 text-[0.68rem] uppercase tracking-[0.14em] text-stone-400">
                                      Threshold checks
                                    </p>
                                    <div className="grid gap-1.5">
                                      {(
                                        selectedAudit.threshold_checks ?? []
                                      ).map((item, idx) => (
                                        <div
                                          key={`${String(item.name)}-${idx}`}
                                          className="flex items-center justify-between text-xs"
                                        >
                                          <span className="text-stone-500">
                                            {String(item.name ?? "--")}
                                          </span>
                                          <span
                                            className={
                                              item.passed
                                                ? "font-semibold text-teal-800"
                                                : "font-semibold text-rose-800"
                                            }
                                          >
                                            {item.passed ? "PASS" : "FAIL"} ·{" "}
                                            {formatNumber(item.value)} /{" "}
                                            {formatNumber(item.threshold)}
                                          </span>
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                ) : null}
                                {(
                                  selectedAudit.learning_adjustments_applied ??
                                  []
                                ).length ? (
                                  <div className="rounded-[0.9rem] border border-stone-900/8 bg-white px-3 py-2.5">
                                    <p className="mb-2 text-[0.68rem] uppercase tracking-[0.14em] text-stone-400">
                                      Applied adjustments
                                    </p>
                                    <div className="grid gap-1.5">
                                      {(
                                        selectedAudit.learning_adjustments_applied ??
                                        []
                                      ).map((item, idx) => (
                                        <div
                                          key={`${String(item.source)}-${idx}`}
                                          className="text-xs leading-5 text-stone-600"
                                        >
                                          <span className="font-semibold text-stone-900">
                                            {String(item.source ?? "--")}
                                          </span>{" "}
                                          · ×{formatNumber(item.multiplier, 2)}{" "}
                                          · {String(item.reason ?? "--")}
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                ) : null}
                              </div>
                            ) : (
                              <p className="text-xs text-stone-400">
                                No signal audit attached to this trade.
                              </p>
                            )}
                          </div>

                          {/* Replay */}
                          {tradeLifecycle(selectedTrade) === "CLOSED" ? (
                            <div className="p-4">
                              <div className="mb-3 flex items-center gap-2 text-xs font-semibold text-stone-700">
                                <Radar
                                  className="h-3.5 w-3.5 text-teal-800"
                                  strokeWidth={1.8}
                                />
                                Counterfactual replay
                              </div>
                              {replayQuery.isLoading ? (
                                <p className="text-xs text-stone-400">
                                  Loading replay…
                                </p>
                              ) : replayPayload.items?.length ? (
                                <div className="grid gap-2">
                                  <div className="grid grid-cols-3 gap-2 text-center">
                                    <div className="rounded-[0.9rem] bg-stone-950/[0.03] px-2 py-2">
                                      <p className="text-[0.6rem] uppercase tracking-[0.12em] text-stone-400">
                                        Actual
                                      </p>
                                      <p className="mt-1 text-xs font-semibold text-stone-950">
                                        {String(
                                          replayPayload.actual_action
                                            ?.action_label ?? "ENTER_NOW",
                                        )}
                                      </p>
                                    </div>
                                    <div className="rounded-[0.9rem] bg-teal-50 px-2 py-2">
                                      <p className="text-[0.6rem] uppercase tracking-[0.12em] text-teal-700">
                                        Best
                                      </p>
                                      <p className="mt-1 text-xs font-semibold text-teal-900">
                                        {String(
                                          replayPayload.best_action
                                            ?.action_label ?? "--",
                                        )}
                                      </p>
                                    </div>
                                    <div className="rounded-[0.9rem] bg-stone-950/[0.03] px-2 py-2">
                                      <p className="text-[0.6rem] uppercase tracking-[0.12em] text-stone-400">
                                        Delta
                                      </p>
                                      <p
                                        className={`mt-1 text-xs font-semibold ${toNumber(replayPayload.best_action?.delta_r_vs_actual) >= 0 ? "text-teal-800" : "text-rose-800"}`}
                                      >
                                        {formatNumber(
                                          replayPayload.best_action
                                            ?.delta_r_vs_actual,
                                        )}
                                        R
                                      </p>
                                    </div>
                                  </div>
                                  <div className="grid gap-1.5">
                                    {(replayPayload.items ?? []).map((item) => (
                                      <div
                                        key={`${String(item.action_label)}-${String(item.id ?? item.created_at_utc)}`}
                                        className="flex items-center justify-between rounded-[0.9rem] border border-stone-900/8 bg-stone-50/80 px-3 py-2 text-xs"
                                      >
                                        <div>
                                          <p className="font-semibold text-stone-950">
                                            {String(item.action_label ?? "--")}
                                          </p>
                                          <p className="text-stone-400">
                                            {String(
                                              item.learning_regime ?? "--",
                                            )}
                                          </p>
                                        </div>
                                        <div className="text-right">
                                          <span
                                            className={`font-semibold ${toNumber(item.realized_r) >= 0 ? "text-teal-800" : "text-rose-800"}`}
                                          >
                                            {formatNumber(item.realized_r)}R
                                          </span>
                                          <p className="text-stone-400">
                                            {formatNumber(
                                              item.delta_r_vs_actual,
                                            )}
                                            R Δ
                                          </p>
                                        </div>
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              ) : (
                                <p className="text-xs text-stone-400">
                                  No replay artifacts available yet.
                                </p>
                              )}
                            </div>
                          ) : null}
                        </div>
                      ) : (
                        <div className="flex h-48 items-center justify-center">
                          <EmptyState message="Select a trade to see its audit trail." />
                        </div>
                      )
                    ) : null}

                    {/* ── FAILURES TAB ── */}
                    {rightTab === "failures" ? (
                      <div className="grid gap-0">
                        {/* Summary counts */}
                        <div className="grid grid-cols-3 divide-x divide-stone-900/8 border-b border-stone-900/8">
                          {[
                            ["Losing", losingTrades.length],
                            ["Analyzed", analyzedLosses.length],
                            [
                              "Unanalyzed",
                              Math.max(
                                0,
                                losingTrades.length - analyzedLosses.length,
                              ),
                            ],
                          ].map(([label, count]) => (
                            <div
                              key={String(label)}
                              className="px-4 py-3 text-center"
                            >
                              <p className="text-[0.68rem] uppercase tracking-[0.14em] text-stone-400">
                                {label}
                              </p>
                              <p className="mt-1 text-lg font-semibold text-stone-950">
                                {formatNumber(count, 0)}
                              </p>
                            </div>
                          ))}
                        </div>

                        {/* Failure list */}
                        <div className="grid gap-0">
                          {losingTrades.length ? (
                            losingTrades.map((row) => {
                              const key = buildTradeKey(row);
                              const failure = failuresByOrder.get(
                                orderIdentifier(row),
                              );
                              const isSelected = key === selectedTradeKey;
                              return (
                                <div
                                  key={key}
                                  className={`border-b border-stone-900/8 px-4 py-3 last:border-0 ${isSelected ? "bg-amber-50/60" : ""}`}
                                >
                                  <div className="flex items-start justify-between gap-2">
                                    <div className="flex flex-wrap items-center gap-1.5">
                                      <button
                                        type="button"
                                        onClick={() => setSelectedTradeKey(key)}
                                        className="text-sm font-semibold text-stone-950 hover:underline"
                                      >
                                        {String(row.symbol ?? "--")}
                                      </button>
                                      <StatusBadge
                                        label={String(
                                          row.close_reason ??
                                            row.status ??
                                            "--",
                                        )}
                                        tone="bad"
                                      />
                                    </div>
                                    <span className="font-mono text-sm font-semibold text-rose-800">
                                      {hasRealizedR(row as OrderRow)
                                        ? `${formatNumber(row.realized_r)}R`
                                        : `$${formatNumber(row.realized_pnl)}`}
                                    </span>
                                  </div>
                                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                                    {failure ? (
                                      <>
                                        <Link
                                          to={`/failures?order_id=${encodeURIComponent(orderIdentifier(row))}`}
                                          className="rounded-full bg-rose-50 px-2 py-0.5 text-[0.64rem] font-semibold uppercase tracking-[0.12em] text-rose-900"
                                        >
                                          {String(
                                            failure.failure_source ?? "--",
                                          )}
                                        </Link>
                                        <Link
                                          to={`/failures?order_id=${encodeURIComponent(orderIdentifier(row))}`}
                                          className="rounded-full bg-amber-50 px-2 py-0.5 text-[0.64rem] font-semibold text-amber-900"
                                        >
                                          {String(
                                            failure.blamed_component ?? "--",
                                          )}
                                        </Link>
                                      </>
                                    ) : (
                                      <span className="rounded-full bg-stone-100 px-2 py-0.5 text-[0.64rem] font-semibold text-stone-600">
                                        Unanalyzed
                                      </span>
                                    )}
                                  </div>
                                  {failure?.explanation ? (
                                    <p className="mt-1.5 text-xs leading-5 text-stone-500">
                                      {String(failure.explanation)}
                                    </p>
                                  ) : null}
                                  <div className="mt-2 flex items-center gap-2 text-xs text-stone-400">
                                    <span>
                                      {formatTime(tradeTimestamp(row))}
                                    </span>
                                    <span>·</span>
                                    <span>
                                      {String(row.mode ?? "--")} /{" "}
                                      {String(row.interval ?? "--")}
                                    </span>
                                    <span>·</span>
                                    <button
                                      type="button"
                                      onClick={() => {
                                        setSelectedTradeKey(key);
                                        setRightTab("audit");
                                      }}
                                      className="font-semibold text-stone-600 hover:text-stone-900"
                                    >
                                      Audit ↗
                                    </button>
                                    {failure ? (
                                      <>
                                        <span>·</span>
                                        <Link
                                          to={`/failures?order_id=${encodeURIComponent(orderIdentifier(row))}`}
                                          className="font-semibold text-stone-600 hover:text-stone-900"
                                        >
                                          Detail ↗
                                        </Link>
                                      </>
                                    ) : null}
                                  </div>
                                </div>
                              );
                            })
                          ) : (
                            <div className="flex h-48 items-center justify-center">
                              <EmptyState message="No losing trades in the current filter." />
                            </div>
                          )}
                        </div>
                      </div>
                    ) : null}
                  </motion.div>
                </AnimatePresence>
              </div>
            </div>
          </div>
        </div>
      </div>
    </AnimatedRoute>
  );
}
