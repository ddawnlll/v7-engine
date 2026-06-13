import { Copy } from 'lucide-react'

import { formatTime } from '../../lib/format'
import type { JsonRecord } from '../../lib/types'

export type TraceSeverity = 'ERROR' | 'WARN' | 'INFO' | 'DEBUG' | 'SIGNAL' | 'TRADE' | 'SCAN'

function severityClasses(severity: TraceSeverity) {
  if (severity === 'ERROR') return 'bg-rose-50 text-rose-900 border-rose-900/10'
  if (severity === 'WARN') return 'bg-amber-50 text-amber-900 border-amber-900/10'
  if (severity === 'SIGNAL') return 'bg-teal-50 text-teal-900 border-teal-900/10'
  if (severity === 'TRADE') return 'bg-stone-950 text-stone-50 border-stone-950/10'
  if (severity === 'SCAN') return 'bg-sky-50 text-sky-900 border-sky-900/10'
  if (severity === 'DEBUG') return 'bg-stone-100 text-stone-500 border-stone-900/6'
  return 'bg-white text-stone-800 border-stone-900/8'
}

function badgeClasses(severity: TraceSeverity) {
  if (severity === 'ERROR') return 'bg-rose-700 text-white'
  if (severity === 'WARN') return 'bg-amber-700 text-white'
  if (severity === 'SIGNAL') return 'bg-teal-700 text-white'
  if (severity === 'TRADE') return 'bg-stone-900 text-white'
  if (severity === 'SCAN') return 'bg-sky-700 text-white'
  if (severity === 'DEBUG') return 'bg-stone-300 text-stone-700'
  return 'bg-stone-200 text-stone-700'
}

export function inferTraceSeverity(item: JsonRecord): TraceSeverity {
  const source = `${String(item.event_type ?? '')} ${String(item.decision ?? '')} ${String(item.reason_text ?? '')}`.toUpperCase()
  if (source.includes('ERROR') || source.includes('FAILED') || source.includes('DEAD')) return 'ERROR'
  if (source.includes('WARN')) return 'WARN'
  if (source.includes('SIGNAL') || source.includes('BUY') || source.includes('SELL')) return 'SIGNAL'
  if (source.includes('TRADE') || source.includes('ORDER') || source.includes('TP') || source.includes('SL')) return 'TRADE'
  if (source.includes('SCAN') || source.includes('QUEUE')) return 'SCAN'
  if (source.includes('DEBUG') || source.includes('HEARTBEAT')) return 'DEBUG'
  return 'INFO'
}

export function formatTraceLine(item: JsonRecord, severity: TraceSeverity) {
  const timestamp = formatTime(item.timestamp)
  const symbol = String(item.symbol ?? item.worker_id ?? item.run_id ?? 'ENGINE')
  const message = String(item.reason_text ?? item.event_type ?? 'Event')
  return `${timestamp}\t${severity}\t${symbol}\t${message}`
}

export function TraceLogRow({
  item,
  severity,
  onCopy,
}: {
  item: JsonRecord
  severity: TraceSeverity
  onCopy: () => void
}) {
  const symbol = String(item.symbol ?? item.worker_id ?? item.run_id ?? 'ENGINE')
  const message = String(item.reason_text ?? item.event_type ?? 'Event')

  return (
    <div className={`group min-w-0 rounded-[1rem] border px-3 py-3 md:rounded-[1.2rem] md:px-4 ${severityClasses(severity)}`}>
      <div className="grid gap-2 md:hidden">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <span className="font-mono text-[11px] leading-5 opacity-80 sm:text-xs sm:leading-6">{formatTime(item.timestamp)}</span>
          <span className={`inline-flex w-fit rounded-full px-2 py-1 text-[0.64rem] font-semibold uppercase tracking-[0.14em] ${badgeClasses(severity)}`}>
            {severity}
          </span>
          <span className="truncate text-sm font-semibold">{symbol}</span>
        </div>
        <div className="flex min-w-0 items-start justify-between gap-3">
          <span className="min-w-0 flex-1 break-words text-sm leading-6 opacity-90">{message}</span>
          <button
            type="button"
            onClick={onCopy}
            className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full transition hover:bg-stone-950/5"
            aria-label="Copy log line"
          >
            <Copy className="h-4 w-4" strokeWidth={1.8} />
          </button>
        </div>
      </div>

      <div className="hidden min-w-0 items-start gap-3 md:flex">
        <span className="w-32 shrink-0 font-mono text-xs leading-6 opacity-80">{formatTime(item.timestamp)}</span>
        <span className={`inline-flex w-16 shrink-0 justify-center rounded-full px-2.5 py-1 text-[0.68rem] font-semibold uppercase tracking-[0.14em] ${badgeClasses(severity)}`}>
          {severity}
        </span>
        <span className="w-24 shrink-0 truncate text-sm font-semibold">{symbol}</span>
        <span className="min-w-0 flex-1 truncate text-sm leading-6 opacity-90">{message}</span>
        <button
          type="button"
          onClick={onCopy}
          className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full opacity-0 transition hover:bg-stone-950/5 group-hover:opacity-100"
          aria-label="Copy log line"
        >
          <Copy className="h-4 w-4" strokeWidth={1.8} />
        </button>
      </div>
    </div>
  )
}
