import { useMemo, useRef, useState } from 'react'

import { useQuery } from '@tanstack/react-query'
import { Copy, Database, Download, FileJson, TerminalSquare } from 'lucide-react'
import { toast } from 'sonner'

import { JsonViewer } from '../components/ui/JsonViewer'
import { TraceLogRow, formatTraceLine, inferTraceSeverity, type TraceSeverity } from '../components/ui/TraceLogRow'
import { AnimatedRoute } from '../components/ui/AnimatedRoute'
import { EmptyState } from '../components/ui/EmptyState'
import { useDashboardQuery } from '../hooks/useDashboardQuery'
import {
  buildExportDatasets,
  copyToClipboard,
  downloadFile,
  estimateRowCount,
  exportAsCSV,
  exportAsJSON,
  exportFilename,
  type ExportDatasetKey,
  type ExportDateRange,
} from '../lib/export'
import { fetchJobs, fetchTraces } from '../lib/api'
import { formatTime } from '../lib/format'
import type { JobItem, JsonRecord } from '../lib/types'

const datasetOptions: { key: ExportDatasetKey; label: string }[] = [
  { key: 'closed_trades', label: 'Closed Trades' },
  { key: 'open_positions', label: 'Open Positions' },
  { key: 'scan_jobs', label: 'Scan Jobs' },
  { key: 'equity_curve', label: 'Equity Curve' },
  { key: 'daily_buckets', label: 'Daily Buckets' },
  { key: 'trace_logs', label: 'Trace Logs' },
  { key: 'engine_events', label: 'Engine Events' },
  { key: 'raw_payload', label: 'Raw Payload' },
]

const traceSeverityOptions: TraceSeverity[] = ['ERROR', 'WARN', 'INFO', 'DEBUG', 'SIGNAL', 'TRADE', 'SCAN']
const ROW_HEIGHT = 76
const OVERSCAN = 8

