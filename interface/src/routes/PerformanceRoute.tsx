import { Navigate } from 'react-router-dom'

export function PerformanceRoute() {
  return <Navigate replace to="/review/engine/behavior" />
}

function formatMs(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return '--'
  if (value >= 1000) return `${formatNumber(value / 1000, 2)}s`
  return `${formatNumber(value, 1)}ms`
}

function metricTone(value: number | null | undefined, inverse = false) {
  if (value == null || Number.isNaN(value)) return 'text-stone-950'
  if (inverse) {
    if (value > 5000) return 'text-rose-700'
    if (value > 2000) return 'text-amber-700'
    return 'text-teal-700'
  }
  return 'text-stone-950'
}

function StatCard({
  icon: Icon,
  label,
  value,
  note,
  inverse = false,
}: {
  icon: typeof Gauge
  label: string
  value: number | null | undefined
  note: string
  inverse?: boolean
}) {
  return (
    <div className="rounded-[1.4rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_16px_32px_rgba(77,62,40,0.06)]">
      <div className="flex items-center gap-2 text-sm font-semibold text-stone-950">
        <Icon className="h-4 w-4 text-teal-800" strokeWidth={1.8} />
        {label}
      </div>
      <p className={`mt-3 text-3xl font-semibold tracking-[-0.05em] ${metricTone(value, inverse)}`}>{formatMs(value)}</p>
      <p className="mt-2 text-sm leading-6 text-stone-500">{note}</p>
    </div>
  )
}

function SummaryList({ rows }: { rows: Array<[string, string]> }) {
  return (
    <div className="grid gap-2 text-sm">
      {rows.map(([label, value]) => (
        <div key={label} className="flex items-center justify-between rounded-[1rem] bg-stone-950/[0.03] px-3 py-2">
          <span className="text-stone-500">{label}</span>
          <span className="font-semibold text-stone-950">{value}</span>
        </div>
      ))}
    </div>
  )
}

function normalizeComponentRows(rows: PerformanceComponentRow[]) {
  return rows.map((row) => ({
    ...row,
    count: toNumber(row.count, 0),
    avg_ms: row.avg_ms == null ? null : toNumber(row.avg_ms, 0),
    p95_ms: row.p95_ms == null ? null : toNumber(row.p95_ms, 0),
    total_ms: row.total_ms == null ? null : toNumber(row.total_ms, 0),
  }))
}

function timingSummaryRows(summary: PerformanceTimingSummary | undefined, label: string) {
  return [
    [`${label} avg`, formatMs(summary?.avg_ms)],
    [`${label} p50`, formatMs(summary?.p50_ms)],
    [`${label} p95`, formatMs(summary?.p95_ms)],
    [`${label} p99`, formatMs(summary?.p99_ms)],
  ] as Array<[string, string]>
}

