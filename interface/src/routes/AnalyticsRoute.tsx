import { Navigate } from 'react-router-dom'

export function AnalyticsRoute() {
  return <Navigate replace to="/review/engine/performance" />
}

const LOOKBACK_OPTIONS = [
  { label: 'Last 7 days', value: '7' },
  { label: 'Last 30 days', value: '30' },
  { label: 'Last 90 days', value: '90' },
  { label: 'All time', value: '0' },
]

const MIN_SAMPLE_OPTIONS = [
  { label: 'Min 5', value: '5' },
  { label: 'Min 10', value: '10' },
  { label: 'Min 20', value: '20' },
]

const MODE_OPTIONS = [
  { label: 'All modes', value: 'ALL' },
  { label: 'SWING', value: 'SWING' },
  { label: 'SCALP', value: 'SCALP' },
  { label: 'AGGRESSIVE_SCALP', value: 'AGGRESSIVE_SCALP' },
]

const DIRECTION_OPTIONS = [
  { label: 'All directions', value: 'ALL' },
  { label: 'BUY', value: 'BUY' },
  { label: 'SELL', value: 'SELL' },
]

function reliabilityTone(reliability: string | undefined) {
  if (reliability === 'STABLE') return 'bg-teal-100 text-teal-900'
  if (reliability === 'BUILDING_SAMPLE') return 'bg-amber-100 text-amber-900'
  return 'bg-stone-200 text-stone-800'
}

function validationTone(status: string | undefined) {
  if (status === 'PASS') return 'bg-teal-100 text-teal-900'
  if (status === 'PARTIAL') return 'bg-amber-100 text-amber-900'
  return 'bg-rose-100 text-rose-900'
}

function ValidationMetric({
  label,
  value,
  note,
}: {
  label: string
  value: string
  note?: string
}) {
  return (
    <div className="rounded-[1rem] bg-stone-950/[0.03] px-4 py-3">
      <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">{label}</p>
      <p className="mt-2 text-sm font-semibold text-stone-950">{value}</p>
      {note ? <p className="mt-1 text-xs text-stone-500">{note}</p> : null}
    </div>
  )
}

function SwingPatchValidationPanel({
  report,
  onExport,
}: {
  report: SwingPatchValidationPayload
  onExport: () => Promise<void>
}) {
  const checks = report.checks ?? []
  const failedChecks = checks.filter((item) => !item.passed)
  const hardGateRows = Object.entries(report.hard_gates ?? {})
  const regimeCounts = Object.entries(report.regimes?.counts ?? {})
  const regimeWinRates = Object.entries(report.regimes?.win_rates ?? {})

  return (
    <section className="rounded-[1.2rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_12px_24px_rgba(77,62,40,0.06)]">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="grid gap-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-sm font-semibold text-stone-950">Swing patch validation</h2>
            <span className={`rounded-full px-3 py-1 text-xs font-semibold ${validationTone(String(report.overall_status ?? 'FAIL'))}`}>
              {report.overall_status ?? 'UNKNOWN'}
            </span>
          </div>
          <p className="text-xs text-stone-500">
            Sample {formatNumber(report.sample_size, 0)} · Source {String(report.run_source ?? 'unknown')} · Baseline {String(report.baseline?.baseline_id ?? '--')}
          </p>
        </div>
        <button type="button" onClick={() => void onExport()} className="inline-flex items-center gap-2 rounded-full border border-stone-900/8 bg-white px-4 py-2 text-sm font-semibold text-stone-800 transition hover:bg-stone-950/[0.03]">
          <Download className="h-4 w-4" strokeWidth={1.8} />
          Export validation CSV
        </button>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-4">
        <ValidationMetric label="Release gate" value={String(report.release_recommendation ?? '--')} />
        <ValidationMetric label="Hard gates" value={`${hardGateRows.filter(([, passed]) => passed).length}/${hardGateRows.length || 0} passed`} />
        <ValidationMetric label="Failed checks" value={formatNumber(failedChecks.length, 0)} />
        <ValidationMetric label="Generated" value={formatTime(report.generated_at)} />
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <section className="rounded-[1rem] bg-stone-950/[0.03] p-4">
          <h3 className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">Stops</h3>
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            <ValidationMetric label="% STOP_TOO_TIGHT" value={`${formatNumber(toNumber(report.stops?.stop_too_tight_pct) * 100, 1)}%`} note={`Delta ${formatNumber(report.stops?.delta_vs_bad_baseline?.stop_too_tight_pct, 2)}`} />
            <ValidationMetric label="% STOP_STRUCTURALLY_WRONG" value={`${formatNumber(toNumber(report.stops?.stop_structurally_wrong_pct) * 100, 1)}%`} note={`Delta ${formatNumber(report.stops?.delta_vs_bad_baseline?.stop_structurally_wrong_pct, 2)}`} />
            <ValidationMetric label="Avg stop distance ATR" value={formatNumber(report.stops?.avg_stop_distance_atr, 2)} />
            <ValidationMetric label="Avg structural gap ATR" value={formatNumber(report.stops?.avg_structure_gap_atr, 2)} />
          </div>
        </section>

        <section className="rounded-[1rem] bg-stone-950/[0.03] p-4">
          <h3 className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">Stale exits</h3>
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            <ValidationMetric label="Swing EARLY_STALE_EXIT" value={formatNumber(report.stale_exits?.swing_early_stale_exit_count, 0)} note={`Delta ${formatNumber(report.stale_exits?.delta_vs_bad_baseline?.swing_early_stale_exit_count, 0)}`} />
            <ValidationMetric label="Swing 1h+ EARLY_STALE_EXIT" value={formatNumber(report.stale_exits?.swing_1h_plus_early_stale_exit_count, 0)} note={`Delta ${formatNumber(report.stale_exits?.delta_vs_bad_baseline?.swing_1h_plus_early_stale_exit_count, 0)}`} />
            <ValidationMetric label="Swing TIME_STOP count" value={formatNumber(report.stale_exits?.swing_time_stop_count, 0)} />
          </div>
        </section>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <section className="rounded-[1rem] bg-stone-950/[0.03] p-4">
          <h3 className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">Regimes</h3>
          <div className="mt-3 grid gap-3">
            <div className="rounded-[1rem] bg-white px-4 py-3 text-sm text-stone-700">
              Distribution shift {report.regimes?.distribution_shift_ok ? 'OK' : 'FAILED'}
            </div>
            {regimeCounts.length ? regimeCounts.map(([label, count]) => (
              <div key={`count-${label}`} className="flex items-center justify-between rounded-[1rem] bg-white px-4 py-3 text-sm text-stone-800">
                <span>{label}</span>
                <span>{formatNumber(count, 0)} trades</span>
              </div>
            )) : <p className="text-sm text-stone-500">No regime rows in sample.</p>}
            {regimeWinRates.length ? regimeWinRates.map(([label, value]) => (
              <div key={`wr-${label}`} className="flex items-center justify-between rounded-[1rem] bg-white px-4 py-3 text-sm text-stone-800">
                <span>{label} win rate</span>
                <span>{formatNumber(value * 100, 1)}%</span>
              </div>
            )) : null}
          </div>
        </section>

        <section className="rounded-[1rem] bg-stone-950/[0.03] p-4">
          <h3 className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">Confidence</h3>
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            <ValidationMetric label="Accepted before" value={formatNumber(report.confidence?.accepted_signal_count_before, 0)} />
            <ValidationMetric label="Accepted after" value={formatNumber(report.confidence?.accepted_signal_count_after, 0)} />
            <ValidationMetric label="Calibration gap" value={formatNumber(report.confidence?.bucket_calibration_gap, 2)} />
            <ValidationMetric label="70-80 gap" value={formatNumber(report.confidence?.bucket_70_80_gap, 2)} note={`Delta ${formatNumber(report.confidence?.delta_vs_bad_baseline?.bucket_70_80_gap, 2)}`} />
            <ValidationMetric label="Penalty affected count" value={formatNumber(report.confidence?.component_penalty_affected_count, 0)} />
            <ValidationMetric label="Low-confidence flood" value={report.confidence?.low_confidence_flood_flag ? 'Yes' : 'No'} />
          </div>
        </section>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <section className="rounded-[1rem] bg-stone-950/[0.03] p-4">
          <h3 className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">Hard gates</h3>
          <div className="mt-3 grid gap-3">
            {hardGateRows.map(([key, passed]) => (
              <div key={key} className={`flex items-center justify-between rounded-[1rem] px-4 py-3 text-sm ${passed ? 'bg-teal-50 text-teal-900' : 'bg-rose-50 text-rose-900'}`}>
                <span>{key}</span>
                <span>{passed ? 'PASS' : 'FAIL'}</span>
              </div>
            ))}
          </div>
        </section>

        <section className="rounded-[1rem] bg-stone-950/[0.03] p-4">
          <h3 className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">Failed checks</h3>
          <div className="mt-3 grid gap-3">
            {failedChecks.length ? failedChecks.map((item) => (
              <div key={String(item.key)} className={`rounded-[1rem] px-4 py-3 text-sm ${item.severity === 'hard' ? 'bg-rose-50 text-rose-900' : 'bg-amber-50 text-amber-900'}`}>
                <div className="font-semibold">{item.key}</div>
                <div className="mt-1 text-xs">{item.reason}</div>
              </div>
            )) : (
              <div className="rounded-[1rem] bg-teal-50 px-4 py-3 text-sm text-teal-900">No failed checks in this sample.</div>
            )}
          </div>
        </section>
      </div>
    </section>
  )
}

