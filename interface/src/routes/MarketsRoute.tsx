import { useEffect, useEffectEvent, useMemo, useRef, useState } from 'react'

import { useQuery } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'framer-motion'
import {
  AudioWaveform,
  CandlestickChart,
  Expand,
  Gauge,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  Sparkles,
  X,
} from 'lucide-react'
import { useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'

import { CandlestickChart as CandleCanvas } from '../components/charts/CandlestickChart'
import { AnimatedRoute } from '../components/ui/AnimatedRoute'
import { EmptyState } from '../components/ui/EmptyState'
import { StatusBadge } from '../components/ui/StatusBadge'
import { useSettings } from '../contexts/SettingsContext'
import { fetchKlines, fetchMarketAnalysis, fetchMarketOverview, fetchMarketSignals, fetchSymbols } from '../lib/api'
import { compactNumber, formatNumber, formatPercent, toNumber } from '../lib/format'
import type { AnalysisPayload, JsonRecord } from '../lib/types'

const intervals = ['15m', '30m', '1h', '2h', '4h', '6h', '12h', '1d', '3d', '7d', '14d', '1M']
const modes = ['SCALP', 'SWING', 'AGGRESSIVE_SCALP']

function badgeToneForDirection(direction: string | undefined): 'neutral' | 'good' | 'warn' | 'bad' {
  if (direction === 'BUY') return 'good'
  if (direction === 'SELL') return 'bad'
  if (direction === 'NEUTRAL') return 'warn'
  return 'neutral'
}

function marketCardTone(value: number) {
  return value >= 0 ? 'text-teal-900' : 'text-rose-800'
}

function oscillatorTone(action: string | undefined) {
  if (action === 'Buy') return 'text-teal-700'
  if (action === 'Sell') return 'text-rose-700'
  return 'text-stone-500'
}

function compactSymbol(symbol: string) {
  return symbol.replace('USDT', '')
}

function numericOrNull(value: unknown) {
  const num = Number(value)
  return Number.isFinite(num) ? num : null
}

function formatMetricNumber(value: unknown, digits = 2) {
  const num = numericOrNull(value)
  return num === null ? '--' : formatNumber(num, digits)
}

function formatMetricPercent(value: unknown, digits = 1) {
  const num = numericOrNull(value)
  return num === null ? '--' : formatPercent(num, digits)
}

function formatMetricCompact(value: unknown, suffix = '') {
  const num = numericOrNull(value)
  if (num === null) return '--'
  return `${compactNumber(num)}${suffix}`
}

type AnalysisHistoryEntry = {
  symbol: string
  interval: string
  mode: string
  direction: string
  confidence: number
  entry: number
  timestamp: string
}

function marketListKey(item: JsonRecord, index: number) {
  return `${String(item.symbol ?? '--')}-${String(item.interval ?? item.mode ?? item.direction ?? index)}`
}

function confidenceTone(value: number | null) {
  if (value === null) return 'bg-slate-400'
  if (value >= 70) return 'bg-teal-600'
  if (value >= 50) return 'bg-amber-500'
  return 'bg-emerald-600'
}

function directionDot(direction: string | undefined) {
  if (direction === 'BUY') return 'bg-teal-500'
  if (direction === 'SELL') return 'bg-rose-500'
  return 'bg-stone-400'
}

function clampPercent(value: number) {
  return Math.max(0, Math.min(value, 100))
}

function shareToPercent(value: unknown) {
  const num = numericOrNull(value)
  if (num === null) return null
  return clampPercent(num <= 1 ? num * 100 : num)
}

function normalizeOscillator(name: string, value: unknown) {
  const num = numericOrNull(value)
  if (num === null) return null
  const upper = name.toUpperCase()
  if (upper.includes('WILLIAMS')) return clampPercent(num + 100)
  if (upper.includes('CCI')) return clampPercent(((num + 200) / 400) * 100)
  if (upper.includes('MACD')) return clampPercent(50 + num * 25)
  return clampPercent(num)
}

function firstNonBlank(...values: unknown[]) {
  for (const value of values) {
    const text = String(value ?? '').trim()
    if (text) return text
  }
  return ''
}

function formatBars(value: unknown) {
  const num = numericOrNull(value)
  if (num === null || num <= 0) return '--'
  const rounded = Math.round(num)
  return `~${rounded} ${rounded === 1 ? 'bar' : 'bars'}`
}

function formatPercentSize(value: unknown) {
  const num = numericOrNull(value)
  if (num === null) return '--'
  return `${formatNumber(num * 100, 0)}% base risk`
}

export function MarketsRoute() {
  const { settings } = useSettings()
  const darkMode = settings.theme === 'dark'
  const [searchParams, setSearchParams] = useSearchParams()
  const marketOverviewQuery = useQuery({
    queryKey: ['market-overview'],
    queryFn: () => fetchMarketOverview(200),
    refetchInterval: 45_000,
  })
  const marketSignalsQuery = useQuery({
    queryKey: ['market-signals'],
    queryFn: () => fetchMarketSignals(120),
    refetchInterval: 45_000,
  })
  const symbolsQuery = useQuery({
    queryKey: ['symbols', 'markets'],
    queryFn: fetchSymbols,
    refetchInterval: 60_000,
  })
  const marketOverview = marketOverviewQuery.data ?? null
  const marketUniverse = useMemo(
    () => symbolsQuery.data?.symbols ?? marketOverview?.symbols ?? [],
    [marketOverview?.symbols, symbolsQuery.data?.symbols]
  )
  const marketItems = useMemo(() => {
    const overviewItems = marketOverview?.items ?? []
    if (overviewItems.length) {
      return overviewItems
    }
    return marketUniverse.map((symbol) => ({
      symbol,
      price: 0,
      change_pct: 0,
      volume: 0,
      quote_volume: 0,
      count: 0,
      direction: undefined,
      confidence: undefined,
      regime: undefined,
      trend: undefined,
      summary: undefined,
      interval: '15m',
      mode: 'SCALP',
      created_at_utc: undefined,
    }))
  }, [marketOverview?.items, marketUniverse])
  const topMovers = useMemo(() => marketOverview?.top_movers ?? [], [marketOverview?.top_movers])
  const marketSignals = marketSignalsQuery.data?.items ?? []
  const [selectedInterval, setSelectedInterval] = useState('15m')
  const [selectedMode, setSelectedMode] = useState('SCALP')
  const [searchTerm, setSearchTerm] = useState('')
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [isWatchlistCollapsed, setIsWatchlistCollapsed] = useState(false)
  const [lastAnalyzedAt, setLastAnalyzedAt] = useState<string | null>(null)
  const [lastAnalyzedKey, setLastAnalyzedKey] = useState<string | null>(null)
  const [analysisHistory, setAnalysisHistory] = useState<Record<string, AnalysisHistoryEntry[]>>({})
  const pendingSearchAnalyzeSymbolRef = useRef<string | null>(null)

  const selectedSymbol = useMemo(() => {
    const querySymbol = searchParams.get('symbol')?.toUpperCase()
    const availableMarkets = marketItems.length ? marketItems : topMovers
    if (querySymbol && availableMarkets.some((item) => String(item.symbol ?? '').toUpperCase() === querySymbol)) {
      return querySymbol
    }
    return String((availableMarkets[0]?.symbol ?? querySymbol ?? 'BTCUSDT')).toUpperCase()
  }, [marketItems, searchParams, topMovers])

  const filteredMarketItems = useMemo(() => {
    const term = searchTerm.trim().toUpperCase()
    if (!term) return marketItems
    return marketItems.filter((item) => String(item.symbol ?? '').includes(term))
  }, [marketItems, searchTerm])
  const searchPrimaryResult = filteredMarketItems[0] ?? null

  function updateSelectedSymbol(symbol: string) {
    const nextSymbol = symbol.toUpperCase()
    setSearchParams((current) => {
      const next = new URLSearchParams(current)
      next.set('symbol', nextSymbol)
      return next
    }, { replace: true })
  }

  useEffect(() => {
    if (!isFullscreen) return undefined
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setIsFullscreen(false)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => {
      document.body.style.overflow = previous
      window.removeEventListener('keydown', onKeyDown)
    }
  }, [isFullscreen])

  const selectedMarket =
    marketItems.find((item) => String(item.symbol ?? '') === selectedSymbol) ??
    topMovers.find((item) => String(item.symbol ?? '') === selectedSymbol) ??
    null
  const selectedSignal =
    marketSignals.find((item) => String(item.symbol ?? '') === selectedSymbol) ??
    null

  const analysisQuery = useQuery({
    queryKey: ['analysis', selectedSymbol, selectedInterval, selectedMode],
    queryFn: () => fetchMarketAnalysis(selectedSymbol, selectedInterval, selectedMode),
    enabled: Boolean(selectedSymbol),
    refetchInterval: 45_000,
  })

  const klinesQuery = useQuery({
    queryKey: ['klines', selectedSymbol, selectedInterval],
    queryFn: () => fetchKlines(selectedSymbol, selectedInterval, 120),
    enabled: Boolean(selectedSymbol),
    refetchInterval: 45_000,
  })

  const analysis: AnalysisPayload | undefined = analysisQuery.data
  const snapshot = (analysis?.snapshot ?? {}) as JsonRecord
  const v6Result = ((analysis?.v6_result ?? {}) as JsonRecord)
  const v6Decision = ((v6Result.decision ?? {}) as JsonRecord)
  const v6Status = ((v6Result.status ?? {}) as JsonRecord)
  const v6Scores = ((v6Result.scores ?? {}) as JsonRecord)
  const v6ExecutionGuidance = ((v6Result.execution_guidance ?? {}) as JsonRecord)
  const v6Uncertainty = ((v6Result.uncertainty_quality ?? {}) as JsonRecord)
  const v6Deterministic = ((v6Result.deterministic_interaction ?? {}) as JsonRecord)
  const v6Fallback = ((v6Result.fallback_degradation ?? {}) as JsonRecord)
  const v6Observability = ((v6Result.observability ?? {}) as JsonRecord)
  const v6Identity = ((v6Result.identity ?? {}) as JsonRecord)
  const factors = Array.isArray(analysis?.factors) ? (analysis.factors as JsonRecord[]) : []
  const advancedAnalysis = (analysis?.advanced_analysis ?? {}) as JsonRecord
  const oscillatorRows = Array.isArray(advancedAnalysis.oscillators) ? (advancedAnalysis.oscillators as JsonRecord[]) : []
  const oscillatorSummary = (advancedAnalysis.summary ?? {}) as JsonRecord
  const direction = String(analysis?.direction ?? selectedSignal?.direction ?? selectedMarket?.direction ?? 'NEUTRAL')
  const confidenceValue = numericOrNull(analysis?.confidence)
  const regime = String(analysis?.regime ?? selectedSignal?.regime ?? snapshot.regime ?? snapshot.market_state ?? 'Unknown')
  const regimeDetail = firstNonBlank(
    analysis?.regime_detail,
    v6Deterministic.deterministic_warning,
    v6Deterministic.deterministic_disagreement_reason,
    v6Deterministic.regime_transition_risk,
    snapshot.regime_detail,
    snapshot.bias_reason,
    'Waiting for a fresh evaluation.',
  )
  const entryPrice = analysis?.entry_price ?? analysis?.entry ?? v6ExecutionGuidance.entry_price
  const stopLoss = analysis?.stop_loss ?? analysis?.sl ?? v6ExecutionGuidance.stop_loss
  const takeProfit = analysis?.take_profit ?? analysis?.tp ?? v6ExecutionGuidance.take_profit
  const riskReward = toNumber(analysis?.risk_reward ?? v6Scores.risk_reward_estimate)
  const tradeSummary = firstNonBlank(
    analysis?.summary,
    analysis?.reason_text,
    v6Decision.decision_summary,
    v6Observability.reason_summary,
    'The analyzer has not provided a narrative for this selection yet.',
  )
  const noTradeReason = String(analysis?.no_trade_reason ?? '')
  const expectedDuration = firstNonBlank(analysis?.expected_duration, formatBars(v6Scores.expected_hold_time))
  const recommendedSize = firstNonBlank(analysis?.recommended_size, formatPercentSize(v6ExecutionGuidance.size_multiplier))
  const v6ExecutionNotes = Array.isArray(v6ExecutionGuidance.execution_notes) ? v6ExecutionGuidance.execution_notes.map((item) => String(item)).filter(Boolean) : []
  const v6FeatureGroups = Array.isArray(v6Observability.top_feature_groups) ? v6Observability.top_feature_groups.map((item) => String(item)).filter(Boolean) : []
  const v6ReviewTags = Array.isArray(v6Observability.review_tags) ? v6Observability.review_tags.map((item) => String(item)).filter(Boolean) : []
  const v6DecisionSummaryRows = [
    ['Recommended Action', firstNonBlank(v6Decision.recommended_action, direction)],
    ['Signal Status', firstNonBlank(v6Status.signal_status, analysis?.signal_status)],
    ['Decision Status', firstNonBlank(v6Status.decision_status)],
    ['Actionable', v6Status.is_actionable == null ? '--' : (Boolean(v6Status.is_actionable) ? 'Yes' : 'No')],
    ['Decision Quality', firstNonBlank(v6Uncertainty.decision_quality)],
    ['Uncertainty', firstNonBlank(v6Uncertainty.uncertainty_type)],
    ['Constraint Level', firstNonBlank(v6Deterministic.constraint_level)],
    ['Deterministic Alignment', firstNonBlank(v6Deterministic.deterministic_alignment)],
    ['Execution Path', firstNonBlank(v6ExecutionGuidance.risk_expression)],
    ['Time Sensitivity', firstNonBlank(v6ExecutionGuidance.time_sensitivity)],
    ['Engine', firstNonBlank(v6Identity.engine_name, analysis?.engine_name)],
    ['Model Version', firstNonBlank(v6Identity.model_artifact_version, analysis?.engine_version)],
  ].filter(([, value]) => value && value !== '--')
  const analysisKey = `${selectedSymbol}:${selectedInterval}:${selectedMode}`
  const hasManualAnalysis = lastAnalyzedKey === analysisKey
  const isAnalyzing = analysisQuery.isFetching || klinesQuery.isFetching
  const ema9 = numericOrNull(snapshot.ema_9)
  const ema21 = numericOrNull(snapshot.ema_21)
  const ema50 = numericOrNull(snapshot.ema_50)
  const ema200 = numericOrNull(snapshot.ema_200)
  const bbUpper = numericOrNull(snapshot.bb_upper)
  const bbMid = numericOrNull(snapshot.bb_mid)
  const bbLower = numericOrNull(snapshot.bb_lower)
  const bbWidth = numericOrNull(snapshot.bb_width)
  const rsiSlope = numericOrNull(snapshot.rsi_slope)
  const macdHist = numericOrNull(snapshot.macd_hist)
  const macdHistDelta = numericOrNull(snapshot.macd_hist_delta)
  const buyVolumeShare = shareToPercent(snapshot.buy_volume_share)
  const sellVolumeShare = shareToPercent(snapshot.sell_volume_share)
  const flowImbalance = numericOrNull(snapshot.flow_imbalance)
  const bidDepth = numericOrNull(snapshot.orderbook_bid_depth)
  const askDepth = numericOrNull(snapshot.orderbook_ask_depth)
  const totalDepth = Math.max((bidDepth ?? 0) + (askDepth ?? 0), 1)
  const bidDepthShare = clampPercent(((bidDepth ?? 0) / totalDepth) * 100)
  const askDepthShare = clampPercent(((askDepth ?? 0) / totalDepth) * 100)
  const distToResist = numericOrNull(snapshot.dist_to_resist)
  const distToSupport = numericOrNull(snapshot.dist_to_support)
  const sessionLabel = String(snapshot.session_label ?? '--')
  const sessionLiquidity = shareToPercent(snapshot.session_liquidity_score)
  const lastPrice = numericOrNull(selectedMarket?.price)
  const emaLadder = [
    { label: 'EMA9', value: ema9 },
    { label: 'EMA21', value: ema21 },
    { label: 'EMA50', value: ema50 },
    { label: 'EMA200', value: ema200 },
  ]
  const factorRows = factors.map((factor, index) => {
    const score = numericOrNull(factor.score) ?? 0
    const weight = numericOrNull(factor.weight) ?? 1
    const weighted = score * weight
    return {
      id: `${String(factor.name ?? 'factor')}-${index}`,
      name: String(factor.name ?? 'Factor'),
      role: String(factor.role ?? 'CONTEXT'),
      signal: String(factor.signal ?? 'NEUTRAL'),
      reason: String(factor.reason ?? 'No reason supplied.'),
      used: factor.used !== false,
      score,
      weight,
      weighted,
    }
  })
  const maxFactorContribution = Math.max(...factorRows.map((factor) => Math.abs(factor.weighted)), 0.1)
  async function runFocusedAnalysis() {
    toast.loading(`Analyzing ${selectedSymbol} on ${selectedInterval}`, {
      id: 'market-analyze',
      description: `Mode: ${selectedMode.replaceAll('_', ' ')}`,
    })
    const [analysisResult, klinesResult] = await Promise.all([analysisQuery.refetch(), klinesQuery.refetch()])
    if (analysisResult.error || klinesResult.error) {
      const message = analysisResult.error instanceof Error
        ? analysisResult.error.message
        : klinesResult.error instanceof Error
          ? klinesResult.error.message
          : 'The Python analyzer did not return a valid response.'
      toast.error('Analyze failed', {
        id: 'market-analyze',
        description: message,
      })
      return
    }
    setLastAnalyzedAt(new Date().toISOString())
    setLastAnalyzedKey(analysisKey)
    const result = analysisResult.data
    const resultDirection = String(result?.direction ?? selectedSignal?.direction ?? selectedMarket?.direction ?? 'NEUTRAL')
    const resultConfidence = numericOrNull(result?.confidence) ?? 0
    const resultEntry = Number(result?.entry_price ?? result?.entry) || 0
    setAnalysisHistory((current) => {
      const nextEntry: AnalysisHistoryEntry = {
        symbol: selectedSymbol,
        interval: selectedInterval,
        mode: selectedMode,
        direction: resultDirection,
        confidence: resultConfidence,
        entry: resultEntry,
        timestamp: new Date().toISOString(),
      }
      const currentRows = current[selectedSymbol] ?? []
      return {
        ...current,
        [selectedSymbol]: [nextEntry, ...currentRows].slice(0, 8),
      }
    })
    toast.success('Analysis ready', {
      id: 'market-analyze',
      description: `${selectedSymbol} is now surfaced in the analysis sidebar.`,
    })
  }

  const triggerFocusedAnalysis = useEffectEvent(() => {
    void runFocusedAnalysis()
  })

  useEffect(() => {
    if (!pendingSearchAnalyzeSymbolRef.current || pendingSearchAnalyzeSymbolRef.current !== selectedSymbol) return
    pendingSearchAnalyzeSymbolRef.current = null
    triggerFocusedAnalysis()
  }, [selectedSymbol])

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.repeat || event.metaKey || event.ctrlKey || event.altKey) return
      const target = event.target
      if (
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target instanceof HTMLSelectElement ||
        (target instanceof HTMLElement && target.isContentEditable)
      ) {
        return
      }
      if (event.key.toLowerCase() !== 'a') return
      event.preventDefault()
      triggerFocusedAnalysis()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  if (marketOverviewQuery.isLoading && !marketOverview) {
    return (
      <AnimatedRoute>
        <EmptyState message="Loading market explorer..." />
      </AnimatedRoute>
    )
  }

  const analysisPanel = hasManualAnalysis ? (
    <div className="grid gap-5">
      <div className="grid gap-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="grid gap-2">
            <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">Focused Analysis</p>
            <div className="flex flex-wrap items-center gap-3">
              <StatusBadge label={direction} tone={badgeToneForDirection(direction)} />
              <span className="text-sm text-stone-500">{selectedInterval}</span>
              <span className="text-sm text-stone-500">{selectedMode.replaceAll('_', ' ')}</span>
            </div>
          </div>
          <div className="rounded-full bg-stone-950/[0.03] px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-stone-500">
            {lastAnalyzedAt ? new Date(lastAnalyzedAt).toLocaleTimeString() : 'Ready'}
          </div>
        </div>

        <div className="rounded-[1.4rem] border border-stone-900/8 bg-white p-4 shadow-[0_12px_24px_rgba(71,53,29,0.05)]">
          <div className="flex items-end justify-between gap-4">
            <div>
              <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">Confidence</p>
              <p className="mt-2 text-4xl font-semibold tracking-[-0.06em] text-stone-950">
                {confidenceValue === null ? '--' : `${confidenceValue.toFixed(0)}%`}
              </p>
            </div>
            <div className="text-right">
              <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">Regime</p>
              <p className="mt-2 text-sm font-semibold text-stone-950">{regime}</p>
            </div>
          </div>
          <div className="mt-4 h-2.5 overflow-hidden rounded-full bg-stone-200">
            <div
              className={`h-full rounded-full transition-all ${confidenceTone(confidenceValue)}`}
              style={{ width: `${Math.max(8, clampPercent(confidenceValue ?? 0))}%` }}
            />
          </div>
          {noTradeReason ? (
            <div className="mt-4 rounded-[1rem] border border-amber-200 bg-amber-50 px-4 py-3 text-sm font-medium text-amber-900">
              {noTradeReason}
            </div>
          ) : null}
          <p className="mt-4 text-sm leading-7 text-stone-600">{tradeSummary}</p>
        </div>
      </div>

      <div className="grid gap-3">
        {[
          ['Entry', formatNumber(entryPrice, 4)],
          ['Stop', formatNumber(stopLoss, 4)],
          ['Target', formatNumber(takeProfit, 4)],
          ['Risk / Reward', Number.isFinite(riskReward) && riskReward > 0 ? `${formatNumber(riskReward)}R` : '--'],
          ['Expected Duration', expectedDuration || '--'],
          ['Recommended Size', recommendedSize || '--'],
        ].map(([label, value]) => (
          <div key={label} className="flex items-center justify-between gap-3 rounded-[1.1rem] bg-stone-950/[0.03] px-4 py-3">
            <span className="text-sm text-stone-500">{label}</span>
            <span className="font-mono text-sm font-semibold text-stone-950">{value}</span>
          </div>
        ))}
      </div>

      <div className="rounded-[1.2rem] bg-stone-950/[0.03] p-4">
        <div className="flex items-center gap-2 text-sm font-semibold text-stone-950">
          <Gauge className="h-4 w-4 text-teal-800" strokeWidth={1.8} />
          Regime Detail
        </div>
        <p className="mt-3 text-sm leading-7 text-stone-600">{regimeDetail}</p>
      </div>

      <div className="grid gap-3 rounded-[1.2rem] bg-stone-950/[0.03] p-4">
        <div className="flex items-center justify-between gap-3">
          <div className="grid gap-1">
            <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">Market Context</p>
            <p className="text-sm font-semibold text-stone-950">EMA ladder, bands, and session state</p>
          </div>
          <span className="rounded-full bg-white px-3 py-1.5 text-xs font-semibold text-stone-700">
            {sessionLabel} {sessionLiquidity === null ? '' : `· ${formatNumber(sessionLiquidity, 0)}% liquidity`}
          </span>
        </div>

        <div className="grid gap-2">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-stone-500">EMA Ladder</p>
          <div className="grid gap-2 sm:grid-cols-2">
            {emaLadder.map((item) => (
              <div key={item.label} className="flex items-center justify-between gap-3 rounded-[1rem] bg-white px-3 py-2.5">
                <span className="text-sm text-stone-500">{item.label}</span>
                <span className={`font-mono text-sm font-semibold ${
                  lastPrice !== null && item.value !== null
                    ? lastPrice >= item.value ? 'text-teal-700' : 'text-rose-700'
                    : 'text-stone-700'
                }`}>
                  {formatMetricNumber(item.value, 2)}
                </span>
              </div>
            ))}
          </div>
        </div>

        <div className="grid gap-2 sm:grid-cols-2">
          <div className="rounded-[1rem] bg-white px-3 py-3">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-stone-500">Bollinger Bands</p>
            <p className="mt-2 text-sm text-stone-700">
              {formatMetricNumber(bbLower, 2)} / {formatMetricNumber(bbMid, 2)} / {formatMetricNumber(bbUpper, 2)}
            </p>
            <p className="mt-1 text-xs text-stone-500">Width {formatMetricPercent(bbWidth, 1)}</p>
          </div>
          <div className="rounded-[1rem] bg-white px-3 py-3">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-stone-500">Momentum Read</p>
            <p className="mt-2 text-sm text-stone-700">
              RSI slope {rsiSlope === null ? '--' : formatNumber(rsiSlope, 2)} · MACD hist {formatMetricNumber(macdHist, 3)}
            </p>
            <p className="mt-1 text-xs text-stone-500">Hist delta {formatMetricNumber(macdHistDelta, 3)}</p>
          </div>
        </div>

        <div className="grid gap-2 sm:grid-cols-2">
          <div className="rounded-[1rem] bg-white px-3 py-3">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-stone-500">Distance to Levels</p>
            <p className="mt-2 text-sm text-stone-700">Support {formatMetricPercent(distToSupport, 2)}</p>
            <p className="mt-1 text-sm text-stone-700">Resistance {formatMetricPercent(distToResist, 2)}</p>
          </div>
          <div className="rounded-[1rem] bg-white px-3 py-3">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-stone-500">Trend Context</p>
            <p className="mt-2 text-sm text-stone-700">{String(analysis?.trend ?? snapshot.trend ?? '--')}</p>
            <p className="mt-1 text-xs text-stone-500">Price {lastPrice === null ? '--' : formatNumber(lastPrice, 2)}</p>
          </div>
        </div>
      </div>

      <div className="grid gap-3 rounded-[1.2rem] bg-stone-950/[0.03] p-4">
        <div className="grid gap-1">
          <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">V6 Decision</p>
          <p className="text-sm font-semibold text-stone-950">Direct fields from the V6 analysis contract</p>
        </div>
        <div className="grid gap-2">
          {v6DecisionSummaryRows.length ? v6DecisionSummaryRows.map(([label, value]) => (
            <div key={label} className="flex items-center justify-between gap-3 rounded-[1rem] bg-white px-4 py-3">
              <span className="text-sm text-stone-500">{label}</span>
              <span className="text-right text-sm font-semibold text-stone-950">{value}</span>
            </div>
          )) : <EmptyState message="The current analyzer response did not expose V6 decision metadata for this symbol yet." />}
        </div>
        {v6ExecutionNotes.length ? (
          <div className="rounded-[1rem] bg-white px-4 py-3">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-stone-500">Execution Notes</p>
            <p className="mt-2 text-sm leading-7 text-stone-700">{v6ExecutionNotes.join(' · ')}</p>
          </div>
        ) : null}
        {v6FeatureGroups.length || v6ReviewTags.length ? (
          <div className="grid gap-2 sm:grid-cols-2">
            <div className="rounded-[1rem] bg-white px-4 py-3">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-stone-500">Top Feature Groups</p>
              <p className="mt-2 text-sm leading-7 text-stone-700">{v6FeatureGroups.length ? v6FeatureGroups.join(' · ') : '--'}</p>
            </div>
            <div className="rounded-[1rem] bg-white px-4 py-3">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-stone-500">Review Tags</p>
              <p className="mt-2 text-sm leading-7 text-stone-700">{v6ReviewTags.length ? v6ReviewTags.join(' · ') : '--'}</p>
            </div>
          </div>
        ) : null}
        {(Boolean(v6Fallback.fallback_used) || firstNonBlank(v6Fallback.fallback_reason, v6Fallback.degraded_reason)) ? (
          <div className="rounded-[1rem] border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
            {Boolean(v6Fallback.fallback_used) ? 'Fallback active.' : 'Degraded decision.'} {firstNonBlank(v6Fallback.fallback_reason, v6Fallback.degraded_reason)}
          </div>
        ) : null}
      </div>

      <div className="grid gap-3 rounded-[1.2rem] bg-stone-950/[0.03] p-4">
        <div className="grid gap-1">
          <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">Order Flow</p>
          <p className="text-sm font-semibold text-stone-950">Volume share and book pressure</p>
        </div>

        <div className="grid gap-2">
          <div className="flex items-center justify-between gap-3 text-sm">
            <span className="text-stone-500">Buy / Sell volume</span>
            <span className="font-semibold text-stone-950">
              {buyVolumeShare === null ? '--' : `${formatNumber(buyVolumeShare, 1)}%`} / {sellVolumeShare === null ? '--' : `${formatNumber(sellVolumeShare, 1)}%`}
            </span>
          </div>
          <div className="flex h-2.5 overflow-hidden rounded-full bg-stone-200">
            <div className="bg-teal-600" style={{ width: `${buyVolumeShare ?? 50}%` }} />
            <div className="bg-rose-500" style={{ width: `${sellVolumeShare ?? 50}%` }} />
          </div>
          <p className="text-xs text-stone-500">Flow imbalance {formatMetricNumber(flowImbalance, 3)}</p>
        </div>

        <div className="grid gap-2">
          <div className="flex items-center justify-between gap-3 text-sm">
            <span className="text-stone-500">Bid / Ask depth</span>
            <span className="font-semibold text-stone-950">
              {formatMetricNumber(bidDepth, 2)} / {formatMetricNumber(askDepth, 2)}
            </span>
          </div>
          <div className="flex h-2.5 overflow-hidden rounded-full bg-stone-200">
            <div className="bg-teal-600/90" style={{ width: `${bidDepthShare}%` }} />
            <div className="bg-rose-500/90" style={{ width: `${askDepthShare}%` }} />
          </div>
        </div>
      </div>

      <div className="grid gap-3 rounded-[1.2rem] bg-stone-950/[0.03] p-4">
        <div className="grid gap-1">
          <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">Signal Factors</p>
          <p className="text-sm font-semibold text-stone-950">Weighted contributors behind the decision</p>
        </div>
        <div className="grid gap-2">
          {factorRows.length ? factorRows.map((factor) => {
            const width = clampPercent((Math.abs(factor.weighted) / maxFactorContribution) * 100)
            const tone = factor.signal === 'BUY' ? 'text-teal-700' : factor.signal === 'SELL' ? 'text-rose-700' : 'text-stone-600'
            return (
              <div key={factor.id} className="rounded-[1rem] bg-white px-4 py-3 shadow-[0_10px_24px_rgba(71,53,29,0.04)]">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-semibold text-stone-950">{factor.name}</span>
                    <span className="rounded-full bg-stone-100 px-2 py-1 text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-stone-600">
                      {factor.role}
                    </span>
                    {!factor.used ? (
                      <span className="rounded-full bg-amber-50 px-2 py-1 text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-amber-700">
                        filtered
                      </span>
                    ) : null}
                  </div>
                  <span className={`text-sm font-semibold ${tone}`}>{factor.signal}</span>
                </div>
                <p className="mt-2 text-sm leading-6 text-stone-600">{factor.reason}</p>
                <div className="mt-3 grid gap-2 sm:grid-cols-[1fr_auto] sm:items-center">
                  <div className="h-2.5 overflow-hidden rounded-full bg-stone-200">
                    <div
                      className={`h-full rounded-full ${factor.weighted >= 0 ? 'bg-teal-600' : 'bg-rose-500'}`}
                      style={{ width: `${Math.max(6, width)}%` }}
                    />
                  </div>
                  <span className="text-xs font-semibold text-stone-500">
                    {formatNumber(factor.score, 2)} × {formatNumber(factor.weight, 2)} = {formatNumber(factor.weighted, 2)}
                  </span>
                </div>
              </div>
            )
          }) : <EmptyState message="Factor breakdown will appear once the analyzer returns interpretable factor rows." />}
        </div>
      </div>

      <div className="border-t border-stone-900/8 pt-4">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-sm font-semibold text-stone-950">
            <AudioWaveform className="h-4 w-4 text-teal-800" strokeWidth={1.8} />
            Oscillator Pulse
          </div>
          <div className="flex flex-wrap gap-2 text-xs">
            {[
              ['Buy', formatNumber(oscillatorSummary.Buy, 0), 'text-teal-700'],
              ['Neutral', formatNumber(oscillatorSummary.Neutral, 0), 'text-amber-700'],
              ['Sell', formatNumber(oscillatorSummary.Sell, 0), 'text-rose-700'],
            ].map(([label, value, tone]) => (
              <span key={label} className={`rounded-full bg-white px-2.5 py-1 font-semibold ${tone}`}>
                {label} {value}
              </span>
            ))}
          </div>
        </div>
        <div className="grid gap-2">
          {oscillatorRows.length ? oscillatorRows.map((row, index) => (
            <div key={`${String(row.name ?? 'osc')}-${index}`} className="grid gap-2 rounded-[1rem] bg-white px-4 py-3 shadow-[0_10px_24px_rgba(71,53,29,0.04)]">
              <div className="flex items-center justify-between gap-3">
                <span className="text-sm font-semibold text-stone-950">{String(row.name ?? 'Oscillator')}</span>
                <span className={`text-sm font-semibold ${oscillatorTone(String(row.action ?? ''))}`}>
                  {String(row.action ?? 'Neutral')}
                </span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-stone-200">
                <div
                  className={`h-full rounded-full ${
                    String(row.action ?? '') === 'Buy'
                      ? 'bg-teal-600'
                      : String(row.action ?? '') === 'Sell'
                        ? 'bg-rose-500'
                        : 'bg-amber-500'
                  }`}
                  style={{ width: `${Math.max(6, normalizeOscillator(String(row.name ?? ''), row.value) ?? 0)}%` }}
                />
              </div>
              <div className="flex items-center justify-between gap-3 text-sm">
                <span className="text-stone-500">Value</span>
                <span className="font-mono font-semibold text-stone-700">{String(row.value ?? '--')}</span>
              </div>
            </div>
          )) : <EmptyState message="Run analysis to surface advanced oscillator details." />}
        </div>
      </div>
    </div>
  ) : (
    <div className="flex min-h-full flex-col items-center justify-center gap-5 text-center">
      <div className="grid gap-2">
        <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">Analysis Sidebar</p>
        <h3 className="text-2xl font-semibold tracking-[-0.05em] text-stone-950">{selectedSymbol}</h3>
        <div className="flex flex-wrap items-center justify-center gap-3">
          <StatusBadge label={String(selectedSignal?.direction ?? direction)} tone={badgeToneForDirection(String(selectedSignal?.direction ?? direction))} />
          <span className="text-sm text-stone-500">{regime}</span>
        </div>
      </div>
      <p className="max-w-sm text-sm leading-7 text-stone-600">
        Run Analyze to lock a fresh read for this symbol. Signal direction, trade plan, and oscillator pulse will stay visible here while the chart remains in view.
      </p>
      <button
        type="button"
        className="inline-flex items-center justify-center gap-2 rounded-full bg-stone-950 px-5 py-3 text-sm font-semibold text-stone-50 transition hover:-translate-y-0.5 hover:bg-stone-900 disabled:cursor-not-allowed disabled:opacity-60"
        onClick={() => {
          void runFocusedAnalysis()
        }}
        disabled={isAnalyzing}
      >
        <Sparkles className="h-4 w-4" strokeWidth={1.8} />
        {isAnalyzing ? 'Analyzing...' : 'Analyze'}
      </button>
      <div className="grid w-full gap-3 rounded-[1.2rem] bg-stone-950/[0.03] p-4 text-left">
        <div className="flex items-center justify-between gap-3">
          <span className="text-sm text-stone-500">Last signal</span>
          <span className="text-sm font-semibold text-stone-950">{String(selectedSignal?.direction ?? 'Unknown')}</span>
        </div>
        <div className="flex items-center justify-between gap-3">
          <span className="text-sm text-stone-500">Trend</span>
          <span className="text-sm font-semibold text-stone-950">{String(selectedSignal?.trend ?? selectedMarket?.trend ?? '--')}</span>
        </div>
        <div className="flex items-center justify-between gap-3">
          <span className="text-sm text-stone-500">Shortcut</span>
          <span className="rounded bg-white px-2 py-1 font-mono text-xs font-semibold text-stone-700">A</span>
        </div>
      </div>
    </div>
  )

  const symbolHistory = analysisHistory[selectedSymbol] ?? []
  const heatmapItems = [...marketItems]
    .sort((left, right) => Math.abs(toNumber(right.change_pct)) - Math.abs(toNumber(left.change_pct)))
    .slice(0, 12)

  return (
    <AnimatedRoute>
      <div className="grid gap-4">
        <section className="sticky top-[5.7rem] z-10 rounded-[1.7rem] border border-stone-900/8 bg-white/86 px-4 py-3 shadow-[0_18px_40px_rgba(77,62,40,0.08)] backdrop-blur-xl sm:px-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2">
              {intervals.map((interval) => (
                <button
                  key={interval}
                  type="button"
                  className={`rounded-full px-4 py-2 text-sm font-semibold transition ${
                    selectedInterval === interval
                      ? 'bg-stone-950 text-stone-50'
                      : 'border border-stone-900/8 bg-stone-950/[0.03] text-stone-700 hover:bg-stone-950/[0.06]'
                  }`}
                  onClick={() => setSelectedInterval(interval)}
                >
                  {interval}
                </button>
              ))}
            </div>

            <div className="flex flex-wrap items-center gap-2">
              {modes.map((mode) => (
                <button
                  key={mode}
                  type="button"
                  className={`rounded-full px-4 py-2 text-sm font-semibold transition ${
                    selectedMode === mode
                      ? 'bg-teal-900 text-stone-50'
                      : 'border border-stone-900/8 bg-white text-stone-700 hover:bg-stone-950/[0.03]'
                  }`}
                  onClick={() => setSelectedMode(mode)}
                >
                  {mode.replaceAll('_', ' ')}
                </button>
              ))}
            </div>

            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                className="inline-flex items-center justify-center gap-2 rounded-full border border-stone-900/10 bg-white px-4 py-2.5 text-sm font-semibold text-stone-900 transition hover:bg-stone-950/[0.03]"
                onClick={() => setIsWatchlistCollapsed((value) => !value)}
              >
                {isWatchlistCollapsed ? <PanelLeftOpen className="h-4 w-4" strokeWidth={1.8} /> : <PanelLeftClose className="h-4 w-4" strokeWidth={1.8} />}
                {isWatchlistCollapsed ? 'Show Watchlist' : 'Collapse Watchlist'}
              </button>
              <button
                type="button"
                className="inline-flex items-center justify-center gap-2 rounded-full border border-stone-900/10 bg-white px-4 py-2.5 text-sm font-semibold text-stone-900 transition hover:bg-stone-950/[0.03]"
                onClick={() => setIsFullscreen(true)}
              >
                <Expand className="h-4 w-4" strokeWidth={1.8} />
                Focus Mode
              </button>
              <button
                type="button"
                className="inline-flex items-center justify-center gap-2 rounded-full bg-stone-950 px-5 py-2.5 text-sm font-semibold text-stone-50 transition hover:-translate-y-0.5 hover:bg-stone-900 disabled:cursor-not-allowed disabled:opacity-60"
                onClick={() => {
                  void runFocusedAnalysis()
                }}
                disabled={isAnalyzing}
              >
                <Sparkles className="h-4 w-4" strokeWidth={1.8} />
                {isAnalyzing ? 'Analyzing...' : 'Analyze'}
              </button>
            </div>
          </div>
        </section>

        <section className="overflow-hidden rounded-[1.5rem] border border-stone-900/8 bg-white/74 px-4 py-3 shadow-[0_18px_40px_rgba(77,62,40,0.08)]">
          {topMovers.length ? (
            <div className="flex gap-3 overflow-x-auto pb-1">
              {topMovers.slice(0, 14).map((item, index) => {
              const symbol = String(item.symbol ?? '--')
              const change = numericOrNull(item.change_pct) ?? 0
              const active = symbol === selectedSymbol
              return (
                <button
                  key={marketListKey(item as JsonRecord, index)}
                  type="button"
                  className={`shrink-0 rounded-full px-4 py-2 text-sm font-semibold transition ${
                    active
                      ? 'bg-stone-950 text-stone-50'
                      : 'bg-stone-950/[0.03] text-stone-700 hover:bg-stone-950/[0.06]'
                  }`}
                  onClick={() => updateSelectedSymbol(symbol)}
                >
                  <span>{symbol}</span>
                  <span className={`ml-3 ${active ? 'text-stone-200' : marketCardTone(change)}`}>{formatMetricPercent(item.change_pct, 2)}</span>
                </button>
              )
              })}
            </div>
          ) : <EmptyState message="Top movers will appear once the market runtime has enough live data for the active universe." />}
        </section>

        <div className={`grid gap-4 ${isWatchlistCollapsed ? 'lg:grid-cols-[4.5rem_minmax(0,1fr)]' : 'lg:grid-cols-[18rem_minmax(0,1fr)]'}`}>
          <aside className="rounded-[1.7rem] border border-stone-900/8 bg-white/82 shadow-[0_18px_40px_rgba(77,62,40,0.08)]">
            <div className="grid gap-3 p-3">
              <div className="flex items-center justify-between gap-3">
                {!isWatchlistCollapsed ? (
                  <div className="grid gap-1">
                    <p className="text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-stone-500">Watchlist</p>
                    <p className="text-sm text-stone-500">Collapse it once you’ve chosen a market.</p>
                  </div>
                ) : (
                  <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-2xl bg-stone-950 text-stone-50">
                    <Search className="h-4 w-4" strokeWidth={1.8} />
                  </div>
                )}
              </div>

              {!isWatchlistCollapsed ? (
                <label className="relative block">
                  <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-stone-400" strokeWidth={1.8} />
                  <input
                    value={searchTerm}
                    onChange={(event) => setSearchTerm(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key !== 'Enter' || !searchPrimaryResult) return
                      event.preventDefault()
                      const nextSymbol = String(searchPrimaryResult.symbol ?? '')
                      updateSelectedSymbol(nextSymbol)
                      setSearchTerm('')
                      if (event.metaKey || event.ctrlKey) {
                        pendingSearchAnalyzeSymbolRef.current = nextSymbol.toUpperCase()
                      }
                    }}
                    placeholder="Search symbol or pair"
                    className="w-full rounded-2xl border border-stone-900/8 bg-white px-11 py-3 text-sm text-stone-900 outline-none transition focus:border-teal-900/20 focus:ring-4 focus:ring-teal-900/6"
                  />
                </label>
              ) : null}

              {!isWatchlistCollapsed && searchTerm.trim() && searchPrimaryResult ? (
                <div className="rounded-2xl border border-stone-900/8 bg-stone-950/[0.03] p-3">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="grid gap-1">
                      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-stone-500">Top Match</p>
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold text-stone-950">
                          {String(searchPrimaryResult.symbol ?? '--')}
                        </span>
                        <span className={`text-sm font-semibold ${marketCardTone(numericOrNull(searchPrimaryResult.change_pct) ?? 0)}`}>
                          {formatMetricPercent(searchPrimaryResult.change_pct, 2)}
                        </span>
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        className="rounded-full border border-stone-900/8 bg-white px-3 py-2 text-sm font-semibold text-stone-700 transition hover:bg-stone-950/[0.03]"
                        onClick={() => {
                          updateSelectedSymbol(String(searchPrimaryResult.symbol ?? ''))
                          setSearchTerm('')
                        }}
                      >
                        Select
                      </button>
                      <button
                        type="button"
                        className="rounded-full bg-stone-950 px-3 py-2 text-sm font-semibold text-stone-50 transition hover:bg-stone-900"
                        onClick={() => {
                          const nextSymbol = String(searchPrimaryResult.symbol ?? '')
                          updateSelectedSymbol(nextSymbol)
                          setSearchTerm('')
                          pendingSearchAnalyzeSymbolRef.current = nextSymbol.toUpperCase()
                        }}
                      >
                        Select & Analyze
                      </button>
                    </div>
                  </div>
                  <p className="mt-2 text-xs text-stone-500">Press Enter to select, or Cmd/Ctrl+Enter to analyze immediately.</p>
                </div>
              ) : null}

              <div className={`grid gap-2 overflow-y-auto ${isWatchlistCollapsed ? 'max-h-[42rem]' : 'max-h-[46rem]'}`}>
                {filteredMarketItems.length ? filteredMarketItems.slice(0, isWatchlistCollapsed ? 24 : 100).map((item, index) => {
                  const symbol = String(item.symbol ?? '--')
                  const change = numericOrNull(item.change_pct) ?? 0
                  const active = symbol === selectedSymbol
                  return (
                    <button
                      key={marketListKey(item as JsonRecord, index)}
                      type="button"
                      className={`text-left transition ${
                        isWatchlistCollapsed
                          ? `mx-auto flex h-12 w-12 items-center justify-center rounded-2xl font-semibold ${
                              active ? 'bg-stone-950 text-stone-50' : 'bg-stone-950/[0.03] text-stone-700 hover:bg-stone-950/[0.06]'
                            }`
                          : `flex items-center justify-between rounded-2xl px-4 py-4 ${
                              active ? 'bg-stone-950 text-stone-50 shadow-[0_14px_28px_rgba(28,26,23,0.12)]' : 'bg-white/80 hover:bg-white'
                            }`
                      }`}
                      onClick={() => updateSelectedSymbol(symbol)}
                      title={symbol}
                    >
                      {isWatchlistCollapsed ? (
                        <span className="relative text-xs">
                          {compactSymbol(symbol).slice(0, 4)}
                          <span className={`absolute -right-1 -top-1 h-2.5 w-2.5 rounded-full ${directionDot(String(item.direction ?? ''))}`} />
                        </span>
                      ) : (
                        <>
                          <div className="grid gap-1">
                            <span className={`flex items-center gap-2 text-sm font-semibold ${active ? 'text-stone-50' : 'text-stone-950'}`}>
                              <span className={`h-2.5 w-2.5 rounded-full ${active ? 'bg-stone-50' : directionDot(String(item.direction ?? ''))}`} />
                              {symbol}
                            </span>
                            <span className={`text-sm ${active ? 'text-stone-300' : 'text-stone-500'}`}>{formatMetricNumber(item.price, 4)}</span>
                          </div>
                          <span className={`text-sm font-semibold ${active ? 'text-stone-50' : marketCardTone(change)}`}>
                            {formatMetricPercent(item.change_pct, 2)}
                          </span>
                        </>
                      )}
                    </button>
                  )
                }) : <EmptyState message="No symbols matched your search." />}
              </div>
            </div>
          </aside>

          <section className="grid gap-4">
            <div className="grid gap-4 xl:h-[44rem] xl:grid-cols-[1.55fr_0.85fr]">
              <div className={`relative overflow-hidden rounded-[1.9rem] border border-stone-900/8 bg-white/86 p-4 shadow-[0_24px_60px_rgba(77,62,40,0.08)] ${isAnalyzing ? 'ring-2 ring-teal-500/30' : ''}`}>
                {isAnalyzing ? <div className="pointer-events-none absolute inset-0 animate-pulse rounded-[1.9rem] border border-teal-500/40" /> : null}
                <div className="mb-4 flex flex-wrap items-start justify-between gap-4">
                  <div className="grid gap-2">
                    <div className="flex flex-wrap items-center gap-3">
                      <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-stone-950 text-stone-50">
                        <CandlestickChart className="h-5 w-5" strokeWidth={1.8} />
                      </div>
                      <div>
                        <div className="flex flex-wrap items-center gap-3">
                          <h2 className="text-3xl font-semibold tracking-[-0.06em] text-stone-950">{selectedSymbol}</h2>
                          <span className="font-mono text-lg text-stone-600">{formatMetricNumber(selectedMarket?.price, 4)}</span>
                          <StatusBadge label={direction} tone={badgeToneForDirection(direction)} />
                          <span className={`text-sm font-semibold ${marketCardTone(numericOrNull(selectedMarket?.change_pct) ?? 0)}`}>
                            {formatMetricPercent(selectedMarket?.change_pct, 2)}
                          </span>
                        </div>
                        <p className="mt-2 text-sm text-stone-500">
                          {lastAnalyzedAt ? `Last manual analyze: ${new Date(lastAnalyzedAt).toLocaleString()}` : 'Analyze to populate the permanent trade-plan sidebar.'}
                        </p>
                      </div>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-3 text-sm text-stone-500">
                    <span className="rounded-full bg-stone-950/[0.03] px-3 py-2">{formatMetricCompact(selectedMarket?.quote_volume ?? selectedMarket?.volume, ' volume')}</span>
                    <span className="rounded-full bg-stone-950/[0.03] px-3 py-2">{formatMetricCompact(selectedMarket?.count, ' trades')}</span>
                    <span className="rounded-full bg-stone-950/[0.03] px-3 py-2">{regime}</span>
                    <span className="rounded-full bg-stone-950/[0.03] px-3 py-2">
                      {sessionLabel}{sessionLiquidity === null ? '' : ` · ${formatNumber(sessionLiquidity, 0)}% liquidity`}
                    </span>
                  </div>
                </div>

                <CandleCanvas
                  rows={klinesQuery.data ?? []}
                  title={`${selectedSymbol} · ${selectedInterval}`}
                  height={600}
                  theme={darkMode ? 'dark' : 'light'}
                  levels={{
                    entry: Number(entryPrice) || null,
                    zoneLow: Number(analysis?.entry_zone_low) || null,
                    zoneHigh: Number(analysis?.entry_zone_high) || null,
                    stopLoss: Number(stopLoss) || null,
                    takeProfit: Number(takeProfit) || null,
                  }}
                />
              </div>

              <section className="min-h-0 rounded-[1.8rem] border border-stone-900/8 bg-white/86 p-4 shadow-[0_24px_60px_rgba(77,62,40,0.08)]">
                <div className="mb-4 flex items-center justify-between gap-3">
                  <div className="grid gap-1">
                    <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">Analysis</p>
                    <h2 className="text-lg font-semibold tracking-[-0.04em] text-stone-950">Trade plan and oscillator pulse</h2>
                  </div>
                  <span className="rounded-full bg-stone-950/[0.03] px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-stone-500">A shortcut</span>
                </div>
                <div className="max-h-[36rem] overflow-y-auto pr-1">
                  {analysisPanel}
                </div>
              </section>
            </div>
          </section>
        </div>

        <div className="grid gap-4 xl:grid-cols-[1.55fr_0.85fr]">
          <section className="rounded-[1.6rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_18px_40px_rgba(77,62,40,0.08)]">
            <div className="mb-4 flex items-center justify-between gap-3">
              <div className="grid gap-1">
                <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">Heatmap</p>
                <h2 className="text-lg font-semibold tracking-[-0.04em] text-stone-950">Universe scan at a glance</h2>
              </div>
              <span className="text-sm text-stone-500">Tap a tile to focus the chart</span>
            </div>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {heatmapItems.length ? heatmapItems.map((item, index) => {
                const symbol = String(item.symbol ?? '--')
                const change = numericOrNull(item.change_pct) ?? 0
                const active = symbol === selectedSymbol
                const intensity = Math.min(0.22 + Math.abs(change) / 20, 0.5)
                const background = darkMode
                  ? change >= 0
                    ? `linear-gradient(135deg, rgba(20,92,86,${Math.min(intensity + 0.06, 0.55)}), rgba(15,23,42,0.94))`
                    : `linear-gradient(135deg, rgba(190,24,93,${Math.min(intensity + 0.08, 0.58)}), rgba(15,23,42,0.94))`
                  : change >= 0
                    ? `linear-gradient(135deg, rgba(20,92,86,${intensity}), rgba(255,255,255,0.96))`
                    : `linear-gradient(135deg, rgba(190,24,93,${intensity}), rgba(255,255,255,0.96))`
                return (
                  <button
                    key={marketListKey(item as JsonRecord, index)}
                    type="button"
                    onClick={() => updateSelectedSymbol(symbol)}
                    className={`rounded-[1.35rem] border p-4 text-left shadow-[0_12px_24px_rgba(71,53,29,0.04)] transition hover:-translate-y-0.5 ${
                      darkMode
                        ? active
                          ? 'border-white/18 ring-1 ring-white/10'
                          : 'border-white/8'
                        : active
                          ? 'border-stone-950/20'
                          : 'border-stone-900/8'
                    }`}
                    style={{ background }}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="grid gap-1">
                        <strong className={`text-base font-semibold ${darkMode ? 'text-stone-50' : 'text-stone-950'}`}>{symbol}</strong>
                        <span className={`text-sm ${darkMode ? 'text-stone-300' : 'text-stone-600'}`}>{formatMetricNumber(item.price, 4)}</span>
                      </div>
                      <span className={`text-sm font-semibold ${darkMode ? (change >= 0 ? 'text-emerald-300' : 'text-rose-300') : marketCardTone(change)}`}>
                        {formatMetricPercent(item.change_pct, 2)}
                      </span>
                    </div>
                    <div className={`mt-3 text-xs uppercase tracking-[0.16em] ${darkMode ? 'text-stone-300' : 'text-stone-500'}`}>
                      {formatMetricCompact(item.quote_volume ?? item.volume, ' volume')}
                    </div>
                  </button>
                )
              }) : <EmptyState message="Heatmap tiles will appear once real market data is available for the active universe." />}
            </div>
          </section>

          <section className="rounded-[1.5rem] border border-stone-900/8 bg-white/82 p-4 shadow-[0_18px_40px_rgba(77,62,40,0.08)]">
            <div className="mb-4 flex items-center justify-between gap-3">
              <div className="grid gap-1">
                <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">Analysis History</p>
                <h2 className="text-lg font-semibold tracking-[-0.04em] text-stone-950">
                  Recent reads for {selectedSymbol}
                </h2>
              </div>
              <span className="text-sm text-stone-500">{symbolHistory.length} stored</span>
            </div>
            <div className="grid gap-3">
              {symbolHistory.length ? symbolHistory.map((item, index) => (
                <div key={`${item.timestamp}-${index}`} className="grid gap-3 rounded-[1.25rem] bg-stone-950/[0.03] p-4 md:grid-cols-[0.85fr_0.55fr_0.5fr_auto] md:items-center">
                  <div className="grid gap-1">
                    <div className="flex items-center gap-2">
                      <StatusBadge label={item.direction} tone={badgeToneForDirection(item.direction)} />
                      <span className="text-sm font-semibold text-stone-950">{item.confidence.toFixed(0)}%</span>
                    </div>
                    <span className="text-sm text-stone-500">{item.mode.replaceAll('_', ' ')} / {item.interval}</span>
                  </div>
                  <div className="font-mono text-sm font-semibold text-stone-950">
                    {formatNumber(item.entry, 4)}
                  </div>
                  <div className="text-sm text-stone-500">{new Date(item.timestamp).toLocaleTimeString()}</div>
                  <button
                    type="button"
                    className="rounded-full border border-stone-900/8 bg-white px-3 py-2 text-sm font-semibold text-stone-700 transition hover:bg-stone-950/[0.03]"
                    onClick={() => {
                      setSelectedInterval(item.interval)
                      setSelectedMode(item.mode)
                      setLastAnalyzedKey(`${selectedSymbol}:${item.interval}:${item.mode}`)
                    }}
                  >
                    Revisit
                  </button>
                </div>
              )) : <EmptyState message="Run Analyze a few times to build local session history for this symbol." />}
            </div>
          </section>
        </div>
      </div>

      <AnimatePresence>
        {isFullscreen ? (
          <motion.div
            className="fixed inset-0 z-40 bg-[rgba(20,17,14,0.78)] p-3 backdrop-blur-md sm:p-5"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <motion.div
              className="mx-auto grid h-full w-full max-w-[1720px] grid-rows-[auto_1fr] gap-4 rounded-[2rem] border border-white/10 bg-[linear-gradient(180deg,rgba(26,23,20,0.97),rgba(18,16,14,0.99))] p-4 text-stone-50 shadow-[0_28px_80px_rgba(0,0,0,0.3)] sm:p-5"
              initial={{ scale: 0.97, y: 16 }}
              animate={{ scale: 1, y: 0 }}
              exit={{ scale: 0.98, y: 10 }}
              transition={{ duration: 0.2, ease: 'easeOut' }}
            >
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="grid gap-2">
                  <p className="text-[0.72rem] font-semibold uppercase tracking-[0.22em] text-teal-300">Focused Analysis</p>
                  <div className="flex flex-wrap items-center gap-3">
                    <h2 className="text-3xl font-semibold tracking-[-0.05em] text-stone-50">{selectedSymbol}</h2>
                    <StatusBadge label={direction} tone={badgeToneForDirection(direction)} />
                    <span className="text-sm text-stone-300">{selectedInterval}</span>
                    <span className="text-sm text-stone-300">{selectedMode.replaceAll('_', ' ')}</span>
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    className="inline-flex items-center justify-center gap-2 rounded-full bg-white px-4 py-2.5 text-sm font-semibold text-stone-950 transition hover:bg-stone-100"
                    onClick={() => {
                      void runFocusedAnalysis()
                    }}
                    disabled={analysisQuery.isFetching || klinesQuery.isFetching}
                  >
                    <Sparkles className="h-4 w-4" strokeWidth={1.8} />
                    {analysisQuery.isFetching || klinesQuery.isFetching ? 'Analyzing...' : 'Analyze'}
                  </button>
                  <button
                    type="button"
                    className="inline-flex items-center justify-center gap-2 rounded-full border border-white/12 bg-white/6 px-4 py-2.5 text-sm font-semibold text-stone-50 transition hover:bg-white/10"
                    onClick={() => setIsFullscreen(false)}
                  >
                    <X className="h-4 w-4" strokeWidth={1.8} />
                    Close
                  </button>
                </div>
              </div>

              <div className="grid min-h-0 gap-4 lg:grid-cols-[1.55fr_0.45fr]">
                <div className="min-h-0 rounded-[1.6rem] border border-white/8 bg-white/4 p-3">
                  <CandleCanvas
                    rows={klinesQuery.data ?? []}
                    title={`${selectedSymbol} · ${selectedInterval} · focus mode`}
                    height={720}
                    theme="dark"
                    levels={{
                      entry: Number(entryPrice) || null,
                      zoneLow: Number(analysis?.entry_zone_low) || null,
                      zoneHigh: Number(analysis?.entry_zone_high) || null,
                      stopLoss: Number(stopLoss) || null,
                      takeProfit: Number(takeProfit) || null,
                    }}
                  />
                </div>
                <div className="grid min-h-0 gap-4 overflow-y-auto rounded-[1.6rem] border border-white/8 bg-white/4 p-4">
                  <div className="grid gap-3">
                    <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-300">Trade Plan</p>
                    {[
                      ['Entry', formatNumber(entryPrice, 4)],
                      ['Stop', formatNumber(stopLoss, 4)],
                      ['Target', formatNumber(takeProfit, 4)],
                      ['Confidence', confidenceValue === null ? '--' : `${confidenceValue.toFixed(0)}%`],
                      ['Risk / Reward', Number.isFinite(riskReward) && riskReward > 0 ? `${formatNumber(riskReward)}R` : '--'],
                      ['Duration', expectedDuration || '--'],
                    ].map(([label, value]) => (
                      <div key={label} className="rounded-2xl border border-white/8 bg-white/6 p-4">
                        <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-300">{label}</p>
                        <p className="mt-2 font-mono text-lg font-semibold text-stone-50">{value}</p>
                      </div>
                    ))}
                  </div>
                  <div className="grid gap-3">
                    <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-300">Narrative</p>
                    <div className="rounded-2xl border border-white/8 bg-white/6 p-4 text-sm leading-7 text-stone-300">
                      {noTradeReason || tradeSummary}
                    </div>
                  </div>
                  <div className="grid gap-3">
                    <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-300">Oscillator Pulse</p>
                    <div className="grid gap-3">
                      {oscillatorRows.length ? oscillatorRows.slice(0, 8).map((row, index) => (
                        <div key={`${String(row.name ?? 'osc-full')}-${index}`} className="rounded-2xl border border-white/8 bg-white/6 p-4">
                          <div className="flex items-center justify-between gap-3">
                            <span className="text-sm font-semibold text-stone-50">{String(row.name ?? 'Oscillator')}</span>
                            <span className={`text-sm font-semibold ${String(row.action ?? '') === 'Buy' ? 'text-teal-300' : String(row.action ?? '') === 'Sell' ? 'text-rose-300' : 'text-stone-300'}`}>
                              {String(row.action ?? 'Neutral')}
                            </span>
                          </div>
                          <p className="mt-2 text-sm text-stone-300">Value {String(row.value ?? '--')}</p>
                        </div>
                      )) : <EmptyState message="Run analysis to load oscillator details in focus mode." />}
                    </div>
                  </div>
                </div>
              </div>
            </motion.div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </AnimatedRoute>
  )
}
