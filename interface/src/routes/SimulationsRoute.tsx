import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { toast } from "sonner";
import {
  ArrowRight,
  ChevronDown,
  ChevronUp,
  CircleCheck,
  Clock3,
  Copy,
  Download,
  FileJson,
  FlaskConical,
  Loader2,
  OctagonX,
  Play,
  Radar,
  Search,
  Sparkles,
  Square,
  TrendingUp,
  Workflow,
} from "lucide-react";

import { AnimatedRoute } from "../components/ui/AnimatedRoute";
import { EmptyState } from "../components/ui/EmptyState";
import { LiveSimulationEventPanel } from "../components/scans/LiveSimulationEventPanel";
import {
  AlertBanner,
  BreakdownList,
  SectionHeader,
  SkipBar,
  SortHeader,
} from "../components/analytics/RuntimeDiagnostics";
import { useSettings } from "../contexts/SettingsContext";
import { useSimulationEventStream } from "../hooks/useSimulationEventStream";
import {
  createSimulation,
  fetchRuntimeSettingsForScope,
  fetchRuntimeSettingsMetadataForScope,
  fetchSimulationDecisionTraces,
  fetchSimulationDiagnostics,
  fetchSimulationExport,
  fetchSimulationParityReport,
  fetchSimulationRun,
  fetchSimulations,
  fetchSimulationWhatIf,
  fetchSymbols,
  forceStopSimulation,
  simulationExportUrl,
  submitSimulationFailureAnalysis,
  stopSimulation,
} from "../lib/api";
import {
  copyToClipboard,
  downloadFile,
  exportAsCSV,
  exportFilename,
} from "../lib/export";
import type {
  JsonRecord,
  SimulationDecisionTrace,
  SimulationDiagnosticsResponse,
  SimulationParityReport,
  SimulationResult,
  SimulationRun,
  SimulationWhatIfResponse,
  RuntimeSettingControl,
} from "../lib/types";

// ─── types ────────────────────────────────────────────────────────────────────

type SimStatus = "RUNNING" | "COMPLETED" | "FAILED" | "STOPPED" | "PENDING";
type SimStageStatus = "DONE" | "ACTIVE" | "PENDING" | "FAILED";
type TradeDirection = "BUY" | "SELL";
type TradeMode = "SCALP" | "SWING" | "AGGRESSIVE_SCALP";
type TradeStatus = "CLOSED" | "OPEN" | "STOPPED_OUT";
type SimulationProfile = {
  id: string;
  name: string;
  tag: "simulation-profile";
  scanWorkers: number;
  scanStepBars: number;
  timeForwardStepBars: number;
  riskPerTradePct: number;
  minConfidence: number;
  maxHoldBars: number;
  feeBps: number;
  slippageBps: number;
  settings?: Record<string, string>;
};

type SimulationPreset = {
  id: string;
  name: string;
  period: "7d" | "30d" | "90d" | "custom";
  capital: number;
  symbols: string[];
  intervals: string[];
  modes: string[];
  profileId?: string;
};

type TradeSortKey =
  | "symbol"
  | "mode"
  | "direction"
  | "pnl"
  | "confidence"
  | "hold_time"
  | "status";

type SimulationDetailTab =
  | "overview"
  | "trace"
  | "diagnostics"
  | "what-if"
  | "health"
  | "parity"
  | "exports";

type TraceFilters = {
  symbol: string;
  interval: string;
  mode: string;
  direction: string;
  reason: string;
  minConfidence: string;
  maxConfidence: string;
  fallbackOnly: boolean;
  errorsOnly: boolean;
};

type WhatIfInputs = {
  minConfidence: string;
  feesBps: string;
  slippageBps: string;
  maxHoldBars: string;
  riskPerTrade: string;
};

interface SimStage {
  key: string;
  label: string;
  status: SimStageStatus;
  detail: string;
}

interface SimTrade {
  id: string;
  symbol: string;
  direction: TradeDirection;
  mode: TradeMode;
  interval: string;
  entryPrice: number;
  exitPrice: number | null;
  pnl: number | null;
  pnlPct: number | null;
  confidence: number;
  holdTimeHours: number | null;
  status: TradeStatus;
  openedAt: string;
  closedAt: string | null;
  stopReason: string | null;
}

interface SimulationSkipSample {
  reason: string;
  symbol: string;
  interval: string;
  mode: string;
  timestamp: string;
  direction: string;
  confidence: number | null;
  signalStatus: string;
  fallbackReason: string | null;
  summary: string;
  noTradeReason: string;
}

interface SimRun {
  id: number;
  name: string;
  status: SimStatus;
  periodStart: string;
  periodEnd: string;
  symbolCount: number;
  symbols: string[];
  intervals: string[];
  modes: string[];
  capital: number;
  createdAt: string;
  progressPct: number;
  timeElapsedH: number;
  timeRemainingH: number;
  currentSimDate: string | null;
  totalPnl: number | null;
  totalPnlPct: number | null;
  winRate: number | null;
  tradeCount: number;
  openTradeCount: number;
  closedTradeCount: number;
  maxDrawdownPct: number | null;
  sharpeRatio: number | null;
  avgHoldTimeH: number | null;
  stages: SimStage[];
  trades: SimTrade[];
  skipBreakdown: Array<{ key: string; count: number; pct: number }>;
  skipSamples: SimulationSkipSample[];
  equityCurve: number[];
  perMode: Array<{
    mode: string;
    pnl: number;
    trades: number;
    winRate: number;
  }>;
  alerts: Array<{ tone: "bad" | "warning"; title: string; message: string }>;
  reproducibility?: JsonRecord;
  performanceDiagnostics?: JsonRecord;
  htfContextRequestedCount?: number;
  htfContextMissingCount?: number;
}

// ─── constants ────────────────────────────────────────────────────────────────

const INTERVAL_OPTION_CATALOG = [
  "15m",
  "30m",
  "1h",
  "2h",
  "4h",
  "6h",
  "12h",
  "1d",
  "3d",
  "7d",
  "14d",
  "1M",
];
const STRATEGY_MODE_OPTIONS = ["SCALP", "SWING", "AGGRESSIVE_SCALP"];
const SIMULATION_PRESETS_KEY = "trading-bot.simulation-presets.v1";
const SIMULATION_PROFILES_KEY = "trading-bot.simulation-profiles.v1";
const DEFAULT_SIMULATION_PROFILES: SimulationProfile[] = [
  {
    id: "sim-balanced",
    name: "Simulation Balanced",
    tag: "simulation-profile",
    scanWorkers: 4,
    scanStepBars: 1,
    timeForwardStepBars: 1,
    riskPerTradePct: 1,
    minConfidence: 55,
    maxHoldBars: 0,
    feeBps: 4,
    slippageBps: 2,
  },
  {
    id: "sim-fast",
    name: "Simulation Fast",
    tag: "simulation-profile",
    scanWorkers: 16,
    scanStepBars: 2,
    timeForwardStepBars: 2,
    riskPerTradePct: 1,
    minConfidence: 60,
    maxHoldBars: 0,
    feeBps: 4,
    slippageBps: 3,
  },
  {
    id: "sim-strict",
    name: "Simulation Strict",
    tag: "simulation-profile",
    scanWorkers: 8,
    scanStepBars: 1,
    timeForwardStepBars: 1,
    riskPerTradePct: 0.5,
    minConfidence: 70,
    maxHoldBars: 0,
    feeBps: 5,
    slippageBps: 5,
  },
];
const BUILTIN_SIMULATION_PRESETS: SimulationPreset[] = [
  {
    id: "last-7-scalp",
    name: "Last 7d · Scalp focus",
    period: "7d",
    capital: 25_000,
    symbols: ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
    intervals: ["15m", "1h"],
    modes: ["SCALP", "AGGRESSIVE_SCALP"],
  },
  {
    id: "last-30-balanced",
    name: "Last 30d · Balanced",
    period: "30d",
    capital: 50_000,
    symbols: ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
    intervals: ["1h", "4h"],
    modes: ["SCALP", "SWING"],
  },
  {
    id: "last-90-swing",
    name: "Last 90d · Swing",
    period: "90d",
    capital: 50_000,
    symbols: ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
    intervals: ["4h", "1d"],
    modes: ["SWING"],
  },
];

const EXAMPLE_TRADES: SimTrade[] = [
  {
    id: "t1",
    symbol: "BTCUSDT",
    direction: "BUY",
    mode: "SWING",
    interval: "4h",
    entryPrice: 68_420,
    exitPrice: 71_200,
    pnl: 1240,
    pnlPct: 4.06,
    confidence: 84.2,
    holdTimeHours: 18.4,
    status: "CLOSED",
    openedAt: "2026-03-29T08:00Z",
    closedAt: "2026-03-30T02:24Z",
    stopReason: null,
  },
  {
    id: "t2",
    symbol: "ETHUSDT",
    direction: "BUY",
    mode: "SCALP",
    interval: "1h",
    entryPrice: 3_480,
    exitPrice: 3_548,
    pnl: 680,
    pnlPct: 1.95,
    confidence: 76.1,
    holdTimeHours: 3.2,
    status: "CLOSED",
    openedAt: "2026-03-30T10:00Z",
    closedAt: "2026-03-30T13:12Z",
    stopReason: null,
  },
  {
    id: "t3",
    symbol: "SOLUSDT",
    direction: "SELL",
    mode: "SWING",
    interval: "1d",
    entryPrice: 182.4,
    exitPrice: 174.2,
    pnl: 540,
    pnlPct: 4.49,
    confidence: 81.0,
    holdTimeHours: 48.0,
    status: "CLOSED",
    openedAt: "2026-04-01T00:00Z",
    closedAt: "2026-04-03T00:00Z",
    stopReason: null,
  },
  {
    id: "t4",
    symbol: "AVAXUSDT",
    direction: "BUY",
    mode: "SCALP",
    interval: "1h",
    entryPrice: 38.2,
    exitPrice: 39.1,
    pnl: 430,
    pnlPct: 2.36,
    confidence: 72.5,
    holdTimeHours: 2.1,
    status: "CLOSED",
    openedAt: "2026-04-02T14:00Z",
    closedAt: "2026-04-02T16:06Z",
    stopReason: null,
  },
  {
    id: "t5",
    symbol: "DOTUSDT",
    direction: "SELL",
    mode: "SWING",
    interval: "4h",
    entryPrice: 9.84,
    exitPrice: 9.44,
    pnl: 380,
    pnlPct: 4.07,
    confidence: 78.3,
    holdTimeHours: 22.0,
    status: "CLOSED",
    openedAt: "2026-04-04T06:00Z",
    closedAt: "2026-04-05T04:00Z",
    stopReason: null,
  },
  {
    id: "t6",
    symbol: "BNBUSDT",
    direction: "BUY",
    mode: "SCALP",
    interval: "1h",
    entryPrice: 612,
    exitPrice: 596,
    pnl: -320,
    pnlPct: -2.61,
    confidence: 61.0,
    holdTimeHours: 1.8,
    status: "STOPPED_OUT",
    openedAt: "2026-04-06T09:00Z",
    closedAt: "2026-04-06T10:48Z",
    stopReason: "stop-loss hit",
  },
  {
    id: "t7",
    symbol: "XRPUSDT",
    direction: "SELL",
    mode: "SCALP",
    interval: "4h",
    entryPrice: 0.628,
    exitPrice: 0.642,
    pnl: -210,
    pnlPct: -2.23,
    confidence: 58.4,
    holdTimeHours: 4.0,
    status: "STOPPED_OUT",
    openedAt: "2026-04-06T12:00Z",
    closedAt: "2026-04-06T16:00Z",
    stopReason: "stop-loss hit",
  },
  {
    id: "t8",
    symbol: "ADAUSDT",
    direction: "BUY",
    mode: "SWING",
    interval: "1d",
    entryPrice: 0.492,
    exitPrice: 0.481,
    pnl: -150,
    pnlPct: -2.24,
    confidence: 64.2,
    holdTimeHours: 36.0,
    status: "CLOSED",
    openedAt: "2026-04-07T00:00Z",
    closedAt: "2026-04-08T12:00Z",
    stopReason: null,
  },
  {
    id: "t9",
    symbol: "MATICUSDT",
    direction: "BUY",
    mode: "AGGRESSIVE_SCALP",
    interval: "15m",
    entryPrice: 0.714,
    exitPrice: 0.728,
    pnl: 290,
    pnlPct: 1.96,
    confidence: 69.8,
    holdTimeHours: 0.5,
    status: "CLOSED",
    openedAt: "2026-04-08T11:00Z",
    closedAt: "2026-04-08T11:30Z",
    stopReason: null,
  },
  {
    id: "t10",
    symbol: "LINKUSDT",
    direction: "BUY",
    mode: "SWING",
    interval: "4h",
    entryPrice: 15.84,
    exitPrice: 16.92,
    pnl: 520,
    pnlPct: 6.82,
    confidence: 88.1,
    holdTimeHours: 20.0,
    status: "CLOSED",
    openedAt: "2026-04-09T08:00Z",
    closedAt: "2026-04-10T04:00Z",
    stopReason: null,
  },
  {
    id: "t11",
    symbol: "UNIUSDT",
    direction: "SELL",
    mode: "SCALP",
    interval: "1h",
    entryPrice: 11.24,
    exitPrice: 11.08,
    pnl: 180,
    pnlPct: 1.42,
    confidence: 71.2,
    holdTimeHours: 2.5,
    status: "CLOSED",
    openedAt: "2026-04-10T15:00Z",
    closedAt: "2026-04-10T17:30Z",
    stopReason: null,
  },
  {
    id: "t12",
    symbol: "BTCUSDT",
    direction: "BUY",
    mode: "SCALP",
    interval: "1h",
    entryPrice: 70_180,
    exitPrice: null,
    pnl: null,
    pnlPct: null,
    confidence: 79.4,
    holdTimeHours: null,
    status: "OPEN",
    openedAt: "2026-04-14T06:00Z",
    closedAt: null,
    stopReason: null,
  },
  {
    id: "t13",
    symbol: "ETHUSDT",
    direction: "BUY",
    mode: "SWING",
    interval: "4h",
    entryPrice: 3_612,
    exitPrice: null,
    pnl: null,
    pnlPct: null,
    confidence: 82.6,
    holdTimeHours: null,
    status: "OPEN",
    openedAt: "2026-04-13T20:00Z",
    closedAt: null,
    stopReason: null,
  },
];

const EXAMPLE_RUNS: SimRun[] = [
  {
    id: 1,
    name: "Full-month SCALP + SWING",
    status: "RUNNING",
    periodStart: "2026-03-27",
    periodEnd: "2026-04-27",
    symbolCount: 47,
    symbols: [
      "BTCUSDT",
      "ETHUSDT",
      "SOLUSDT",
      "BNBUSDT",
      "XRPUSDT",
      "AVAXUSDT",
      "ADAUSDT",
      "DOTUSDT",
      "MATICUSDT",
      "LINKUSDT",
      "UNIUSDT",
      "LTCUSDT",
      "ATOMUSDT",
      "NEARUSDT",
      "APTUSDT",
    ],
    intervals: ["1h", "4h", "1d"],
    modes: ["SCALP", "SWING"],
    capital: 50_000,
    createdAt: "2026-04-09T08:14Z",
    progressPct: 62,
    timeElapsedH: 438,
    timeRemainingH: 318,
    currentSimDate: "2026-04-14",
    totalPnl: 6_840,
    totalPnlPct: 13.68,
    winRate: 61,
    tradeCount: 138,
    openTradeCount: 54,
    closedTradeCount: 84,
    maxDrawdownPct: -4.2,
    sharpeRatio: 1.84,
    avgHoldTimeH: 6.2,
    stages: [
      {
        key: "scan_replay",
        label: "Historical scan replay",
        status: "DONE",
        detail: "12,480 scans replayed",
      },
      {
        key: "signal_gen",
        label: "Signal generation",
        status: "DONE",
        detail: "3,211 signals emitted",
      },
      {
        key: "trade_calc",
        label: "Time-forward trade calc",
        status: "ACTIVE",
        detail: "62% complete · Apr 14 →",
      },
      {
        key: "pnl_attr",
        label: "P&L attribution",
        status: "PENDING",
        detail: "pending",
      },
      {
        key: "learning_replay",
        label: "Learning model replay",
        status: "PENDING",
        detail: "pending",
      },
    ],
    trades: EXAMPLE_TRADES,
    skipBreakdown: [
      { key: "low_confidence", count: 1820, pct: 34 },
      { key: "duplicate_open", count: 1178, pct: 22 },
      { key: "daily_cap_reached", count: 962, pct: 18 },
      { key: "missing_levels", count: 749, pct: 14 },
      { key: "other", count: 641, pct: 12 },
    ],
    skipSamples: [],
    equityCurve: [
      50, 52, 54, 51, 56, 59, 57, 61, 58, 63, 60, 65, 62, 59, 55, 60, 64, 68,
      70, 72,
    ],
    perMode: [
      { mode: "SCALP", pnl: 4210, trades: 78, winRate: 63 },
      { mode: "SWING", pnl: 2630, trades: 60, winRate: 58 },
    ],
    alerts: [
      {
        tone: "warning",
        title: "Apr 6 — Drawdown cascade",
        message:
          "3 SCALP positions stop-outed within 4h. Max drawdown reached. Engine paused simulation for 2h.",
      },
    ],
  },
  {
    id: 2,
    name: "Q1 close AGGRESSIVE",
    status: "COMPLETED",
    periodStart: "2026-03-01",
    periodEnd: "2026-03-31",
    symbolCount: 32,
    symbols: [
      "BTCUSDT",
      "ETHUSDT",
      "SOLUSDT",
      "BNBUSDT",
      "XRPUSDT",
      "AVAXUSDT",
    ],
    intervals: ["15m", "1h", "4h"],
    modes: ["SCALP", "AGGRESSIVE_SCALP"],
    capital: 30_000,
    createdAt: "2026-04-05T14:22Z",
    progressPct: 100,
    timeElapsedH: 312,
    timeRemainingH: 0,
    currentSimDate: null,
    totalPnl: 4_260,
    totalPnlPct: 14.2,
    winRate: 67,
    tradeCount: 241,
    openTradeCount: 0,
    closedTradeCount: 241,
    maxDrawdownPct: -3.1,
    sharpeRatio: 2.14,
    avgHoldTimeH: 2.8,
    stages: [
      {
        key: "scan_replay",
        label: "Historical scan replay",
        status: "DONE",
        detail: "8,640 scans replayed",
      },
      {
        key: "signal_gen",
        label: "Signal generation",
        status: "DONE",
        detail: "5,412 signals emitted",
      },
      {
        key: "trade_calc",
        label: "Time-forward trade calc",
        status: "DONE",
        detail: "241 trades settled",
      },
      {
        key: "pnl_attr",
        label: "P&L attribution",
        status: "DONE",
        detail: "complete",
      },
      {
        key: "learning_replay",
        label: "Learning model replay",
        status: "DONE",
        detail: "complete",
      },
    ],
    trades: EXAMPLE_TRADES.filter((t) => t.status !== "OPEN").slice(0, 8),
    skipBreakdown: [
      { key: "low_confidence", count: 2100, pct: 41 },
      { key: "duplicate_open", count: 1050, pct: 21 },
      { key: "daily_cap_reached", count: 810, pct: 16 },
      { key: "missing_levels", count: 610, pct: 12 },
      { key: "other", count: 520, pct: 10 },
    ],
    skipSamples: [],
    equityCurve: [
      50, 53, 55, 58, 61, 65, 62, 67, 70, 74, 71, 76, 80, 78, 82, 85, 83, 87,
      90, 92,
    ],
    perMode: [
      { mode: "SCALP", pnl: 2480, trades: 140, winRate: 70 },
      { mode: "AGGRESSIVE_SCALP", pnl: 1780, trades: 101, winRate: 63 },
    ],
    alerts: [],
  },
  {
    id: 3,
    name: "Swing only — Feb",
    status: "COMPLETED",
    periodStart: "2026-02-01",
    periodEnd: "2026-02-28",
    symbolCount: 20,
    symbols: ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "ADAUSDT"],
    intervals: ["4h", "1d"],
    modes: ["SWING"],
    capital: 25_000,
    createdAt: "2026-03-20T09:00Z",
    progressPct: 100,
    timeElapsedH: 280,
    timeRemainingH: 0,
    currentSimDate: null,
    totalPnl: -775,
    totalPnlPct: -3.1,
    winRate: 44,
    tradeCount: 62,
    openTradeCount: 0,
    closedTradeCount: 62,
    maxDrawdownPct: -7.8,
    sharpeRatio: 0.62,
    avgHoldTimeH: 31.4,
    stages: [
      {
        key: "scan_replay",
        label: "Historical scan replay",
        status: "DONE",
        detail: "3,840 scans replayed",
      },
      {
        key: "signal_gen",
        label: "Signal generation",
        status: "DONE",
        detail: "912 signals emitted",
      },
      {
        key: "trade_calc",
        label: "Time-forward trade calc",
        status: "DONE",
        detail: "62 trades settled",
      },
      {
        key: "pnl_attr",
        label: "P&L attribution",
        status: "DONE",
        detail: "complete",
      },
      {
        key: "learning_replay",
        label: "Learning model replay",
        status: "DONE",
        detail: "complete",
      },
    ],
    trades: EXAMPLE_TRADES.filter((t) => ["t3", "t8", "t10"].includes(t.id)),
    skipBreakdown: [
      { key: "low_confidence", count: 430, pct: 47 },
      { key: "missing_levels", count: 240, pct: 26 },
      { key: "other", count: 242, pct: 27 },
    ],
    skipSamples: [],
    equityCurve: [
      50, 49, 51, 48, 46, 50, 47, 44, 42, 45, 43, 40, 41, 39, 38, 40, 42, 41,
      40, 47,
    ],
    perMode: [{ mode: "SWING", pnl: -775, trades: 62, winRate: 44 }],
    alerts: [
      {
        tone: "bad",
        title: "High drawdown detected",
        message:
          "Max drawdown of −7.8% exceeds the −5% threshold. SWING-only runs in bearish Feb conditions underperformed significantly.",
      },
    ],
  },
  {
    id: 4,
    name: "Scalp stress test",
    status: "STOPPED",
    periodStart: "2026-01-15",
    periodEnd: "2026-02-01",
    symbolCount: 60,
    symbols: ["BTCUSDT", "ETHUSDT"],
    intervals: ["15m", "1h"],
    modes: ["SCALP", "AGGRESSIVE_SCALP"],
    capital: 10_000,
    createdAt: "2026-03-10T11:30Z",
    progressPct: 31,
    timeElapsedH: 48,
    timeRemainingH: 0,
    currentSimDate: "2026-01-21",
    totalPnl: null,
    totalPnlPct: null,
    winRate: null,
    tradeCount: 28,
    openTradeCount: 0,
    closedTradeCount: 28,
    maxDrawdownPct: null,
    sharpeRatio: null,
    avgHoldTimeH: null,
    stages: [
      {
        key: "scan_replay",
        label: "Historical scan replay",
        status: "DONE",
        detail: "4,032 scans replayed",
      },
      {
        key: "signal_gen",
        label: "Signal generation",
        status: "DONE",
        detail: "881 signals emitted",
      },
      {
        key: "trade_calc",
        label: "Time-forward trade calc",
        status: "FAILED",
        detail: "aborted — memory limit",
      },
      {
        key: "pnl_attr",
        label: "P&L attribution",
        status: "PENDING",
        detail: "not reached",
      },
      {
        key: "learning_replay",
        label: "Learning model replay",
        status: "PENDING",
        detail: "not reached",
      },
    ],
    trades: [],
    skipBreakdown: [],
    skipSamples: [],
    equityCurve: [
      50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 50,
      50, 50,
    ],
    perMode: [],
    alerts: [
      {
        tone: "bad",
        title: "Simulation aborted",
        message:
          "Time-forward trade calc stage hit memory limit processing 60-symbol universe at 15m intervals. Reduce symbol count or use 1h minimum.",
      },
    ],
  },
];

// ─── pure helpers ─────────────────────────────────────────────────────────────