function LeaderboardTable({
  title,
  rows,
}: {
  title: string
  rows: TradeAnalyticsGroupRow[]
}) {
  return (
    <section className="rounded-[1.2rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_12px_24px_rgba(77,62,40,0.06)]">
      <h2 className="text-sm font-semibold text-stone-950">{title}</h2>
      {rows.length ? (
        <div className="mt-4 overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="text-left text-stone-500">
              <tr>
                <th className="pb-2 pr-4">Method</th>
                <th className="pb-2 pr-4 text-right">Trades</th>
                <th className="pb-2 pr-4 text-right">Win</th>
                <th className="pb-2 pr-4 text-right">Avg R</th>
                <th className="pb-2 pr-4 text-right">Net R</th>
                <th className="pb-2 pr-4 text-right">PF</th>
                <th className="pb-2 pr-4 text-right">MDD</th>
                <th className="pb-2 pr-4 text-right">Hold</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={String(row.label)} className="border-t border-stone-900/8 align-top">
                  <td className="py-3 pr-4">
                    <div className="grid gap-1">
                      <Link to={`/trades?method=${encodeURIComponent(String(row.label ?? ''))}`} className="font-semibold text-stone-950 hover:text-teal-800">
                        {row.label}
                      </Link>
                      <div className="flex flex-wrap gap-2 text-xs">
                        <span className={`rounded-full px-2 py-1 font-semibold ${reliabilityTone(String(row.reliability ?? 'LOW_SAMPLE'))}`}>{row.reliability}</span>
                        {row.reason_summary ? <span className="text-stone-500">{row.reason_summary}</span> : null}
                      </div>
                    </div>
                  </td>
                  <td className="py-3 pr-4 text-right text-stone-700">{formatNumber(row.trades, 0)}</td>
                  <td className="py-3 pr-4 text-right text-stone-700">{formatNumber(toNumber(row.win_rate) * 100, 1)}%</td>
                  <td className={`py-3 pr-4 text-right font-semibold ${toNumber(row.avg_realized_r) >= 0 ? 'text-teal-800' : 'text-rose-700'}`}>{formatNumber(row.avg_realized_r, 2)}</td>
                  <td className={`py-3 pr-4 text-right font-semibold ${toNumber(row.net_r) >= 0 ? 'text-teal-800' : 'text-rose-700'}`}>{formatNumber(row.net_r, 2)}</td>
                  <td className="py-3 pr-4 text-right text-stone-700">{formatNumber(row.profit_factor, 2)}</td>
                  <td className="py-3 pr-4 text-right text-stone-700">{formatNumber(row.max_drawdown_r, 2)}</td>
                  <td className="py-3 pr-4 text-right text-stone-700">{formatNumber(row.avg_hold_minutes, 0)}m</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="mt-3 text-sm text-stone-500">No ranked rows for this scope.</p>
      )}
    </section>
  )
}