export function LoggingRoute() {
  const dashboardQuery = useDashboardQuery()
  const jobsQuery = useQuery({
    queryKey: ['logging-jobs'],
    queryFn: () => fetchJobs(250),
    refetchInterval: 30_000,
  })
  const tracesQuery = useQuery({
    queryKey: ['logging-traces'],
    queryFn: () => fetchTraces(500),
    refetchInterval: 30_000,
  })

  const dashboard = dashboardQuery.data ?? null
  const jobs = ((jobsQuery.data?.items ?? []) as JobItem[]) ?? []

  const [selectedDatasets, setSelectedDatasets] = useState<ExportDatasetKey[]>([
    'closed_trades',
    'open_positions',
    'scan_jobs',
    'equity_curve',
    'daily_buckets',
    'trace_logs',
    'engine_events',
  ])
  const [exportFormat, setExportFormat] = useState<'json' | 'csv'>('json')
  const [dateRange, setDateRange] = useState<ExportDateRange>('7d')
  const [traceQuery, setTraceQuery] = useState('')
  const [severityFilter, setSeverityFilter] = useState<TraceSeverity[]>(['ERROR', 'WARN', 'INFO', 'DEBUG', 'SIGNAL', 'TRADE', 'SCAN'])
  const [scrollTop, setScrollTop] = useState(0)
  const listRef = useRef<HTMLDivElement | null>(null)

  const datasetMap = useMemo(() => buildExportDatasets(dashboard, jobs, dateRange), [dashboard, jobs, dateRange])
  const estimatedRows = estimateRowCount(selectedDatasets, datasetMap)

  const traceRows = useMemo(() => {
    const term = traceQuery.trim().toUpperCase()
    const combined = [
      ...((tracesQuery.data?.items ?? []) as JsonRecord[]),
      ...((dashboard?.highlights?.recent_events ?? []) as JsonRecord[]),
    ]
      .map((item, index) => ({
        id: `${String(item.timestamp ?? 'trace')}-${index}-${String(item.event_type ?? item.reason_text ?? 'item')}`,
        item,
        severity: inferTraceSeverity(item),
      }))
      .filter((row) => severityFilter.includes(row.severity))
      .filter((row) => {
        if (!term) return true
        const haystack = `${String(row.item.event_type ?? '')} ${String(row.item.symbol ?? '')} ${String(row.item.reason_text ?? '')}`.toUpperCase()
        return haystack.includes(term)
      })
      .sort((left, right) => String(right.item.timestamp ?? '').localeCompare(String(left.item.timestamp ?? '')))
    return combined
  }, [dashboard?.highlights?.recent_events, severityFilter, traceQuery, tracesQuery.data?.items])

  const containerHeight = 520
  const startIndex = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - OVERSCAN)
  const visibleCount = Math.ceil(containerHeight / ROW_HEIGHT) + OVERSCAN * 2
  const endIndex = Math.min(traceRows.length, startIndex + visibleCount)
  const visibleRows = traceRows.slice(startIndex, endIndex)
  const topSpacer = startIndex * ROW_HEIGHT
  const bottomSpacer = Math.max(0, (traceRows.length - endIndex) * ROW_HEIGHT)

  async function handleDownload() {
    if (!selectedDatasets.length) {
      toast.error('Choose at least one dataset first.')
      return
    }

    if (exportFormat === 'json') {
      const content = exportAsJSON(selectedDatasets, datasetMap)
      downloadFile(content, exportFilename('trading-bot-export', 'json'), 'application/json')
      toast.success('JSON export downloaded.')
      return
    }

    if (selectedDatasets.length === 1) {
      const key = selectedDatasets[0]
      const content = exportAsCSV(datasetMap[key])
      downloadFile(content, exportFilename(String(key), 'csv'), 'text/csv;charset=utf-8')
      toast.success('CSV export downloaded.')
      return
    }

    selectedDatasets.forEach((key) => {
      const content = exportAsCSV(datasetMap[key])
      downloadFile(content, exportFilename(String(key), 'csv'), 'text/csv;charset=utf-8')
    })
    toast.success('Downloaded one CSV file per dataset.')
  }

  async function handleCopyExport() {
    if (!selectedDatasets.length) {
      toast.error('Choose at least one dataset first.')
      return
    }
    const content = exportAsJSON(selectedDatasets, datasetMap)
    await copyToClipboard(content)
    toast.success('Export JSON copied to clipboard.')
  }

  async function handleCopyTraceVisible() {
    const content = JSON.stringify(traceRows.map((row) => row.item), null, 2)
    await copyToClipboard(content)
    toast.success('Visible trace logs copied.')
  }

  function toggleDataset(key: ExportDatasetKey) {
    setSelectedDatasets((current) =>
      current.includes(key) ? current.filter((item) => item !== key) : [...current, key],
    )
  }

  function toggleSeverity(value: TraceSeverity) {
    setSeverityFilter((current) =>
      current.includes(value) ? current.filter((item) => item !== value) : [...current, value],
    )
  }

  const selectedDatasetCount = selectedDatasets.length
  const allDatasetsSelected = selectedDatasetCount === datasetOptions.length

  function toggleAllDatasets() {
    setSelectedDatasets(allDatasetsSelected ? [] : datasetOptions.map((option) => option.key))
  }

  if (dashboardQuery.isLoading && !dashboard) {
    return (
      <AnimatedRoute>
        <EmptyState message="Loading logging and export tools..." />
      </AnimatedRoute>
    )
  }

  return (
    <AnimatedRoute>
      <div className="grid min-w-0 gap-3 lg:gap-4">
        <section className="rounded-[1.5rem] border border-stone-900/8 bg-white/84 px-4 py-4 shadow-[0_18px_40px_rgba(77,62,40,0.08)]">
          <div className="grid gap-3 lg:grid-cols-[1.15fr_0.85fr] lg:items-end">
            <div className="grid gap-2">
              <p className="text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-teal-800">Logging & Export</p>
              <h1 className="text-2xl font-semibold tracking-[-0.05em] text-stone-950 sm:text-3xl">Diagnostic tools for engine analysis.</h1>
              <p className="max-w-3xl text-sm leading-6 text-stone-500">
                Export raw datasets, inspect complete trace history, and browse the live dashboard payload without leaving the interface.
              </p>
            </div>
            <div className="hidden gap-2 rounded-[1.3rem] border border-stone-900/8 bg-stone-950 px-4 py-4 text-stone-50 shadow-[0_20px_44px_rgba(28,26,23,0.18)] lg:grid">
              <div className="flex items-center gap-2 text-sm font-semibold uppercase tracking-[0.18em] text-stone-300">
                <TerminalSquare className="h-4 w-4 text-teal-300" strokeWidth={1.8} />
                Developer Surface
              </div>
              <div className="grid gap-1 text-sm leading-6 text-stone-300">
                <p>Trace logs, exports, and raw payload inspection in one place.</p>
                <p>Built for debugging engine behavior quickly.</p>
              </div>
            </div>
          </div>
        </section>

        <section className="rounded-[1.5rem] border border-stone-900/8 bg-white/82 p-4 shadow-[0_18px_40px_rgba(77,62,40,0.08)] sm:p-5">
          <div className="mb-3 flex items-center gap-3">
            <Database className="h-5 w-5 text-teal-800" strokeWidth={1.8} />
            <div>
              <p className="text-sm font-semibold uppercase tracking-[0.18em] text-stone-500">Export Data</p>
              <h2 className="mt-1 text-lg font-semibold text-stone-950 sm:text-xl">Select datasets, format, and date range.</h2>
            </div>
          </div>
          <div className="grid gap-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex flex-wrap items-center gap-3">
                <p className="text-sm font-semibold text-stone-950">
                  Datasets
                  <span className="ml-2 text-stone-500">
                    ({selectedDatasetCount} of {datasetOptions.length} selected)
                  </span>
                </p>
              </div>
              <button
                type="button"
                onClick={toggleAllDatasets}
                className="rounded-full border border-stone-900/8 bg-white px-4 py-2 text-sm font-semibold text-stone-700 transition hover:bg-stone-950/[0.03]"
              >
                {allDatasetsSelected ? 'Clear All' : 'Select All'}
              </button>
            </div>

            <div className="grid grid-cols-2 gap-2 lg:grid-cols-3 xl:grid-cols-4">
              {datasetOptions.map((option) => (
                <button
                  key={option.key}
                  type="button"
                  onClick={() => toggleDataset(option.key)}
                  className={`flex min-h-[3.1rem] items-center gap-2 rounded-[1rem] border px-3 py-2.5 text-left transition ${
                    selectedDatasets.includes(option.key)
                      ? 'border-stone-950 bg-stone-950 text-stone-50 shadow-[0_18px_36px_rgba(28,26,23,0.16)]'
                      : 'border-stone-900/8 bg-white text-stone-700 hover:bg-stone-950/[0.03]'
                  }`}
                >
                  <span
                    className={`inline-flex h-4 w-4 items-center justify-center rounded border text-[0.68rem] font-semibold ${
                      selectedDatasets.includes(option.key)
                        ? 'border-teal-300 bg-teal-300 text-stone-950'
                        : 'border-stone-300 text-transparent'
                    }`}
                  >
                    ✓
                  </span>
                  <span className="text-xs font-semibold leading-5 sm:text-sm">{option.label}</span>
                </button>
              ))}
            </div>

            <div className="grid gap-3 md:grid-cols-2">
              <div className="rounded-[1.1rem] bg-stone-950/[0.03] p-3.5">
                <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">Format</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {(['json', 'csv'] as const).map((value) => (
                    <button
                      key={value}
                      type="button"
                      onClick={() => setExportFormat(value)}
                      className={`rounded-full px-3 py-2 text-sm font-semibold transition ${
                        exportFormat === value
                          ? 'bg-stone-950 text-stone-50'
                          : 'border border-stone-900/8 bg-white text-stone-700 hover:bg-stone-950/[0.03]'
                      }`}
                    >
                      {value.toUpperCase()}
                    </button>
                  ))}
                </div>
              </div>

              <div className="rounded-[1.1rem] bg-stone-950/[0.03] p-3.5">
                <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">Date Range</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {([
                    ['7d', 'Last 7d'],
                    ['30d', 'Last 30d'],
                    ['all', 'All'],
                  ] as [ExportDateRange, string][]).map(([value, label]) => (
                    <button
                      key={value}
                      type="button"
                      onClick={() => setDateRange(value)}
                      className={`rounded-full px-3 py-2 text-sm font-semibold transition ${
                        dateRange === value
                          ? 'bg-stone-950 text-stone-50'
                          : 'border border-stone-900/8 bg-white text-stone-700 hover:bg-stone-950/[0.03]'
                      }`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>

            </div>

            <div className="flex flex-col gap-3 rounded-[1.1rem] bg-stone-950/[0.03] p-3.5 xl:flex-row xl:items-center xl:justify-between">
              <div className="grid gap-1">
                <p className="text-sm text-stone-500">
                  <span className="font-semibold text-stone-950">~{estimatedRows.toLocaleString()} rows</span>
                  <span className="mx-2 text-stone-300">·</span>
                  <span className="font-semibold text-stone-950">{selectedDatasetCount} datasets</span>
                </p>
                <p className="text-sm text-stone-500">
                  JSON bundles everything into one payload. CSV downloads one file per dataset when multiple datasets are selected.
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => void handleDownload()}
                    className="inline-flex items-center gap-2 rounded-full bg-stone-950 px-3.5 py-2 text-sm font-semibold text-stone-50 transition hover:bg-stone-900"
                  >
                    <Download className="h-4 w-4" strokeWidth={1.8} />
                    Download File
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleCopyExport()}
                    className="inline-flex items-center gap-2 rounded-full border border-stone-900/8 bg-white px-3.5 py-2 text-sm font-semibold text-stone-800 transition hover:bg-stone-950/[0.03]"
                  >
                    <Copy className="h-4 w-4" strokeWidth={1.8} />
                    Copy to Clipboard
                  </button>
              </div>
            </div>
          </div>
        </section>

        <section className="rounded-[1.5rem] border border-stone-900/8 bg-white/82 p-4 shadow-[0_18px_40px_rgba(77,62,40,0.08)] sm:p-5">
          <div className="mb-3 flex items-center gap-3">
            <TerminalSquare className="h-5 w-5 text-teal-800" strokeWidth={1.8} />
            <div>
              <p className="text-sm font-semibold uppercase tracking-[0.18em] text-stone-500">Trace Log Viewer</p>
              <h2 className="mt-1 text-lg font-semibold text-stone-950 sm:text-xl">Complete engine event history.</h2>
            </div>
          </div>

          <div className="grid gap-3">
            <input
              value={traceQuery}
              onChange={(event) => setTraceQuery(event.target.value)}
              placeholder="Search event type, symbol, or reason text"
              className="h-11 rounded-2xl border border-stone-900/8 bg-white px-4 text-sm text-stone-900 outline-none transition focus:border-teal-900/20 focus:ring-4 focus:ring-teal-900/6"
            />
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <div className="flex flex-wrap gap-2">
                {traceSeverityOptions.map((severity) => (
                  <button
                    key={severity}
                    type="button"
                    onClick={() => toggleSeverity(severity)}
                    className={`rounded-full px-4 py-2 text-sm font-semibold transition ${
                      severityFilter.includes(severity)
                        ? 'bg-stone-950 text-stone-50'
                        : 'border border-stone-900/8 bg-white text-stone-700 hover:bg-stone-950/[0.03]'
                    }`}
                  >
                    {severity}
                  </button>
                ))}
              </div>
              <button
                type="button"
                onClick={() => void handleCopyTraceVisible()}
                className="inline-flex items-center gap-2 rounded-full border border-stone-900/8 bg-white px-3.5 py-2 text-sm font-semibold text-stone-800 transition hover:bg-stone-950/[0.03]"
              >
                <Copy className="h-4 w-4" strokeWidth={1.8} />
                Copy All Visible
              </button>
            </div>
          </div>

          <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-stone-500">
              Showing <span className="font-semibold text-stone-950">{traceRows.length}</span> events
            </p>
            <p className="text-sm text-stone-500">Newest first, multi-filter aware, virtualized for long logs.</p>
          </div>

          <div
            ref={listRef}
            onScroll={(event) => setScrollTop(event.currentTarget.scrollTop)}
            className="mt-3 h-[34vh] min-h-[260px] max-h-[460px] overflow-y-auto overflow-x-hidden rounded-[1.1rem] bg-stone-950/[0.02] p-2.5 sm:mt-4 sm:min-h-[300px] sm:p-3"
          >
            <div style={{ height: topSpacer }} />
            <div className="grid gap-2">
              {visibleRows.length ? visibleRows.map((row) => (
                <TraceLogRow
                  key={row.id}
                  item={row.item}
                  severity={row.severity}
                  onCopy={() => {
                    void copyToClipboard(formatTraceLine(row.item, row.severity))
                    toast.success('Trace line copied.')
                  }}
                />
              )) : (
                <EmptyState message="No trace events matched the current filters." />
              )}
            </div>
            <div style={{ height: bottomSpacer }} />
          </div>
        </section>

        <section className="rounded-[1.5rem] border border-stone-900/8 bg-white/82 p-4 shadow-[0_18px_40px_rgba(77,62,40,0.08)] sm:p-5">
          <div className="mb-3 flex items-center gap-3">
            <FileJson className="h-5 w-5 text-teal-800" strokeWidth={1.8} />
            <div>
              <p className="text-sm font-semibold uppercase tracking-[0.18em] text-stone-500">Engine Snapshot</p>
              <h2 className="mt-1 text-lg font-semibold text-stone-950 sm:text-xl">Raw DashboardPayload as of {formatTime(dashboard?.generated_at)}</h2>
            </div>
          </div>
          <JsonViewer
            meta={`Last fetched ${formatTime(dashboard?.generated_at)}`}
            json={dashboard ?? {}}
            onCopy={() => {
              void copyToClipboard(JSON.stringify(dashboard ?? {}, null, 2))
              toast.success('Full payload copied to clipboard.')
            }}
            onDownload={() => downloadFile(
              JSON.stringify(dashboard ?? {}, null, 2),
              exportFilename('dashboard-snapshot', 'json'),
              'application/json',
            )}
            onRefresh={() => {
              void dashboardQuery.refetch()
              toast.success('Snapshot refresh requested.')
            }}
          />
        </section>
      </div>
    </AnimatedRoute>
  )
}