function LegacyPerformanceRouteUnused() {
  const [exportPanelOpen, setExportPanelOpen] = useState(false)
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)
  const performanceQuery = useQuery({
    queryKey: ['performance-analytics'],
    queryFn: () => fetchPerformance(250),
    refetchInterval: 30_000,
    refetchOnWindowFocus: false,
  })

  const payload = (performanceQuery.data ?? {}) as PerformancePayload
  const analytics = (payload.analytics ?? {}) as PerformanceAnalytics
  const scanRuns = analytics.scan_runs ?? {}
  const analysis = analytics.analysis ?? {}
  const marketFetch = analytics.market_fetch ?? {}
  const recentScans = ((analytics.recent_scans ?? []) as PerformanceRecentScanRow[])
  const statusCounts = analytics.status_counts ?? {}
  const slowComponents = normalizeComponentRows(((analytics.slow_components ?? analytics.component_breakdown ?? []) as PerformanceComponentRow[]).slice(0, 10))
  const db = (analytics.db ?? {}) as PerformanceDbSummary
  const caches = (analytics.caches ?? {}) as PerformanceCacheSummary
  const concurrency = (analytics.concurrency ?? {}) as PerformanceConcurrencySummary

  useEffect(() => {
    if (!selectedRunId && recentScans.length) {
      setSelectedRunId(String(recentScans[0]?.run_id ?? ''))
    }
  }, [recentScans, selectedRunId])

  const selectedScan = useMemo(
    () => recentScans.find((item) => String(item.run_id ?? '') === String(selectedRunId ?? '')) ?? recentScans[0] ?? null,
    [recentScans, selectedRunId],
  )

  const chartData = useMemo(
    () => recentScans
      .slice(0, 18)
      .reverse()
      .map((item, index) => {
        const composition = (item.composition ?? {}) as Record<string, unknown>
        return {
          name: item.run_id ? String(item.run_id).slice(-4) : `#${index + 1}`,
          fetch_ms: toNumber(composition.fetch_ms, 0),
          analysis_ms: toNumber(composition.analysis_ms, 0),
          db_write_ms: toNumber(composition.db_write_ms, 0),
          audit_ms: toNumber(composition.audit_ms, 0),
          attribution_ms: toNumber(composition.attribution_ms, 0),
          execution_ms: toNumber(composition.execution_ms, 0),
          learning_ms: toNumber(composition.learning_ms, 0),
          uncovered_ms: toNumber(composition.uncovered_ms, 0),
        }
      }),
    [recentScans],
  )

  const statusRows = useMemo(
    () => Object.entries(statusCounts)
      .map(([label, count]) => ({ label, count: toNumber(count, 0) }))
      .sort((a, b) => b.count - a.count),
    [statusCounts],
  )

  const dbFamilyRows = useMemo(
    () => Object.entries(db.families ?? {}).map(([label, value]) => ({
      label,
      count: toNumber(value.count, 0),
      avg_ms: value.avg_ms,
      p95_ms: value.p95_ms,
      total_ms: value.total_ms,
    })).sort((a, b) => toNumber(b.total_ms, 0) - toNumber(a.total_ms, 0)),
    [db.families],
  )

  const analyticsExport = useMemo(
    () => ({
      generated_at: new Date().toISOString(),
      analytics,
      selected_scan: selectedScan,
    }),
    [analytics, selectedScan],
  )

  async function handleCopyFullPayload() {
    await copyToClipboard(JSON.stringify(payload, null, 2))
    toast.success('Full performance payload copied.')
  }

  async function handleCopyAnalyticsPayload() {
    await copyToClipboard(JSON.stringify(analyticsExport, null, 2))
    toast.success('Performance analytics copied.')
  }

  if (performanceQuery.isLoading && !performanceQuery.data) {
    return (
      <AnimatedRoute>
        <EmptyState message="Loading performance analytics..." />
      </AnimatedRoute>
    )
  }

  return (
    <AnimatedRoute>
      <div className="grid gap-4">
        <section className="rounded-[1.7rem] border border-stone-900/8 bg-white/84 px-4 py-4 shadow-[0_18px_40px_rgba(77,62,40,0.08)]">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="grid gap-2">
              <p className="text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-teal-800">Engine Behavior Review</p>
              <h1 className="text-3xl font-semibold tracking-[-0.06em] text-stone-950">Fallbacks, timing, cache pressure, DB pressure, and scan-behavior drilldowns.</h1>
              <p className="text-sm text-stone-500">This page owns the mechanical side of engine behavior: timing, composition, runtime pressure, and scan-level drilldowns.</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => setExportPanelOpen((value) => !value)}
                className="inline-flex items-center gap-2 rounded-full border border-stone-900/8 bg-white px-4 py-2.5 text-sm font-semibold text-stone-800 transition hover:bg-stone-950/[0.03]"
              >
                <FileJson className="h-4 w-4" strokeWidth={1.8} />
                {exportPanelOpen ? 'Hide Export Panel' : 'Open Export Panel'}
              </button>
              <button
                type="button"
                onClick={() => void handleCopyAnalyticsPayload()}
                className="inline-flex items-center gap-2 rounded-full bg-stone-950 px-4 py-2.5 text-sm font-semibold text-stone-50 transition hover:bg-stone-900"
              >
                <Copy className="h-4 w-4" strokeWidth={1.8} />
                Copy Analytics
              </button>
            </div>
          </div>
        </section>

        {exportPanelOpen ? (
          <JsonViewer
            title="Performance Export"
            meta="Copy analytics plus the currently selected scan drilldown."
            json={analyticsExport}
            onCopy={() => {
              void handleCopyAnalyticsPayload()
            }}
            onRefresh={() => {
              void performanceQuery.refetch()
            }}
          />
        ) : null}

        {exportPanelOpen ? (
          <section className="rounded-[1.4rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_16px_32px_rgba(77,62,40,0.06)]">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="grid gap-1">
                <p className="text-sm font-semibold text-stone-950">Copy Targets</p>
                <p className="text-sm text-stone-500">Copy the analytics payload with the selected scan drilldown, or the full response for deeper offline analysis.</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => void handleCopyAnalyticsPayload()}
                  className="inline-flex items-center gap-2 rounded-full border border-stone-900/8 bg-white px-4 py-2 text-sm font-semibold text-stone-800 transition hover:bg-stone-950/[0.03]"
                >
                  <Copy className="h-4 w-4" strokeWidth={1.8} />
                  Copy Analytics JSON
                </button>
                <button
                  type="button"
                  onClick={() => void handleCopyFullPayload()}
                  className="inline-flex items-center gap-2 rounded-full border border-stone-900/8 bg-white px-4 py-2 text-sm font-semibold text-stone-800 transition hover:bg-stone-950/[0.03]"
                >
                  <Copy className="h-4 w-4" strokeWidth={1.8} />
                  Copy Full Payload
                </button>
              </div>
            </div>
          </section>
        ) : null}

        <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard icon={Gauge} label="Scan p95" value={scanRuns.p95_ms} note={`${formatNumber(scanRuns.count, 0)} completed scans in scope`} inverse />
          <StatCard icon={Radar} label="Analysis p95" value={analysis.p95_ms} note={`${formatNumber(analysis.count, 0)} analysis tasks aggregated`} inverse />
          <StatCard icon={TimerReset} label="Fetch p95" value={marketFetch.p95_ms} note={`${formatNumber(marketFetch.count, 0)} fetch tasks aggregated`} inverse />
          <StatCard icon={Clock3} label="Scan p99" value={scanRuns.p99_ms} note="Tail latency for full scan duration" inverse />
        </section>

        <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <div className="rounded-[1.4rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_16px_32px_rgba(77,62,40,0.06)]">
            <p className="text-sm font-semibold text-stone-950">Timing Summary</p>
            <div className="mt-3 grid gap-2">
              <SummaryList rows={timingSummaryRows(scanRuns, 'Scan')} />
            </div>
          </div>
          <div className="rounded-[1.4rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_16px_32px_rgba(77,62,40,0.06)]">
            <p className="text-sm font-semibold text-stone-950">Analysis Summary</p>
            <div className="mt-3 grid gap-2">
              <SummaryList rows={timingSummaryRows(analysis, 'Analysis')} />
            </div>
          </div>
          <div className="rounded-[1.4rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_16px_32px_rgba(77,62,40,0.06)]">
            <p className="text-sm font-semibold text-stone-950">Concurrency</p>
            <div className="mt-3 grid gap-2 text-sm">
              <SummaryList rows={[
                ['Scan workers', formatNumber(concurrency.fetch_worker_capacity ?? concurrency.scan_workers, 0)],
                ['Analysis workers', formatNumber(concurrency.analysis_worker_capacity, 0)],
                ['Max concurrent fetches', formatNumber(concurrency.max_concurrent_fetches, 0)],
                ['Avg concurrent fetches', formatNumber(concurrency.avg_concurrent_fetches, 2)],
              ]} />
            </div>
          </div>
          <div className="rounded-[1.4rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_16px_32px_rgba(77,62,40,0.06)]">
            <p className="text-sm font-semibold text-stone-950">DB + Cache</p>
            <div className="mt-3 grid gap-2 text-sm">
              <SummaryList rows={[
                ['DB read total', formatMs(db.total_read_ms)],
                ['DB write total', formatMs(db.total_write_ms)],
                ['Market cache hit rate', caches.market_bundle?.hit_rate_pct != null ? `${formatNumber(caches.market_bundle?.hit_rate_pct, 2)}%` : '--'],
                ['HTF cache hit rate', caches.htf_trend?.hit_rate_pct != null ? `${formatNumber(caches.htf_trend?.hit_rate_pct, 2)}%` : '--'],
              ]} />
            </div>
          </div>
        </section>

        <div className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
          <section className="rounded-[1.6rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_18px_40px_rgba(77,62,40,0.08)]">
            <div className="mb-4 grid gap-1">
              <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">Time Composition</p>
              <h2 className="text-xl font-semibold tracking-[-0.04em] text-stone-950">Scan wall time broken down by major components</h2>
            </div>
            <div className="h-[340px]">
              {chartData.length ? (
                <ResponsiveContainer width="100%" height="100%" minWidth={0}>
                  <BarChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(120,113,108,0.18)" />
                    <XAxis dataKey="name" tickLine={false} axisLine={false} tick={{ fill: '#78716c', fontSize: 12 }} />
                    <YAxis tickLine={false} axisLine={false} tick={{ fill: '#78716c', fontSize: 12 }} />
                    <Tooltip
                      formatter={(value) => [formatMs(typeof value === 'number' ? value : Number(value ?? 0)), undefined]}
                      labelFormatter={(label) => `Run ${label}`}
                      contentStyle={{ borderRadius: 16, border: '1px solid rgba(28,25,23,0.08)', background: 'rgba(255,255,255,0.96)' }}
                    />
                    <Bar dataKey="fetch_ms" stackId="time" fill="#0f766e" radius={[0, 0, 0, 0]} />
                    <Bar dataKey="analysis_ms" stackId="time" fill="#b45309" radius={[0, 0, 0, 0]} />
                    <Bar dataKey="db_write_ms" stackId="time" fill="#7c3aed" radius={[0, 0, 0, 0]} />
                    <Bar dataKey="audit_ms" stackId="time" fill="#2563eb" radius={[0, 0, 0, 0]} />
                    <Bar dataKey="attribution_ms" stackId="time" fill="#dc2626" radius={[0, 0, 0, 0]} />
                    <Bar dataKey="execution_ms" stackId="time" fill="#14532d" radius={[0, 0, 0, 0]} />
                    <Bar dataKey="learning_ms" stackId="time" fill="#92400e" radius={[0, 0, 0, 0]} />
                    <Bar dataKey="uncovered_ms" stackId="time" fill="#57534e" radius={[8, 8, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <EmptyState message="No completed scan timing history is available yet." />
              )}
            </div>
          </section>

          <section className="rounded-[1.6rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_18px_40px_rgba(77,62,40,0.08)]">
            <div className="mb-4 grid gap-1">
              <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">Slow Components</p>
              <h2 className="text-xl font-semibold tracking-[-0.04em] text-stone-950">Largest time contributors across the sampled scans</h2>
            </div>
            <div className="grid gap-2">
              {slowComponents.length ? slowComponents.map((row) => (
                <div key={String(row.component_id)} className="rounded-[1rem] bg-stone-950/[0.03] px-3 py-3">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold text-stone-950">{row.label}</p>
                      <p className="text-xs text-stone-500">{row.group} · {formatNumber(row.count, 0)} calls</p>
                    </div>
                    <div className="text-right text-sm">
                      <p className="font-semibold text-stone-950">{formatMs(row.total_ms)}</p>
                      <p className="text-stone-500">p95 {formatMs(row.p95_ms)}</p>
                    </div>
                  </div>
                </div>
              )) : <EmptyState message="No component breakdown available yet." />}
            </div>
          </section>
        </div>

        <div className="grid gap-4 xl:grid-cols-[0.85fr_1.15fr]">
          <section className="rounded-[1.6rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_18px_40px_rgba(77,62,40,0.08)]">
            <div className="mb-4 grid gap-1">
              <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">Recent Scans</p>
              <h2 className="text-xl font-semibold tracking-[-0.04em] text-stone-950">Pick a run for a full drilldown</h2>
            </div>
            <div className="grid max-h-[640px] gap-2 overflow-y-auto pr-1">
              {recentScans.length ? recentScans.map((scan) => {
                const active = String(scan.run_id ?? '') === String(selectedScan?.run_id ?? '')
                return (
                  <button
                    type="button"
                    key={String(scan.run_id ?? scan.finished_at_utc ?? scan.started_at_utc)}
                    onClick={() => setSelectedRunId(String(scan.run_id ?? ''))}
                    className={`rounded-[1.2rem] border px-4 py-3 text-left transition ${active ? 'border-teal-700/30 bg-teal-50/60' : 'border-stone-900/8 bg-stone-950/[0.03] hover:bg-white'}`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="grid gap-1">
                        <p className="text-sm font-semibold text-stone-950">{String(scan.run_id ?? '--')}</p>
                        <p className="text-xs text-stone-500">{formatTime(scan.finished_at_utc ?? scan.started_at_utc)}</p>
                      </div>
                      <span className="rounded-full border border-stone-900/8 bg-white px-3 py-1 text-xs font-semibold text-stone-700">{String(scan.status ?? '--')}</span>
                    </div>
                    <div className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
                      <div className="flex items-center justify-between rounded-[0.95rem] bg-white px-3 py-2">
                        <span className="text-stone-500">Scan</span>
                        <span className="font-semibold text-stone-950">{formatMs(scan.duration_ms)}</span>
                      </div>
                      <div className="flex items-center justify-between rounded-[0.95rem] bg-white px-3 py-2">
                        <span className="text-stone-500">Analysis avg</span>
                        <span className="font-semibold text-stone-950">{formatMs(scan.analysis_avg_ms)}</span>
                      </div>
                      <div className="flex items-center justify-between rounded-[0.95rem] bg-white px-3 py-2">
                        <span className="text-stone-500">Fetch avg</span>
                        <span className="font-semibold text-stone-950">{formatMs(scan.market_fetch_avg_ms)}</span>
                      </div>
                      <div className="flex items-center justify-between rounded-[0.95rem] bg-white px-3 py-2">
                        <span className="text-stone-500">Tasks</span>
                        <span className="font-semibold text-stone-950">{formatNumber(scan.completed_tasks, 0)}/{formatNumber(scan.total_tasks, 0)}</span>
                      </div>
                    </div>
                  </button>
                )
              }) : <EmptyState message="No scan timing rows yet." />}
            </div>
          </section>

          <section className="rounded-[1.6rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_18px_40px_rgba(77,62,40,0.08)]">
            <div className="mb-4 grid gap-1">
              <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">Selected Scan Drilldown</p>
              <h2 className="text-xl font-semibold tracking-[-0.04em] text-stone-950">{selectedScan?.run_id ? `Run ${selectedScan.run_id}` : 'No scan selected'}</h2>
            </div>

            {selectedScan ? (
              <div className="grid gap-4">
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="rounded-[1.2rem] border border-stone-900/8 bg-stone-950/[0.03] p-4">
                    <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-stone-950">
                      <Layers3 className="h-4 w-4 text-teal-800" strokeWidth={1.8} />
                      Time composition
                    </div>
                    <SummaryList rows={[
                      ['Fetch', formatMs(selectedScan.composition?.fetch_ms as number | undefined)],
                      ['Analysis', formatMs(selectedScan.composition?.analysis_ms as number | undefined)],
                      ['DB write', formatMs(selectedScan.composition?.db_write_ms as number | undefined)],
                      ['Audit', formatMs(selectedScan.composition?.audit_ms as number | undefined)],
                      ['Attribution', formatMs(selectedScan.composition?.attribution_ms as number | undefined)],
                      ['Execution', formatMs(selectedScan.composition?.execution_ms as number | undefined)],
                      ['Learning', formatMs(selectedScan.composition?.learning_ms as number | undefined)],
                      ['Uncovered', formatMs(selectedScan.composition?.uncovered_ms as number | undefined)],
                    ]} />
                  </div>

                  <div className="rounded-[1.2rem] border border-stone-900/8 bg-stone-950/[0.03] p-4">
                    <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-stone-950">
                      <Database className="h-4 w-4 text-teal-800" strokeWidth={1.8} />
                      DB, cache, and concurrency
                    </div>
                    <SummaryList rows={[
                      ['DB read total', formatMs(selectedScan.db?.total_read_ms)],
                      ['DB write total', formatMs(selectedScan.db?.total_write_ms)],
                      ['Rows written', formatNumber(selectedScan.db?.rows_written, 0)],
                      ['Market cache hit rate', selectedScan.caches?.market_bundle?.hit_rate_pct != null ? `${formatNumber(selectedScan.caches?.market_bundle?.hit_rate_pct, 2)}%` : '--'],
                      ['HTF cache hit rate', selectedScan.caches?.htf_trend?.hit_rate_pct != null ? `${formatNumber(selectedScan.caches?.htf_trend?.hit_rate_pct, 2)}%` : '--'],
                      ['Fetch workers', formatNumber(selectedScan.concurrency?.fetch_worker_capacity, 0)],
                      ['Analysis workers', formatNumber(selectedScan.concurrency?.analysis_worker_capacity, 0)],
                      ['Max concurrent fetches', formatNumber(selectedScan.concurrency?.max_concurrent_fetches, 0)],
                    ]} />
                  </div>
                </div>

                <div className="rounded-[1.2rem] border border-stone-900/8 bg-stone-950/[0.03] p-4">
                  <p className="text-sm font-semibold text-stone-950">Top contributors for this run</p>
                  <div className="mt-3 grid gap-2">
                    {normalizeComponentRows((selectedScan.top_components ?? []) as PerformanceComponentRow[]).length ? normalizeComponentRows((selectedScan.top_components ?? []) as PerformanceComponentRow[]).map((row) => (
                      <div key={String(row.component_id)} className="flex items-center justify-between rounded-[0.95rem] bg-white px-3 py-2 text-sm">
                        <span className="text-stone-600">{row.label}</span>
                        <span className="font-semibold text-stone-950">{formatMs(row.total_ms)} · p95 {formatMs(row.p95_ms)}</span>
                      </div>
                    )) : <EmptyState message="No component rows recorded for this scan." />}
                  </div>
                </div>

                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="rounded-[1.2rem] border border-stone-900/8 bg-stone-950/[0.03] p-4">
                    <p className="text-sm font-semibold text-stone-950">DB families</p>
                    <div className="mt-3 grid gap-2">
                      {Object.entries(selectedScan.db?.families ?? {}).length ? Object.entries(selectedScan.db?.families ?? {}).map(([label, value]) => (
                        <div key={label} className="flex items-center justify-between rounded-[0.95rem] bg-white px-3 py-2 text-sm">
                          <span className="text-stone-600">{label}</span>
                          <span className="font-semibold text-stone-950">{formatMs(value.total_ms)} · {formatNumber(value.count, 0)} calls</span>
                        </div>
                      )) : <EmptyState message="No DB family metrics recorded." />}
                    </div>
                  </div>

                  <div className="rounded-[1.2rem] border border-stone-900/8 bg-stone-950/[0.03] p-4">
                    <p className="text-sm font-semibold text-stone-950">Scope and debug</p>
                    <div className="mt-3 grid gap-2 text-sm">
                      <SummaryList rows={[
                        ['Total tasks', formatNumber(selectedScan.scope?.total_tasks as number | undefined, 0)],
                        ['Effective tasks', formatNumber(selectedScan.scope?.effective_tasks as number | undefined, 0)],
                        ['Fetch tasks', formatNumber(selectedScan.scope?.fetch_tasks as number | undefined, 0)],
                        ['Bundle req. no cache', formatNumber(selectedScan.scope?.estimated_bundle_requests_without_cache as number | undefined, 0)],
                        ['Bundle req. with cache', formatNumber(selectedScan.scope?.estimated_unique_bundle_requests_with_cache as number | undefined, 0)],
                        ['Pending fetch count', formatNumber(selectedScan.debug?.pending_fetch_count as number | undefined, 0)],
                        ['Wait heartbeats', formatNumber(selectedScan.debug?.wait_heartbeats as number | undefined, 0)],
                        ['Last progress reason', String(selectedScan.debug?.last_progress_reason ?? '--')],
                      ]} />
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <EmptyState message="Select a recent scan to inspect its component and timing breakdown." />
            )}
          </section>
        </div>

        <div className="grid gap-4 xl:grid-cols-[0.9fr_1.1fr]">
          <section className="rounded-[1.6rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_18px_40px_rgba(77,62,40,0.08)]">
            <div className="mb-4 grid gap-1">
              <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">DB Pressure</p>
              <h2 className="text-xl font-semibold tracking-[-0.04em] text-stone-950">Query families and write pressure seen in sampled scans</h2>
            </div>
            <div className="grid gap-2">
              {dbFamilyRows.length ? dbFamilyRows.map((row) => (
                <div key={row.label} className="flex items-center justify-between rounded-[1rem] bg-stone-950/[0.03] px-3 py-3 text-sm">
                  <div>
                    <p className="font-semibold text-stone-950">{row.label}</p>
                    <p className="text-stone-500">{formatNumber(row.count, 0)} calls · avg {formatMs(row.avg_ms)}</p>
                  </div>
                  <div className="text-right">
                    <p className="font-semibold text-stone-950">{formatMs(row.total_ms)}</p>
                    <p className="text-stone-500">p95 {formatMs(row.p95_ms)}</p>
                  </div>
                </div>
              )) : <EmptyState message="No DB family metrics available yet." />}
            </div>
          </section>

          <section className="rounded-[1.6rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_18px_40px_rgba(77,62,40,0.08)]">
            <div className="mb-4 grid gap-1">
              <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">Status + Coverage</p>
              <h2 className="text-xl font-semibold tracking-[-0.04em] text-stone-950">Operational state, cache behavior, and sampled run health</h2>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-[1rem] bg-stone-950/[0.03] p-4">
                <p className="text-sm font-semibold text-stone-950">Recent scan statuses</p>
                <div className="mt-3 grid gap-2">
                  {statusRows.length ? statusRows.slice(0, 6).map((row) => (
                    <div key={row.label} className="flex items-center justify-between rounded-[0.95rem] bg-white px-3 py-2 text-sm">
                      <span className="text-stone-600">{row.label}</span>
                      <span className="font-semibold text-stone-950">{formatNumber(row.count, 0)}</span>
                    </div>
                  )) : <EmptyState message="No status rows yet." />}
                </div>
              </div>

              <div className="rounded-[1rem] bg-stone-950/[0.03] p-4">
                <p className="text-sm font-semibold text-stone-950">Cache and learning activity</p>
                <div className="mt-3 grid gap-2">
                  <SummaryList rows={[
                    ['Market bundle requests', formatNumber(caches.market_bundle?.requests, 0)],
                    ['Market bundle hit rate', caches.market_bundle?.hit_rate_pct != null ? `${formatNumber(caches.market_bundle?.hit_rate_pct, 2)}%` : '--'],
                    ['HTF trend requests', formatNumber(caches.htf_trend?.requests, 0)],
                    ['HTF trend hit rate', caches.htf_trend?.hit_rate_pct != null ? `${formatNumber(caches.htf_trend?.hit_rate_pct, 2)}%` : '--'],
                    ['Self-learning active tasks', formatNumber(caches.self_learning?.active_tasks, 0)],
                    ['Self-learning bypassed', formatNumber(caches.self_learning?.bypassed_tasks, 0)],
                  ]} />
                </div>
              </div>
            </div>
          </section>
        </div>
      </div>
    </AnimatedRoute>
  )
}