function LegacyAnalyticsRouteUnused() {
  const [activeTab, setActiveTab] = useState<'performance' | 'improvements'>('performance')
  const [searchParams, setSearchParams] = useSearchParams()
  const lookback = searchParams.get('lookback') ?? '30'
  const minSamples = searchParams.get('min_samples') ?? '10'
  const mode = searchParams.get('mode') ?? 'ALL'
  const symbol = searchParams.get('symbol') ?? ''
  const interval = searchParams.get('interval') ?? 'ALL'
  const direction = searchParams.get('direction') ?? 'ALL'

  const payloadQuery = useQuery({
    queryKey: ['trade-analytics', lookback, minSamples, mode, symbol, interval, direction],
    queryFn: () => getTradeAnalytics(Number(lookback), Number(minSamples), { mode, symbol, interval, direction }),
    refetchOnWindowFocus: false,
  })
  const improvementsQuery = useQuery({
    queryKey: ['improvement-analytics', lookback, minSamples, mode, symbol, interval, direction],
    queryFn: () => getImprovementAnalytics(Number(lookback), Number(minSamples), { mode, symbol, interval, direction }),
    refetchOnWindowFocus: false,
  })
  const swingPatchValidationQuery = useQuery({
    queryKey: ['swing-patch-validation', lookback],
    queryFn: () => getSwingPatchValidation(Number(lookback), 60),
    refetchOnWindowFocus: false,
  })
  const symbolsQuery = useQuery({
    queryKey: ['symbols', 'analytics'],
    queryFn: fetchSymbols,
    refetchOnWindowFocus: false,
    staleTime: 60_000,
  })

  const payload = (payloadQuery.data ?? {}) as TradeAnalyticsPayload
  const overview = payload.overview ?? {}
  const leaderboards = payload.leaderboards ?? {}
  const timing = payload.timing ?? {}
  const symbolBoards = payload.symbols ?? {}
  const marketConditions = payload.market_conditions ?? {}
  const directionBoard = payload.direction?.by_direction ?? []
  const confidenceBuckets = payload.confidence_buckets ?? []
  const exitQuality = payload.exit_quality ?? {}
  const confidenceMonotonicity = payload.confidence_monotonicity ?? {}
  const validationDashboards = payload.validation_dashboards ?? {}
  const symbolThrottles = payload.symbol_throttles ?? {}
  const recommendations = payload.recommendations ?? {}
  const comparison = payload.comparison ?? {}
  const auditAnalytics = payload.audit_analytics ?? {}
  const swingPatchValidation = (swingPatchValidationQuery.data ?? {}) as SwingPatchValidationPayload
  const symbols = symbolsQuery.data?.symbols ?? []
  const improvements = (improvementsQuery.data ?? {}) as ImprovementAnalyticsPayload
  const improvementsOverview = improvements.overview ?? {}
  const improvementRegistry = improvements.component_registry?.items ?? []
  const improvementImpact = improvements.component_impact?.by_component ?? []
  const changeImpact = improvements.change_impact?.items ?? []
  const recentChanges = improvements.recent_changes?.items ?? []
  const recommendationsImpact = improvements.recommendations ?? {}
  const operatorAlerts = improvements.operator_alerts ?? []
  const improvementComparison = improvements.comparison ?? {}
  const rolloutMeasurement = improvements.rollout_measurement ?? {}

  const statCards = useMemo(() => ([
    ['Closed trades', formatNumber(overview.total_closed_trades, 0), 'Real closed trades in scope.'],
    ['Win rate', `${formatNumber(toNumber(overview.win_rate) * 100, 1)}%`, 'Closed-trade hit rate.'],
    ['Avg realized R', `${formatNumber(overview.avg_realized_r, 2)}R`, 'Expectancy per trade.'],
    ['Profit factor', formatNumber(overview.profit_factor, 2), 'Gross win R / gross loss R.'],
    ['Best mode', String(overview.best_mode ?? '--'), 'Highest ranked stable mode.'],
    ['Worst mode', String(overview.worst_mode ?? '--'), 'Lowest ranked stable mode.'],
    ['Best setup', String(overview.best_setup_method ?? '--'), 'Best setup method by expectancy.'],
    ['Worst setup', String(overview.worst_setup_method ?? '--'), 'Worst setup method by expectancy.'],
  ]), [overview])

  function updateParam(key: string, value: string) {
    const next = new URLSearchParams(searchParams)
    if (!value || value === 'ALL') next.delete(key)
    else next.set(key, value)
    setSearchParams(next, { replace: true })
  }

  async function handleExport() {
    try {
      const csv = activeTab === 'performance'
        ? await exportTradeAnalytics(Number(lookback), { mode, symbol, interval, direction })
        : await exportImprovementAnalytics(Number(lookback), Number(minSamples), { mode, symbol, interval, direction })
      downloadFile(csv, exportFilename('trade-analytics', 'csv'), 'text/csv;charset=utf-8')
      toast.success(activeTab === 'performance' ? 'Trade analytics CSV downloaded.' : 'Improvements CSV downloaded.')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to export analytics.')
    }
  }

  async function handleValidationExport() {
    try {
      const csv = await exportSwingPatchValidationCsv(Number(lookback), 60)
      downloadFile(csv, exportFilename('swing-patch-validation', 'csv'), 'text/csv;charset=utf-8')
      toast.success('Swing patch validation CSV downloaded.')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to export swing patch validation.')
    }
  }

  if (payloadQuery.isLoading && !payloadQuery.data && improvementsQuery.isLoading && !improvementsQuery.data) {
    return <AnimatedRoute><EmptyState message="Loading analytics..." /></AnimatedRoute>
  }

  if (!toNumber(overview.total_closed_trades, 0)) {
    return (
      <AnimatedRoute>
        <div className="mx-auto grid w-full max-w-[1200px] gap-4 px-2 py-2">
        <section className="flex flex-wrap items-start justify-between gap-4 rounded-[1.3rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_16px_32px_rgba(77,62,40,0.06)]">
          <div className="grid gap-1">
            <h1 className="text-xl font-medium text-stone-950">Engine performance review</h1>
            <p className="text-sm text-stone-500">Decision quality, edge concentration, and where the engine is adding or losing value.</p>
          </div>
          </section>
          <EmptyState message="No closed trades available for analytics yet." />
        </div>
      </AnimatedRoute>
    )
  }

  const heatmapSessions = Object.keys(timing.session_hour_heatmap ?? {})
  const heatmapHours = Array.from(new Set(heatmapSessions.flatMap((sessionKey) => Object.keys((timing.session_hour_heatmap ?? {})[sessionKey] ?? {})))).sort((a, b) => Number(a) - Number(b))
  const topRows = (rows: TradeAnalyticsGroupRow[] | undefined, count = 6) => (rows ?? []).slice(0, count)

  return (
    <AnimatedRoute>
      <div className="mx-auto grid w-full max-w-[1200px] gap-4 px-2 py-2">
        <section className="flex flex-wrap items-start justify-between gap-4 rounded-[1.3rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_16px_32px_rgba(77,62,40,0.06)]">
          <div className="grid gap-1">
            <h1 className="text-xl font-medium text-stone-950">Engine performance review</h1>
            <p className="text-sm text-stone-500">Decision quality, edge concentration, and where the engine is adding or losing value.</p>
            <p className="text-xs text-stone-500">Timing analytics are locked to {payload.filters?.timezone ?? 'UTC'}.</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="mr-2 inline-flex rounded-full border border-stone-900/8 bg-stone-100 p-1">
              {[
                { id: 'performance', label: 'Performance' },
                { id: 'improvements', label: 'Improvements' },
              ].map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setActiveTab(tab.id as 'performance' | 'improvements')}
                  className={`rounded-full px-3 py-1.5 text-sm font-semibold transition ${activeTab === tab.id ? 'bg-white text-stone-950 shadow-sm' : 'text-stone-600'}`}
                >
                  {tab.label}
                </button>
              ))}
            </div>
            <select value={lookback} onChange={(event) => updateParam('lookback', event.target.value)} className="rounded-full border border-stone-900/8 bg-white px-3 py-2 text-sm">
              {LOOKBACK_OPTIONS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
            </select>
            <select value={minSamples} onChange={(event) => updateParam('min_samples', event.target.value)} className="rounded-full border border-stone-900/8 bg-white px-3 py-2 text-sm">
              {MIN_SAMPLE_OPTIONS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
            </select>
            <select value={mode} onChange={(event) => updateParam('mode', event.target.value)} className="rounded-full border border-stone-900/8 bg-white px-3 py-2 text-sm">
              {MODE_OPTIONS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
            </select>
            <select value={direction} onChange={(event) => updateParam('direction', event.target.value)} className="rounded-full border border-stone-900/8 bg-white px-3 py-2 text-sm">
              {DIRECTION_OPTIONS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
            </select>
            <select value={interval} onChange={(event) => updateParam('interval', event.target.value)} className="rounded-full border border-stone-900/8 bg-white px-3 py-2 text-sm">
              <option value="ALL">All intervals</option>
              {['15m', '30m', '1h', '4h', '1d', '3d', '7d', '14d', '1M'].map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
            <select value={symbol} onChange={(event) => updateParam('symbol', event.target.value)} className="rounded-full border border-stone-900/8 bg-white px-3 py-2 text-sm">
              <option value="">All symbols</option>
              {symbols.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
            <button type="button" onClick={() => void handleExport()} className="inline-flex items-center gap-2 rounded-full border border-stone-900/8 bg-white px-4 py-2 text-sm font-semibold text-stone-800 transition hover:bg-stone-950/[0.03]">
              <Download className="h-4 w-4" strokeWidth={1.8} />
              Export CSV
            </button>
          </div>
        </section>
        {activeTab === 'performance' ? (
          <>
        {swingPatchValidation.ok ? (
          <SwingPatchValidationPanel report={swingPatchValidation} onExport={handleValidationExport} />
        ) : null}
        <section className="grid gap-3 md:grid-cols-4 xl:grid-cols-8">
          {statCards.map(([label, value, note]) => (
            <div key={label} className="rounded-[1.2rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_12px_24px_rgba(77,62,40,0.06)]">
              <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">{label}</p>
              <p className="mt-2 text-lg font-semibold text-stone-950">{value}</p>
              <p className="mt-2 text-xs leading-5 text-stone-500">{note}</p>
            </div>
          ))}
        </section>

        <div className="grid gap-4 xl:grid-cols-2">
          <LeaderboardTable title="Best modes" rows={leaderboards.best_modes ?? []} />
          <LeaderboardTable title="Worst modes" rows={leaderboards.worst_modes ?? []} />
          <LeaderboardTable title="Best setup methods" rows={topRows(leaderboards.best_setup_methods, 8)} />
          <LeaderboardTable title="Worst setup methods" rows={topRows(leaderboards.worst_setup_methods, 8)} />
        </div>

        <div className="grid gap-4 xl:grid-cols-2">
          <section className="rounded-[1.2rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_12px_24px_rgba(77,62,40,0.06)]">
            <h2 className="text-sm font-semibold text-stone-950">Timing heatmap</h2>
            <div className="mt-4 overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead>
                  <tr>
                    <th className="pb-2 pr-3 text-left text-stone-500">Session</th>
                    {heatmapHours.map((hour) => <th key={hour} className="pb-2 px-2 text-center text-stone-500">{hour}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {heatmapSessions.map((sessionKey) => (
                    <tr key={sessionKey} className="border-t border-stone-900/8">
                      <td className="py-2 pr-3 font-semibold text-stone-950">{sessionKey}</td>
                      {heatmapHours.map((hour) => {
                        const value = Number((timing.session_hour_heatmap ?? {})[sessionKey]?.[hour] ?? 0)
                        return (
                          <td key={`${sessionKey}-${hour}`} className={`px-2 py-2 text-center text-xs ${value ? 'bg-amber-100 text-amber-900' : 'text-stone-400'}`}>
                            {value || '—'}
                          </td>
                        )
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="rounded-[1.2rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_12px_24px_rgba(77,62,40,0.06)]">
            <h2 className="text-sm font-semibold text-stone-950">Day-of-week breakdown</h2>
            <div className="mt-4 grid gap-3">
              {(timing.by_day_of_week ?? []).map((row) => (
                <div key={String(row.label)} className="grid grid-cols-[100px_1fr_60px_60px] items-center gap-3 text-sm">
                  <span className="font-semibold text-stone-950">{row.label}</span>
                  <div className="h-2 rounded-full bg-stone-100">
                    <div className={`h-2 rounded-full ${toNumber(row.avg_realized_r) >= 0 ? 'bg-teal-700' : 'bg-rose-600'}`} style={{ width: `${Math.min(100, Math.abs(toNumber(row.avg_realized_r)) * 40)}%` }} />
                  </div>
                  <span className="text-right text-stone-700">{formatNumber(toNumber(row.win_rate) * 100, 1)}%</span>
                  <span className={`text-right font-semibold ${toNumber(row.avg_realized_r) >= 0 ? 'text-teal-800' : 'text-rose-700'}`}>{formatNumber(row.avg_realized_r, 2)}R</span>
                </div>
              ))}
            </div>
          </section>
        </div>

        <div className="grid gap-4 xl:grid-cols-2">
          <LeaderboardTable title="Best symbols" rows={topRows(symbolBoards.best_symbols, 8)} />
          <LeaderboardTable title="Worst symbols" rows={topRows(symbolBoards.worst_symbols, 8)} />
          <LeaderboardTable title="Best symbol + interval" rows={topRows(symbolBoards.best_symbol_intervals, 8)} />
          <LeaderboardTable title="Worst symbol + interval" rows={topRows(symbolBoards.worst_symbol_intervals, 8)} />
        </div>

        <div className="grid gap-4 xl:grid-cols-2">
          <LeaderboardTable title="Best intervals" rows={topRows(symbolBoards.best_intervals, 8)} />
          <LeaderboardTable title="Worst intervals" rows={topRows(symbolBoards.worst_intervals, 8)} />
        </div>

        <div className="grid gap-4 xl:grid-cols-3">
          <LeaderboardTable title="Regime breakdown" rows={topRows(marketConditions.by_regime, 6)} />
          <LeaderboardTable title="Trend breakdown" rows={topRows(marketConditions.by_trend, 6)} />
          <LeaderboardTable title="Volatility breakdown" rows={topRows(marketConditions.by_volatility_bucket, 6)} />
        </div>

        <div className="grid gap-4 xl:grid-cols-3">
          <LeaderboardTable title="Long vs short" rows={topRows(directionBoard, 4)} />
          <section className="rounded-[1.2rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_12px_24px_rgba(77,62,40,0.06)]">
            <h2 className="text-sm font-semibold text-stone-950">Confidence buckets</h2>
            <div className="mt-4 grid gap-3">
              {confidenceBuckets.map((row) => (
                <div key={String(row.label)} className="grid grid-cols-[80px_1fr_70px_70px] items-center gap-3 text-sm">
                  <span className="font-semibold text-stone-950">{row.label}</span>
                  <div className="h-2 rounded-full bg-stone-100">
                    <div className={`h-2 rounded-full ${toNumber(row.avg_realized_r) >= 0 ? 'bg-teal-700' : 'bg-rose-600'}`} style={{ width: `${Math.min(100, Math.abs(toNumber(row.avg_realized_r)) * 40)}%` }} />
                  </div>
                  <span className="text-right text-stone-700">{formatNumber(toNumber(row.win_rate) * 100, 1)}%</span>
                  <span className={`text-right font-semibold ${toNumber(row.avg_realized_r) >= 0 ? 'text-teal-800' : 'text-rose-700'}`}>{formatNumber(row.avg_realized_r, 2)}R</span>
                </div>
              ))}
            </div>
          </section>
          <section className="rounded-[1.2rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_12px_24px_rgba(77,62,40,0.06)]">
            <h2 className="text-sm font-semibold text-stone-950">Exit quality</h2>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              {[
                ['Stop-hit', `${formatNumber(toNumber(exitQuality.stop_hit_rate) * 100, 1)}%`],
                ['Target-hit', `${formatNumber(toNumber(exitQuality.target_hit_rate) * 100, 1)}%`],
                ['Time-exit', `${formatNumber(toNumber(exitQuality.time_exit_rate) * 100, 1)}%`],
                ['Avg hold', `${formatNumber(exitQuality.avg_hold_minutes, 0)}m`],
              ].map(([label, value]) => (
                <div key={label} className="rounded-[1rem] bg-stone-950/[0.03] px-4 py-3">
                  <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">{label}</p>
                  <p className="mt-2 text-sm font-semibold text-stone-950">{value}</p>
                </div>
              ))}
            </div>
          </section>
        </div>

        <div className="grid gap-4 xl:grid-cols-3">
          <section className="rounded-[1.2rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_12px_24px_rgba(77,62,40,0.06)]">
            <h2 className="text-sm font-semibold text-stone-950">Confidence monotonicity</h2>
            <div className="mt-4 grid gap-3">
              {[
                { label: 'Pre-learning', report: confidenceMonotonicity.pre_learning },
                { label: 'Post-learning', report: confidenceMonotonicity.post_learning },
              ].map(({ label, report }) => (
                <div key={label} className="rounded-[1rem] bg-stone-950/[0.03] px-4 py-3 text-sm">
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-semibold text-stone-950">{label}</span>
                    <span className="text-stone-600">{String((report as Record<string, unknown> | undefined)?.status ?? 'UNKNOWN')}</span>
                  </div>
                  <div className="mt-1 text-xs text-stone-600">Score {formatNumber((report as Record<string, unknown> | undefined)?.score, 2)}</div>
                </div>
              ))}
            </div>
          </section>
          <section className="rounded-[1.2rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_12px_24px_rgba(77,62,40,0.06)]">
            <h2 className="text-sm font-semibold text-stone-950">Stop-hit validation</h2>
            <div className="mt-4 grid gap-3">
              <div className="rounded-[1rem] bg-stone-950/[0.03] px-4 py-3 text-sm text-stone-700">
                Overall {formatNumber(toNumber((validationDashboards.stop_hit_rate as Record<string, unknown> | undefined)?.overall) * 100, 1)}%
              </div>
              {(((validationDashboards.stop_hit_rate as Record<string, unknown> | undefined)?.by_mode as Array<Record<string, unknown>>) ?? []).slice(0, 4).map((row) => (
                <div key={String(row.label)} className="flex items-center justify-between rounded-[1rem] bg-rose-50 px-4 py-3 text-sm text-rose-900">
                  <span>{String(row.label ?? '--')}</span>
                  <span>{formatNumber(toNumber(row.rate) * 100, 1)}%</span>
                </div>
              ))}
            </div>
          </section>
          <section className="rounded-[1.2rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_12px_24px_rgba(77,62,40,0.06)]">
            <h2 className="text-sm font-semibold text-stone-950">Time-stop validation</h2>
            <div className="mt-4 grid gap-3">
              <div className="rounded-[1rem] bg-stone-950/[0.03] px-4 py-3 text-sm text-stone-700">
                Overall {formatNumber(toNumber((validationDashboards.time_stop_rate as Record<string, unknown> | undefined)?.overall) * 100, 1)}% · Avg {formatNumber((validationDashboards.time_stop_rate as Record<string, unknown> | undefined)?.avg_realized_r, 2)}R
              </div>
              {(((validationDashboards.time_stop_rate as Record<string, unknown> | undefined)?.by_mode as Array<Record<string, unknown>>) ?? []).slice(0, 4).map((row) => (
                <div key={String(row.label)} className="flex items-center justify-between rounded-[1rem] bg-amber-50 px-4 py-3 text-sm text-amber-900">
                  <span>{String(row.label ?? '--')}</span>
                  <span>{formatNumber(toNumber(row.rate) * 100, 1)}%</span>
                </div>
              ))}
            </div>
          </section>
        </div>

        <section className="rounded-[1.2rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_12px_24px_rgba(77,62,40,0.06)]">
          <h2 className="text-sm font-semibold text-stone-950">Universe throttles</h2>
          <div className="mt-4 flex flex-wrap items-center gap-2 text-xs text-stone-600">
            <span className="rounded-full bg-stone-950/[0.03] px-3 py-1.5">{symbolThrottles.enabled ? 'Enabled' : 'Disabled'}</span>
            <span className="rounded-full bg-stone-950/[0.03] px-3 py-1.5">{formatNumber(symbolThrottles.total_throttled, 0)} throttled</span>
          </div>
          <div className="mt-4 grid gap-3 xl:grid-cols-3">
            {((symbolThrottles.throttled_symbols as Array<Record<string, unknown>>) ?? []).slice(0, 6).map((item) => (
              <div key={String(item.symbol ?? '--')} className="rounded-[1rem] bg-amber-50 px-4 py-3 text-sm text-amber-900">
                <div className="flex items-center justify-between gap-3">
                  <span className="font-semibold">{String(item.symbol ?? '--')}</span>
                  <span>{formatNumber(item.stop_hit_rate_pct, 1)}%</span>
                </div>
                <div className="mt-1 text-xs">{String(item.reason ?? 'Throttled')}</div>
              </div>
            ))}
            {!((symbolThrottles.throttled_symbols as Array<Record<string, unknown>>) ?? []).length ? (
              <p className="text-sm text-stone-500">No symbols are currently throttled.</p>
            ) : null}
          </div>
        </section>

        <div className="grid gap-4 xl:grid-cols-2">
          <section className="rounded-[1.2rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_12px_24px_rgba(77,62,40,0.06)]">
            <h2 className="text-sm font-semibold text-stone-950">Recommendations</h2>
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              <div className="grid gap-3">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-teal-800">Scale up</p>
                {(recommendations.scale_up_methods ?? []).slice(0, 3).map((row) => (
                  <div key={String(row.label)} className="rounded-[1rem] bg-teal-50 px-4 py-3 text-sm text-teal-900">
                    <div className="font-semibold">{row.label}</div>
                    <div className="mt-1 text-xs">{row.reason_summary}</div>
                  </div>
                ))}
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-amber-800">Strongest sessions</p>
                {(recommendations.strongest_sessions ?? []).slice(0, 3).map((row) => (
                  <div key={String(row.label)} className="rounded-[1rem] bg-amber-50 px-4 py-3 text-sm text-amber-900">{row.label} · {formatNumber(row.avg_realized_r, 2)}R</div>
                ))}
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-teal-800">Strongest hours</p>
                {(recommendations.strongest_hours ?? []).slice(0, 3).map((row) => (
                  <div key={String(row.label)} className="rounded-[1rem] bg-teal-50 px-4 py-3 text-sm text-teal-900">{row.label}:00 · {formatNumber(row.avg_realized_r, 2)}R</div>
                ))}
              </div>
              <div className="grid gap-3">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-rose-700">Reduce or pause</p>
                {(recommendations.reduce_or_pause_methods ?? []).slice(0, 3).map((row) => (
                  <div key={String(row.label)} className="rounded-[1rem] bg-rose-50 px-4 py-3 text-sm text-rose-900">
                    <div className="font-semibold">{row.label}</div>
                    <div className="mt-1 text-xs">{row.reason_summary}</div>
                  </div>
                ))}
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-600">Weakest sessions</p>
                {(recommendations.weakest_sessions ?? []).slice(0, 3).map((row) => (
                  <div key={String(row.label)} className="rounded-[1rem] bg-stone-100 px-4 py-3 text-sm text-stone-800">{row.label} · {formatNumber(row.avg_realized_r, 2)}R</div>
                ))}
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-rose-700">Weakest hours</p>
                {(recommendations.weakest_hours ?? []).slice(0, 3).map((row) => (
                  <div key={String(row.label)} className="rounded-[1rem] bg-rose-50 px-4 py-3 text-sm text-rose-900">{row.label}:00 · {formatNumber(row.avg_realized_r, 2)}R</div>
                ))}
              </div>
            </div>
          </section>

          <section className="rounded-[1.2rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_12px_24px_rgba(77,62,40,0.06)]">
            <h2 className="text-sm font-semibold text-stone-950">Drift detection</h2>
            <div className="mt-4 grid gap-3">
              {comparison.edge_decay_warning ? (
                <div className="rounded-[1rem] bg-rose-50 px-4 py-3 text-sm font-semibold text-rose-900">Edge decay warning: a previously strong method has turned negative in the latest window.</div>
              ) : null}
              {(comparison.improving_methods ?? []).slice(0, 3).map((row) => (
                <div key={`improving-${row.label}`} className="flex items-center justify-between rounded-[1rem] bg-teal-50 px-4 py-3 text-sm text-teal-900">
                  <span className="inline-flex items-center gap-2"><TrendingUp className="h-4 w-4" /> {row.label}</span>
                  <span>+{formatNumber(row.delta_avg_r, 2)}R</span>
                </div>
              ))}
              {(comparison.decaying_methods ?? []).slice(0, 3).map((row) => (
                <div key={`decaying-${row.label}`} className="flex items-center justify-between rounded-[1rem] bg-amber-50 px-4 py-3 text-sm text-amber-900">
                  <span>{row.label}</span>
                  <span>{formatNumber(row.delta_avg_r, 2)}R</span>
                </div>
              ))}
              {(comparison.worsening_methods ?? []).slice(0, 3).map((row) => (
                <div key={`worsening-${row.label}`} className="flex items-center justify-between rounded-[1rem] bg-rose-50 px-4 py-3 text-sm text-rose-900">
                  <span className="inline-flex items-center gap-2"><TrendingDown className="h-4 w-4" /> {row.label}</span>
                  <span>{formatNumber(row.delta_avg_r, 2)}R</span>
                </div>
              ))}
              {(comparison.emerging_methods ?? []).slice(0, 3).map((row) => (
                <div key={`emerging-${row.label}`} className="rounded-[1rem] bg-stone-100 px-4 py-3 text-sm text-stone-800">Emerging: {row.label}</div>
              ))}
            </div>
          </section>
        </div>

        {auditAnalytics.available ? (
          <section className="rounded-[1.2rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_12px_24px_rgba(77,62,40,0.06)]">
            <h2 className="text-sm font-semibold text-stone-950">Audit-linked analyzer analytics</h2>
            <div className="mt-4 grid gap-4 xl:grid-cols-2">
              <div className="rounded-[1rem] bg-stone-950/[0.03] p-4">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">Threshold pass frequency</p>
                <pre className="mt-3 overflow-x-auto text-xs text-stone-700">{JSON.stringify(auditAnalytics.threshold_pass_frequency ?? {}, null, 2)}</pre>
              </div>
              <div className="rounded-[1rem] bg-stone-950/[0.03] p-4">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">Factor score distributions</p>
                <pre className="mt-3 overflow-x-auto text-xs text-stone-700">{JSON.stringify(auditAnalytics.factor_score_distributions ?? {}, null, 2)}</pre>
              </div>
              <div className="rounded-[1rem] bg-stone-950/[0.03] p-4">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">Learning adjustments on winners vs losers</p>
                <pre className="mt-3 overflow-x-auto text-xs text-stone-700">{JSON.stringify(auditAnalytics.learning_adjustments_presence ?? {}, null, 2)}</pre>
              </div>
              <div className="rounded-[1rem] bg-stone-950/[0.03] p-4">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">Circuit breaker impact</p>
                <pre className="mt-3 overflow-x-auto text-xs text-stone-700">{JSON.stringify(auditAnalytics.circuit_breaker_impact ?? {}, null, 2)}</pre>
              </div>
            </div>
          </section>
        ) : null}

        <section className="rounded-[1.2rem] border border-stone-900/8 bg-white/84 p-4 text-xs text-stone-500 shadow-[0_12px_24px_rgba(77,62,40,0.06)]">
          Generated {formatTime(payload.meta?.generated_at)}.
        </section>
          </>
        ) : (
          <>
            <section className="grid gap-3 md:grid-cols-4 xl:grid-cols-8">
              {[
                ['Registered', formatNumber(improvementsOverview.total_registered_components, 0), 'Canonical registry rows.'],
                ['Active', formatNumber(improvementsOverview.active_components, 0), 'Currently live components.'],
                ['Experimental', formatNumber(improvementsOverview.experimental_components, 0), 'Still building evidence.'],
                ['Changed', formatNumber(improvementsOverview.components_changed_in_window, 0), 'Components changed in scope.'],
                ['Promoted', formatNumber(improvementsOverview.promoted_components_in_window, 0), 'Enabled this window.'],
                ['Rolled back', formatNumber(improvementsOverview.rolled_back_components_in_window, 0), 'Disabled this window.'],
                ['Best improving', String(improvementsOverview.best_improving_component ?? '--'), 'Top positive expectancy delta.'],
                ['Worst degrading', String(improvementsOverview.worst_degrading_component ?? '--'), 'Most negative stable component.'],
              ].map(([label, value, note]) => (
                <div key={label} className="rounded-[1.2rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_12px_24px_rgba(77,62,40,0.06)]">
                  <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">{label}</p>
                  <p className="mt-2 text-lg font-semibold text-stone-950">{value}</p>
                  <p className="mt-2 text-xs leading-5 text-stone-500">{note}</p>
                </div>
              ))}
            </section>

            <div className="grid gap-4 xl:grid-cols-2">
              <section className="rounded-[1.2rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_12px_24px_rgba(77,62,40,0.06)]">
                <h2 className="text-sm font-semibold text-stone-950">Recent changes</h2>
                <div className="mt-4 grid gap-3">
                  {recentChanges.slice(0, 8).map((item) => (
                    <details key={String(item.change_id)} className="rounded-[1rem] bg-stone-950/[0.03] px-4 py-3 text-sm">
                      <summary className="cursor-pointer list-none font-semibold text-stone-950">{item.component_id} · {item.change_type}</summary>
                      <div className="mt-2 grid gap-1 text-xs text-stone-600">
                        <span>{formatTime(item.effective_at_utc)}</span>
                        <span>{item.change_reason}</span>
                        <span>before: {JSON.stringify(item.old_value ?? {})}</span>
                        <span>after: {JSON.stringify(item.new_value ?? {})}</span>
                      </div>
                    </details>
                  ))}
                </div>
              </section>

              <section className="rounded-[1.2rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_12px_24px_rgba(77,62,40,0.06)]">
                <h2 className="text-sm font-semibold text-stone-950">Operator alerts</h2>
                <div className="mt-4 grid gap-3">
                  {operatorAlerts.length ? operatorAlerts.map((item, index) => (
                    <div key={`${item.severity}-${index}`} className={`rounded-[1rem] px-4 py-3 text-sm ${item.severity === 'critical' ? 'bg-rose-50 text-rose-900' : 'bg-amber-50 text-amber-900'}`}>
                      {item.message}
                    </div>
                  )) : (
                    <p className="text-sm text-stone-500">No operator alerts for this window.</p>
                  )}
                </div>
              </section>
            </div>

            <section className="rounded-[1.2rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_12px_24px_rgba(77,62,40,0.06)]">
              <h2 className="text-sm font-semibold text-stone-950">Rollout measurement</h2>
              <div className="mt-4 grid gap-3 md:grid-cols-3">
                <div className="rounded-[1rem] bg-stone-950/[0.03] px-4 py-3 text-sm">
                  <div className="font-semibold text-stone-950">Current window</div>
                  <div className="mt-1 text-xs text-stone-600">Trades {formatNumber((rolloutMeasurement.current_window as Record<string, unknown> | undefined)?.trade_count, 0)}</div>
                  <div className="mt-1 text-xs text-stone-600">Param hash {String(((rolloutMeasurement.current_window as Record<string, unknown> | undefined)?.manifest as Record<string, unknown> | undefined)?.param_hash ?? '--')}</div>
                </div>
                <div className="rounded-[1rem] bg-stone-950/[0.03] px-4 py-3 text-sm">
                  <div className="font-semibold text-stone-950">Prior window</div>
                  <div className="mt-1 text-xs text-stone-600">Trades {formatNumber((rolloutMeasurement.prior_window as Record<string, unknown> | undefined)?.trade_count, 0)}</div>
                  <div className="mt-1 text-xs text-stone-600">Param hash {String(((rolloutMeasurement.prior_window as Record<string, unknown> | undefined)?.manifest as Record<string, unknown> | undefined)?.param_hash ?? '--')}</div>
                </div>
                <div className="rounded-[1rem] bg-stone-950/[0.03] px-4 py-3 text-sm">
                  <div className="font-semibold text-stone-950">Frozen config</div>
                  <div className="mt-1 text-xs text-stone-600">
                    {(rolloutMeasurement.frozen_config_snapshot as Record<string, unknown> | undefined)?.config_changed ? 'Config changed between windows' : 'Config stable between windows'}
                  </div>
                </div>
              </div>
            </section>

            <div className="grid gap-4 xl:grid-cols-2">
              <section className="rounded-[1.2rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_12px_24px_rgba(77,62,40,0.06)]">
                <h2 className="text-sm font-semibold text-stone-950">Component registry</h2>
                <div className="mt-4 overflow-x-auto">
                  <table className="min-w-full text-sm">
                    <thead className="text-left text-stone-500">
                      <tr>
                        <th className="pb-2 pr-4">Component</th>
                        <th className="pb-2 pr-4">Type</th>
                        <th className="pb-2 pr-4">Status</th>
                        <th className="pb-2 pr-4">Version</th>
                        <th className="pb-2 pr-4">Owner</th>
                        <th className="pb-2 pr-4">Seen</th>
                      </tr>
                    </thead>
                    <tbody>
                      {improvementRegistry.slice(0, 12).map((row) => (
                        <tr key={String(row.component_id)} className="border-t border-stone-900/8 align-top">
                          <td className="py-3 pr-4">
                            <div className="font-semibold text-stone-950">{row.ui_label ?? row.component_name}</div>
                            <div className="text-xs text-stone-500">{row.component_id}</div>
                          </td>
                          <td className="py-3 pr-4 text-stone-700">{row.component_type}</td>
                          <td className="py-3 pr-4"><span className={`rounded-full px-2 py-1 text-xs font-semibold ${row.status === 'ACTIVE' ? 'bg-teal-100 text-teal-900' : row.status === 'EXPERIMENTAL' ? 'bg-amber-100 text-amber-900' : 'bg-stone-200 text-stone-800'}`}>{row.status}</span></td>
                          <td className="py-3 pr-4 text-stone-700">{row.version}</td>
                          <td className="py-3 pr-4 text-stone-700">{row.owner}</td>
                          <td className="py-3 pr-4 text-xs text-stone-500">{formatTime(row.last_seen ?? row.updated_at_utc)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>

              <section className="rounded-[1.2rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_12px_24px_rgba(77,62,40,0.06)]">
                <h2 className="text-sm font-semibold text-stone-950">Best improving components</h2>
                <div className="mt-4 grid gap-3">
                  {improvementImpact.filter((item) => !item.provisional).slice(0, 6).map((row) => (
                    <div key={String(row.component_id)} className="rounded-[1rem] bg-teal-50 px-4 py-3 text-sm text-teal-900">
                      <div className="flex items-center justify-between gap-3">
                        <span className="font-semibold">{row.label}</span>
                        <span>Δ {formatNumber(row.expectancy_delta_vs_baseline, 2)}R</span>
                      </div>
                      <div className="mt-1 text-xs">Trades {formatNumber(row.trades_affected, 0)} · Avg {formatNumber(row.avg_realized_r, 2)}R · {row.sample_reliability}</div>
                    </div>
                  ))}
                </div>
                <h3 className="mt-5 text-sm font-semibold text-stone-950">Worst degrading components</h3>
                <div className="mt-4 grid gap-3">
                  {improvementImpact.filter((item) => !item.provisional).slice(-6).reverse().map((row) => (
                    <div key={`worst-${String(row.component_id)}`} className="rounded-[1rem] bg-rose-50 px-4 py-3 text-sm text-rose-900">
                      <div className="flex items-center justify-between gap-3">
                        <span className="font-semibold">{row.label}</span>
                        <span>Δ {formatNumber(row.expectancy_delta_vs_baseline, 2)}R</span>
                      </div>
                      <div className="mt-1 text-xs">Trades {formatNumber(row.trades_affected, 0)} · Avg {formatNumber(row.avg_realized_r, 2)}R · {row.sample_reliability}</div>
                    </div>
                  ))}
                </div>
              </section>
            </div>

            <div className="grid gap-4 xl:grid-cols-2">
              <section className="rounded-[1.2rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_12px_24px_rgba(77,62,40,0.06)]">
                <h2 className="text-sm font-semibold text-stone-950">Change impact leaderboard</h2>
                <div className="mt-4 grid gap-3">
                  {changeImpact.slice(0, 10).map((row) => (
                    <div key={String(row.change_id)} className="rounded-[1rem] bg-stone-950/[0.03] px-4 py-3 text-sm">
                      <div className="flex items-center justify-between gap-3">
                        <span className="font-semibold text-stone-950">{row.component_id} · {row.change_type}</span>
                        <span className={`${toNumber(row.expectancy_delta) >= 0 ? 'text-teal-800' : 'text-rose-700'} font-semibold`}>{formatNumber(row.expectancy_delta, 2)}R</span>
                      </div>
                      <div className="mt-1 text-xs text-stone-600">Before {formatNumber(row.avg_r_before, 2)}R / {formatNumber(row.trades_before, 0)} trades · After {formatNumber(row.avg_r_after, 2)}R / {formatNumber(row.trades_after, 0)} trades · {row.sample_reliability}</div>
                    </div>
                  ))}
                </div>
              </section>

              <section className="rounded-[1.2rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_12px_24px_rgba(77,62,40,0.06)]">
                <h2 className="text-sm font-semibold text-stone-950">Combination impact</h2>
                <div className="mt-4 grid gap-3">
                  {(improvements.combination_impact?.best_combinations ?? []).slice(0, 5).map((row) => (
                    <div key={`combo-best-${String(row.label)}`} className="rounded-[1rem] bg-teal-50 px-4 py-3 text-sm text-teal-900">{row.label} · {formatNumber(row.avg_realized_r, 2)}R · {formatNumber(row.trades_affected, 0)} trades</div>
                  ))}
                  {(improvements.combination_impact?.worst_combinations ?? []).slice(0, 5).map((row) => (
                    <div key={`combo-worst-${String(row.label)}`} className="rounded-[1rem] bg-rose-50 px-4 py-3 text-sm text-rose-900">{row.label} · {formatNumber(row.avg_realized_r, 2)}R · {formatNumber(row.trades_affected, 0)} trades</div>
                  ))}
                </div>
              </section>
            </div>

            <div className="grid gap-4 xl:grid-cols-3">
              <LeaderboardTable title="Context by mode" rows={(improvements.contextual_impact?.by_mode ?? []) as TradeAnalyticsGroupRow[]} />
              <LeaderboardTable title="Context by regime" rows={(improvements.contextual_impact?.by_regime ?? []) as TradeAnalyticsGroupRow[]} />
              <LeaderboardTable title="Context by direction" rows={(improvements.contextual_impact?.by_direction ?? []) as TradeAnalyticsGroupRow[]} />
            </div>

            <div className="grid gap-4 xl:grid-cols-2">
              <section className="rounded-[1.2rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_12px_24px_rgba(77,62,40,0.06)]">
                <h2 className="text-sm font-semibold text-stone-950">Recommendations</h2>
                <div className="mt-4 grid gap-3">
                  {[
                    ...(recommendationsImpact.promote_now ?? []),
                    ...(recommendationsImpact.keep_experimental ?? []),
                    ...(recommendationsImpact.pause_or_rollback ?? []),
                    ...(recommendationsImpact.investigate ?? []),
                  ].slice(0, 10).map((item, index) => (
                    <div key={`${item.component_id}-${index}`} className="rounded-[1rem] bg-stone-950/[0.03] px-4 py-3 text-sm">
                      <div className="flex items-center justify-between gap-3">
                        <span className="font-semibold text-stone-950">{item.label}</span>
                        <span className="rounded-full bg-stone-200 px-2 py-1 text-xs font-semibold text-stone-800">{item.action}</span>
                      </div>
                      <div className="mt-1 text-xs text-stone-600">{item.reason_summary}</div>
                    </div>
                  ))}
                </div>
              </section>

              <section className="rounded-[1.2rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_12px_24px_rgba(77,62,40,0.06)]">
                <h2 className="text-sm font-semibold text-stone-950">Drift safeguards</h2>
                <div className="mt-4 grid gap-3">
                  {improvementComparison.edge_decay_warning ? (
                    <div className="rounded-[1rem] bg-rose-50 px-4 py-3 text-sm font-semibold text-rose-900">A previously strong component has turned negative in the current window.</div>
                  ) : null}
                  {(improvementComparison.improving_components ?? []).slice(0, 3).map((row) => (
                    <div key={`imp-${row.label}`} className="rounded-[1rem] bg-teal-50 px-4 py-3 text-sm text-teal-900">{row.label} · +{formatNumber(row.delta_avg_r, 2)}R</div>
                  ))}
                  {(improvementComparison.degrading_components ?? []).slice(0, 3).map((row) => (
                    <div key={`deg-${row.label}`} className="rounded-[1rem] bg-amber-50 px-4 py-3 text-sm text-amber-900">{row.label} · {formatNumber(row.delta_avg_r, 2)}R</div>
                  ))}
                  {(improvementComparison.recently_broken_components ?? []).slice(0, 3).map((row) => (
                    <div key={`broken-${row.label}`} className="rounded-[1rem] bg-rose-50 px-4 py-3 text-sm text-rose-900">{row.label} broke after rollout</div>
                  ))}
                </div>
              </section>
            </div>

            <section className="rounded-[1.2rem] border border-stone-900/8 bg-white/84 p-4 text-xs text-stone-500 shadow-[0_12px_24px_rgba(77,62,40,0.06)]">
              Generated {formatTime(improvements.meta?.generated_at)}.
            </section>
          </>
        )}
      </div>
    </AnimatedRoute>
  )
}
