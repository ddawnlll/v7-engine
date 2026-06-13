import type { DashboardPayload, JobItem, JsonRecord } from './types'

export type ExportDatasetKey =
  | 'closed_trades'
  | 'open_positions'
  | 'scan_jobs'
  | 'equity_curve'
  | 'daily_buckets'
  | 'trace_logs'
  | 'engine_events'
  | 'raw_payload'

export type ExportDateRange = '7d' | '30d' | 'all'

export type ExportDatasetMap = Record<ExportDatasetKey, unknown[] | JsonRecord | null>

const DAY_MS = 24 * 60 * 60 * 1000

function timestampForRange(value: unknown) {
  if (!value) return null
  const date = new Date(String(value))
  if (Number.isNaN(date.getTime())) return null
  return date.getTime()
}

function dateForDailyBucket(value: unknown) {
  if (!value) return null
  const date = new Date(`${String(value)}T00:00:00`)
  if (Number.isNaN(date.getTime())) return null
  return date.getTime()
}

function withinRange(timestamp: number | null, range: ExportDateRange) {
  if (range === 'all') return true
  if (timestamp == null) return false
  const days = range === '7d' ? 7 : 30
  return Date.now() - timestamp <= days * DAY_MS
}

export function buildExportDatasets(
  dashboard: DashboardPayload | null,
  jobs: JobItem[],
  range: ExportDateRange,
): ExportDatasetMap {
  const closedTrades = (dashboard?.orders?.closed_orders ?? dashboard?.portfolio?.recent_closed ?? []).filter((row) =>
    withinRange(timestampForRange((row as JsonRecord).close_timestamp ?? (row as JsonRecord).open_timestamp), range),
  )
  const openPositions = (dashboard?.orders?.open_orders ?? dashboard?.portfolio?.open_positions ?? []).filter((row) =>
    withinRange(timestampForRange((row as JsonRecord).open_timestamp), range),
  )
  const scanJobs = jobs.filter((job) =>
    withinRange(timestampForRange(job.created_at ?? job.started_at ?? job.finished_at), range),
  )
  const equityCurve = (dashboard?.portfolio?.equity_curve ?? []).filter((row) =>
    withinRange(timestampForRange((row as JsonRecord).time), range),
  )
  const dailyBuckets = (dashboard?.portfolio?.daily ?? []).filter((row) =>
    withinRange(dateForDailyBucket((row as JsonRecord).date), range),
  )
  const traceLogs = (dashboard?.trace_logs?.items ?? []).filter((row) =>
    withinRange(timestampForRange((row as JsonRecord).timestamp), range),
  )
  const engineEvents = (dashboard?.highlights?.recent_events ?? []).filter((row) =>
    withinRange(timestampForRange((row as JsonRecord).timestamp), range),
  )

  return {
    closed_trades: closedTrades as unknown[],
    open_positions: openPositions as unknown[],
    scan_jobs: scanJobs as unknown[],
    equity_curve: equityCurve as unknown[],
    daily_buckets: dailyBuckets as unknown[],
    trace_logs: traceLogs as unknown[],
    engine_events: engineEvents as unknown[],
    raw_payload: dashboard ? (dashboard as JsonRecord) : null,
  }
}

export function estimateRowCount(
  selectedDatasets: ExportDatasetKey[],
  datasetMap: ExportDatasetMap,
) {
  return selectedDatasets.reduce((total, key) => {
    const value = datasetMap[key]
    if (Array.isArray(value)) return total + value.length
    if (value && typeof value === 'object') return total + 1
    return total
  }, 0)
}

export function exportAsJSON(
  selectedDatasets: ExportDatasetKey[],
  datasetMap: ExportDatasetMap,
) {
  const payload = selectedDatasets.reduce<Record<string, unknown>>((result, key) => {
    result[key] = datasetMap[key]
    return result
  }, {})
  return JSON.stringify(payload, null, 2)
}

function csvEscape(value: unknown) {
  const text = value == null ? '' : typeof value === 'object' ? JSON.stringify(value) : String(value)
  if (/[",\n]/.test(text)) return `"${text.replace(/"/g, '""')}"`
  return text
}

export function exportAsCSV(dataset: unknown[] | JsonRecord | null) {
  if (!dataset) return ''
  const rows = Array.isArray(dataset) ? dataset : [dataset]
  if (!rows.length) return ''

  const keys = Array.from(
    rows.reduce<Set<string>>((set, row) => {
      if (row && typeof row === 'object') {
        Object.keys(row as JsonRecord).forEach((key) => set.add(key))
      }
      return set
    }, new Set<string>()),
  )

  const header = keys.join(',')
  const body = rows.map((row) => {
    const record = row as JsonRecord
    return keys.map((key) => csvEscape(record?.[key])).join(',')
  })

  return [header, ...body].join('\n')
}

export function downloadFile(content: string, filename: string, mimeType: string) {
  const blob = new Blob([content], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

export async function copyToClipboard(content: string) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(content)
    return
  }

  const textarea = document.createElement('textarea')
  textarea.value = content
  textarea.setAttribute('readonly', 'true')
  textarea.style.position = 'absolute'
  textarea.style.left = '-9999px'
  document.body.appendChild(textarea)
  textarea.select()
  document.execCommand('copy')
  document.body.removeChild(textarea)
}

export function exportFilename(prefix: string, extension: 'json' | 'csv') {
  const stamp = new Date().toISOString().replace(/[:.]/g, '-')
  return `${prefix}-${stamp}.${extension}`
}