function numberFrom(value: unknown, fallback = 0): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}
function stringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.map((v) => String(v)).filter(Boolean)
    : [];
}
function splitCsv(value: unknown): string[] {
  return String(value ?? "")
    .split(",")
    .map((v) => v.trim())
    .filter(Boolean);
}
function uniqueStrings(values: string[]): string[] {
  return Array.from(
    new Set(values.map((v) => String(v).trim()).filter(Boolean)),
  );
}
function stringifySettings(settings: Record<string, unknown>) {
  return Object.fromEntries(
    Object.entries(settings).map(([key, value]) => [
      key,
      value === null || value === undefined ? "" : String(value),
    ]),
  );
}
function csvItems(value: string) {
  return String(value ?? "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}
function firstSetting(settings: Record<string, string>, keys: string[], fallback: string | number = "") {
  for (const key of keys) {
    const value = settings[key];
    if (value !== undefined && value !== null && String(value).length > 0) return value;
  }
  return String(fallback);
}
function settingNumber(settings: Record<string, string>, keys: string[], fallback: number) {
  const parsed = Number(firstSetting(settings, keys, fallback));
  return Number.isFinite(parsed) ? parsed : fallback;
}
function legacyProfileDefaults(profile: SimulationProfile) {
  return {
    AUTONOMOUS_SCAN_WORKERS: String(profile.scanWorkers),
    SIMULATION_SCAN_STEP_BARS: String(profile.scanStepBars),
    SIMULATION_TIME_FORWARD_STEP_BARS: String(profile.timeForwardStepBars),
    SIMULATION_RISK_PER_TRADE_PCT: String(profile.riskPerTradePct),
    AUTONOMOUS_MIN_CONFIDENCE: String(profile.minConfidence),
    SIMULATION_MAX_HOLD_BARS: String(profile.maxHoldBars),
    SIMULATION_FEE_BPS: String(profile.feeBps),
    SIMULATION_SLIPPAGE_BPS: String(profile.slippageBps),
  };
}
function profileWithSettings(profile: SimulationProfile, baseSettings: Record<string, string>): SimulationProfile {
  const seed = profile.settings ? {} : legacyProfileDefaults(profile);
  const settings = { ...baseSettings, ...seed, ...(profile.settings ?? {}) };
  return profileFromSettings({ ...profile, settings }, settings);
}
function profileFromSettings(profile: SimulationProfile, settings: Record<string, string>): SimulationProfile {
  return {
    ...profile,
    settings,
    scanWorkers: settingNumber(settings, ["AUTONOMOUS_SCAN_WORKERS", "SCAN_WORKERS", "scan_workers"], profile.scanWorkers),
    scanStepBars: settingNumber(settings, ["SIMULATION_SCAN_STEP_BARS", "SCAN_STEP_BARS", "scan_step_bars"], profile.scanStepBars),
    timeForwardStepBars: settingNumber(settings, ["SIMULATION_TIME_FORWARD_STEP_BARS", "TIME_FORWARD_STEP_BARS", "time_forward_step_bars"], profile.timeForwardStepBars),
    riskPerTradePct: settingNumber(settings, ["SIMULATION_RISK_PER_TRADE_PCT", "RISK_PER_TRADE_PCT", "risk_per_trade_pct"], profile.riskPerTradePct),
    minConfidence: settingNumber(settings, ["AUTONOMOUS_MIN_CONFIDENCE", "MIN_CONFIDENCE", "min_confidence"], profile.minConfidence),
    maxHoldBars: settingNumber(settings, ["SIMULATION_MAX_HOLD_BARS", "MAX_HOLD_BARS", "max_hold_bars"], profile.maxHoldBars),
    feeBps: settingNumber(settings, ["SIMULATION_FEE_BPS", "FEE_BPS", "fee_bps"], profile.feeBps),
    slippageBps: settingNumber(settings, ["SIMULATION_SLIPPAGE_BPS", "SLIPPAGE_BPS", "slippage_bps"], profile.slippageBps),
  };
}
function simulationRuntimeValues(profile: SimulationProfile, baseSettings: Record<string, string>) {
  const settings = profileWithSettings(profile, baseSettings).settings ?? {};
  return {
    settings,
    scanWorkers: settingNumber(settings, ["AUTONOMOUS_SCAN_WORKERS", "SCAN_WORKERS", "scan_workers"], profile.scanWorkers),
    scanStepBars: settingNumber(settings, ["SIMULATION_SCAN_STEP_BARS", "SCAN_STEP_BARS", "scan_step_bars"], profile.scanStepBars),
    timeForwardStepBars: settingNumber(settings, ["SIMULATION_TIME_FORWARD_STEP_BARS", "TIME_FORWARD_STEP_BARS", "time_forward_step_bars"], profile.timeForwardStepBars),
    riskPerTradePct: settingNumber(settings, ["SIMULATION_RISK_PER_TRADE_PCT", "RISK_PER_TRADE_PCT", "risk_per_trade_pct"], profile.riskPerTradePct),
    minConfidence: settingNumber(settings, ["AUTONOMOUS_MIN_CONFIDENCE", "MIN_CONFIDENCE", "min_confidence"], profile.minConfidence),
    maxHoldBars: settingNumber(settings, ["SIMULATION_MAX_HOLD_BARS", "MAX_HOLD_BARS", "max_hold_bars"], profile.maxHoldBars),
    feeBps: settingNumber(settings, ["SIMULATION_FEE_BPS", "FEE_BPS", "fee_bps"], profile.feeBps),
    slippageBps: settingNumber(settings, ["SIMULATION_SLIPPAGE_BPS", "SLIPPAGE_BPS", "slippage_bps"], profile.slippageBps),
  };
}
function dateDaysAgo(days: number): string {
  const d = new Date(Date.now() - days * 24 * 60 * 60 * 1000);
  return d.toISOString().slice(0, 10);
}
function loadUserSimulationPresets(): SimulationPreset[] {
  if (typeof window === "undefined") return [];
  try {
    const parsed = JSON.parse(
      window.localStorage.getItem(SIMULATION_PRESETS_KEY) || "[]",
    ) as SimulationPreset[];
    return Array.isArray(parsed) ? parsed.filter((p) => p?.id && p?.name) : [];
  } catch {
    return [];
  }
}
function saveUserSimulationPresets(presets: SimulationPreset[]) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(SIMULATION_PRESETS_KEY, JSON.stringify(presets));
}
function loadUserSimulationProfiles(): SimulationProfile[] {
  if (typeof window === "undefined") return [];
  try {
    const parsed = JSON.parse(
      window.localStorage.getItem(SIMULATION_PROFILES_KEY) || "[]",
    ) as SimulationProfile[];
    return Array.isArray(parsed)
      ? parsed.filter((p) => p?.id && p?.tag === "simulation-profile")
      : [];
  } catch {
    return [];
  }
}
function saveUserSimulationProfiles(profiles: SimulationProfile[]) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(
    SIMULATION_PROFILES_KEY,
    JSON.stringify(profiles),
  );
}
function simStatus(value: unknown): SimStatus {
  const status = String(value || "PENDING").toUpperCase();
  if (["RUNNING", "COMPLETED", "FAILED", "STOPPED", "PENDING"].includes(status))
    return status as SimStatus;
  return "PENDING";
}
function tradeStatus(value: unknown): TradeStatus {
  const status = String(value || "CLOSED").toUpperCase();
  if (status === "OPEN" || status === "STOPPED_OUT") return status;
  return "CLOSED";
}
function mapApiResultToTrade(result: SimulationResult): SimTrade {
  const details = (result.details ?? {}) as JsonRecord;
  return {
    id: String(
      details.trade_id ?? result.id ?? `${result.symbol}-${result.created_at}`,
    ),
    symbol: String(details.symbol ?? result.symbol ?? "--"),
    direction:
      String(details.direction ?? result.direction ?? "BUY").toUpperCase() ===
      "SELL"
        ? "SELL"
        : "BUY",
    mode: String(details.mode ?? result.mode ?? "SCALP") as TradeMode,
    interval: String(details.interval ?? result.interval ?? "--"),
    entryPrice: numberFrom(details.entry_price),
    exitPrice:
      details.exit_price == null ? null : numberFrom(details.exit_price),
    pnl: details.pnl == null ? null : numberFrom(details.pnl),
    pnlPct: details.pnl_pct == null ? null : numberFrom(details.pnl_pct),
    confidence: numberFrom(details.confidence ?? result.confidence),
    holdTimeHours:
      details.hold_time_hours == null
        ? null
        : numberFrom(details.hold_time_hours),
    status: tradeStatus(details.status),
    openedAt: String(details.opened_at ?? result.created_at ?? ""),
    closedAt: details.closed_at == null ? null : String(details.closed_at),
    stopReason:
      details.stop_reason == null ? null : String(details.stop_reason),
  };
}
function mapApiRunToSimRun(
  run: SimulationRun,
  results: SimulationResult[] = [],
): SimRun {
  const parameters = (run.parameters ?? {}) as JsonRecord;
  const metrics = (run.metrics ?? {}) as JsonRecord;
  const trades = results.map(mapApiResultToTrade);
  const closedTrades = trades.filter((t) => t.status !== "OPEN");
  const totalPnl =
    metrics.total_pnl == null ? null : numberFrom(metrics.total_pnl);
  const capital = numberFrom(metrics.capital ?? parameters.capital, 0);
  return {
    id: numberFrom(run.id),
    name: String(run.name ?? `Simulation #${run.id ?? ""}`),
    status: simStatus(run.status),
    periodStart: String(metrics.period_start ?? parameters.period_start ?? ""),
    periodEnd: String(metrics.period_end ?? parameters.period_end ?? ""),
    symbolCount: numberFrom(
      metrics.symbol_count,
      stringArray(parameters.symbols).length,
    ),
    symbols: stringArray(metrics.symbols).length
      ? stringArray(metrics.symbols)
      : stringArray(parameters.symbols),
    intervals: stringArray(metrics.intervals).length
      ? stringArray(metrics.intervals)
      : stringArray(parameters.intervals),
    modes: stringArray(metrics.modes).length
      ? stringArray(metrics.modes)
      : stringArray(parameters.modes),
    capital,
    createdAt: String(run.created_at ?? ""),
    progressPct: numberFrom(
      metrics.progress_pct,
      simStatus(run.status) === "COMPLETED" ? 100 : 0,
    ),
    timeElapsedH: numberFrom(metrics.time_elapsed_h),
    timeRemainingH: numberFrom(metrics.time_remaining_h),
    currentSimDate:
      metrics.current_sim_date == null
        ? null
        : String(metrics.current_sim_date),
    totalPnl,
    totalPnlPct:
      metrics.total_pnl_pct == null
        ? totalPnl != null && capital
          ? (totalPnl / capital) * 100
          : null
        : numberFrom(metrics.total_pnl_pct),
    winRate: metrics.win_rate == null ? null : numberFrom(metrics.win_rate),
    tradeCount: numberFrom(metrics.trade_count, trades.length),
    openTradeCount: numberFrom(
      metrics.open_trade_count,
      trades.filter((t) => t.status === "OPEN").length,
    ),
    closedTradeCount: numberFrom(
      metrics.closed_trade_count,
      closedTrades.length,
    ),
    maxDrawdownPct:
      metrics.max_drawdown_pct == null
        ? null
        : numberFrom(metrics.max_drawdown_pct),
    sharpeRatio:
      metrics.sharpe_ratio == null ? null : numberFrom(metrics.sharpe_ratio),
    avgHoldTimeH:
      metrics.avg_hold_time_h == null
        ? null
        : numberFrom(metrics.avg_hold_time_h),
    stages: Array.isArray(metrics.stages)
      ? (metrics.stages as unknown as SimStage[])
      : [],
    trades,
    skipBreakdown: Array.isArray(metrics.skip_breakdown)
      ? (metrics.skip_breakdown as Array<{
          key: string;
          count: number;
          pct: number;
        }>)
      : [],
    skipSamples: Array.isArray(metrics.skip_samples)
      ? (metrics.skip_samples as JsonRecord[]).map((row) => ({
          reason: String(row.reason ?? "unknown"),
          symbol: String(row.symbol ?? "--"),
          interval: String(row.interval ?? "--"),
          mode: String(row.mode ?? "--"),
          timestamp: String(row.timestamp ?? ""),
          direction: String(row.direction ?? "NEUTRAL"),
          confidence:
            row.confidence == null ? null : numberFrom(row.confidence),
          signalStatus: String(row.signal_status ?? ""),
          fallbackReason:
            row.fallback_reason == null ? null : String(row.fallback_reason),
          summary: String(row.summary ?? ""),
          noTradeReason: String(row.no_trade_reason ?? ""),
        }))
      : [],
    equityCurve:
      Array.isArray(metrics.equity_curve) && metrics.equity_curve.length
        ? (metrics.equity_curve as number[]).map((v) => numberFrom(v, 50))
        : [
            50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 50,
            50, 50, 50,
          ],
    perMode: Array.isArray(metrics.per_mode)
      ? (metrics.per_mode as Array<{
          mode: string;
          pnl: number;
          trades: number;
          winRate: number;
        }>)
      : [],
    alerts: Array.isArray(metrics.alerts)
      ? (metrics.alerts as Array<{
          tone: "bad" | "warning";
          title: string;
          message: string;
        }>)
      : [],
    reproducibility: (metrics.reproducibility ??
      parameters.reproducibility ??
      {}) as JsonRecord,
    performanceDiagnostics: (metrics.performance_diagnostics ?? {}) as JsonRecord,
    htfContextRequestedCount: numberFrom(metrics.htf_context_requested_count),
    htfContextMissingCount: numberFrom(metrics.htf_context_missing_count),
  };
}
function fmt(n: number | null | undefined, digits = 0): string {
  if (n == null || isNaN(n)) return "--";
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(n);
}
function fmtMoney(n: number | null | undefined, digits = 0): string {
  if (n == null || isNaN(n)) return "--";
  const abs = Math.abs(n);
  const str = new Intl.NumberFormat("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(abs);
  return `${n < 0 ? "−" : "+"}$${str}`;
}
function fmtPct(n: number | null | undefined, digits = 1): string {
  if (n == null || isNaN(n)) return "--";
  return `${n >= 0 ? "+" : ""}${fmt(n, digits)}%`;
}

// ─── theming helpers ──────────────────────────────────────────────────────────

function statusDotClass(s: SimStatus) {
  if (s === "COMPLETED") return "bg-teal-500";
  if (s === "RUNNING") return "bg-amber-500 animate-pulse";
  if (s === "PENDING") return "bg-sky-500";
  return "bg-rose-500";
}
function statusBadgeClass(s: SimStatus) {
  if (s === "COMPLETED")
    return "bg-teal-500/10 text-teal-700 dark:text-teal-400 ring-1 ring-teal-500/20";
  if (s === "RUNNING")
    return "bg-amber-500/10 text-amber-700 dark:text-amber-400 ring-1 ring-amber-500/20";
  if (s === "PENDING")
    return "bg-sky-500/10 text-sky-700 dark:text-sky-400 ring-1 ring-sky-500/20";
  return "bg-rose-500/10 text-rose-700 dark:text-rose-400 ring-1 ring-rose-500/20";
}
function pnlColorClass(n: number | null | undefined) {
  if (n == null) return "text-stone-400";
  return n >= 0
    ? "text-teal-600 dark:text-teal-400"
    : "text-rose-600 dark:text-rose-400";
}
function stageStatusClass(s: SimStageStatus) {
  if (s === "DONE") return "bg-teal-500/10 text-teal-700 dark:text-teal-400";
  if (s === "ACTIVE")
    return "bg-amber-500/10 text-amber-700 dark:text-amber-400";
  if (s === "FAILED") return "bg-rose-500/10 text-rose-600 dark:text-rose-400";
  return "bg-stone-500/10 text-stone-400 border border-stone-900/10 dark:border-stone-100/10";
}
function healthBgClass(status: string) {
  const s = status.toUpperCase();
  if (s === "GOOD")
    return "bg-teal-500/8 border-teal-500/20 text-teal-800 dark:text-teal-300";
  if (s === "WARNING")
    return "bg-amber-500/8 border-amber-500/20 text-amber-800 dark:text-amber-300";
  if (s === "BAD")
    return "bg-rose-500/8 border-rose-500/20 text-rose-700 dark:text-rose-400";
  return "bg-stone-500/5 border-stone-500/20 text-stone-700 dark:text-stone-300";
}
function skipTone(key: string) {
  const n = key.toLowerCase();
  if (n.startsWith("analysis_fallback")) return "bg-rose-500";
  if (n.includes("error")) return "bg-rose-500";
  if (n === "engine_filtered") return "bg-purple-500";
  const map: Record<string, string> = {
    low_confidence: "bg-stone-400",
    duplicate_open: "bg-sky-500",
    daily_cap_reached: "bg-amber-500",
    missing_levels: "bg-orange-500",
    market_unavailable: "bg-fuchsia-500",
    neutral: "bg-teal-500",
  };
  return map[n] ?? "bg-teal-500";
}
function skipLabel(key: string) {
  const [family, detail] = key.split(":");
  if (family === "analysis_fallback")
    return `Analysis fallback${detail ? ` · ${detail.replaceAll("_", " ")}` : ""}`;
  if (family === "engine_filtered") return "Engine filtered / rejected";
  return key.replaceAll("_", " ");
}
function skipDescription(key: string) {
  const n = key.toLowerCase();
  if (n.startsWith("analysis_fallback"))
    return "Analyzer degraded or returned a safe fallback.";
  if (n === "engine_filtered")
    return "Engine produced a non-actionable filtered/rejected decision before runtime trade settlement.";
  if (n === "low_confidence")
    return "Directional signal existed but was below the simulation confidence threshold.";
  if (n === "neutral") return "Engine returned NO_TRADE / no directional edge.";
  if (n === "duplicate_open")
    return "Simulation already had the same symbol/interval/mode/direction open until a later bar.";
  if (n.includes("error"))
    return "Simulation could not analyze this replay point due to an error.";
  return "Simulation skipped this replay point before opening a trade.";
}
function skipFamily(key: string) {
  const n = key.toLowerCase();
  if (n.startsWith("analysis_fallback") || n.includes("error"))
    return "Analyzer health";
  if (["low_confidence", "engine_filtered", "neutral"].includes(n))
    return "Decision output";
  if (["duplicate_open", "daily_cap_reached", "missing_levels"].includes(n))
    return "Runtime filter";
  return "Other";
}
function skipFamilyRows(rows: Array<{ key: string; count: number }>) {
  const counts = new Map<string, number>();
  for (const row of rows)
    counts.set(
      skipFamily(row.key),
      (counts.get(skipFamily(row.key)) ?? 0) + row.count,
    );
  const total = [...counts.values()].reduce((s, c) => s + c, 0);
  return [...counts.entries()]
    .map(([key, count]) => ({
      key,
      count,
      percent: total > 0 ? (count / total) * 100 : 0,
    }))
    .sort((a, b) => b.count - a.count);
}
function simulationSkipDiagnostic(run: SimRun) {
  const total = run.skipBreakdown.reduce((s, r) => s + r.count, 0);
  if (!total) return null;
  const fallback = run.skipBreakdown
    .filter((r) => r.key.toLowerCase().startsWith("analysis_fallback"))
    .reduce((s, r) => s + r.count, 0);
  if (fallback > 0)
    return {
      tone: "bad" as const,
      title: "Analyzer fallback dominated this simulation",
      message: `${fmt(fallback)} replay decisions were safe fallbacks/degraded analyzer outputs. Check model registry/champion availability.`,
    };
  const neutral =
    run.skipBreakdown.find((r) => r.key === "neutral")?.count ?? 0;
  if (run.tradeCount === 0 && neutral / total >= 0.95)
    return {
      tone: "warning" as const,
      title: "Mostly engine-side neutral decisions",
      message:
        "Nearly every replay point was NO_TRADE. For older runs this may be the legacy opaque neutral bucket; rerun to get fallback/filter attribution.",
    };
  return null;
}
function stageIcon(s: SimStageStatus) {
  if (s === "DONE")
    return <CircleCheck className="h-3.5 w-3.5" strokeWidth={1.8} />;
  if (s === "ACTIVE")
    return <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={1.8} />;
  if (s === "FAILED")
    return <OctagonX className="h-3.5 w-3.5" strokeWidth={1.8} />;
  return (
    <div className="h-2 w-2 rounded-full border border-current opacity-40" />
  );
}
function buildEquityPath(points: number[], w: number, h: number): string {
  const n = points.length;
  const xs = points.map((_, i) => (i / (n - 1)) * w);
  const ys = points.map((v) => h - ((v - 40) / 60) * h);
  let d = `M ${xs[0].toFixed(1)} ${ys[0].toFixed(1)}`;
  for (let i = 1; i < n; i++) {
    const cpx = (xs[i - 1] + xs[i]) / 2;
    d += ` C ${cpx.toFixed(1)} ${ys[i - 1].toFixed(1)}, ${cpx.toFixed(1)} ${ys[i].toFixed(1)}, ${xs[i].toFixed(1)} ${ys[i].toFixed(1)}`;
  }
  return d;
}
function buildEquityFill(points: number[], w: number, h: number): string {
  return buildEquityPath(points, w, h) + ` L ${w} ${h} L 0 ${h} Z`;
}
function normalizeReason(reason: unknown) {
  return String(reason || "").trim();
}
function reasonLabel(reason: unknown) {
  return normalizeReason(reason).replaceAll("_", " ") || "none";
}
function primaryBlocker(diagnostics?: SimulationDiagnosticsResponse) {
  return (diagnostics?.top_blockers ?? [])[0];
}
function blockerCount(
  diagnostics: SimulationDiagnosticsResponse | undefined,
  matcher: (reason: string) => boolean,
) {
  return (diagnostics?.top_blockers ?? []).reduce((sum, row) => {
    const r = normalizeReason(row.reason).toLowerCase();
    return matcher(r) ? sum + Number(row.count ?? 0) : sum;
  }, 0);
}
function decisionCount(diagnostics?: SimulationDiagnosticsResponse) {
  const distributionTotal = Object.values(
    diagnostics?.decision_distribution ?? {},
  ).reduce((sum, value) => sum + Number(value ?? 0), 0);
  return (
    Number(
      diagnostics?.trace_coverage?.expected_decision_count ??
        diagnostics?.trace_coverage?.trace_count ??
        distributionTotal ??
        0,
    ) || distributionTotal
  );
}
function diagnosticHasMissingTraceCoverage(
  diagnostics?: SimulationDiagnosticsResponse,
  _summaryCount?: number,
  run?: SimRun | null,
) {
  const coverage = diagnostics?.trace_coverage;
  const status = String(coverage?.coverage_status || "").toLowerCase();
  const traceCount = Number(coverage?.trace_count ?? 0);
  const health = String(diagnostics?.health?.status || "").toUpperCase();
  return (
    health === "UNKNOWN" ||
    status === "missing" ||
    status === "unknown" ||
    (run?.status === "COMPLETED" && traceCount === 0)
  );
}

// ─── shared primitive components ──────────────────────────────────────────────

/** Compact card wrapper used throughout the detail panes */
function Card({
  children,
  className = "",
  ...props
}: React.HTMLAttributes<HTMLDivElement> & {
  children: React.ReactNode;
}) {
  return (
    <div
      {...props}
      className={`rounded-xl border border-stone-900/8 dark:border-stone-100/8 bg-white dark:bg-stone-900 ${className}`}
    >
      {children}
    </div>
  );
}

/** Section heading with icon, title, subtitle */
function PanelHeader({
  icon: Icon,
  title,
  subtitle,
  action,
}: {
  icon: React.ElementType;
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-2 px-3 py-2.5 border-b border-stone-900/8 dark:border-stone-100/8 bg-stone-50/60 dark:bg-stone-950/40 rounded-t-xl">
      <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-teal-500/12 dark:bg-teal-400/10">
        <Icon
          className="h-3 w-3 text-teal-600 dark:text-teal-400"
          strokeWidth={1.8}
        />
      </span>
      <span className="text-[0.7rem] font-semibold text-stone-800 dark:text-stone-200 leading-tight">
        {title}
      </span>
      {subtitle && (
        <span className="ml-auto text-[0.65rem] text-stone-400 dark:text-stone-500 shrink-0">
          {subtitle}
        </span>
      )}
      {action && <span className="ml-auto">{action}</span>}
    </div>
  );
}

/** Status badge pill */
function StatusBadge({ status }: { status: SimStatus }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[0.6rem] font-bold uppercase tracking-wide ${statusBadgeClass(status)}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${statusDotClass(status)}`} />
      {status}
    </span>
  );
}

/** KPI tile for the 6-metric strip */
function KpiTile({
  label,
  value,
  sub,
  valueClass = "",
}: {
  label: string;
  value: string;
  sub?: string;
  valueClass?: string;
}) {
  return (
    <div className="flex flex-col gap-0.5 px-3 py-2.5 border-r border-stone-900/8 dark:border-stone-100/8 last:border-r-0">
      <span className="text-[0.6rem] font-semibold uppercase tracking-widest text-stone-400 dark:text-stone-500 leading-none">
        {label}
      </span>
      <span
        className={`text-[1.05rem] font-semibold tabular-nums leading-tight mt-1 ${valueClass || "text-stone-900 dark:text-stone-100"}`}
      >
        {value}
      </span>
      {sub && (
        <span
          className={`text-[0.6rem] leading-none ${valueClass || "text-stone-400 dark:text-stone-500"}`}
        >
          {sub}
        </span>
      )}
    </div>
  );
}

/** Equity mini chart */
function EquityMiniChart({
  points,
  status,
}: {
  points: number[];
  status: SimStatus;
}) {
  const W = 340;
  const H = 56;
  const linePath = buildEquityPath(points, W, H);
  const fillPath = buildEquityFill(points, W, H);
  const last = points[points.length - 1];
  const color =
    status === "COMPLETED" && last > 50
      ? "#1d9e75"
      : status === "COMPLETED"
        ? "#e24b4a"
        : status === "RUNNING"
          ? "#f59e0b"
          : "#9ca3af";
  const fillId = `eq-${status}-${last}`;
  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      width="100%"
      height={H}
      preserveAspectRatio="none"
    >
      <defs>
        <linearGradient id={fillId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.2" />
          <stop offset="100%" stopColor={color} stopOpacity="0.01" />
        </linearGradient>
      </defs>
      <line
        x1="0"
        y1={H / 2}
        x2={W}
        y2={H / 2}
        stroke="#d4d0c8"
        strokeWidth="0.5"
        strokeDasharray="4 3"
      />
      <path d={fillPath} fill={`url(#${fillId})`} />
      <path
        d={linePath}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** Timeline bar */
function TimelineBar({ run }: { run: SimRun }) {
  const pct = run.progressPct;
  const events = [
    { pct: 8, color: "#3b82f6", label: "scan" },
    { pct: 15, color: "#1d9e75", label: "trade" },
    { pct: 22, color: "#3b82f6", label: "scan" },
    { pct: 31, color: "#1d9e75", label: "trade" },
    { pct: 38, color: "#1d9e75", label: "trade" },
    { pct: 45, color: "#e24b4a", label: "stop" },
    { pct: 52, color: "#3b82f6", label: "scan" },
    { pct: 58, color: "#1d9e75", label: "trade" },
    { pct: 62, color: "#3b82f6", label: "scan" },
  ].filter((e) => e.pct <= pct + 2);
  return (
    <div>
      <div className="relative h-8 overflow-hidden rounded-lg bg-stone-100 dark:bg-stone-800">
        <div
          className="absolute left-0 top-0 h-full bg-teal-500/12 dark:bg-teal-400/10 transition-[width]"
          style={{ width: `${pct}%` }}
        />
        {events.map((e, i) => (
          <div
            key={i}
            className="absolute top-1/2 -translate-y-1/2 h-1.5 w-1.5 rounded-full"
            style={{ left: `calc(${e.pct}% - 3px)`, background: e.color }}
            title={e.label}
          />
        ))}
        {run.status === "RUNNING" && (
          <div
            className="absolute top-0 h-full w-px bg-teal-600 dark:bg-teal-400"
            style={{ left: `${pct}%` }}
          >
            <div className="absolute -top-px left-1.5 whitespace-nowrap rounded bg-teal-600 px-1.5 py-0.5 text-[0.55rem] font-semibold text-white">
              {run.currentSimDate} ▸
            </div>
          </div>
        )}
      </div>
      <div className="mt-1.5 flex items-center justify-between text-[0.6rem] text-stone-400 dark:text-stone-500">
        <span>{run.periodStart}</span>
        <span>{run.periodEnd}</span>
      </div>
      <div className="mt-1.5 flex flex-wrap items-center gap-3 text-[0.6rem] text-stone-400 dark:text-stone-500">
        <span className="flex items-center gap-1">
          <span className="h-1.5 w-1.5 rounded-full bg-teal-500" />
          Trade placed
        </span>
        <span className="flex items-center gap-1">
          <span className="h-1.5 w-1.5 rounded-full bg-blue-500" />
          Scan run
        </span>
        <span className="flex items-center gap-1">
          <span className="h-1.5 w-1.5 rounded-full bg-rose-500" />
          Stop-out
        </span>
        <span className="ml-auto font-medium text-stone-600 dark:text-stone-400">
          {fmt(run.timeElapsedH)}h elapsed
          {run.status === "RUNNING"
            ? ` · ~${fmt(run.timeRemainingH)}h remaining`
            : " total"}
        </span>
      </div>
    </div>
  );
}

function SimulationRuntimeSettingsEditor({
  settings,
  controls,
  onChange,
  onImportRuntime,
}: {
  settings: Record<string, string>;
  controls: RuntimeSettingControl[];
  onChange: (settings: Record<string, string>) => void;
  onImportRuntime: () => void;
}) {
  const [query, setQuery] = useState("");
  const controlsByKey = useMemo(
    () => Object.fromEntries(controls.map((control) => [control.key, control])),
    [controls],
  );
  const keys = useMemo(() => {
    const allKeys = uniqueStrings([
      ...controls.map((control) => control.key),
      ...Object.keys(settings),
    ]).sort();
    const term = query.trim().toUpperCase();
    return term
      ? allKeys.filter((key) => key.toUpperCase().includes(term) || String(settings[key] ?? "").toUpperCase().includes(term))
      : allKeys;
  }, [controls, query, settings]);
  const grouped = useMemo(() => {
    const groups: Array<{ id: string; label: string; keys: string[] }> = [
      { id: "execution", label: "Execution", keys: [] },
      { id: "risk", label: "Risk", keys: [] },
      { id: "universe", label: "Universe", keys: [] },
      { id: "learning", label: "Learning", keys: [] },
      { id: "engine", label: "Engine", keys: [] },
      { id: "other", label: "Other", keys: [] },
    ];
    for (const key of keys) {
      const upper = key.toUpperCase();
      const target = upper.includes("RISK") || upper.includes("LOSS") || upper.includes("CONFIDENCE") || upper.includes("HOLD")
        ? groups[1]
        : upper.includes("SYMBOL") || upper.includes("INTERVAL") || upper.includes("MODE")
          ? groups[2]
          : upper.includes("LEARNING") || upper.includes("CALIBRATION")
            ? groups[3]
            : upper.includes("ENGINE") || upper.includes("V6_") || upper.includes("SHADOW")
              ? groups[4]
              : upper.includes("SCAN") || upper.includes("WORKER") || upper.includes("AUTONOMOUS") || upper.includes("BUDGET") || upper.includes("TIMEOUT")
                ? groups[0]
                : groups[5];
      target.keys.push(key);
    }
    return groups.filter((group) => group.keys.length > 0);
  }, [keys]);
  const update = (key: string, value: string) => onChange({ ...settings, [key]: value });

  return (
    <Card>
      <PanelHeader
        icon={Workflow}
        title="Full runtime config for this simulation"
        subtitle="Draft is stored inside the simulation profile"
        action={(
          <button
            type="button"
            onClick={onImportRuntime}
            className="rounded-lg border border-stone-900/8 dark:border-stone-100/8 bg-white dark:bg-stone-900 px-2.5 py-1 text-[0.65rem] font-semibold text-stone-600 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-800"
          >
            Import current runtime
          </button>
        )}
      />
      <div className="p-3">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search all runtime keys…"
            className="h-8 min-w-[18rem] flex-1 rounded-lg border border-stone-900/8 dark:border-stone-100/8 bg-stone-50 dark:bg-stone-950/40 px-2.5 text-[0.7rem] text-stone-800 dark:text-stone-200 outline-none"
          />
          <span className="text-[0.65rem] text-stone-400 dark:text-stone-500">{keys.length} settings</span>
        </div>
        <div className="space-y-4">
          {grouped.map((group) => (
            <section key={group.id}>
              <div className="mb-2 flex items-center gap-2">
                <h4 className="text-[0.65rem] font-bold uppercase tracking-widest text-stone-500 dark:text-stone-400">{group.label}</h4>
                <span className="rounded-full bg-teal-500/10 px-2 py-0.5 text-[0.6rem] font-bold text-teal-700 dark:text-teal-400">{group.keys.length}</span>
              </div>
              <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
                {group.keys.map((key) => {
                  const control = controlsByKey[key];
                  const value = settings[key] ?? "";
                  const items = csvItems(value);
                  return (
                    <div key={key} className="rounded-lg border border-stone-900/8 dark:border-stone-100/8 bg-stone-50 dark:bg-stone-950/40 p-2.5">
                      <div className="mb-1 flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="truncate text-[0.58rem] font-semibold uppercase tracking-widest text-stone-400 dark:text-stone-500" title={key}>{key}</p>
                          <p className="mt-0.5 text-[0.68rem] font-semibold text-stone-700 dark:text-stone-200">{control?.label ?? key}</p>
                        </div>
                        <button type="button" onClick={() => void navigator.clipboard.writeText(value)} className="text-stone-400 hover:text-stone-700 dark:hover:text-stone-200"><Copy className="h-3 w-3" /></button>
                      </div>
                      {control?.description ? <p className="mb-2 line-clamp-2 text-[0.63rem] leading-5 text-stone-500 dark:text-stone-400">{control.description}</p> : null}
                      {control?.control === "boolean" ? (
                        <div className="flex gap-1.5">
                          {["true", "false"].map((option) => (
                            <button key={option} type="button" onClick={() => update(key, option)} className={`rounded-full px-2 py-0.5 text-[0.62rem] font-semibold ${value === option ? "bg-teal-500/10 text-teal-700 dark:text-teal-400" : "border border-stone-900/8 dark:border-stone-100/8 text-stone-500"}`}>{option}</button>
                          ))}
                        </div>
                      ) : control?.control === "enum" ? (
                        <select value={value} onChange={(event) => update(key, event.target.value)} className="h-7 w-full rounded-md border border-stone-900/8 dark:border-stone-100/8 bg-white dark:bg-stone-900 px-2 text-[0.7rem] text-stone-700 dark:text-stone-200 outline-none">
                          {(control.options ?? []).map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                        </select>
                      ) : control?.control === "multi_enum" ? (
                        <div className="flex flex-wrap gap-1">
                          {(control.options ?? []).map((option) => {
                            const active = items.includes(option.value);
                            return <button key={option.value} type="button" onClick={() => update(key, (active ? items.filter((item) => item !== option.value) : [...items, option.value]).join(","))} className={`rounded-full px-2 py-0.5 text-[0.6rem] font-semibold ${active ? "bg-teal-500/10 text-teal-700 dark:text-teal-400" : "border border-stone-900/8 dark:border-stone-100/8 text-stone-500"}`}>{option.label}</button>;
                          })}
                        </div>
                      ) : (
                        <input type={control?.control === "number" ? "number" : "text"} value={value} min={control?.min_value ?? undefined} max={control?.max_value ?? undefined} step={control?.step ?? undefined} onChange={(event) => update(key, event.target.value)} className="h-7 w-full rounded-md border border-stone-900/8 dark:border-stone-100/8 bg-white dark:bg-stone-900 px-2 text-[0.7rem] text-stone-700 dark:text-stone-200 outline-none" />
                      )}
                    </div>
                  );
                })}
              </div>
            </section>
          ))}
        </div>
      </div>
    </Card>
  );
}

/** Builder chip group for symbols / intervals / modes */
function BuilderChipGroup({
  label,
  values,
  selected,
  onChange,
  helper,
  maxVisible = 36,
}: {
  label: string;
  values: string[];
  selected: string[];
  onChange: (values: string[]) => void;
  helper: string;
  maxVisible?: number;
}) {
  const visible = values.slice(0, maxVisible);
  function toggle(value: string) {
    onChange(
      selected.includes(value)
        ? selected.filter((v) => v !== value)
        : [...selected, value],
    );
  }
  return (
    <Card>
      <div className="p-3 border-b border-stone-900/8 dark:border-stone-100/8 flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-[0.6rem] font-semibold uppercase tracking-widest text-stone-400 dark:text-stone-500">
            {label}
          </p>
          <p className="text-[0.65rem] text-stone-500 dark:text-stone-400 mt-0.5">
            {helper}
          </p>
        </div>
        <div className="flex gap-1.5">
          <button
            type="button"
            onClick={() => onChange([...values])}
            className="rounded-full border border-stone-900/8 dark:border-stone-100/8 bg-white dark:bg-stone-800 px-2.5 py-1 text-[0.65rem] font-semibold text-stone-600 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-700"
          >
            All
          </button>
          <button
            type="button"
            onClick={() => onChange([])}
            className="rounded-full border border-stone-900/8 dark:border-stone-100/8 bg-white dark:bg-stone-800 px-2.5 py-1 text-[0.65rem] font-semibold text-stone-600 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-700"
          >
            Clear
          </button>
        </div>
      </div>
      <div className="p-3 flex flex-wrap gap-1.5">
        {visible.map((value) => {
          const active = selected.includes(value);
          return (
            <button
              key={value}
              type="button"
              onClick={() => toggle(value)}
              className={`rounded-full px-2.5 py-1 text-[0.65rem] font-semibold transition-colors ${active ? "bg-teal-500/10 text-teal-700 dark:text-teal-400 ring-1 ring-teal-500/20" : "border border-stone-900/8 dark:border-stone-100/8 bg-white dark:bg-stone-800 text-stone-600 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-700"}`}
            >
              {value.replaceAll("_", " ")}
            </button>
          );
        })}
        {values.length > maxVisible && (
          <span className="rounded-full bg-stone-100 dark:bg-stone-800 px-2.5 py-1 text-[0.65rem] text-stone-400">
            +{values.length - maxVisible} more
          </span>
        )}
      </div>
    </Card>
  );
}

// ─── run intelligence components ──────────────────────────────────────────────

function SimulationOldRunBanner({
  show,
  onRerun,
}: {
  show: boolean;
  onRerun: () => void;
}) {
  if (!show) return null;
  return (
    <div
      data-testid="simulation-old-run-banner"
      className="rounded-xl border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/30 px-3 py-2.5"
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="text-[0.7rem] font-semibold text-amber-800 dark:text-amber-300">
            Limited diagnostic coverage
          </p>
          <p className="mt-0.5 text-[0.65rem] text-amber-700 dark:text-amber-400 leading-relaxed">
            This run was created before full decision traces were available.
            Rerun with diagnostics to inspect skipped decisions.
          </p>
        </div>
        <button
          type="button"
          onClick={onRerun}
          className="shrink-0 rounded-lg bg-amber-500/15 px-2.5 py-1.5 text-[0.65rem] font-semibold text-amber-800 dark:text-amber-300 hover:bg-amber-500/25"
        >
          Rerun with diagnostics
        </button>
      </div>
    </div>
  );
}

function SimulationReproducibilityCard({ run }: { run?: SimRun | null }) {
  const metadata = (run?.reproducibility ?? {}) as JsonRecord;
  const entries: Array<[string, unknown]> = [
    ["Request hash", metadata.request_payload_hash],
    ["Execution settings hash", metadata.execution_settings_hash],
    ["Analyzer engine", metadata.analyzer_engine_version],
    ["Model version", metadata.model_version],
    ["Snapshot builder", metadata.snapshot_builder_version],
    ["Contract", metadata.contract_version],
  ].filter(
    (entry): entry is [string, unknown] => entry[1] != null && entry[1] !== "",
  );
  const htf = (metadata.htf_context_summary ?? {}) as JsonRecord;
  return (
    <Card data-testid="simulation-reproducibility-card">
      <PanelHeader
        icon={FileJson}
        title="Reproducibility metadata"
        subtitle={
          entries.length
            ? "Stable hashes and replay provenance"
            : "Unavailable for older runs"
        }
      />
      <div className="p-3">
        {entries.length ? (
          <div className="grid gap-1.5">
            {entries.map(([label, value]) => (
              <div
                key={String(label)}
                className="flex items-start justify-between gap-3 rounded-lg bg-stone-50 dark:bg-stone-950/40 px-2.5 py-2"
              >
                <span className="text-[0.65rem] font-semibold text-stone-500 dark:text-stone-400 shrink-0">
                  {label}
                </span>
                <code className="text-[0.65rem] text-stone-700 dark:text-stone-300 font-mono truncate max-w-[60%]">
                  {String(value)}
                </code>
              </div>
            ))}
            {Object.keys(htf).length ? (
              <div className="rounded-lg bg-teal-50 dark:bg-teal-950/30 px-2.5 py-2 text-[0.65rem] text-teal-700 dark:text-teal-400">
                HTF requested {String(htf.requested ?? 0)} · available{" "}
                {String(htf.available ?? 0)} · missing{" "}
                {String(htf.missing ?? 0)}
              </div>
            ) : null}
          </div>
        ) : (
          <p className="text-[0.7rem] text-stone-400 dark:text-stone-500">
            Old simulation runs may not include reproducibility metadata. Rerun
            with diagnostics to populate it.
          </p>
        )}
      </div>
    </Card>
  );
}

function SimulationRunIntelligenceSummary({
  run,
  diagnostics,
  parity,
  onAction,
}: {
  run?: SimRun | null;
  diagnostics?: SimulationDiagnosticsResponse;
  parity?: SimulationParityReport;
  onAction: (
    action:
      | "trace"
      | "diagnostics"
      | "what-if"
      | "parity"
      | "exports"
      | "rerun",
    filters?: Partial<TraceFilters>,
  ) => void;
}) {
  const blocker = primaryBlocker(diagnostics);
  const totalDecisions = decisionCount(diagnostics);
  const traceCount = Number(diagnostics?.trace_coverage?.trace_count ?? 0);
  const fallbackCount = blockerCount(
    diagnostics,
    (r) => r.startsWith("analysis_fallback") || r.includes("fallback"),
  );
  const lowConfidenceCount = blockerCount(
    diagnostics,
    (r) => r === "low_confidence",
  );
  const dataErrorCount = blockerCount(diagnostics, (r) =>
    r.includes("data_error"),
  );
  const htfMissing = Number(run?.htfContextMissingCount ?? 0);
  const htfRequested = Number(run?.htfContextRequestedCount ?? 0);
  const health = String(diagnostics?.health?.status || "UNKNOWN").toUpperCase();
  const blockerReason = normalizeReason(blocker?.reason);
  const trustMessage =
    health === "GOOD"
      ? "This run looks usable for review."
      : health === "UNKNOWN"
        ? "Trust is limited until decision traces are available."
        : "Review blockers before using this run for decisions.";
  const recommended =
    health === "UNKNOWN" && traceCount === 0
      ? { label: "Rerun with diagnostics", action: "rerun" as const }
      : fallbackCount > Math.max(lowConfidenceCount, 0)
        ? {
            label: "Check analyzer registry/champion availability",
            action: "trace" as const,
            filters: { fallbackOnly: true },
          }
        : lowConfidenceCount > 0
          ? {
              label: "Open What-If and test lower confidence",
              action: "what-if" as const,
            }
          : parity?.available === false
            ? {
                label: "Run comparable normal scan for parity",
                action: "parity" as const,
              }
            : { label: "Open diagnostics", action: "diagnostics" as const };

  return (
    <Card data-testid="simulation-intelligence-summary">
      <div className="p-3 bg-teal-500/5 dark:bg-teal-400/5 rounded-xl border border-teal-500/15 dark:border-teal-400/10">
        <div className="flex flex-wrap items-start justify-between gap-2 mb-3">
          <div>
            <p className="text-[0.6rem] font-semibold uppercase tracking-widest text-teal-600 dark:text-teal-400">
              Run intelligence
            </p>
            <p className="mt-0.5 text-sm font-semibold text-stone-900 dark:text-stone-100">
              Can I trust this run?
            </p>
            <p className="mt-0.5 text-[0.65rem] text-stone-500 dark:text-stone-400">
              {trustMessage}
            </p>
          </div>
          <button
            type="button"
            onClick={() =>
              onAction(
                recommended.action,
                "filters" in recommended ? recommended.filters : undefined,
              )
            }
            className="shrink-0 rounded-lg bg-teal-500/12 dark:bg-teal-400/10 px-2.5 py-1.5 text-[0.65rem] font-semibold text-teal-700 dark:text-teal-400 hover:bg-teal-500/20 transition-colors"
          >
            {recommended.label}
          </button>
        </div>
        <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-3 lg:grid-cols-5">
          {[
            {
              label: "Health",
              value: health,
              sub: String(diagnostics?.health?.score ?? "n/a"),
            },
            {
              label: "Trace coverage",
              value: String(
                diagnostics?.trace_coverage?.coverage_status || "unknown",
              ),
              sub: `${fmt(traceCount)} traces`,
            },
            {
              label: "Trades",
              value: fmt(Number(run?.tradeCount ?? 0)),
              sub: `${fmt(totalDecisions)} decisions`,
            },
            {
              label: "Blocker",
              value: reasonLabel(blockerReason) || "none",
              sub: blocker ? `${fmt(Number(blocker.count ?? 0))} hits` : "none",
            },
            {
              label: "Parity",
              value:
                parity?.available === false
                  ? "unavailable"
                  : parity?.available
                    ? "available"
                    : "unknown",
            },
          ].map(({ label, value, sub }) => (
            <div
              key={label}
              className="rounded-lg bg-white/60 dark:bg-stone-900/50 px-2.5 py-2"
            >
              <p className="text-[0.58rem] font-semibold uppercase tracking-widest text-stone-400 dark:text-stone-500">
                {label}
              </p>
              <p className="text-[0.75rem] font-semibold text-stone-800 dark:text-stone-200 mt-0.5 truncate">
                {value}
              </p>
              {sub && (
                <p className="text-[0.6rem] text-stone-400 dark:text-stone-500">
                  {sub}
                </p>
              )}
            </div>
          ))}
        </div>
        <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-4 mt-1.5">
          {[
            {
              label: "Fallback",
              value: fmt(fallbackCount),
              sub: `${fmt(totalDecisions ? (fallbackCount * 100) / totalDecisions : 0, 1)}%`,
            },
            {
              label: "Low confidence",
              value: fmt(lowConfidenceCount),
              sub: `${fmt(totalDecisions ? (lowConfidenceCount * 100) / totalDecisions : 0, 1)}%`,
            },
            {
              label: "HTF missing",
              value: fmt(htfMissing),
              sub: htfRequested
                ? `${fmt((htfMissing * 100) / htfRequested, 1)}%`
                : "n/a",
            },
            { label: "Data errors", value: fmt(dataErrorCount) },
          ].map(({ label, value, sub }) => (
            <div
              key={label}
              className="rounded-lg bg-white/60 dark:bg-stone-900/50 px-2.5 py-2"
            >
              <p className="text-[0.58rem] font-semibold uppercase tracking-widest text-stone-400 dark:text-stone-500">
                {label}
              </p>
              <p className="text-[0.75rem] font-semibold text-stone-800 dark:text-stone-200 mt-0.5">
                {value}
              </p>
              {sub && (
                <p className="text-[0.6rem] text-stone-400 dark:text-stone-500">
                  {sub}
                </p>
              )}
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
}

function SimulationInsightRail({
  run,
  diagnostics,
  parity,
  onAction,
}: {
  run?: SimRun | null;
  diagnostics?: SimulationDiagnosticsResponse;
  parity?: SimulationParityReport;
  onAction: (
    action:
      | "trace"
      | "diagnostics"
      | "what-if"
      | "parity"
      | "exports"
      | "rerun",
    filters?: Partial<TraceFilters>,
  ) => void;
}) {
  const traceCount = Number(diagnostics?.trace_coverage?.trace_count ?? 0);
  const totalDecisions = Math.max(1, decisionCount(diagnostics));
  const fallbackCount = blockerCount(
    diagnostics,
    (r) => r.startsWith("analysis_fallback") || r.includes("fallback"),
  );
  const lowConfidenceCount = blockerCount(
    diagnostics,
    (r) => r === "low_confidence",
  );
  const directionalFiltered = Number(
    (
      diagnostics?.directional_but_filtered ??
      diagnostics?.directional_filtered_counts ??
      {}
    ).directional_total_filtered ?? 0,
  );
  const htfMissing = Number(run?.htfContextMissingCount ?? 0);
  const dataErrorCount = blockerCount(diagnostics, (r) =>
    r.includes("data_error"),
  );

  const actions: Array<{
    title: string;
    detail: string;
    cta: string;
    action:
      | "trace"
      | "diagnostics"
      | "what-if"
      | "parity"
      | "exports"
      | "rerun";
    filters?: Partial<TraceFilters>;
  }> = [];
  if (
    String(diagnostics?.health?.status || "").toUpperCase() === "UNKNOWN" &&
    traceCount === 0
  )
    actions.push({
      title: "Coverage is missing",
      detail: "This run cannot be fully trusted without decision traces.",
      cta: "Rerun with diagnostics",
      action: "rerun",
    });
  if (fallbackCount / totalDecisions > 0.25 || fallbackCount > 0)
    actions.push({
      title: "Fallback decisions detected",
      detail: "Analyzer fallback can dominate no-trade behavior.",
      cta: "Inspect fallback traces",
      action: "trace",
      filters: { fallbackOnly: true },
    });
  if (lowConfidenceCount > 0)
    actions.push({
      title: "Low confidence is blocking trades",
      detail:
        "Test whether a lower threshold would include more directional candidates.",
      cta: "Open What-If",
      action: "what-if",
    });
  if (directionalFiltered > 0)
    actions.push({
      title: "Directional decisions were filtered",
      detail: "The analyzer found direction but runtime rules blocked action.",
      cta: "Inspect filtered traces",
      action: "trace",
      filters: { reason: "engine_filtered" },
    });
  if (htfMissing > 0)
    actions.push({
      title: "HTF context is missing",
      detail: "Higher-timeframe gaps reduce scan parity confidence.",
      cta: "Open diagnostics",
      action: "diagnostics",
    });
  if (parity?.available === false)
    actions.push({
      title: "Parity is unavailable",
      detail: "Comparable normal scan data is required for parity.",
      cta: "Open parity steps",
      action: "parity",
    });
  if (dataErrorCount > 0)
    actions.push({
      title: "Data errors exist",
      detail: "Historical candle/cache availability should be inspected.",
      cta: "Inspect data-error traces",
      action: "trace",
      filters: { reason: "data_error", errorsOnly: true },
    });
  if (!actions.length)
    actions.push({
      title: "No dominant blocker",
      detail: "Start with diagnostics, then export the run package if needed.",
      cta: "Open diagnostics",
      action: "diagnostics",
    });

  return (
    <Card data-testid="simulation-insight-rail">
      <PanelHeader
        icon={Sparkles}
        title="Insights / next actions"
        subtitle="Recommended investigation path"
      />
      <div className="p-2 grid gap-1.5">
        {actions.slice(0, 5).map((item) => (
          <div
            key={`${item.title}-${item.cta}`}
            className="flex items-start justify-between gap-2 rounded-lg bg-stone-50 dark:bg-stone-950/40 px-2.5 py-2"
          >
            <div className="min-w-0">
              <p className="text-[0.7rem] font-semibold text-stone-800 dark:text-stone-200">
                {item.title}
              </p>
              <p className="text-[0.63rem] text-stone-400 dark:text-stone-500 mt-0.5">
                {item.detail}
              </p>
            </div>
            <button
              type="button"
              onClick={() => onAction(item.action, item.filters)}
              className="shrink-0 rounded-lg bg-white dark:bg-stone-800 border border-stone-900/8 dark:border-stone-100/8 px-2 py-1 text-[0.63rem] font-semibold text-teal-700 dark:text-teal-400 hover:bg-teal-50 dark:hover:bg-teal-950/30 transition-colors"
            >
              {item.cta}
            </button>
          </div>
        ))}
      </div>
    </Card>
  );
}

function SimulationHealthCard({
  diagnostics,
  run,
}: {
  diagnostics?: SimulationDiagnosticsResponse;
  run?: SimRun | null;
}) {
  const health = diagnostics?.health;
  const status = String(health?.status || "UNKNOWN").toUpperCase();
  const coverage = diagnostics?.trace_coverage;
  return (
    <div
      data-testid="simulation-health-card"
      className={`rounded-xl border p-3 ${healthBgClass(status)}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="text-[0.6rem] font-semibold uppercase tracking-widest opacity-70">
            Health
          </p>
          <p className="mt-0.5 text-xl font-semibold">{status}</p>
          <p className="text-[0.65rem] opacity-75">
            {health?.score != null
              ? `Score ${fmt(Number(health.score))} / 100`
              : "Score unavailable"}
          </p>
        </div>
        <div className="text-right text-[0.65rem]">
          <p>
            Trace coverage:{" "}
            <strong>{String(coverage?.coverage_status || "unknown")}</strong>
          </p>
          <p>{fmt(Number(coverage?.trace_count ?? 0))} traces</p>
          {run?.status === "STOPPED" && (
            <p className="mt-1 font-semibold text-rose-600 dark:text-rose-400">
              Force/stop status requires review
            </p>
          )}
        </div>
      </div>
      <div className="mt-2.5 grid gap-2 sm:grid-cols-2">
        <div>
          <p className="text-[0.6rem] font-semibold uppercase tracking-widest opacity-70 mb-1">
            Reasons
          </p>
          <ul className="list-disc pl-4 space-y-0.5">
            {(health?.reasons?.length
              ? health.reasons
              : ["no health details returned"]
            ).map((r) => (
              <li key={r} className="text-[0.65rem]">
                {r.replaceAll("_", " ")}
              </li>
            ))}
          </ul>
        </div>
        <div>
          <p className="text-[0.6rem] font-semibold uppercase tracking-widest opacity-70 mb-1">
            Recommended actions
          </p>
          <ul className="list-disc pl-4 space-y-0.5">
            {(health?.recommended_actions?.length
              ? health.recommended_actions
              : ["Rerun with diagnostics if trace coverage is missing."]
            ).map((a) => (
              <li key={a} className="text-[0.65rem]">
                {a}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}

// ─── trace table ──────────────────────────────────────────────────────────────

function SimulationTraceTable({
  traces,
  isLoading,
  isError,
  filters,
  onFiltersChange,
  onLoadMore,
  hasMore,
}: {
  traces: SimulationDecisionTrace[];
  isLoading: boolean;
  isError: boolean;
  filters: TraceFilters;
  onFiltersChange: (next: TraceFilters) => void;
  onLoadMore: () => void;
  hasMore: boolean;
}) {
  const [selectedTraceId, setSelectedTraceId] = useState<
    string | number | null
  >(null);
  const visible = filters.errorsOnly
    ? traces.filter(
        (r) => r.analysis_error || r.data_error || r.insufficient_history,
      )
    : traces;
  const selected = visible.find(
    (row, index) => (row.trace_id || row.id || index) === selectedTraceId,
  );
  const update = (patch: Partial<TraceFilters>) =>
    onFiltersChange({ ...filters, ...patch });

  const quickFilters: Array<{ label: string; patch: Partial<TraceFilters> }> = [
    {
      label: "All",
      patch: {
        reason: "",
        fallbackOnly: false,
        errorsOnly: false,
        direction: "",
      },
    },
    {
      label: "Actionable",
      patch: { reason: "actionable", fallbackOnly: false, errorsOnly: false },
    },
    {
      label: "No-trade",
      patch: { reason: "neutral", fallbackOnly: false, errorsOnly: false },
    },
    {
      label: "Directional filtered",
      patch: {
        reason: "engine_filtered",
        fallbackOnly: false,
        errorsOnly: false,
      },
    },
    {
      label: "Low confidence",
      patch: {
        reason: "low_confidence",
        fallbackOnly: false,
        errorsOnly: false,
      },
    },
    {
      label: "Fallback",
      patch: { reason: "", fallbackOnly: true, errorsOnly: false },
    },
    {
      label: "HTF missing",
      patch: {
        reason: "insufficient_htf_history",
        fallbackOnly: false,
        errorsOnly: false,
      },
    },
    {
      label: "Data errors",
      patch: { reason: "data_error", fallbackOnly: false, errorsOnly: true },
    },
  ];

  return (
    <div data-testid="simulation-trace-table" className="grid gap-2">
      {/* Quick filters */}
      <div
        className="flex flex-wrap gap-1 rounded-lg border border-stone-900/8 dark:border-stone-100/8 bg-stone-50 dark:bg-stone-950/40 p-1.5"
        aria-label="Trace quick filters"
      >
        {quickFilters.map((item) => (
          <button
            key={item.label}
            type="button"
            onClick={() => update(item.patch)}
            className="rounded-md px-2 py-1 text-[0.63rem] font-semibold text-stone-500 dark:text-stone-400 hover:bg-teal-50 dark:hover:bg-teal-950/30 hover:text-teal-700 dark:hover:text-teal-400 transition-colors"
          >
            {item.label}
          </button>
        ))}
      </div>

      {/* Advanced filters */}
      <div className="grid gap-1.5 rounded-lg border border-stone-900/8 dark:border-stone-100/8 bg-white dark:bg-stone-900 p-2 sm:grid-cols-2 lg:grid-cols-4">
        {(
          [
            ["symbol", "Symbol", "Trace symbol filter"],
            ["interval", "Interval", "Trace interval filter"],
            ["mode", "Mode", "Trace mode filter"],
            ["direction", "Direction", "Trace direction filter"],
            ["reason", "Reason", "Trace reason filter"],
            ["minConfidence", "Min conf", "Trace min confidence"],
            ["maxConfidence", "Max conf", "Trace max confidence"],
          ] as [keyof TraceFilters, string, string][]
        ).map(([key, placeholder, ariaLabel]) => (
          <input
            key={key}
            aria-label={ariaLabel}
            value={String(filters[key])}
            onChange={(e) =>
              update({
                [key]: ["symbol", "mode", "direction"].includes(key)
                  ? e.target.value.toUpperCase()
                  : e.target.value,
              } as Partial<TraceFilters>)
            }
            placeholder={placeholder}
            className="h-7 rounded-lg border border-stone-900/8 dark:border-stone-100/8 bg-stone-50 dark:bg-stone-950/40 px-2 text-[0.7rem] text-stone-800 dark:text-stone-200 placeholder:text-stone-400 outline-none focus:border-teal-500/40 focus:ring-2 focus:ring-teal-500/10"
          />
        ))}
        <div className="flex items-center gap-3 text-[0.7rem] text-stone-600 dark:text-stone-400 sm:col-span-2 lg:col-span-1">
          <label className="inline-flex items-center gap-1.5 cursor-pointer">
            <input
              type="checkbox"
              checked={filters.fallbackOnly}
              onChange={(e) => update({ fallbackOnly: e.target.checked })}
              className="rounded"
            />{" "}
            fallback only
          </label>
          <label className="inline-flex items-center gap-1.5 cursor-pointer">
            <input
              type="checkbox"
              checked={filters.errorsOnly}
              onChange={(e) => update({ errorsOnly: e.target.checked })}
              className="rounded"
            />{" "}
            errors only
          </label>
        </div>
      </div>

      {isLoading && (
        <p className="rounded-lg bg-stone-50 dark:bg-stone-950/40 p-3 text-[0.7rem] text-stone-400 dark:text-stone-500">
          Loading decision traces…
        </p>
      )}
      {isError && (
        <AlertBanner
          tone="bad"
          title="Trace load failed"
          message="Unable to fetch decision traces for this run."
        />
      )}
      {!isLoading && !isError && visible.length === 0 && (
        <EmptyState message="No decision traces matched this run/filter. Older runs may need rerun with diagnostics." />
      )}

      {visible.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-stone-900/8 dark:border-stone-100/8 bg-white dark:bg-stone-900">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-stone-900/8 dark:divide-stone-100/8 text-[0.7rem]">
              <thead className="bg-stone-50 dark:bg-stone-950/40 text-left">
                <tr>
                  {[
                    "Timestamp",
                    "Symbol",
                    "Interval",
                    "Mode",
                    "Direction",
                    "Confidence",
                    "Signal status",
                    "Runtime reason",
                    "Fallback",
                    "Summary",
                  ].map((h) => (
                    <th
                      key={h}
                      className="px-2.5 py-2 text-[0.58rem] font-semibold uppercase tracking-widest text-stone-400 dark:text-stone-500 whitespace-nowrap"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-900/8 dark:divide-stone-100/8">
                {visible.map((row, index) => (
                  <tr
                    key={row.trace_id || row.id || index}
                    onClick={() =>
                      setSelectedTraceId(row.trace_id || row.id || index)
                    }
                    className="cursor-pointer align-top hover:bg-stone-50 dark:hover:bg-stone-950/40"
                  >
                    <td className="whitespace-nowrap px-2.5 py-2 text-stone-400 dark:text-stone-500">
                      {String(row.timestamp || "--")}
                    </td>
                    <td className="px-2.5 py-2 font-semibold text-stone-800 dark:text-stone-200">
                      {row.symbol || "--"}
                    </td>
                    <td className="px-2.5 py-2 text-stone-500 dark:text-stone-400">
                      {row.interval || "--"}
                    </td>
                    <td className="px-2.5 py-2 text-stone-500 dark:text-stone-400">
                      {row.mode || "--"}
                    </td>
                    <td className="px-2.5 py-2">
                      <span
                        className={`rounded px-1.5 py-0.5 text-[0.58rem] font-bold ${row.direction === "BUY" ? "bg-teal-500/10 text-teal-700 dark:text-teal-400" : "bg-rose-500/10 text-rose-700 dark:text-rose-400"}`}
                      >
                        {row.direction || "--"}
                      </span>
                    </td>
                    <td className="px-2.5 py-2 tabular-nums text-stone-600 dark:text-stone-300">
                      {row.confidence == null
                        ? "--"
                        : `${fmt(Number(row.confidence), 1)}%`}
                    </td>
                    <td className="px-2.5 py-2 text-stone-500 dark:text-stone-400">
                      {row.signal_status || "--"}
                    </td>
                    <td className="px-2.5 py-2 text-stone-500 dark:text-stone-400">
                      {row.runtime_filter_reason ||
                        row.no_trade_reason ||
                        "actionable"}
                    </td>
                    <td className="px-2.5 py-2">
                      {row.fallback_used ? (
                        <span className="rounded bg-rose-500/10 px-1.5 py-0.5 text-[0.58rem] font-bold text-rose-600 dark:text-rose-400">
                          yes
                        </span>
                      ) : (
                        <span className="text-stone-300 dark:text-stone-600">
                          no
                        </span>
                      )}
                    </td>
                    <td className="min-w-[200px] px-2.5 py-2 text-stone-500 dark:text-stone-400">
                      {row.summary ||
                        row.fallback_reason ||
                        row.analysis_error ||
                        row.data_error ||
                        "--"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {selected && (
        <Card data-testid="simulation-trace-detail">
          <PanelHeader
            icon={FileJson}
            title="Trace detail"
            subtitle={`${selected.symbol || "--"} ${selected.interval || ""} ${selected.mode || ""}`}
          />
          <div className="p-3 grid gap-2 sm:grid-cols-2 text-[0.7rem]">
            {[
              ["Summary", selected.summary || "--"],
              [
                "No-trade reason",
                selected.no_trade_reason ||
                  selected.runtime_filter_reason ||
                  "--",
              ],
              ["Fallback reason", selected.fallback_reason || "--"],
              [
                "Selected action/head",
                `${selected.selected_action || "--"} / ${selected.selected_head || "--"}`,
              ],
              [
                "Entry / SL / TP",
                `${selected.entry_price ?? "--"} / ${selected.stop_loss ?? "--"} / ${selected.take_profit ?? "--"}`,
              ],
              [
                "Confidence raw/final",
                `${selected.confidence_raw ?? "--"} / ${selected.confidence_final ?? "--"}`,
              ],
            ].map(([label, value]) => (
              <div key={String(label)}>
                <p className="font-semibold text-stone-600 dark:text-stone-300">
                  {label}
                </p>
                <p className="text-stone-500 dark:text-stone-400 mt-0.5">
                  {String(value)}
                </p>
              </div>
            ))}
          </div>
          <pre className="mx-3 mb-3 max-h-40 overflow-auto rounded-lg bg-stone-50 dark:bg-stone-950/40 p-2.5 text-[0.63rem] text-stone-600 dark:text-stone-400">
            {JSON.stringify(
              {
                runtime_context: selected.runtime_context,
                snapshot_metadata: selected.snapshot_metadata,
                analyzer_metadata: selected.analyzer_metadata,
              },
              null,
              2,
            )}
          </pre>
        </Card>
      )}

      {hasMore && (
        <button
          type="button"
          onClick={onLoadMore}
          className="self-start rounded-lg border border-stone-900/8 dark:border-stone-100/8 bg-white dark:bg-stone-900 px-3 py-1.5 text-[0.7rem] font-semibold text-stone-600 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-950/40 transition-colors"
        >
          Load next page
        </button>
      )}
    </div>
  );
}

// ─── diagnostics panel ────────────────────────────────────────────────────────

function SimulationDiagnosticsPanel({
  diagnostics,
  onTraceFilter,
  onOpenWhatIf,
}: {
  diagnostics?: SimulationDiagnosticsResponse;
  onTraceFilter?: (filters: Partial<TraceFilters>) => void;
  onOpenWhatIf?: () => void;
}) {
  if (!diagnostics)
    return (
      <p className="rounded-lg bg-stone-50 dark:bg-stone-950/40 p-3 text-[0.7rem] text-stone-400">
        Loading diagnostics…
      </p>
    );

  const distribution = Object.entries(diagnostics.decision_distribution ?? {})
    .map(([key, count]) => ({ key, count: Number(count), percent: 0 }))
    .filter((r) => r.count > 0);
  const total = distribution.reduce((s, r) => s + r.count, 0) || 1;
  const topBlockers = diagnostics.top_blockers ?? [];
  const perSymbol =
    diagnostics.per_symbol_summary ?? diagnostics.per_symbol ?? [];
  const perMode = diagnostics.per_mode_summary ?? diagnostics.per_mode ?? [];
  const directional =
    diagnostics.directional_but_filtered ??
    diagnostics.directional_filtered_counts ??
    {};
  const blocker = primaryBlocker(diagnostics);
  const fallbackCount = blockerCount(
    diagnostics,
    (r) => r.startsWith("analysis_fallback") || r.includes("fallback"),
  );
  const lowConfidenceCount = blockerCount(
    diagnostics,
    (r) => r === "low_confidence",
  );
  const analysisErrors = blockerCount(diagnostics, (r) =>
    r.includes("analysis_error"),
  );
  const dataErrors = blockerCount(diagnostics, (r) => r.includes("data_error"));
  const duplicateOpen = blockerCount(
    diagnostics,
    (r) => r === "duplicate_open",
  );
  const engineFiltered = blockerCount(
    diagnostics,
    (r) => r === "engine_filtered",
  );
  const insufficientHistory = blockerCount(
    diagnostics,
    (r) => r === "insufficient_history",
  );
  const insufficientHtf = blockerCount(
    diagnostics,
    (r) => r === "insufficient_htf_history",
  );
  const htfDataError = blockerCount(diagnostics, (r) => r === "htf_data_error");
  const actionable = Number(
    (diagnostics.decision_distribution ?? {}).actionable ?? 0,
  );
  const filtered =
    lowConfidenceCount + duplicateOpen + engineFiltered + fallbackCount;
  const directionalTotal =
    Number(directional.directional_total_filtered ?? 0) + actionable;

  return (
    <div data-testid="simulation-diagnostics-panel" className="grid gap-3">
      {blocker && (
        <div className="rounded-lg border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/30 p-3 text-[0.7rem] text-amber-800 dark:text-amber-300">
          <p className="font-semibold">
            Main blocker: {reasonLabel(blocker.reason)}
          </p>
          <p className="mt-0.5 opacity-85">
            {fmt(Number(blocker.count ?? 0))} decisions ·{" "}
            {fmt(Number(blocker.percentage ?? 0), 1)}%. Click the blocker below
            to inspect matching traces.
          </p>
        </div>
      )}

      {/* Metric tiles */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {[
          {
            label: "Trace count",
            value: fmt(Number(diagnostics.trace_coverage?.trace_count ?? 0)),
            sub: String(
              diagnostics.trace_coverage?.coverage_status || "unknown",
            ),
          },
          {
            label: "Avg conf",
            value:
              diagnostics.confidence_summary?.avg_confidence == null
                ? "--"
                : `${fmt(Number(diagnostics.confidence_summary.avg_confidence), 1)}%`,
          },
          {
            label: "Below threshold",
            value: fmt(
              Number(
                diagnostics.confidence_summary?.below_threshold_count ?? 0,
              ),
            ),
          },
          {
            label: "Directional filtered",
            value: fmt(Number(directional.directional_total_filtered ?? 0)),
          },
        ].map(({ label, value, sub }) => (
          <div
            key={label}
            className="rounded-lg bg-stone-50 dark:bg-stone-950/40 border border-stone-900/8 dark:border-stone-100/8 px-3 py-2.5"
          >
            <p className="text-[0.58rem] font-semibold uppercase tracking-widest text-stone-400 dark:text-stone-500">
              {label}
            </p>
            <p className="text-sm font-semibold text-stone-800 dark:text-stone-200 mt-0.5">
              {value}
            </p>
            {sub && (
              <p className="text-[0.6rem] text-stone-400 dark:text-stone-500">
                {sub}
              </p>
            )}
          </div>
        ))}
      </div>

      {/* Decision funnel */}
      <Card>
        <PanelHeader
          icon={Workflow}
          title="Trade creation funnel"
          subtitle="Where replayed decisions narrowed into trades"
        />
        <div className="p-3">
          <div className="flex items-center gap-1.5 overflow-x-auto pb-1">
            {[
              ["Total decisions", fmt(total)],
              ["Directional", fmt(directionalTotal)],
              ["Filtered", fmt(filtered)],
              ["Actionable", fmt(actionable)],
              [
                "Opened trades",
                fmt(
                  perSymbol.reduce(
                    (s, r) => s + Number(r.executed_trade_count ?? 0),
                    0,
                  ),
                ),
              ],
            ].map(([label, value], i) => (
              <div key={String(label)} className="contents">
                {i > 0 && (
                  <span className="text-stone-300 dark:text-stone-600 shrink-0 text-xs">
                    ›
                  </span>
                )}
                <div
                  className={`shrink-0 rounded-lg px-3 py-2 text-center min-w-[80px] ${i === 4 ? "bg-teal-500/10 dark:bg-teal-400/10" : i === 2 ? "bg-rose-500/8 dark:bg-rose-400/8" : "bg-stone-50 dark:bg-stone-950/40"} border border-stone-900/8 dark:border-stone-100/8`}
                >
                  <p className="text-[0.58rem] font-semibold uppercase tracking-widest text-stone-400 dark:text-stone-500">
                    {String(label)}
                  </p>
                  <p
                    className={`text-sm font-semibold mt-0.5 ${i === 4 ? "text-teal-700 dark:text-teal-400" : i === 2 ? "text-rose-600 dark:text-rose-400" : "text-stone-800 dark:text-stone-200"}`}
                  >
                    {String(value)}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </Card>

      {/* 3-col analyzer / runtime / data quality */}
      <div className="grid gap-2 sm:grid-cols-3">
        {[
          {
            title: "Analyzer health",
            icon: OctagonX,
            rows: [
              {
                label: "Fallback",
                value: fmt(fallbackCount),
                onClick: () => onTraceFilter?.({ fallbackOnly: true }),
                hint: "inspect fallback traces",
              },
              { label: "Analysis errors", value: fmt(analysisErrors) },
              { label: "Data errors", value: fmt(dataErrors) },
            ],
          },
          {
            title: "Runtime filtering",
            icon: Workflow,
            rows: [
              {
                label: "Low confidence",
                value: fmt(lowConfidenceCount),
                onClick: () => {
                  onTraceFilter?.({ reason: "low_confidence" });
                  onOpenWhatIf?.();
                },
                hint: "test threshold",
              },
              { label: "Duplicate open", value: fmt(duplicateOpen) },
              { label: "Engine filtered", value: fmt(engineFiltered) },
            ],
          },
          {
            title: "Data quality",
            icon: Radar,
            rows: [
              {
                label: "Insufficient history",
                value: fmt(insufficientHistory),
              },
              { label: "Insufficient HTF", value: fmt(insufficientHtf) },
              { label: "HTF data error", value: fmt(htfDataError) },
            ],
          },
        ].map(({ title, icon: Icon, rows }) => (
          <Card key={title}>
            <PanelHeader icon={Icon} title={title} />
            <div className="p-2 grid gap-1">
              {rows.map((row) => (
                <div
                  key={row.label}
                  onClick={row.onClick}
                  className={`flex items-center justify-between px-2.5 py-2 rounded-lg bg-stone-50 dark:bg-stone-950/40 text-[0.7rem] ${row.onClick ? "cursor-pointer hover:bg-teal-50 dark:hover:bg-teal-950/30 transition-colors" : ""}`}
                >
                  <span className="text-stone-500 dark:text-stone-400">
                    {row.label}
                  </span>
                  <div className="text-right">
                    <span className="font-semibold text-stone-800 dark:text-stone-200 tabular-nums">
                      {row.value}
                    </span>
                    {row.hint && (
                      <p className="text-[0.58rem] text-teal-600 dark:text-teal-400">
                        {row.hint}
                      </p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </Card>
        ))}
      </div>

      {/* Decision distribution */}
      {distribution.length > 0 && (
        <Card>
          <PanelHeader icon={Workflow} title="Decision distribution" />
          <div className="p-3">
            <BreakdownList
              rows={distribution.map((r) => ({
                ...r,
                percent: (r.count * 100) / total,
              }))}
              color="bg-teal-500"
            />
          </div>
        </Card>
      )}

      {/* Confidence histogram */}
      <Card>
        <PanelHeader
          icon={TrendingUp}
          title="Confidence histogram"
          subtitle="Threshold bucket marked in amber"
        />
        <div className="p-3">
          <div className="flex items-end gap-1 h-24">
            {(diagnostics.confidence_histogram ?? []).map((bucket) => (
              <div
                key={bucket.bucket_start}
                className="flex flex-1 flex-col items-center gap-0.5"
              >
                <div
                  className={`w-full rounded-t min-h-[4px] ${bucket.threshold_in_bucket ? "bg-amber-400 dark:bg-amber-500" : "bg-teal-500/60 dark:bg-teal-400/50"}`}
                  style={{
                    height: `${Math.max(4, Number(bucket.count || 0) * 12)}px`,
                  }}
                  title={`${bucket.bucket_start}–${bucket.bucket_end}: ${bucket.count}`}
                />
                <span className="text-[0.55rem] text-stone-400 dark:text-stone-500">
                  {bucket.bucket_start}
                </span>
              </div>
            ))}
          </div>
          <p className="mt-1.5 text-[0.63rem] text-amber-600 dark:text-amber-400">
            Threshold marker highlighted in amber.
          </p>
        </div>
      </Card>

      {/* Top blockers + confidence summary */}
      <div className="grid gap-2 sm:grid-cols-2">
        <Card>
          <PanelHeader icon={OctagonX} title="Top blockers" />
          <div className="p-2 grid gap-1">
            {topBlockers.length ? (
              topBlockers.map((row) => (
                <button
                  type="button"
                  key={String(row.reason)}
                  onClick={() =>
                    onTraceFilter?.({ reason: String(row.reason || "") })
                  }
                  className="rounded-lg bg-stone-50 dark:bg-stone-950/40 px-2.5 py-2 text-left text-[0.7rem] hover:bg-teal-50 dark:hover:bg-teal-950/30 transition-colors"
                >
                  <div className="flex justify-between gap-2">
                    <span className="font-semibold text-stone-700 dark:text-stone-300">
                      {String(row.reason || "unknown").replaceAll("_", " ")}
                    </span>
                    <span className="text-stone-400 dark:text-stone-500 tabular-nums shrink-0">
                      {fmt(Number(row.count))} ·{" "}
                      {fmt(Number(row.percentage), 1)}%
                    </span>
                  </div>
                  <p className="mt-0.5 text-[0.63rem] text-stone-400 dark:text-stone-500">
                    {(row.affected_symbols ?? []).join(", ") || "all symbols"}
                  </p>
                </button>
              ))
            ) : (
              <p className="text-[0.7rem] text-stone-400 dark:text-stone-500 p-2">
                No blockers recorded.
              </p>
            )}
          </div>
        </Card>

        <Card>
          <PanelHeader icon={Sparkles} title="Confidence summary" />
          <div className="p-3 grid grid-cols-2 gap-2">
            {[
              {
                label: "Median",
                value:
                  diagnostics.confidence_summary?.median_confidence == null
                    ? "--"
                    : `${fmt(Number(diagnostics.confidence_summary.median_confidence), 1)}%`,
              },
              {
                label: "P10 / P90",
                value: `${fmt(Number(diagnostics.confidence_summary?.p10_confidence ?? 0), 1)} / ${fmt(Number(diagnostics.confidence_summary?.p90_confidence ?? 0), 1)}`,
              },
            ].map(({ label, value }) => (
              <div
                key={label}
                className="rounded-lg bg-stone-50 dark:bg-stone-950/40 border border-stone-900/8 dark:border-stone-100/8 px-2.5 py-2"
              >
                <p className="text-[0.58rem] font-semibold uppercase tracking-widest text-stone-400 dark:text-stone-500">
                  {label}
                </p>
                <p className="text-sm font-semibold text-stone-800 dark:text-stone-200 mt-0.5">
                  {value}
                </p>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* Per-symbol / per-mode */}
      <div className="grid gap-2 sm:grid-cols-2">
        {(
          [
            ["Per-symbol summary", perSymbol as JsonRecord[], "symbol"],
            ["Per-mode summary", perMode as JsonRecord[], "mode"],
          ] as [string, JsonRecord[], string][]
        ).map(([title, rows, primaryKey]) => (
          <Card key={title}>
            <PanelHeader
              icon={Radar}
              title={title}
              subtitle="Click to filter trace"
            />
            <div className="overflow-hidden">
              <table className="w-full text-[0.7rem]">
                <tbody className="divide-y divide-stone-900/8 dark:divide-stone-100/8">
                  {rows.slice(0, 6).map((row, idx) => (
                    <tr
                      key={String(row[primaryKey] ?? idx)}
                      onClick={() =>
                        onTraceFilter?.({
                          [primaryKey]: String(row[primaryKey] || ""),
                        })
                      }
                      className="cursor-pointer hover:bg-teal-50 dark:hover:bg-teal-950/30 transition-colors"
                    >
                      <td className="px-2.5 py-1.5 font-semibold text-stone-700 dark:text-stone-300">
                        {String(row[primaryKey] ?? "--")}
                      </td>
                      <td className="px-2.5 py-1.5 text-stone-400 dark:text-stone-500 tabular-nums">
                        {fmt(Number(row.decision_count ?? 0))} dec
                      </td>
                      <td className="px-2.5 py-1.5 text-stone-400 dark:text-stone-500 tabular-nums">
                        {fmt(Number(row.executed_trade_count ?? 0))} tr
                      </td>
                      <td
                        className={`px-2.5 py-1.5 tabular-nums font-semibold ${Number(row.total_pnl ?? 0) >= 0 ? "text-teal-600 dark:text-teal-400" : "text-rose-600 dark:text-rose-400"}`}
                      >
                        {fmtMoney(Number(row.total_pnl ?? 0))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!rows.length && (
                <p className="p-2.5 text-[0.7rem] text-stone-400 dark:text-stone-500">
                  No rows.
                </p>
              )}
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}

// ─── what-if panel ────────────────────────────────────────────────────────────

function SimulationWhatIfPanel({
  result,
  inputs,
  onInputsChange,
  isLoading,
  diagnostics,
  onTraceFilter,
}: {
  result?: SimulationWhatIfResponse;
  inputs: WhatIfInputs;
  onInputsChange: (next: WhatIfInputs) => void;
  isLoading: boolean;
  diagnostics?: SimulationDiagnosticsResponse;
  onTraceFilter?: (filters: Partial<TraceFilters>) => void;
}) {
  const update = (patch: Partial<WhatIfInputs>) =>
    onInputsChange({ ...inputs, ...patch });
  const lowConfidenceDominates =
    normalizeReason(primaryBlocker(diagnostics)?.reason) === "low_confidence";

  return (
    <div data-testid="simulation-what-if-panel" className="grid gap-3">
      <div className="rounded-lg border border-sky-200 dark:border-sky-800 bg-sky-50 dark:bg-sky-950/30 p-3 text-[0.7rem] text-sky-800 dark:text-sky-300">
        <p className="font-semibold mb-0.5">Why this matters</p>
        <p>
          What-if estimates how many directional candidates would become
          actionable under changed thresholds/cost assumptions without rerunning
          the engine.
        </p>
        {lowConfidenceDominates && (
          <p className="mt-1.5 rounded-lg bg-amber-100 dark:bg-amber-950/40 px-2.5 py-1.5 font-semibold text-amber-800 dark:text-amber-300">
            Low confidence is the primary blocker — test a lower confidence
            threshold first.
          </p>
        )}
      </div>

      <Card>
        <PanelHeader icon={Workflow} title="Scenario parameters" />
        <div className="p-3 grid gap-2 sm:grid-cols-3 lg:grid-cols-5">
          {(
            [
              ["minConfidence", "Min confidence"],
              ["feesBps", "Fees bps"],
              ["slippageBps", "Slippage bps"],
              ["maxHoldBars", "Max hold bars"],
              ["riskPerTrade", "Risk / trade"],
            ] as [keyof WhatIfInputs, string][]
          ).map(([key, label]) => (
            <label key={key} className="flex flex-col gap-1">
              <span className="text-[0.58rem] font-semibold uppercase tracking-widest text-stone-400 dark:text-stone-500">
                {label}
              </span>
              <input
                value={inputs[key]}
                onChange={(e) =>
                  update({ [key]: e.target.value } as Partial<WhatIfInputs>)
                }
                className="h-7 rounded-lg border border-stone-900/8 dark:border-stone-100/8 bg-stone-50 dark:bg-stone-950/40 px-2 text-[0.7rem] text-stone-800 dark:text-stone-200 outline-none focus:border-teal-500/40 focus:ring-2 focus:ring-teal-500/10"
              />
            </label>
          ))}
        </div>
      </Card>

      {isLoading && (
        <p className="text-[0.7rem] text-stone-400 dark:text-stone-500">
          Calculating approximate what-if…
        </p>
      )}
      {result?.available === false && (
        <AlertBanner
          tone="warning"
          title="What-if unavailable"
          message={
            result.reason || "No decision traces are available for this run."
          }
        />
      )}

      {result && result.available !== false && (
        <Card>
          <PanelHeader
            icon={Sparkles}
            title="Approximate what-if"
            subtitle={`estimate_type=${result.estimate_type || "unknown"}`}
          />
          <div className="p-3">
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {[
                {
                  label: "Current min",
                  value: `${fmt(Number(result.current_min_confidence ?? 0), 1)}%`,
                },
                {
                  label: "Hypothetical min",
                  value: `${fmt(Number(result.hypothetical_min_confidence ?? 0), 1)}%`,
                },
                {
                  label: "Current actionable",
                  value: fmt(Number(result.current_actionable_count ?? 0)),
                },
                {
                  label: "Hypothetical actionable",
                  value: fmt(Number(result.hypothetical_actionable_count ?? 0)),
                },
                {
                  label: "Additional candidates",
                  value: fmt(
                    Number(result.additional_directional_candidates ?? 0),
                  ),
                },
                {
                  label: "Cost bps",
                  value: fmt(
                    Number(result.fee_slippage_sensitivity?.combined_bps ?? 0),
                    1,
                  ),
                },
                {
                  label: "Max hold",
                  value: String(
                    result.max_hold_sensitivity?.max_hold_bars ?? "--",
                  ),
                },
                {
                  label: "Nominal risk",
                  value:
                    result.risk_per_trade_estimate?.total_nominal_risk == null
                      ? "--"
                      : fmt(
                          Number(
                            result.risk_per_trade_estimate.total_nominal_risk,
                          ),
                          2,
                        ),
                },
              ].map(({ label, value }) => (
                <div
                  key={label}
                  className="rounded-lg bg-stone-50 dark:bg-stone-950/40 border border-stone-900/8 dark:border-stone-100/8 px-2.5 py-2"
                >
                  <p className="text-[0.58rem] font-semibold uppercase tracking-widest text-stone-400 dark:text-stone-500">
                    {label}
                  </p>
                  <p className="text-sm font-semibold text-stone-800 dark:text-stone-200 mt-0.5 tabular-nums">
                    {value}
                  </p>
                </div>
              ))}
            </div>
            <div className="mt-2.5 flex flex-wrap gap-1.5 text-[0.7rem]">
              <span className="text-stone-500 dark:text-stone-400">
                Newly included symbols:
              </span>
              {(result.newly_included_symbols ?? []).length ? (
                result.newly_included_symbols?.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => onTraceFilter?.({ symbol: s })}
                    className="rounded bg-white dark:bg-stone-800 border border-stone-900/8 dark:border-stone-100/8 px-1.5 py-0.5 font-semibold text-teal-700 dark:text-teal-400"
                  >
                    {s}
                  </button>
                ))
              ) : (
                <span className="text-stone-400 dark:text-stone-500">none</span>
              )}
              <span className="text-stone-500 dark:text-stone-400 ml-1">
                Modes:
              </span>
              {(result.newly_included_modes ?? []).length ? (
                result.newly_included_modes?.map((m) => (
                  <button
                    key={m}
                    type="button"
                    onClick={() => onTraceFilter?.({ mode: m })}
                    className="rounded bg-white dark:bg-stone-800 border border-stone-900/8 dark:border-stone-100/8 px-1.5 py-0.5 font-semibold text-teal-700 dark:text-teal-400"
                  >
                    {m}
                  </button>
                ))
              ) : (
                <span className="text-stone-400 dark:text-stone-500">none</span>
              )}
            </div>
            <p className="mt-1.5 text-[0.63rem] text-amber-600 dark:text-amber-400">
              Approximate only: this does not rerun the simulation engine.
            </p>
          </div>
        </Card>
      )}
    </div>
  );
}

// ─── parity panel ─────────────────────────────────────────────────────────────

function SimulationParityPanel({
  parity,
}: {
  parity?: SimulationParityReport;
}) {
  if (!parity)
    return (
      <p className="rounded-lg bg-stone-50 dark:bg-stone-950/40 p-3 text-[0.7rem] text-stone-400">
        Loading parity report…
      </p>
    );
  return (
    <div data-testid="simulation-parity-panel" className="grid gap-3">
      {parity.available === false && (
        <div className="rounded-xl border border-sky-200 dark:border-sky-800 bg-sky-50 dark:bg-sky-950/30 p-3 text-[0.7rem] text-sky-800 dark:text-sky-300">
          <p className="font-semibold">No comparable scan data</p>
          <p className="mt-0.5">
            Reason: {parity.reason || "no_comparable_scan_data"}. Safe-empty
            parity is informational, not an error.
          </p>
          <div className="mt-2.5 rounded-lg bg-white/70 dark:bg-sky-950/40 p-2.5">
            <p className="font-semibold mb-1">How to make parity available</p>
            <ol className="list-decimal pl-4 space-y-0.5">
              <li>
                Run a normal scan over the same symbols, intervals, modes, and
                timestamp window.
              </li>
              <li>
                Use the same runtime profile, analyzer engine, and model version
                where possible.
              </li>
              <li>
                Reopen this parity report after comparable scan data exists.
              </li>
            </ol>
          </div>
        </div>
      )}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {[
          {
            label: "Compared",
            value: fmt(Number(parity.compared_decision_count ?? 0)),
          },
          {
            label: "Direction match",
            value:
              parity.direction_match_pct == null
                ? "--"
                : `${fmt(Number(parity.direction_match_pct), 1)}%`,
          },
          {
            label: "Actionability",
            value:
              parity.actionability_match_pct == null
                ? "--"
                : `${fmt(Number(parity.actionability_match_pct), 1)}%`,
          },
          {
            label: "Conf delta",
            value:
              parity.confidence_delta_avg == null
                ? "--"
                : fmt(Number(parity.confidence_delta_avg), 3),
          },
          {
            label: "Fallback delta",
            value:
              parity.fallback_rate_delta == null
                ? "--"
                : fmt(Number(parity.fallback_rate_delta), 3),
          },
          {
            label: "Reason match",
            value:
              parity.no_trade_reason_match_pct == null
                ? "--"
                : `${fmt(Number(parity.no_trade_reason_match_pct), 1)}%`,
          },
          {
            label: "Missing scan",
            value: fmt(Number(parity.missing_scan_context_count ?? 0)),
          },
          {
            label: "Missing sim",
            value: fmt(Number(parity.missing_sim_context_count ?? 0)),
          },
        ].map(({ label, value }) => (
          <div
            key={label}
            className="rounded-lg bg-stone-50 dark:bg-stone-950/40 border border-stone-900/8 dark:border-stone-100/8 px-2.5 py-2"
          >
            <p className="text-[0.58rem] font-semibold uppercase tracking-widest text-stone-400 dark:text-stone-500">
              {label}
            </p>
            <p className="text-sm font-semibold text-stone-800 dark:text-stone-200 mt-0.5 tabular-nums">
              {value}
            </p>
          </div>
        ))}
      </div>
      <Card>
        <PanelHeader
          icon={Workflow}
          title="Mismatches"
          subtitle="Appears when comparable scan rows exist"
        />
        <div className="p-3">
          {parity.mismatches?.length ? (
            <pre className="max-h-64 overflow-auto rounded-lg bg-stone-50 dark:bg-stone-950/40 p-2.5 text-[0.7rem] text-stone-600 dark:text-stone-400">
              {JSON.stringify(parity.mismatches, null, 2)}
            </pre>
          ) : (
            <p className="text-[0.7rem] text-stone-400 dark:text-stone-500">
              No mismatch rows returned.
            </p>
          )}
        </div>
      </Card>
    </div>
  );
}

// ─── summary + export panels ─────────────────────────────────────────────────

function SimulationPerformanceDiagnosticsPanel({ run }: { run: SimRun }) {
  const diagnostics = (run.performanceDiagnostics ?? {}) as JsonRecord;
  const buckets = Array.isArray(diagnostics.buckets) ? (diagnostics.buckets as JsonRecord[]) : [];
  const slowest = (diagnostics.slowest ?? {}) as Record<string, JsonRecord[]>;
  const topBuckets = buckets.slice(0, 8);
  const wallMs = numberFrom(diagnostics.wall_clock_ms);
  return (
    <Card>
      <PanelHeader icon={Clock3} title="Performance diagnostics" subtitle="Where simulation wall-clock time is going" />
      <div className="p-3">
        {!topBuckets.length ? (
          <p className="text-[0.7rem] text-stone-500 dark:text-stone-400">No timing data recorded for this run yet. Start a new simulation to collect component timings.</p>
        ) : (
          <div className="grid gap-3 lg:grid-cols-[1.2fr_1fr]">
            <div>
              <div className="mb-2 flex items-center justify-between text-[0.65rem] text-stone-500 dark:text-stone-400">
                <span>Wall clock: <span className="font-semibold text-stone-800 dark:text-stone-200">{fmt(wallMs / 1000, 2)}s</span></span>
                <span>{topBuckets.length} measured buckets</span>
              </div>
              <div className="space-y-2">
                {topBuckets.map((bucket) => {
                  const pct = Math.max(0, Math.min(100, numberFrom(bucket.pct_of_measured)));
                  return (
                    <div key={String(bucket.key)} className="rounded-lg border border-stone-900/8 bg-stone-50 p-2 dark:border-stone-100/8 dark:bg-stone-950/40">
                      <div className="flex items-center justify-between gap-2 text-[0.7rem]">
                        <span className="font-semibold text-stone-700 dark:text-stone-200">{String(bucket.key)}</span>
                        <span className="tabular-nums text-stone-500">{fmt(numberFrom(bucket.ms), 1)} ms · {fmt(pct, 1)}%</span>
                      </div>
                      <div className="mt-1 h-2 overflow-hidden rounded-full bg-stone-200 dark:bg-stone-800">
                        <div className="h-full rounded-full bg-teal-500" style={{ width: `${pct}%` }} />
                      </div>
                      <p className="mt-1 text-[0.62rem] text-stone-500">count {fmt(numberFrom(bucket.count), 0)} · avg {fmt(numberFrom(bucket.avg_ms), 2)} ms</p>
                    </div>
                  );
                })}
              </div>
            </div>
            <div className="rounded-lg border border-stone-900/8 bg-stone-50 p-3 dark:border-stone-100/8 dark:bg-stone-950/40">
              <p className="text-[0.65rem] font-bold uppercase tracking-widest text-stone-500">Slowest examples</p>
              <div className="mt-2 max-h-72 space-y-2 overflow-auto">
                {Object.entries(slowest).slice(0, 5).flatMap(([bucket, rows]) => (rows ?? []).slice(0, 3).map((row, index) => (
                  <div key={`${bucket}-${index}-${String(row.elapsed_ms)}`} className="rounded-md bg-white p-2 text-[0.65rem] text-stone-600 dark:bg-stone-900 dark:text-stone-300">
                    <div className="font-semibold text-stone-800 dark:text-stone-100">{bucket} · {fmt(numberFrom(row.elapsed_ms), 2)} ms</div>
                    <div className="mt-0.5 truncate">{[row.symbol, row.interval, row.mode, row.timestamp].filter(Boolean).join(' · ') || 'aggregate step'}</div>
                  </div>
                ))).slice(0, 12)}
              </div>
            </div>
          </div>
        )}
      </div>
    </Card>
  );
}

function SimulationSummaryPanel({ run, onAnalyzeFailures, analyzing }: { run: SimRun; onAnalyzeFailures: () => void; analyzing: boolean }) {
  const closed = run.trades.filter((trade) => trade.status === "CLOSED" && trade.pnl != null);
  const winners = closed.filter((trade) => Number(trade.pnl) > 0);
  const losers = closed.filter((trade) => Number(trade.pnl) < 0);
  const grossProfit = winners.reduce((sum, trade) => sum + Number(trade.pnl ?? 0), 0);
  const grossLoss = Math.abs(losers.reduce((sum, trade) => sum + Number(trade.pnl ?? 0), 0));
  const avgWin = winners.length ? grossProfit / winners.length : 0;
  const avgLoss = losers.length ? grossLoss / losers.length : 0;
  const profitFactor = grossLoss > 0 ? grossProfit / grossLoss : grossProfit > 0 ? Infinity : 0;
  const expectancy = closed.length ? (grossProfit - grossLoss) / closed.length : 0;
  const bestMode = run.perMode.length ? [...run.perMode].sort((a, b) => b.pnl - a.pnl)[0] : null;
  const worstMode = run.perMode.length ? [...run.perMode].sort((a, b) => a.pnl - b.pnl)[0] : null;
  const good = [
    run.totalPnl != null && run.totalPnl > 0 ? `Net positive: ${fmtMoney(run.totalPnl)}` : null,
    run.winRate != null && run.winRate >= 50 ? `Win rate held at ${fmt(run.winRate, 1)}%` : null,
    profitFactor >= 1.25 ? `Profit factor ${profitFactor === Infinity ? "∞" : fmt(profitFactor, 2)}` : null,
    bestMode && bestMode.pnl > 0 ? `${bestMode.mode} contributed ${fmtMoney(bestMode.pnl)}` : null,
  ].filter(Boolean);
  const bad = [
    run.totalPnl != null && run.totalPnl < 0 ? `Net loss: ${fmtMoney(run.totalPnl)}` : null,
    run.maxDrawdownPct != null && run.maxDrawdownPct > 10 ? `Drawdown reached ${fmt(run.maxDrawdownPct, 1)}%` : null,
    profitFactor > 0 && profitFactor < 1 ? `Profit factor below breakeven (${fmt(profitFactor, 2)})` : null,
    worstMode && worstMode.pnl < 0 ? `${worstMode.mode} lost ${fmtMoney(Math.abs(worstMode.pnl))}` : null,
    losers.length ? `${losers.length} losing trades ready for failure analysis` : null,
  ].filter(Boolean);

  return (
    <Card>
      <PanelHeader icon={Sparkles} title="Simulation summary" subtitle="What worked, what failed, and calculated edge" />
      <div className="grid gap-3 p-3 lg:grid-cols-[1.1fr_1fr_1fr]">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-2">
          {[
            ["Net P&L", run.totalPnl != null ? fmtMoney(run.totalPnl) : "--"],
            ["Win rate", run.winRate != null ? `${fmt(run.winRate, 1)}%` : "--"],
            ["Profit factor", profitFactor === Infinity ? "∞" : fmt(profitFactor, 2)],
            ["Expectancy", fmtMoney(expectancy)],
            ["Avg win", fmtMoney(avgWin)],
            ["Avg loss", fmtMoney(avgLoss)],
          ].map(([label, value]) => (
            <div key={label} className="rounded-lg bg-stone-50 p-2 dark:bg-stone-950/40">
              <p className="text-[0.58rem] uppercase tracking-widest text-stone-400">{label}</p>
              <p className="mt-1 text-sm font-semibold text-stone-800 dark:text-stone-100">{value}</p>
            </div>
          ))}
        </div>
        <div className="rounded-lg border border-teal-500/15 bg-teal-500/5 p-3">
          <p className="text-[0.65rem] font-bold uppercase tracking-widest text-teal-700 dark:text-teal-400">Good</p>
          <ul className="mt-2 space-y-1 text-[0.7rem] text-stone-600 dark:text-stone-300">
            {(good.length ? good : ["No strong positive edge detected yet."]).map((item) => <li key={String(item)}>• {item}</li>)}
          </ul>
        </div>
        <div className="rounded-lg border border-rose-500/15 bg-rose-500/5 p-3">
          <div className="flex items-center justify-between gap-2">
            <p className="text-[0.65rem] font-bold uppercase tracking-widest text-rose-700 dark:text-rose-400">Bad / failures</p>
            <div className="flex flex-wrap gap-1">
              <button type="button" onClick={onAnalyzeFailures} disabled={analyzing || losers.length === 0} className="rounded-md bg-rose-500/10 px-2 py-1 text-[0.62rem] font-semibold text-rose-700 transition hover:bg-rose-500/20 disabled:opacity-40 dark:text-rose-400">
                {analyzing ? "Sending…" : "Send failures to analyzer"}
              </button>
              <a href={`/failures?profile=simulation-${run.id}&lookback=3650&min_confidence=0`} className="rounded-md border border-rose-500/20 px-2 py-1 text-[0.62rem] font-semibold text-rose-700 hover:bg-rose-500/10 dark:text-rose-400">
                Open analysis
              </a>
            </div>
          </div>
          <ul className="mt-2 space-y-1 text-[0.7rem] text-stone-600 dark:text-stone-300">
            {(bad.length ? bad : ["No losing trades or obvious weakness detected."]).map((item) => <li key={String(item)}>• {item}</li>)}
          </ul>
        </div>
      </div>
    </Card>
  );
}

function SimulationExportPanel({ run }: { run: SimRun }) {
  const runId = run.id;
  const [target, setTarget] = useState("decision_traces");
  const [format, setFormat] = useState<"json" | "csv" | "jsonl">("json");
  const [advancedMode, setAdvancedMode] = useState("ALL");
  const [advancedDirection, setAdvancedDirection] = useState("ALL");
  const [advancedOutcome, setAdvancedOutcome] = useState("ALL");
  const targets = [
    "decision_traces",
    "trades",
    "diagnostics_summary",
    "confidence_histogram",
    "per_symbol_summary",
    "per_mode_summary",
    "skip_breakdown",
    "skip_samples",
    "parity_report",
  ];
  const filteredTrades = run.trades.filter((trade) => {
    const pnl = Number(trade.pnl ?? 0);
    return (advancedMode === "ALL" || trade.mode === advancedMode) &&
      (advancedDirection === "ALL" || trade.direction === advancedDirection) &&
      (advancedOutcome === "ALL" || (advancedOutcome === "FAILURES" ? pnl < 0 : advancedOutcome === "WINNERS" ? pnl > 0 : trade.status === advancedOutcome));
  });
  function downloadAdvancedTradeExport() {
    const rows = filteredTrades.map((trade) => ({
      run_id: runId,
      symbol: trade.symbol,
      mode: trade.mode,
      direction: trade.direction,
      interval: trade.interval,
      status: trade.status,
      confidence: trade.confidence,
      pnl: trade.pnl,
      pnl_pct: trade.pnlPct,
      hold_time_hours: trade.holdTimeHours,
      stop_reason: trade.stopReason ?? "",
      opened_at: trade.openedAt,
      closed_at: trade.closedAt ?? "",
    }));
    const suffix = [advancedOutcome, advancedMode, advancedDirection].filter((value) => value !== "ALL").join("-").toLowerCase() || "filtered";
	    if (format === "csv") downloadFile(exportAsCSV(rows), exportFilename(`simulation-${runId}-${suffix}-trades`, "csv"), "text/csv;charset=utf-8");
	    else downloadFile(format === "jsonl" ? rows.map((row) => JSON.stringify(row)).join("\n") : JSON.stringify(rows, null, 2), exportFilename(`simulation-${runId}-${suffix}-trades`, format === "jsonl" ? "json" : format), format === "jsonl" ? "application/x-ndjson" : "application/json");
    toast.success(`Advanced export downloaded (${rows.length} trades).`);
  }
  async function downloadExport() {
    const filename = `simulation-${runId}-${target}.${format}`;
    const payload = await fetchSimulationExport(runId, { target, format });
    downloadFile(
      typeof payload === "string" ? payload : JSON.stringify(payload, null, 2),
      filename,
      format === "csv"
        ? "text/csv;charset=utf-8"
        : format === "jsonl"
          ? "application/x-ndjson"
          : "application/json",
    );
    toast.success("Simulation export downloaded.");
  }
  return (
    <div data-testid="simulation-export-panel" className="grid gap-3">
      <Card>
        <PanelHeader
          icon={FileJson}
          title="Exports"
          subtitle="Backend exports are bounded by configured row limits"
        />
        <div className="p-3">
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              className="h-8 rounded-lg border border-stone-900/8 dark:border-stone-100/8 bg-stone-50 dark:bg-stone-950/40 px-2.5 text-[0.7rem] text-stone-800 dark:text-stone-200 outline-none"
            >
              {targets.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
            <select
              value={format}
              onChange={(e) =>
                setFormat(e.target.value as "json" | "csv" | "jsonl")
              }
              className="h-8 rounded-lg border border-stone-900/8 dark:border-stone-100/8 bg-stone-50 dark:bg-stone-950/40 px-2.5 text-[0.7rem] text-stone-800 dark:text-stone-200 outline-none"
            >
              <option value="json">json</option>
              <option value="csv">csv</option>
              <option value="jsonl">jsonl</option>
            </select>
            <button
              type="button"
              onClick={downloadExport}
              className="rounded-lg bg-teal-500/10 dark:bg-teal-400/10 px-3 py-1.5 text-[0.7rem] font-semibold text-teal-700 dark:text-teal-400 hover:bg-teal-500/20 transition-colors"
            >
              Download export
            </button>
            <a
              className="rounded-lg border border-stone-900/8 dark:border-stone-100/8 px-3 py-1.5 text-[0.7rem] font-semibold text-stone-600 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-950/40 transition-colors"
              href={simulationExportUrl(runId, { target, format })}
              target="_blank"
              rel="noreferrer"
            >
              Open endpoint
            </a>
          </div>
          <div className="mt-4 rounded-lg border border-stone-900/8 bg-stone-50 p-3 dark:border-stone-100/8 dark:bg-stone-950/40">
            <p className="mb-2 text-[0.65rem] font-bold uppercase tracking-widest text-stone-500">Advanced filtered trade export</p>
            <div className="flex flex-wrap items-center gap-2">
              <select value={advancedOutcome} onChange={(e) => setAdvancedOutcome(e.target.value)} className="h-8 rounded-lg border border-stone-900/8 dark:border-stone-100/8 bg-white dark:bg-stone-900 px-2.5 text-[0.7rem] text-stone-800 dark:text-stone-200 outline-none">
                <option value="ALL">all outcomes</option>
                <option value="FAILURES">failures only</option>
                <option value="WINNERS">winners only</option>
                <option value="CLOSED">closed</option>
                <option value="OPEN">open</option>
                <option value="STOPPED_OUT">stopped out</option>
              </select>
              <select value={advancedMode} onChange={(e) => setAdvancedMode(e.target.value)} className="h-8 rounded-lg border border-stone-900/8 dark:border-stone-100/8 bg-white dark:bg-stone-900 px-2.5 text-[0.7rem] text-stone-800 dark:text-stone-200 outline-none">
                <option value="ALL">all modes</option>
                {STRATEGY_MODE_OPTIONS.map((mode) => <option key={mode} value={mode}>{mode}</option>)}
              </select>
              <select value={advancedDirection} onChange={(e) => setAdvancedDirection(e.target.value)} className="h-8 rounded-lg border border-stone-900/8 dark:border-stone-100/8 bg-white dark:bg-stone-900 px-2.5 text-[0.7rem] text-stone-800 dark:text-stone-200 outline-none">
                <option value="ALL">all directions</option>
                <option value="BUY">longs</option>
                <option value="SELL">shorts</option>
              </select>
              <button type="button" onClick={downloadAdvancedTradeExport} className="rounded-lg bg-teal-500/10 px-3 py-1.5 text-[0.7rem] font-semibold text-teal-700 hover:bg-teal-500/20 dark:text-teal-400">
                Export {filteredTrades.length} matching trades
              </button>
              <span className="text-[0.65rem] text-stone-400">Example: failures + SCALP + shorts</span>
            </div>
          </div>
          <p className="mt-2.5 text-[0.65rem] text-stone-400 dark:text-stone-500">
            Backend exports are raw artifacts; advanced export filters the visible trade outcomes client-side.
          </p>
        </div>
      </Card>
    </div>
  );
}

// ─── main page ────────────────────────────────────────────────────────────────

export function SimulationsRoute() {
  const queryClient = useQueryClient();
  const { settings } = useSettings();
  const today = new Date();
  const monthAgo = new Date(today.getTime() - 30 * 24 * 60 * 60 * 1000);
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const [tradeQuery, setTradeQuery] = useState("");
  const [tradeFilter, setTradeFilter] = useState<
    "ALL" | "CLOSED" | "OPEN" | "STOPPED_OUT"
  >("ALL");
  const [tradeSortKey, setTradeSortKey] = useState<TradeSortKey>("pnl");
  const [tradeSortDesc, setTradeSortDesc] = useState(true);
  const [showAllSymbols, setShowAllSymbols] = useState(false);
  const [builderOpen, setBuilderOpen] = useState(false);
  const [periodStart, setPeriodStart] = useState(
    monthAgo.toISOString().slice(0, 10),
  );
  const [periodEnd, setPeriodEnd] = useState(today.toISOString().slice(0, 10));
  const [capital, setCapital] = useState("50000");
  const [selectedSymbols, setSelectedSymbols] = useState<string[]>([
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
  ]);
  const [selectedIntervals, setSelectedIntervals] = useState<string[]>([
    "1h",
    "4h",
  ]);
  const [selectedModes, setSelectedModes] = useState<string[]>([
    "SCALP",
    "SWING",
  ]);
  const [userPresets, setUserPresets] = useState<SimulationPreset[]>(() =>
    loadUserSimulationPresets(),
  );
  const [presetName, setPresetName] = useState("My simulation preset");
  const [userProfiles, setUserProfiles] = useState<SimulationProfile[]>(() =>
    loadUserSimulationProfiles(),
  );
  const [selectedProfileId, setSelectedProfileId] = useState("sim-balanced");
  const [profileDraft, setProfileDraft] = useState<SimulationProfile>(
    DEFAULT_SIMULATION_PROFILES[0],
  );
  const [detailTab, setDetailTab] = useState<SimulationDetailTab>("overview");
  const [traceFilters, setTraceFilters] = useState<TraceFilters>({
    symbol: "",
    interval: "",
    mode: "",
    direction: "",
    reason: "",
    minConfidence: "",
    maxConfidence: "",
    fallbackOnly: false,
    errorsOnly: false,
  });
  const [traceCursor, setTraceCursor] = useState<number | null>(null);
  const [whatIfInputs, setWhatIfInputs] = useState<WhatIfInputs>({
    minConfidence: "45",
    feesBps: "4",
    slippageBps: "2",
    maxHoldBars: "",
    riskPerTrade: "",
  });

  const symbolsQuery = useQuery({
    queryKey: ["symbols", "simulations-route"],
    queryFn: fetchSymbols,
    staleTime: 60_000,
  });
  const runtimeSettingsQuery = useQuery({
    queryKey: ["runtime-settings", "simulations-route"],
    queryFn: () => fetchRuntimeSettingsForScope(),
    staleTime: 60_000,
  });
  const runtimeSettingsMetadataQuery = useQuery({
    queryKey: ["runtime-settings-metadata", "simulations-route"],
    queryFn: () => fetchRuntimeSettingsMetadataForScope(),
    staleTime: 60_000,
  });
  const runtimeSettings = runtimeSettingsQuery.data ?? {};
  const runtimeSettingsDraftBase = useMemo(
    () => stringifySettings(runtimeSettings as Record<string, unknown>),
    [runtimeSettings],
  );

  const availableSymbols = useMemo(() => {
    const live = stringArray(symbolsQuery.data?.symbols);
    return uniqueStrings([
      ...(live.length ? live : []),
      ...splitCsv(runtimeSettings.AUTONOMOUS_SYMBOLS),
      "BTCUSDT",
      "ETHUSDT",
      "SOLUSDT",
    ]);
  }, [runtimeSettings.AUTONOMOUS_SYMBOLS, symbolsQuery.data?.symbols]);

  const availableIntervals = useMemo(
    () =>
      uniqueStrings([
        ...splitCsv(runtimeSettings.AUTONOMOUS_INTERVALS),
        ...INTERVAL_OPTION_CATALOG,
      ]),
    [runtimeSettings.AUTONOMOUS_INTERVALS],
  );
  const availableModes = useMemo(
    () =>
      uniqueStrings([
        ...splitCsv(runtimeSettings.AUTONOMOUS_MODES),
        ...STRATEGY_MODE_OPTIONS,
      ]),
    [runtimeSettings.AUTONOMOUS_MODES],
  );
  const allPresets = useMemo(
    () => [...BUILTIN_SIMULATION_PRESETS, ...userPresets],
    [userPresets],
  );
  const allSimulationProfiles = useMemo(
    () => [...DEFAULT_SIMULATION_PROFILES, ...userProfiles],
    [userProfiles],
  );

  const runsQuery = useQuery({
    queryKey: ["simulations"],
    queryFn: () => fetchSimulations(50),
    refetchInterval: (query) => {
      const rows = query.state.data?.runs ?? [];
      return rows.some((r) => simStatus(r.status) === "RUNNING") ? 5000 : false;
    },
  });

  const apiRuns = runsQuery.data?.runs ?? [];
  const listRuns = useMemo(() => {
    const mapped = apiRuns.map((r) => mapApiRunToSimRun(r));
    return mapped.length ? mapped : runsQuery.isError ? EXAMPLE_RUNS : [];
  }, [apiRuns, runsQuery.isError]);
  const previousRunImportOptions = useMemo(
    () => apiRuns.filter((item) => item.parameters),
    [apiRuns],
  );

  useEffect(() => {
    if (selectedRunId == null && listRuns.length > 0)
      setSelectedRunId(listRuns[0].id);
  }, [listRuns, selectedRunId]);

  const simulationEvents = useSimulationEventStream({
    runId: selectedRunId,
    enabled: selectedRunId != null,
  });

  const detailQuery = useQuery({
    queryKey: ["simulation", selectedRunId],
    queryFn: () => fetchSimulationRun(selectedRunId!),
    enabled: selectedRunId != null,
    refetchInterval: (query) => {
      const running = simStatus(query.state.data?.run?.status) === "RUNNING";
      const live = simulationEvents.connectionState === "open";
      return running && !live ? 3000 : false;
    },
    refetchOnWindowFocus: true,
  });

  useEffect(() => {
    setTraceCursor(null);
  }, [selectedRunId, traceFilters]);

  const traceQuery = useQuery({
    queryKey: [
      "simulation-decision-traces",
      selectedRunId,
      traceFilters,
      traceCursor,
    ],
    queryFn: () =>
      fetchSimulationDecisionTraces(selectedRunId!, {
        symbol: traceFilters.symbol || undefined,
        interval: traceFilters.interval || undefined,
        mode: traceFilters.mode || undefined,
        direction: traceFilters.direction || undefined,
        reason: traceFilters.reason || undefined,
        fallback_used: traceFilters.fallbackOnly ? true : undefined,
        min_confidence: traceFilters.minConfidence
          ? Number(traceFilters.minConfidence)
          : undefined,
        max_confidence: traceFilters.maxConfidence
          ? Number(traceFilters.maxConfidence)
          : undefined,
        cursor: traceCursor,
        limit: 250,
      }),
    enabled: selectedRunId != null && detailTab === "trace",
  });

  const diagnosticsQuery = useQuery({
    queryKey: ["simulation-diagnostics", selectedRunId],
    queryFn: () => fetchSimulationDiagnostics(selectedRunId!),
    enabled: selectedRunId != null,
  });
  const whatIfQuery = useQuery({
    queryKey: ["simulation-what-if", selectedRunId, whatIfInputs],
    queryFn: () =>
      fetchSimulationWhatIf(selectedRunId!, {
        min_confidence: whatIfInputs.minConfidence
          ? Number(whatIfInputs.minConfidence)
          : undefined,
        fees_bps: whatIfInputs.feesBps
          ? Number(whatIfInputs.feesBps)
          : undefined,
        slippage_bps: whatIfInputs.slippageBps
          ? Number(whatIfInputs.slippageBps)
          : undefined,
        max_hold_bars: whatIfInputs.maxHoldBars
          ? Number(whatIfInputs.maxHoldBars)
          : undefined,
        risk_per_trade: whatIfInputs.riskPerTrade
          ? Number(whatIfInputs.riskPerTrade)
          : undefined,
      }),
    enabled: selectedRunId != null && detailTab === "what-if",
  });
  const parityQuery = useQuery({
    queryKey: ["simulation-parity", selectedRunId],
    queryFn: () => fetchSimulationParityReport(selectedRunId!),
    enabled: selectedRunId != null,
  });

  useEffect(() => {
    const payload = simulationEvents.latestEvent;
    if (selectedRunId == null || !payload) return;
    if (payload.run) {
      queryClient.setQueryData(
        ["simulation", selectedRunId],
        (
          current:
            | {
                ok?: boolean;
                run?: SimulationRun;
                results?: SimulationResult[];
              }
            | undefined,
        ) => ({
          ok: true,
          run: payload.run,
          results: payload.results ?? current?.results ?? [],
        }),
      );
      queryClient.setQueryData(
        ["simulations"],
        (
          current:
            | { ok?: boolean; runs?: SimulationRun[]; summary?: JsonRecord }
            | undefined,
        ) => {
          if (!current?.runs) return current;
          return {
            ...current,
            runs: current.runs.map((row) =>
              Number(row.id) === selectedRunId ? payload.run! : row,
            ),
          };
        },
      );
    }
    if (
      ["completed", "failed", "stopped", "stop_requested"].includes(
        String(payload.type),
      )
    ) {
      void queryClient.invalidateQueries({ queryKey: ["simulations"] });
      void queryClient.invalidateQueries({
        queryKey: ["simulation", selectedRunId],
      });
      void queryClient.invalidateQueries({
        queryKey: ["simulation-diagnostics", selectedRunId],
      });
      void queryClient.invalidateQueries({
        queryKey: ["simulation-decision-traces", selectedRunId],
      });
    }
  }, [queryClient, selectedRunId, simulationEvents.latestEvent]);

  const createMutation = useMutation({
    mutationFn: createSimulation,
    onSuccess: async (payload) => {
      toast.success("Simulation queued");
      await queryClient.invalidateQueries({ queryKey: ["simulations"] });
      const id = Number(payload.run?.id);
      if (Number.isFinite(id)) setSelectedRunId(id);
      setBuilderOpen(false);
    },
    onError: (error) =>
      toast.error("Failed to start simulation", {
        description: error instanceof Error ? error.message : "Unknown error",
      }),
  });

  const stopMutation = useMutation({
    mutationFn: stopSimulation,
    onSuccess: async () => {
      toast.success("Stop requested");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["simulations"] }),
        queryClient.invalidateQueries({
          queryKey: ["simulation", selectedRunId],
        }),
      ]);
    },
    onError: (error) =>
      toast.error("Failed to stop simulation", {
        description: error instanceof Error ? error.message : "Unknown error",
      }),
  });

  const failureAnalysisMutation = useMutation({
    mutationFn: (runId: number) => submitSimulationFailureAnalysis(runId, { persist: true }),
    onSuccess: (payload) => {
      const count = Number((payload.summary as JsonRecord | undefined)?.total ?? 0);
      toast.success("Simulation failures sent to failure analyzer", { description: `${fmt(count, 0)} failures classified under ${String(payload.profile_id ?? "simulation profile")}.` });
    },
    onError: (error) => toast.error("Failure analysis failed", { description: error instanceof Error ? error.message : "Unknown error" }),
  });

  const forceStopMutation = useMutation({
    mutationFn: forceStopSimulation,
    onSuccess: async (payload) => {
      toast.success("Simulation force-stopped");
      if (payload.run?.id != null) {
        const forcedId = Number(payload.run.id);
        queryClient.setQueryData(
          ["simulation", forcedId],
          (
            current:
              | {
                  ok?: boolean;
                  run?: SimulationRun;
                  results?: SimulationResult[];
                }
              | undefined,
          ) => ({
            ok: true,
            run: payload.run,
            results: current?.results ?? [],
          }),
        );
        queryClient.setQueryData(
          ["simulations"],
          (
            current:
              | { ok?: boolean; runs?: SimulationRun[]; summary?: JsonRecord }
              | undefined,
          ) => {
            if (!current?.runs) return current;
            return {
              ...current,
              runs: current.runs.map((row) =>
                Number(row.id) === forcedId ? payload.run! : row,
              ),
            };
          },
        );
      }
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["simulations"] }),
        queryClient.invalidateQueries({
          queryKey: ["simulation", selectedRunId],
        }),
      ]);
    },
    onError: (error) =>
      toast.error("Failed to force-stop simulation", {
        description: error instanceof Error ? error.message : "Unknown error",
      }),
  });

  const run = useMemo(() => {
    if (detailQuery.data?.run)
      return mapApiRunToSimRun(
        detailQuery.data.run,
        detailQuery.data.results ?? [],
      );
    return listRuns.find((r) => r.id === selectedRunId) ?? listRuns[0] ?? null;
  }, [detailQuery.data, listRuns, selectedRunId]);

  const skipFamilySummary = useMemo(
    () => skipFamilyRows(run?.skipBreakdown ?? []),
    [run?.skipBreakdown],
  );
  const skipDiagnostic = useMemo(
    () => (run ? simulationSkipDiagnostic(run) : null),
    [run],
  );

  const filteredTrades = useMemo(() => {
    const term = tradeQuery.trim().toUpperCase();
    if (!run) return [];
    return run.trades.filter((t) => {
      const matchQ =
        !term ||
        t.symbol.includes(term) ||
        t.mode.includes(term) ||
        t.direction.includes(term);
      const matchF = tradeFilter === "ALL" ? true : t.status === tradeFilter;
      return matchQ && matchF;
    });
  }, [run, tradeQuery, tradeFilter]);

  const sortedTrades = useMemo(() => {
    const rows = [...filteredTrades];
    rows.sort((a, b) => {
      let r = 0;
      switch (tradeSortKey) {
        case "symbol":
          r = a.symbol.localeCompare(b.symbol);
          break;
        case "mode":
          r = a.mode.localeCompare(b.mode);
          break;
        case "direction":
          r = a.direction.localeCompare(b.direction);
          break;
        case "pnl":
          r = (a.pnl ?? -Infinity) - (b.pnl ?? -Infinity);
          break;
        case "confidence":
          r = a.confidence - b.confidence;
          break;
        case "hold_time":
          r = (a.holdTimeHours ?? -Infinity) - (b.holdTimeHours ?? -Infinity);
          break;
        case "status":
          r = a.status.localeCompare(b.status);
          break;
      }
      return tradeSortDesc ? -r : r;
    });
    return rows;
  }, [filteredTrades, tradeSortKey, tradeSortDesc]);

  function handleSort(key: TradeSortKey) {
    if (tradeSortKey === key) setTradeSortDesc((d) => !d);
    else {
      setTradeSortKey(key);
      setTradeSortDesc(key === "pnl" || key === "confidence");
    }
  }

  useEffect(() => {
    const selected =
      allSimulationProfiles.find((p) => p.id === selectedProfileId) ??
      allSimulationProfiles[0];
    if (selected) setProfileDraft(profileWithSettings(selected, runtimeSettingsDraftBase));
  }, [allSimulationProfiles, runtimeSettingsDraftBase, selectedProfileId]);

  function applyPreset(preset: SimulationPreset) {
    const days =
      preset.period === "7d"
        ? 7
        : preset.period === "30d"
          ? 30
          : preset.period === "90d"
            ? 90
            : 30;
    if (preset.period !== "custom") {
      setPeriodStart(dateDaysAgo(days));
      setPeriodEnd(new Date().toISOString().slice(0, 10));
    }
    setCapital(String(preset.capital));
    setSelectedSymbols(uniqueStrings(preset.symbols));
    setSelectedIntervals(uniqueStrings(preset.intervals));
    setSelectedModes(uniqueStrings(preset.modes));
    setPresetName(preset.name);
    if (
      preset.profileId &&
      allSimulationProfiles.some((p) => p.id === preset.profileId)
    )
      setSelectedProfileId(preset.profileId!);
  }

  function savePreset() {
    const name = presetName.trim();
    if (!name) {
      toast.error("Preset name is required.");
      return;
    }
    const preset: SimulationPreset = {
      id: `user-${name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`,
      name,
      period: "custom",
      capital: Number(capital) || 50_000,
      symbols: selectedSymbols,
      intervals: selectedIntervals,
      modes: selectedModes,
      profileId: selectedProfileId,
    };
    const next = [...userPresets.filter((p) => p.id !== preset.id), preset];
    setUserPresets(next);
    saveUserSimulationPresets(next);
    toast.success("Simulation preset saved.");
  }

  function deletePreset(id: string) {
    const next = userPresets.filter((p) => p.id !== id);
    setUserPresets(next);
    saveUserSimulationPresets(next);
    toast.success("Simulation preset deleted.");
  }

  function saveSimulationProfile() {
    const id = profileDraft.id.startsWith("user-")
      ? profileDraft.id
      : `user-${profileDraft.name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
    const profile = profileWithSettings({ ...profileDraft, id, tag: "simulation-profile" as const }, runtimeSettingsDraftBase);
    const next = [...userProfiles.filter((p) => p.id !== id), profile];
    setUserProfiles(next);
    saveUserSimulationProfiles(next);
    setSelectedProfileId(id);
    toast.success("Simulation profile saved.");
  }

  function updateProfileSettings(settings: Record<string, string>) {
    setProfileDraft((current) => profileFromSettings(current, settings));
  }

  function importRuntimeIntoProfile() {
    updateProfileSettings(runtimeSettingsDraftBase);
    toast.success("Current runtime settings imported into simulation profile draft.");
  }

  function importPreviousRunConfig(runId: number) {
    const previous = apiRuns.find((item) => Number(item.id) === runId);
    const params = (previous?.parameters ?? {}) as JsonRecord;
    const previousProfile = (params.simulation_profile ?? {}) as Partial<SimulationProfile> & JsonRecord;
    const previousSettings = stringifySettings((previousProfile.settings ?? params.execution_settings ?? {}) as Record<string, unknown>);
    if (Object.keys(previousSettings).length === 0) {
      toast.error("That simulation did not include importable config.");
      return;
    }
    updateProfileSettings({ ...runtimeSettingsDraftBase, ...previousSettings });
    if (params.capital != null) setCapital(String(params.capital));
    if (Array.isArray(params.symbols)) setSelectedSymbols(uniqueStrings(params.symbols.map(String)));
    if (Array.isArray(params.intervals)) setSelectedIntervals(uniqueStrings(params.intervals.map(String)));
    if (Array.isArray(params.modes)) setSelectedModes(uniqueStrings(params.modes.map(String)));
    toast.success(`Imported config from simulation #${runId}.`);
  }

  function deleteSimulationProfile(id: string) {
    const next = userProfiles.filter((p) => p.id !== id);
    setUserProfiles(next);
    saveUserSimulationProfiles(next);
    setSelectedProfileId("sim-balanced");
    toast.success("Simulation profile deleted.");
  }

  function buildSimulationPayload(
    overrides: Partial<Parameters<typeof createSimulation>[0]> = {},
  ) {
    const symbols = selectedSymbols.map((s) => s.toUpperCase());
    const intervals = selectedIntervals;
    const modes = selectedModes.map((m) => m.toUpperCase());
    const resolved = simulationRuntimeValues(profileDraft, runtimeSettingsDraftBase);
    const profile = profileWithSettings(profileDraft, runtimeSettingsDraftBase);
    return {
      requested_by: "interface",
      period_start: periodStart,
      period_end: periodEnd,
      symbols,
      intervals,
      modes,
      capital: Number(capital),
      risk_per_trade_pct: resolved.riskPerTradePct,
      min_confidence: resolved.minConfidence,
      max_hold_bars: resolved.maxHoldBars || null,
      scan_step_bars: resolved.scanStepBars,
      scan_workers: resolved.scanWorkers,
      time_forward_step_bars: resolved.timeForwardStepBars,
      simulation_profile_id: profile.id,
      simulation_profile: profile as unknown as JsonRecord,
      execution_settings: {
        ...resolved.settings,
        risk_per_trade_pct: resolved.riskPerTradePct,
        min_confidence: resolved.minConfidence,
        max_hold_bars: resolved.maxHoldBars || null,
        fee_bps: resolved.feeBps,
        slippage_bps: resolved.slippageBps,
        scan_step_bars: resolved.scanStepBars,
        scan_workers: resolved.scanWorkers,
        time_forward_step_bars: resolved.timeForwardStepBars,
        record_htf_availability: firstSetting(resolved.settings, ["SIMULATION_RECORD_HTF_AVAILABILITY", "record_htf_availability"], "true"),
        require_htf_context: firstSetting(resolved.settings, ["SIMULATION_REQUIRE_HTF_CONTEXT", "require_htf_context"], "false"),
      },
      name: `${modes.join("+")} ${periodStart} → ${periodEnd}`,
      ...overrides,
    };
  }

  function startSimulation() {
    const symbols = selectedSymbols.map((s) => s.toUpperCase());
    const intervals = selectedIntervals;
    const modes = selectedModes.map((m) => m.toUpperCase());
    const resolvedCapital = Number(capital);
    if (!periodStart || !periodEnd || periodEnd <= periodStart) {
      toast.error("Choose a valid historical period.");
      return;
    }
    if (!symbols.length || !intervals.length || !modes.length) {
      toast.error("Symbols, intervals, and modes are required.");
      return;
    }
    if (!Number.isFinite(resolvedCapital) || resolvedCapital <= 0) {
      toast.error("Initial capital must be greater than zero.");
      return;
    }
    createMutation.mutate(buildSimulationPayload({ capital: resolvedCapital }));
  }

  function rerunWithDiagnostics() {
    if (!detailQuery.data?.run) return;
    const params = (detailQuery.data.run.parameters ?? {}) as JsonRecord;
    const executionSettings = (params.execution_settings ?? {}) as JsonRecord;
    createMutation.mutate({
      ...(params as Parameters<typeof createSimulation>[0]),
      requested_by: "interface",
      name: `Diagnostic rerun of #${detailQuery.data.run.id}`,
      execution_settings: {
        ...executionSettings,
        record_htf_availability: true,
        require_htf_context: executionSettings.require_htf_context ?? false,
      },
    });
  }

  function openTraceWithFilters(filters: Partial<TraceFilters>) {
    setTraceFilters((current) => ({ ...current, ...filters }));
    setTraceCursor(null);
    setDetailTab("trace");
  }

  function handleInsightAction(
    action:
      | "trace"
      | "diagnostics"
      | "what-if"
      | "parity"
      | "exports"
      | "rerun",
    filters?: Partial<TraceFilters>,
  ) {
    if (action === "rerun") {
      rerunWithDiagnostics();
      return;
    }
    if (action === "trace") {
      openTraceWithFilters(filters ?? {});
      return;
    }
    setDetailTab(action);
  }

  async function copyRunDetails() {
    if (!run) return;
    await copyToClipboard(JSON.stringify({ run, trades: run.trades }, null, 2));
    toast.success("Simulation details copied.");
  }
  function exportRunJson() {
    if (!run) return;
    downloadFile(
      JSON.stringify({ run, trades: run.trades }, null, 2),
      exportFilename(`simulation-${run.id}`, "json"),
      "application/json",
    );
    toast.success("Simulation JSON downloaded.");
  }
  function exportTradesCsv() {
    if (!run?.trades.length) {
      toast.error("No trades to export.");
      return;
    }
    downloadFile(
      exportAsCSV(run.trades as unknown as JsonRecord[]),
      exportFilename(`simulation-${run.id}-trades`, "csv"),
      "text/csv;charset=utf-8",
    );
    toast.success("Simulation CSV downloaded.");
  }

  const oldRunMissingTraces = diagnosticHasMissingTraceCoverage(
    diagnosticsQuery.data,
    undefined,
    run,
  );
  const traceRows = traceQuery.data?.items ?? [];
  const runningCount = listRuns.filter((r) => r.status === "RUNNING").length;
  const completedCount = listRuns.filter(
    (r) => r.status === "COMPLETED",
  ).length;
  const failedStoppedCount = listRuns.filter((r) =>
    ["FAILED", "STOPPED"].includes(r.status),
  ).length;
  const resolvedProfileRuntime = useMemo(
    () => simulationRuntimeValues(profileDraft, runtimeSettingsDraftBase),
    [profileDraft, runtimeSettingsDraftBase],
  );
  const darkMode = settings.theme === "dark";
  const shellBg = darkMode
    ? "bg-slate-950 text-slate-100"
    : "bg-stone-100 text-stone-900";
  const cardBg = darkMode ? "bg-slate-900/88" : "bg-white/84";
  const paneBg = darkMode ? "bg-slate-900/72" : "bg-white/70";
  const canvasBg = darkMode ? "bg-slate-950/55" : "bg-stone-50";
  const subtleBorder = darkMode ? "border-white/10" : "border-stone-900/8";
  const mutedText = darkMode ? "text-slate-400" : "text-stone-500";
  const strongText = darkMode ? "text-slate-100" : "text-stone-950";

  // ─── tab content for col 3 ──────────────────────────────────────────────────

  const TABS: [SimulationDetailTab, string][] = [
    ["overview", "Overview"],
    ["trace", "Decision trace"],
    ["diagnostics", "Diagnostics"],
    ["what-if", "What-If"],
    ["health", "Health"],
    ["parity", "Parity"],
    ["exports", "Exports"],
  ];

  return (
    <AnimatedRoute>
      {/* ─── page shell: flex column, fills viewport ─── */}
      <div className={`flex min-h-screen flex-col gap-4 overflow-y-auto p-3 ${shellBg}`}>
        {/* ══ TOPBAR ══════════════════════════════════════════════════════════ */}
        <motion.header
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
          className={`flex flex-shrink-0 flex-wrap items-center gap-3 rounded-[1.8rem] border px-6 py-4 shadow-[0_18px_40px_rgba(77,62,40,0.08)] ${subtleBorder} ${cardBg}`}
        >
          {/* Identity */}
          <div className="flex items-center gap-2.5">
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-teal-500/12 dark:bg-teal-400/10">
              <FlaskConical
                className="h-3.5 w-3.5 text-teal-600 dark:text-teal-400"
                strokeWidth={1.8}
              />
            </div>
            <div>
              <h1 className={`text-sm font-bold tracking-tight leading-tight ${strongText}`}> 
                Backtesting & Simulations
              </h1>
              <p className={`hidden text-xs sm:block ${mutedText}`}> 
                Run engine over history · replay scans · forward-settle trades
              </p>
            </div>
          </div>

          {/* Stat pills */}
          <div className="flex gap-0 ml-2 overflow-hidden rounded-lg border border-stone-900/8 dark:border-stone-100/8">
            {(
              [
                ["Total", listRuns.length, ""],
                ["Running", runningCount, "text-amber-600 dark:text-amber-400"],
                [
                  "Completed",
                  completedCount,
                  "text-teal-600 dark:text-teal-400",
                ],
                [
                  "Failed/Stopped",
                  failedStoppedCount,
                  "text-rose-600 dark:text-rose-400",
                ],
              ] as [string, number, string][]
            ).map(([label, value, cls], i) => (
              <div
                key={label}
                className={`flex items-center gap-1.5 px-3 py-1.5 text-[0.65rem] bg-white dark:bg-stone-900 ${i > 0 ? "border-l border-stone-900/8 dark:border-stone-100/8" : ""}`}
              >
                <span className="text-stone-400 dark:text-stone-500">
                  {label}
                </span>
                <span
                  className={`font-semibold tabular-nums ${cls || "text-stone-700 dark:text-stone-300"}`}
                >
                  {value}
                </span>
              </div>
            ))}
          </div>

          {/* New simulation */}
          <button
            type="button"
            onClick={() => setBuilderOpen((o) => !o)}
            className="ml-auto flex items-center gap-1.5 rounded-lg bg-teal-500 hover:bg-teal-600 dark:bg-teal-600 dark:hover:bg-teal-500 px-3 py-1.5 text-[0.7rem] font-semibold text-white transition-colors shadow-sm"
          >
            <Play className="h-3 w-3" strokeWidth={2} />
            New simulation
          </button>
        </motion.header>

        {/* ══ MAIN 3-COL BODY ════════════════════════════════════════════════ */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.24, delay: 0.04, ease: [0.22, 1, 0.36, 1] }}
          className={`flex min-h-0 flex-1 gap-0 overflow-hidden rounded-[1.8rem] border shadow-[0_18px_40px_rgba(77,62,40,0.08)] ${subtleBorder} ${canvasBg}`}
        >
          {/* ── COL 1: Run list (fixed 196px) ─────────────────────────────── */}
          <aside className={`flex w-[196px] shrink-0 flex-col border-r ${subtleBorder} ${paneBg}`}> 
            <div className="flex items-center justify-between px-3 py-2 border-b border-stone-900/8 dark:border-stone-100/8 shrink-0">
              <span className="text-[0.6rem] font-semibold uppercase tracking-widest text-stone-400 dark:text-stone-500">
                Runs
              </span>
              <span className="rounded-full bg-stone-100 dark:bg-stone-800 px-2 py-0.5 text-[0.6rem] font-semibold text-stone-500 dark:text-stone-400">
                {listRuns.length}
              </span>
            </div>
            <div className="flex-1 overflow-y-auto p-1.5 min-h-0">
              {runsQuery.isLoading && (
                <p className="p-3 text-[0.65rem] text-stone-400 dark:text-stone-500">
                  Loading…
                </p>
              )}
              {!runsQuery.isLoading && listRuns.length === 0 && (
                <p className="p-3 text-[0.65rem] text-stone-400 dark:text-stone-500">
                  No simulations yet.
                </p>
              )}
              {listRuns.map((r) => {
                const active = r.id === selectedRunId;
                return (
                  <motion.button
                    key={r.id}
                    type="button"
                    layout
                    initial={{ opacity: 0, x: -6 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
                    onClick={() => {
                      setSelectedRunId(r.id);
                      setShowAllSymbols(false);
                    }}
                    className={`w-full rounded-xl border-l-2 px-2.5 py-2 text-left mb-1 transition-colors ${active ? "border-l-teal-500 bg-teal-500/6 dark:bg-teal-400/8 border border-teal-500/15 dark:border-teal-400/10" : "border-transparent hover:bg-stone-50 dark:hover:bg-stone-950/40 border border-transparent"}`}
                  >
                    <p className="text-[0.7rem] font-semibold text-stone-800 dark:text-stone-200 truncate leading-tight">
                      {r.name}
                    </p>
                    <p className="text-[0.58rem] text-stone-400 dark:text-stone-500 mt-0.5">
                      {r.periodStart} → {r.periodEnd}
                    </p>
                    <div className="flex items-center justify-between mt-1.5 gap-1">
                      <StatusBadge status={r.status} />
                      {r.totalPnl != null && (
                        <span
                          className={`text-[0.65rem] font-semibold tabular-nums ${pnlColorClass(r.totalPnl)}`}
                        >
                          {fmtMoney(r.totalPnl)}
                        </span>
                      )}
                    </div>
                    {r.status === "RUNNING" && (
                      <div className="mt-1.5">
                        <div className="h-1 rounded-full bg-stone-100 dark:bg-stone-800 overflow-hidden">
                          <div
                            className="h-full rounded-full bg-amber-400 dark:bg-amber-500 transition-[width]"
                            style={{ width: `${r.progressPct}%` }}
                          />
                        </div>
                        <p className="text-right text-[0.55rem] text-stone-400 dark:text-stone-500 mt-0.5">
                          {r.progressPct}%
                        </p>
                      </div>
                    )}
                  </motion.button>
                );
              })}
            </div>
            <div className="p-2 border-t border-stone-900/8 dark:border-stone-100/8 shrink-0">
              <button
                type="button"
                onClick={() => setBuilderOpen((o) => !o)}
                className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-teal-500/8 dark:bg-teal-400/8 py-2 text-[0.65rem] font-semibold text-teal-700 dark:text-teal-400 hover:bg-teal-500/15 transition-colors"
              >
                <Play className="h-3 w-3" strokeWidth={2} />
                New simulation
              </button>
            </div>
          </aside>

          {/* ── COL 2: Run detail (fixed 360px) ───────────────────────────── */}
          <main className={`flex min-h-0 w-[360px] shrink-0 flex-col border-r ${subtleBorder} ${paneBg}`}> 
            {run ? (
              <>
                {/* Run identity + actions — fixed */}
                <div className="shrink-0 px-3 pt-3 pb-2.5 border-b border-stone-900/8 dark:border-stone-100/8">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="text-[0.58rem] font-semibold uppercase tracking-widest text-stone-400 dark:text-stone-500">
                        Selected run
                      </p>
                      <h2 className="text-[0.85rem] font-semibold text-stone-900 dark:text-stone-100 mt-0.5 truncate">
                        #{run.id} — {run.name}
                      </h2>
                      <div className="flex flex-wrap items-center gap-1.5 mt-1.5">
                        <StatusBadge status={run.status} />
                        <span className="text-[0.6rem] text-stone-400 dark:text-stone-500">
                          {run.periodStart} → {run.periodEnd}
                        </span>
                      </div>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-1 mt-2">
                    <button
                      type="button"
                      onClick={() => stopMutation.mutate(run.id)}
                      disabled={
                        run.status !== "RUNNING" || stopMutation.isPending
                      }
                      className="inline-flex items-center gap-1 rounded-lg border border-rose-200 dark:border-rose-800 bg-rose-50 dark:bg-rose-950/30 px-2 py-1 text-[0.63rem] font-semibold text-rose-700 dark:text-rose-400 hover:bg-rose-100 dark:hover:bg-rose-950/50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                    >
                      <Square className="h-2.5 w-2.5" strokeWidth={2} />
                      Stop
                    </button>
                    <button
                      type="button"
                      onClick={() => forceStopMutation.mutate(run.id)}
                      disabled={
                        run.status !== "RUNNING" || forceStopMutation.isPending
                      }
                      className="inline-flex items-center gap-1 rounded-lg border border-rose-200 dark:border-rose-800 bg-rose-50 dark:bg-rose-950/30 px-2 py-1 text-[0.63rem] font-semibold text-rose-700 dark:text-rose-400 hover:bg-rose-100 dark:hover:bg-rose-950/50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                    >
                      <OctagonX className="h-2.5 w-2.5" strokeWidth={2} />
                      Force stop
                    </button>
                    <button
                      type="button"
                      onClick={copyRunDetails}
                      className="inline-flex items-center gap-1 rounded-lg border border-stone-900/8 dark:border-stone-100/8 bg-stone-50 dark:bg-stone-950/40 px-2 py-1 text-[0.63rem] font-semibold text-stone-600 dark:text-stone-400 hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
                    >
                      <Copy className="h-2.5 w-2.5" strokeWidth={2} />
                      Copy
                    </button>
                    <button
                      type="button"
                      onClick={exportRunJson}
                      className="inline-flex items-center gap-1 rounded-lg border border-stone-900/8 dark:border-stone-100/8 bg-stone-50 dark:bg-stone-950/40 px-2 py-1 text-[0.63rem] font-semibold text-stone-600 dark:text-stone-400 hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
                    >
                      <Download className="h-2.5 w-2.5" strokeWidth={2} />
                      JSON
                    </button>
                    <button
                      type="button"
                      onClick={exportTradesCsv}
                      className="inline-flex items-center gap-1 rounded-lg border border-stone-900/8 dark:border-stone-100/8 bg-stone-50 dark:bg-stone-950/40 px-2 py-1 text-[0.63rem] font-semibold text-stone-600 dark:text-stone-400 hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
                    >
                      <Download className="h-2.5 w-2.5" strokeWidth={2} />
                      CSV
                    </button>
                  </div>
                </div>

                {/* KPI strip — fixed */}
                <div className="shrink-0 grid grid-cols-3 border-b border-stone-900/8 dark:border-stone-100/8">
                  <KpiTile
                    label="Total P&L"
                    value={run.totalPnl != null ? fmtMoney(run.totalPnl) : "--"}
                    sub={
                      run.totalPnlPct != null
                        ? fmtPct(run.totalPnlPct)
                        : undefined
                    }
                    valueClass={
                      run.totalPnl != null ? pnlColorClass(run.totalPnl) : ""
                    }
                  />
                  <KpiTile
                    label="Win rate"
                    value={run.winRate != null ? `${run.winRate}%` : "--"}
                    sub={`${run.closedTradeCount} closed`}
                  />
                  <KpiTile
                    label="Max drawdown"
                    value={
                      run.maxDrawdownPct != null
                        ? fmtPct(run.maxDrawdownPct)
                        : "--"
                    }
                    valueClass={pnlColorClass(run.maxDrawdownPct)}
                  />
                  <KpiTile
                    label="Sharpe"
                    value={
                      run.sharpeRatio != null ? fmt(run.sharpeRatio, 2) : "--"
                    }
                    sub={
                      run.sharpeRatio != null
                        ? run.sharpeRatio >= 1.5
                          ? "≥ 1.5 ✓"
                          : "< 1.5"
                        : undefined
                    }
                    valueClass={
                      run.sharpeRatio != null
                        ? run.sharpeRatio >= 1.5
                          ? "text-teal-600 dark:text-teal-400"
                          : "text-rose-600 dark:text-rose-400"
                        : ""
                    }
                  />
                  <KpiTile
                    label="Trades"
                    value={fmt(run.tradeCount)}
                    sub={`${run.openTradeCount} open`}
                  />
                  <KpiTile
                    label="Avg hold"
                    value={
                      run.avgHoldTimeH != null
                        ? `${fmt(run.avgHoldTimeH, 1)}h`
                        : "--"
                    }
                  />
                </div>

                {/* Scrollable detail area */}
                <div className="flex-1 overflow-y-auto min-h-0">
                  <div className="p-3 grid gap-3">
                    {/* Alerts */}
                    {run.alerts.map((a, i) => (
                      <div
                        key={i}
                        className={`rounded-xl border px-3 py-2.5 ${a.tone === "bad" ? "border-rose-200 dark:border-rose-800 bg-rose-50 dark:bg-rose-950/30" : "border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/30"}`}
                      >
                        <p
                          className={`text-[0.7rem] font-semibold ${a.tone === "bad" ? "text-rose-700 dark:text-rose-400" : "text-amber-700 dark:text-amber-400"}`}
                        >
                          {a.title}
                        </p>
                        <p
                          className={`text-[0.65rem] mt-0.5 leading-relaxed ${a.tone === "bad" ? "text-rose-600 dark:text-rose-500" : "text-amber-600 dark:text-amber-500"}`}
                        >
                          {a.message}
                        </p>
                      </div>
                    ))}

                    <SimulationOldRunBanner
                      show={oldRunMissingTraces}
                      onRerun={rerunWithDiagnostics}
                    />
                    <SimulationRunIntelligenceSummary
                      run={run}
                      diagnostics={diagnosticsQuery.data}
                      parity={parityQuery.data}
                      onAction={handleInsightAction}
                    />
                    <SimulationInsightRail
                      run={run}
                      diagnostics={diagnosticsQuery.data}
                      parity={parityQuery.data}
                      onAction={handleInsightAction}
                    />
                    {diagnosticsQuery.data?.health && (
                      <SimulationHealthCard
                        diagnostics={diagnosticsQuery.data}
                        run={run}
                      />
                    )}

                    <LiveSimulationEventPanel
                      latestEvent={simulationEvents.latestEvent}
                      events={simulationEvents.events}
                      connectionState={simulationEvents.connectionState}
                      runId={simulationEvents.runId}
                      url={simulationEvents.url}
                    />

                    {/* Timeline */}
                    <Card>
                      <PanelHeader
                        icon={Clock3}
                        title="Simulation timeline"
                        subtitle={`${run.progressPct}% complete`}
                      />
                      <div className="p-3">
                        <TimelineBar run={run} />
                      </div>
                    </Card>

                    {/* Equity + Stages side by side */}
                    <div className="grid grid-cols-2 gap-3">
                      <Card>
                        <PanelHeader icon={TrendingUp} title="Equity curve" />
                        <div className="p-2">
                          <div className="rounded-lg overflow-hidden bg-stone-50 dark:bg-stone-950/40">
                            <EquityMiniChart
                              points={run.equityCurve}
                              status={run.status}
                            />
                          </div>
                        </div>
                      </Card>
                      <Card>
                        <PanelHeader icon={Workflow} title="Engine stages" />
                        <div className="p-2 grid gap-1">
                          {run.stages.map((stage) => (
                            <div
                              key={stage.key}
                              className="flex items-center gap-2 rounded-lg bg-stone-50 dark:bg-stone-950/40 px-2 py-1.5"
                            >
                              <span
                                className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-md ${stageStatusClass(stage.status)}`}
                              >
                                {stageIcon(stage.status)}
                              </span>
                              <div className="min-w-0">
                                <p className="text-[0.65rem] font-semibold text-stone-700 dark:text-stone-300 truncate">
                                  {stage.label}
                                </p>
                                <p className="text-[0.58rem] text-stone-400 dark:text-stone-500">
                                  {stage.detail}
                                </p>
                              </div>
                            </div>
                          ))}
                        </div>
                      </Card>
                    </div>

                    {/* Per-mode */}
                    {run.perMode.length > 0 && (
                      <Card>
                        <PanelHeader icon={Sparkles} title="Per-mode results" />
                        <div className="p-3 grid gap-2">
                          {run.perMode.map((m) => (
                            <div
                              key={m.mode}
                              className="flex items-center gap-3"
                            >
                              <span className="text-[0.63rem] font-semibold uppercase tracking-widest text-stone-400 dark:text-stone-500 w-24 shrink-0">
                                {m.mode}
                              </span>
                              <div className="flex-1 h-1.5 rounded-full bg-stone-100 dark:bg-stone-800 overflow-hidden">
                                <div
                                  className="h-full rounded-full bg-teal-500 dark:bg-teal-400"
                                  style={{ width: `${m.winRate}%` }}
                                />
                              </div>
                              <span
                                className={`text-[0.7rem] font-semibold tabular-nums shrink-0 ${pnlColorClass(m.pnl)}`}
                              >
                                {fmtMoney(m.pnl)}
                              </span>
                              <span className="text-[0.63rem] text-stone-400 dark:text-stone-500 shrink-0">
                                {m.winRate}% · {m.trades}t
                              </span>
                            </div>
                          ))}
                        </div>
                      </Card>
                    )}

                    {/* Skip breakdown */}
                    {run.skipBreakdown.length > 0 && (
                      <Card>
                        <PanelHeader
                          icon={Workflow}
                          title="Skip breakdown"
                          subtitle={`${fmt(run.skipBreakdown.reduce((s, r) => s + r.count, 0))} skipped`}
                        />
                        <div className="p-3 grid gap-2.5">
                          {skipDiagnostic && (
                            <AlertBanner
                              tone={skipDiagnostic.tone}
                              title={skipDiagnostic.title}
                              message={skipDiagnostic.message}
                            />
                          )}
                          <SkipBar
                            rows={run.skipBreakdown}
                            toneForKey={skipTone}
                            labelForKey={skipLabel}
                          />
                          <div className="grid gap-2 sm:grid-cols-2">
                            <div>
                              <p className="text-[0.58rem] font-semibold uppercase tracking-widest text-stone-400 dark:text-stone-500 mb-1.5">
                                By family
                              </p>
                              <BreakdownList
                                rows={skipFamilySummary}
                                color="bg-teal-500"
                              />
                            </div>
                            <div className="grid gap-1">
                              <p className="text-[0.58rem] font-semibold uppercase tracking-widest text-stone-400 dark:text-stone-500 mb-0.5">
                                By reason
                              </p>
                              {run.skipBreakdown.map((r) => (
                                <div
                                  key={r.key}
                                  className="rounded-lg border border-stone-900/8 dark:border-stone-100/8 bg-white dark:bg-stone-800 px-2.5 py-2"
                                >
                                  <div className="flex items-center justify-between gap-1.5 text-[0.7rem]">
                                    <div className="flex items-center gap-1.5 min-w-0">
                                      <span
                                        className={`h-1.5 w-1.5 rounded-sm shrink-0 ${skipTone(r.key)}`}
                                      />
                                      <span className="font-semibold text-stone-700 dark:text-stone-300 truncate">
                                        {skipLabel(r.key)}
                                      </span>
                                    </div>
                                    <span className="tabular-nums text-stone-400 dark:text-stone-500 shrink-0">
                                      {fmt(r.count)} · {r.pct}%
                                    </span>
                                  </div>
                                  <p className="mt-0.5 text-[0.6rem] text-stone-400 dark:text-stone-500 leading-relaxed">
                                    {skipDescription(r.key)}
                                  </p>
                                </div>
                              ))}
                            </div>
                          </div>
                          {run.skipSamples.length === 0 && (
                            <div className="rounded-lg border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/30 px-2.5 py-2 text-[0.65rem] text-amber-700 dark:text-amber-400">
                              No per-decision skip samples stored for this run.
                              Rerun to see no-trade summaries and confidence
                              breakdown.
                            </div>
                          )}
                        </div>
                      </Card>
                    )}

                    {/* Scope: symbols */}
                    <Card>
                      <PanelHeader
                        icon={Radar}
                        title="Simulation scope"
                        subtitle={`${run.symbolCount} symbols`}
                      />
                      <div className="p-3">
                        <div className="grid grid-cols-3 gap-2 mb-3 text-[0.7rem]">
                          {[
                            ["Intervals", run.intervals.join(", ")],
                            ["Modes", run.modes.join(", ")],
                            ["Capital", `$${fmt(run.capital)}`],
                          ].map(([label, value]) => (
                            <div key={String(label)}>
                              <p className="text-[0.58rem] font-semibold uppercase tracking-widest text-stone-400 dark:text-stone-500">
                                {String(label)}
                              </p>
                              <p className="text-stone-700 dark:text-stone-300 mt-0.5 font-medium">
                                {String(value)}
                              </p>
                            </div>
                          ))}
                        </div>
                        <div className="flex flex-wrap gap-1">
                          {(showAllSymbols
                            ? run.symbols
                            : run.symbols.slice(0, 10)
                          ).map((s) => (
                            <span
                              key={s}
                              className="rounded-md border border-stone-900/8 dark:border-stone-100/8 bg-stone-50 dark:bg-stone-950/40 px-1.5 py-0.5 text-[0.63rem] font-semibold text-stone-600 dark:text-stone-400"
                            >
                              {s}
                            </span>
                          ))}
                          {!showAllSymbols && run.symbols.length > 10 && (
                            <button
                              type="button"
                              onClick={() => setShowAllSymbols(true)}
                              className="rounded-md border border-stone-900/8 dark:border-stone-100/8 bg-stone-50 dark:bg-stone-950/40 px-1.5 py-0.5 text-[0.63rem] text-stone-400 dark:text-stone-500 hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors flex items-center gap-0.5"
                            >
                              +{run.symbols.length - 10} more{" "}
                              <ChevronDown
                                className="h-2.5 w-2.5"
                                strokeWidth={2}
                              />
                            </button>
                          )}
                          {showAllSymbols && (
                            <button
                              type="button"
                              onClick={() => setShowAllSymbols(false)}
                              className="rounded-md border border-stone-900/8 dark:border-stone-100/8 bg-stone-50 dark:bg-stone-950/40 px-1.5 py-0.5 text-[0.63rem] text-stone-400 dark:text-stone-500 hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors flex items-center gap-0.5"
                            >
                              Show less{" "}
                              <ChevronUp
                                className="h-2.5 w-2.5"
                                strokeWidth={2}
                              />
                            </button>
                          )}
                        </div>
                      </div>
                    </Card>
                  </div>
                </div>
              </>
            ) : (
              <div className="flex flex-1 items-center justify-center p-8">
                <EmptyState message="Select a simulation run to inspect its detail." />
              </div>
            )}
          </main>

          {/* ── COL 3: Diagnostic console (flex 1) ───────────────────────── */}
          <section className={`flex min-h-0 min-w-0 flex-1 flex-col ${canvasBg}`}> 
            {run ? (
              <>
                {/* Tab bar — fixed */}
                <div
                  className="shrink-0 flex gap-1 px-2.5 py-2 border-b border-stone-900/8 dark:border-stone-100/8 bg-white dark:bg-stone-900 overflow-x-auto"
                  role="tablist"
                  aria-label="Simulation diagnostic sections"
                >
                  {TABS.map(([tab, label]) => (
                    <button
                      key={tab}
                      type="button"
                      role="tab"
                      aria-selected={detailTab === tab}
                      onClick={() => setDetailTab(tab)}
                      className={`shrink-0 rounded-lg px-3 py-1.5 text-[0.65rem] font-semibold transition-colors ${detailTab === tab ? "bg-stone-100 dark:bg-stone-800 text-stone-800 dark:text-stone-200 border border-stone-900/8 dark:border-stone-100/8" : "text-stone-400 dark:text-stone-500 hover:text-stone-600 dark:hover:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-950/40"}`}
                    >
                      {label}
                    </button>
                  ))}
                </div>

                {/* Tab content — scrollable */}
                <div className="flex-1 overflow-y-auto min-h-0 p-3">
                  <AnimatePresence mode="wait">
                    <motion.div
                      key={detailTab}
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: 4 }}
                      transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
                    >
                  {detailTab === "trace" && (
                    <SimulationTraceTable
                      traces={traceRows}
                      isLoading={traceQuery.isLoading}
                      isError={traceQuery.isError}
                      filters={traceFilters}
                      onFiltersChange={setTraceFilters}
                      hasMore={Boolean(traceQuery.data?.has_more)}
                      onLoadMore={() =>
                        setTraceCursor(
                          Number(traceQuery.data?.next_cursor ?? 0) || null,
                        )
                      }
                    />
                  )}
                  {detailTab === "diagnostics" && (
                    <SimulationDiagnosticsPanel
                      diagnostics={diagnosticsQuery.data}
                      onTraceFilter={openTraceWithFilters}
                      onOpenWhatIf={() => setDetailTab("what-if")}
                    />
                  )}
                  {detailTab === "what-if" && (
                    <SimulationWhatIfPanel
                      result={whatIfQuery.data}
                      inputs={whatIfInputs}
                      onInputsChange={setWhatIfInputs}
                      isLoading={whatIfQuery.isLoading}
                      diagnostics={diagnosticsQuery.data}
                      onTraceFilter={openTraceWithFilters}
                    />
                  )}
                  {detailTab === "health" && (
                    <div className="grid gap-3">
                      <SimulationHealthCard
                        diagnostics={diagnosticsQuery.data}
                        run={run}
                      />
                      <SimulationReproducibilityCard run={run} />
                    </div>
                  )}
                  {detailTab === "parity" && (
                    <SimulationParityPanel parity={parityQuery.data} />
                  )}
                  {detailTab === "exports" && (
                    <SimulationExportPanel run={run} />
                  )}

                  {detailTab === "overview" && (
                    <div className="grid gap-3">
                      <SimulationSummaryPanel
                        run={run}
                        onAnalyzeFailures={() => failureAnalysisMutation.mutate(run.id)}
                        analyzing={failureAnalysisMutation.isPending}
                      />
                      <SimulationPerformanceDiagnosticsPanel run={run} />

                      {/* Overview summary tiles */}
                      <div className="grid gap-2 sm:grid-cols-3">
                        {[
                          {
                            icon: Radar,
                            title: "Run scope",
                            body: `${run.symbols.length} symbols · ${run.intervals.join(", ")} · ${run.modes.join(", ")}`,
                            sub: `${run.periodStart} → ${run.periodEnd} · $${fmt(run.capital)}`,
                          },
                          {
                            icon: CircleCheck,
                            title: "Health / coverage",
                            body: String(
                              diagnosticsQuery.data?.health?.status ||
                                "UNKNOWN",
                            ),
                            sub: `${fmt(Number(diagnosticsQuery.data?.trace_coverage?.trace_count ?? 0))} traces · ${String(diagnosticsQuery.data?.trace_coverage?.coverage_status || "unknown")}`,
                          },
                          {
                            icon: OctagonX,
                            title: "Primary blocker",
                            body: reasonLabel(
                              primaryBlocker(diagnosticsQuery.data)?.reason ||
                                "none",
                            ),
                            sub: `${fmt(Number(primaryBlocker(diagnosticsQuery.data)?.count ?? 0))} decisions`,
                          },
                        ].map(({ icon: Icon, title, body, sub }) => (
                          <Card key={title}>
                            <PanelHeader icon={Icon} title={title} />
                            <div className="p-3">
                              <p className="text-sm font-semibold text-stone-800 dark:text-stone-200">
                                {body}
                              </p>
                              <p className="text-[0.65rem] text-stone-400 dark:text-stone-500 mt-0.5">
                                {sub}
                              </p>
                            </div>
                          </Card>
                        ))}
                      </div>

                      {/* Quick action buttons */}
                      <div className="flex flex-wrap gap-1.5">
                        {[
                          ["diagnostics", "Open diagnostics"],
                          ["trace", "Open traces"],
                          ["exports", "Export run package"],
                        ].map(([tab, label]) => (
                          <button
                            key={tab}
                            type="button"
                            onClick={() =>
                              setDetailTab(tab as SimulationDetailTab)
                            }
                            className="rounded-lg bg-teal-500/8 dark:bg-teal-400/8 px-3 py-1.5 text-[0.7rem] font-semibold text-teal-700 dark:text-teal-400 hover:bg-teal-500/15 transition-colors"
                          >
                            {label}
                          </button>
                        ))}
                        <button
                          type="button"
                          onClick={rerunWithDiagnostics}
                          className="rounded-lg border border-stone-900/8 dark:border-stone-100/8 bg-white dark:bg-stone-900 px-3 py-1.5 text-[0.7rem] font-semibold text-stone-600 dark:text-stone-400 hover:bg-stone-50 dark:hover:bg-stone-950/40 transition-colors"
                        >
                          Rerun with diagnostics
                        </button>
                      </div>

                      <SimulationReproducibilityCard run={run} />

                      {/* Trade search + filter */}
                      <div className="flex flex-wrap items-center gap-2">
                        <SectionHeader
                          icon={Sparkles}
                          title="Trade results"
                          subtitle={`${run.trades.length} trades`}
                        />
                        <div className="relative ml-auto">
                          <Search
                            className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 h-3 w-3 text-stone-400"
                            strokeWidth={1.8}
                          />
                          <input
                            value={tradeQuery}
                            onChange={(e) => setTradeQuery(e.target.value)}
                            placeholder="Symbol, mode…"
                            className="h-7 w-44 rounded-lg border border-stone-900/8 dark:border-stone-100/8 bg-white dark:bg-stone-900 pl-7 pr-2.5 text-[0.7rem] text-stone-800 dark:text-stone-200 outline-none placeholder:text-stone-400 focus:border-teal-500/40 focus:ring-2 focus:ring-teal-500/10"
                          />
                        </div>
                      </div>

                      <div className="flex flex-wrap gap-1 items-center">
                        {(
                          ["ALL", "CLOSED", "OPEN", "STOPPED_OUT"] as const
                        ).map((f) => (
                          <button
                            key={f}
                            type="button"
                            onClick={() => setTradeFilter(f)}
                            className={`rounded-lg px-2.5 py-1 text-[0.63rem] font-semibold uppercase tracking-wide transition-colors ${tradeFilter === f ? "bg-teal-500/10 dark:bg-teal-400/10 text-teal-700 dark:text-teal-400" : "bg-stone-100 dark:bg-stone-800 text-stone-500 dark:text-stone-400 hover:bg-stone-200 dark:hover:bg-stone-700"}`}
                          >
                            {f.replaceAll("_", " ")}
                          </button>
                        ))}
                        <span className="ml-auto text-[0.63rem] text-stone-400 dark:text-stone-500">
                          {sortedTrades.length} rows
                        </span>
                      </div>

                      {/* Confidence vs P&L scatter */}
                      {run.trades.filter((t) => t.pnl != null).length > 0 && (
                        <Card>
                          <PanelHeader
                            icon={TrendingUp}
                            title="Confidence vs P&L"
                            subtitle="Each dot = one settled trade"
                          />
                          <div className="p-3">
                            <div className="rounded-lg overflow-hidden bg-stone-50 dark:bg-stone-950/40 px-3 py-2">
                              <svg
                                viewBox="0 0 340 100"
                                width="100%"
                                height="100"
                              >
                                <line
                                  x1="28"
                                  y1="5"
                                  x2="28"
                                  y2="85"
                                  stroke="#d4d0c8"
                                  strokeWidth="0.5"
                                />
                                <line
                                  x1="28"
                                  y1="85"
                                  x2="335"
                                  y2="85"
                                  stroke="#d4d0c8"
                                  strokeWidth="0.5"
                                />
                                <line
                                  x1="28"
                                  y1="45"
                                  x2="335"
                                  y2="45"
                                  stroke="#d4d0c8"
                                  strokeWidth="0.5"
                                  strokeDasharray="3 3"
                                />
                                <text
                                  x="5"
                                  y="48"
                                  fontSize="7"
                                  fill="#a8a59e"
                                  textAnchor="middle"
                                >
                                  $0
                                </text>
                                <text
                                  x="175"
                                  y="95"
                                  fontSize="7"
                                  fill="#a8a59e"
                                  textAnchor="middle"
                                >
                                  confidence →
                                </text>
                                {run.trades
                                  .filter((t) => t.pnl != null)
                                  .map((t) => {
                                    const cx =
                                      28 + ((t.confidence - 55) / 45) * 305;
                                    const cy = 45 - (t.pnl! / 1400) * 38;
                                    return (
                                      <circle
                                        key={t.id}
                                        cx={cx.toFixed(1)}
                                        cy={Math.min(
                                          84,
                                          Math.max(6, cy),
                                        ).toFixed(1)}
                                        r={Math.min(
                                          5,
                                          Math.max(2, Math.abs(t.pnl!) / 200),
                                        )}
                                        fill={
                                          t.pnl! >= 0 ? "#1d9e75" : "#e24b4a"
                                        }
                                        opacity="0.7"
                                      />
                                    );
                                  })}
                                <line
                                  x1="40"
                                  y1="72"
                                  x2="330"
                                  y2="15"
                                  stroke="#1d9e75"
                                  strokeWidth="0.8"
                                  strokeDasharray="4 3"
                                  opacity="0.35"
                                />
                              </svg>
                            </div>
                          </div>
                        </Card>
                      )}

                      {/* Trade table */}
                      {sortedTrades.length > 0 ? (
                        <Card>
                          <PanelHeader
                            icon={ArrowRight}
                            title="Per-trade detail"
                            subtitle={`${sortedTrades.length} trades`}
                          />
                          <div className="overflow-x-auto">
                            <table className="min-w-full divide-y divide-stone-900/8 dark:divide-stone-100/8 text-[0.7rem]">
                              <thead className="bg-stone-50 dark:bg-stone-950/40">
                                <tr>
                                  {(
                                    [
                                      ["symbol", "Symbol"],
                                      ["mode", "Mode"],
                                      ["direction", "Dir"],
                                      ["confidence", "Conf"],
                                      ["pnl", "P&L"],
                                      ["hold_time", "Hold"],
                                      ["status", "Status"],
                                    ] as [TradeSortKey, string][]
                                  ).map(([key, label]) => (
                                    <th
                                      key={key}
                                      className="px-2.5 py-2 text-left"
                                    >
                                      <SortHeader
                                        label={label}
                                        active={tradeSortKey === key}
                                        descending={tradeSortDesc}
                                        onClick={() => handleSort(key)}
                                      />
                                    </th>
                                  ))}
                                </tr>
                              </thead>
                              <tbody className="divide-y divide-stone-900/8 dark:divide-stone-100/8">
                                {sortedTrades.map((t) => (
                                  <tr
                                    key={t.id}
                                    className="hover:bg-stone-50 dark:hover:bg-stone-950/40 transition-colors"
                                  >
                                    <td className="px-2.5 py-2">
                                      <p className="font-semibold text-stone-800 dark:text-stone-200">
                                        {t.symbol}
                                      </p>
                                      <p className="text-[0.58rem] text-stone-400 dark:text-stone-500">
                                        {t.interval}
                                      </p>
                                    </td>
                                    <td className="px-2.5 py-2 text-stone-500 dark:text-stone-400">
                                      {t.mode}
                                    </td>
                                    <td className="px-2.5 py-2">
                                      <span
                                        className={`rounded px-1.5 py-0.5 text-[0.58rem] font-bold uppercase ${t.direction === "BUY" ? "bg-teal-500/10 text-teal-700 dark:text-teal-400" : "bg-rose-500/10 text-rose-700 dark:text-rose-400"}`}
                                      >
                                        {t.direction}
                                      </span>
                                    </td>
                                    <td className="px-2.5 py-2 tabular-nums text-stone-600 dark:text-stone-300">
                                      {fmt(t.confidence, 1)}%
                                    </td>
                                    <td className="px-2.5 py-2">
                                      <p
                                        className={`font-semibold tabular-nums ${pnlColorClass(t.pnl)}`}
                                      >
                                        {t.pnl != null ? fmtMoney(t.pnl) : "--"}
                                      </p>
                                      {t.pnlPct != null && (
                                        <p
                                          className={`text-[0.6rem] ${pnlColorClass(t.pnl)}`}
                                        >
                                          {fmtPct(t.pnlPct)}
                                        </p>
                                      )}
                                    </td>
                                    <td className="px-2.5 py-2 tabular-nums text-stone-500 dark:text-stone-400">
                                      {t.holdTimeHours != null
                                        ? `${fmt(t.holdTimeHours, 1)}h`
                                        : "—"}
                                    </td>
                                    <td className="px-2.5 py-2">
                                      {t.status === "CLOSED" && (
                                        <span className="rounded bg-teal-500/10 px-1.5 py-0.5 text-[0.58rem] font-bold text-teal-700 dark:text-teal-400">
                                          Closed
                                        </span>
                                      )}
                                      {t.status === "OPEN" && (
                                        <span className="rounded bg-sky-500/10 px-1.5 py-0.5 text-[0.58rem] font-bold text-sky-700 dark:text-sky-400">
                                          Open
                                        </span>
                                      )}
                                      {t.status === "STOPPED_OUT" && (
                                        <div>
                                          <span className="rounded bg-rose-500/10 px-1.5 py-0.5 text-[0.58rem] font-bold text-rose-700 dark:text-rose-400">
                                            Stopped
                                          </span>
                                          {t.stopReason && (
                                            <p className="mt-0.5 text-[0.58rem] text-rose-500 dark:text-rose-400">
                                              {t.stopReason}
                                            </p>
                                          )}
                                        </div>
                                      )}
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </Card>
                      ) : (
                        <div className="rounded-xl border border-stone-900/8 dark:border-stone-100/8 bg-white dark:bg-stone-900 p-8">
                          <EmptyState
                            message={
                              run.trades.length === 0
                                ? "No trades have been settled for this run yet."
                                : "No trades matched the filter."
                            }
                          />
                        </div>
                      )}
                    </div>
                  )}
                    </motion.div>
                  </AnimatePresence>
                </div>
              </>
            ) : (
              <div className="flex flex-1 items-center justify-center p-8">
                <EmptyState message="Select a simulation run to inspect per-trade outcomes." />
              </div>
            )}
          </section>
        </motion.div>

        {/* ══ NEW SIMULATION BUILDER ═════════════════════════════════════════ */}
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.22, delay: 0.08, ease: [0.22, 1, 0.36, 1] }}
          className={`flex-shrink-0 overflow-hidden rounded-[1.8rem] border shadow-[0_18px_40px_rgba(77,62,40,0.08)] ${subtleBorder} ${cardBg}`}
        >
          <button
            type="button"
            onClick={() => setBuilderOpen((o) => !o)}
            className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-stone-50 dark:hover:bg-stone-950/40 transition-colors"
          >
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-teal-500/10 dark:bg-teal-400/10">
              <FlaskConical
                className="h-3 w-3 text-teal-600 dark:text-teal-400"
                strokeWidth={1.8}
              />
            </span>
            <span className="text-[0.75rem] font-semibold text-stone-800 dark:text-stone-200">
              New Simulation
            </span>
            <span className="text-[0.7rem] text-stone-400 dark:text-stone-500">
              Configure period, symbols, modes, and capital then run
            </span>
            {builderOpen ? (
              <ChevronUp
                className="ml-auto h-3.5 w-3.5 text-stone-400"
                strokeWidth={2}
              />
            ) : (
              <ChevronDown
                className="ml-auto h-3.5 w-3.5 text-stone-400"
                strokeWidth={2}
              />
            )}
          </button>

          <AnimatePresence initial={false}>
            {builderOpen && (
            <motion.div
              key="simulation-builder"
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
              className="grid gap-4 overflow-hidden border-t border-stone-900/8 px-4 py-4 dark:border-stone-100/8"
            >
              {/* Presets */}
              <Card>
                <PanelHeader
                  icon={Sparkles}
                  title="Simulation presets"
                  subtitle="Built-ins and saved local presets"
                />
                <div className="p-3">
                  <div className="flex flex-wrap items-center gap-2 mb-3">
                    <input
                      value={presetName}
                      onChange={(e) => setPresetName(e.target.value)}
                      placeholder="Preset name"
                      className="h-7 w-48 rounded-lg border border-stone-900/8 dark:border-stone-100/8 bg-stone-50 dark:bg-stone-950/40 px-2.5 text-[0.7rem] text-stone-800 dark:text-stone-200 outline-none"
                    />
                    <button
                      type="button"
                      onClick={savePreset}
                      className="rounded-lg bg-teal-500/8 dark:bg-teal-400/8 px-3 py-1.5 text-[0.7rem] font-semibold text-teal-700 dark:text-teal-400 hover:bg-teal-500/15 transition-colors"
                    >
                      Save / update
                    </button>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {allPresets.map((preset) => (
                      <div
                        key={preset.id}
                        className="inline-flex overflow-hidden rounded-full border border-stone-900/8 dark:border-stone-100/8 bg-stone-50 dark:bg-stone-950/40"
                      >
                        <button
                          type="button"
                          onClick={() => applyPreset(preset)}
                          className="px-2.5 py-1 text-[0.65rem] font-semibold text-stone-700 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
                        >
                          {preset.name}
                        </button>
                        {preset.id.startsWith("user-") && (
                          <button
                            type="button"
                            onClick={() => deletePreset(preset.id)}
                            className="border-l border-stone-900/8 dark:border-stone-100/8 px-2 text-[0.65rem] font-bold text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-950/30 transition-colors"
                          >
                            ×
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              </Card>

              {/* Period + Capital */}
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                <Card>
                  <PanelHeader icon={Clock3} title="Period" />
                  <div className="p-3">
                    <div className="flex flex-wrap gap-1.5 mb-2">
                      {(
                        [
                          ["7D", 7],
                          ["30D", 30],
                          ["90D", 90],
                        ] as [string, number][]
                      ).map(([label, days]) => (
                        <button
                          key={label}
                          type="button"
                          onClick={() => {
                            setPeriodStart(dateDaysAgo(days));
                            setPeriodEnd(new Date().toISOString().slice(0, 10));
                          }}
                          className="rounded-full border border-stone-900/8 dark:border-stone-100/8 bg-stone-50 dark:bg-stone-950/40 px-2.5 py-1 text-[0.65rem] font-semibold text-stone-600 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                    <div className="grid grid-cols-2 gap-1.5">
                      <input
                        type="date"
                        value={periodStart}
                        onChange={(e) => setPeriodStart(e.target.value)}
                        className="h-7 rounded-lg border border-stone-900/8 dark:border-stone-100/8 bg-stone-50 dark:bg-stone-950/40 px-2 text-[0.7rem] text-stone-700 dark:text-stone-300 outline-none"
                      />
                      <input
                        type="date"
                        value={periodEnd}
                        onChange={(e) => setPeriodEnd(e.target.value)}
                        className="h-7 rounded-lg border border-stone-900/8 dark:border-stone-100/8 bg-stone-50 dark:bg-stone-950/40 px-2 text-[0.7rem] text-stone-700 dark:text-stone-300 outline-none"
                      />
                    </div>
                  </div>
                </Card>

                <Card className="lg:col-span-2">
                  <PanelHeader icon={TrendingUp} title="Initial capital" />
                  <div className="p-3">
                    <div className="flex flex-wrap gap-1.5 mb-2">
                      {[10000, 25000, 50000, 100000, 250000].map((amount) => (
                        <button
                          key={amount}
                          type="button"
                          onClick={() => setCapital(String(amount))}
                          className={`rounded-full px-2.5 py-1 text-[0.65rem] font-semibold transition-colors ${Number(capital) === amount ? "bg-teal-500/10 dark:bg-teal-400/10 text-teal-700 dark:text-teal-400 ring-1 ring-teal-500/20" : "border border-stone-900/8 dark:border-stone-100/8 bg-stone-50 dark:bg-stone-950/40 text-stone-600 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-800"}`}
                        >
                          ${fmt(amount)}
                        </button>
                      ))}
                    </div>
                    <input
                      type="number"
                      value={capital}
                      onChange={(e) => setCapital(e.target.value)}
                      className="h-7 w-40 rounded-lg border border-stone-900/8 dark:border-stone-100/8 bg-stone-50 dark:bg-stone-950/40 px-2.5 text-[0.7rem] text-stone-700 dark:text-stone-300 outline-none"
                    />
                  </div>
                </Card>
              </div>

              {/* Runtime profile */}
              <Card>
                <PanelHeader
                  icon={Workflow}
                  title="Simulation runtime profile"
                  subtitle="Pseudo-profiles tagged simulation-profile; isolated from main runtime menus"
                />
                <div className="p-3">
                  <div className="flex flex-wrap items-center gap-2 mb-3">
                    <select
                      value={selectedProfileId}
                      onChange={(e) => setSelectedProfileId(e.target.value)}
                      className="h-7 rounded-lg border border-stone-900/8 dark:border-stone-100/8 bg-stone-50 dark:bg-stone-950/40 px-2.5 text-[0.7rem] text-stone-700 dark:text-stone-300 outline-none"
                    >
                      {allSimulationProfiles.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name}
                        </option>
                      ))}
                    </select>
                    <button
                      type="button"
                      onClick={saveSimulationProfile}
                      className="rounded-lg bg-teal-500/8 dark:bg-teal-400/8 px-3 py-1.5 text-[0.7rem] font-semibold text-teal-700 dark:text-teal-400 hover:bg-teal-500/15 transition-colors"
                    >
                      Save profile
                    </button>
                    {selectedProfileId.startsWith("user-") && (
                      <button
                        type="button"
                        onClick={() =>
                          deleteSimulationProfile(selectedProfileId)
                        }
                        className="rounded-lg bg-rose-500/8 dark:bg-rose-400/8 px-3 py-1.5 text-[0.7rem] font-semibold text-rose-600 dark:text-rose-400 hover:bg-rose-500/15 transition-colors"
                      >
                        Delete
                      </button>
                    )}
                  </div>
                  <div className="grid gap-3 lg:grid-cols-[minmax(0,18rem)_minmax(0,1fr)]">
                    <label className="flex flex-col gap-1">
                      <span className="text-[0.58rem] font-semibold uppercase tracking-widest text-stone-400 dark:text-stone-500">
                        Name
                      </span>
                      <input
                        value={profileDraft.name}
                        onChange={(e) =>
                          setProfileDraft({
                            ...profileDraft,
                            name: e.target.value,
                          })
                        }
                        className="h-8 rounded-lg border border-stone-900/8 dark:border-stone-100/8 bg-stone-50 dark:bg-stone-950/40 px-2 text-[0.7rem] text-stone-700 dark:text-stone-300 outline-none"
                      />
                      <p className="text-[0.63rem] leading-5 text-stone-500 dark:text-stone-400">
                        Execution values below are resolved from the full runtime config editor, not separate duplicate controls.
                      </p>
                    </label>
                    <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
                      {[
                        ["Workers", resolvedProfileRuntime.scanWorkers],
                        ["Scan step bars", resolvedProfileRuntime.scanStepBars],
                        ["Time-forward bars", resolvedProfileRuntime.timeForwardStepBars],
                        ["Risk / trade", resolvedProfileRuntime.riskPerTradePct],
                        ["Min confidence", resolvedProfileRuntime.minConfidence],
                        ["Max hold bars", resolvedProfileRuntime.maxHoldBars || "default"],
                        ["Fee bps", resolvedProfileRuntime.feeBps],
                        ["Slippage bps", resolvedProfileRuntime.slippageBps],
                      ].map(([label, value]) => (
                        <div key={String(label)} className="rounded-lg border border-stone-900/8 dark:border-stone-100/8 bg-stone-50 dark:bg-stone-950/40 px-3 py-2">
                          <p className="text-[0.58rem] font-semibold uppercase tracking-widest text-stone-400 dark:text-stone-500">{label}</p>
                          <p className="mt-1 text-sm font-semibold text-stone-800 dark:text-stone-200">{String(value)}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </Card>

              <Card>
                <PanelHeader
                  icon={Download}
                  title="Import config from previous run"
                  subtitle="Copy scenario and profile settings from historical simulations"
                />
                <div className="p-3">
                  {previousRunImportOptions.length === 0 ? (
                    <p className="text-[0.7rem] text-stone-500 dark:text-stone-400">No prior simulation run with saved parameters is available yet.</p>
                  ) : (
                    <div className="flex flex-wrap gap-2">
                      {previousRunImportOptions.slice(0, 12).map((previous) => (
                        <button
                          key={String(previous.id)}
                          type="button"
                          onClick={() => importPreviousRunConfig(Number(previous.id))}
                          className="rounded-full border border-stone-900/8 dark:border-stone-100/8 bg-stone-50 dark:bg-stone-950/40 px-2.5 py-1 text-[0.65rem] font-semibold text-stone-600 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
                        >
                          #{String(previous.id)} · {String(previous.name ?? "simulation")}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </Card>

              <SimulationRuntimeSettingsEditor
                settings={profileDraft.settings ?? runtimeSettingsDraftBase}
                controls={runtimeSettingsMetadataQuery.data?.controls ?? []}
                onChange={updateProfileSettings}
                onImportRuntime={importRuntimeIntoProfile}
              />

              <BuilderChipGroup
                label="Symbols"
                values={availableSymbols}
                selected={selectedSymbols}
                onChange={(v) => setSelectedSymbols(uniqueStrings(v))}
                helper="Tap markets to include."
              />
              <BuilderChipGroup
                label="Intervals"
                values={availableIntervals}
                selected={selectedIntervals}
                onChange={(v) => setSelectedIntervals(uniqueStrings(v))}
                helper="Select one or more historical replay intervals."
              />
              <BuilderChipGroup
                label="Modes"
                values={availableModes}
                selected={selectedModes}
                onChange={(v) => setSelectedModes(uniqueStrings(v))}
                helper="Use the active runtime strategy mode taxonomy."
              />

              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={startSimulation}
                  disabled={createMutation.isPending}
                  className="inline-flex items-center gap-2 rounded-xl bg-teal-500 hover:bg-teal-600 dark:bg-teal-600 dark:hover:bg-teal-500 px-5 py-2.5 text-[0.8rem] font-semibold text-white transition-colors shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <Play className="h-3.5 w-3.5" strokeWidth={2} />
                  {createMutation.isPending ? "Starting…" : "Run simulation"}
                </button>
                <button
                  type="button"
                  onClick={() => setBuilderOpen(false)}
                  className="rounded-xl border border-stone-900/8 dark:border-stone-100/8 px-5 py-2.5 text-[0.8rem] text-stone-500 dark:text-stone-400 hover:bg-stone-50 dark:hover:bg-stone-950/40 transition-colors"
                >
                  Cancel
                </button>
              </div>
            </motion.div>
            )}
          </AnimatePresence>
        </motion.div>
      </div>
    </AnimatedRoute>
  );
}
