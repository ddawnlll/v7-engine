import type { ElementType } from 'react'
import { AlertTriangle, ArrowDown, ArrowUp, ArrowUpDown } from 'lucide-react'

import { formatNumber } from '../../lib/format'

export type BreakdownRow = { key: string; count: number; percent?: number; pct?: number }

export function MetricTile({ label, value, delta, deltaColor }: { label: string; value: string; delta?: string; deltaColor?: string }) {
  const resolvedDeltaColor = deltaColor ?? (delta?.startsWith('+') ? 'text-rose-600' : delta?.startsWith('-') || delta?.startsWith('−') ? 'text-teal-700' : 'text-stone-500')
  return (
    <div className="rounded-xl bg-stone-950/[0.03] px-3 py-3">
      <p className="text-[0.65rem] font-medium uppercase tracking-widest text-stone-500">{label}</p>
      <p className="mt-1.5 text-lg font-semibold tabular-nums text-stone-950">{value}</p>
      {delta != null && <p className={`mt-0.5 text-xs font-medium ${resolvedDeltaColor}`}>{delta}</p>}
    </div>
  )
}

export function SectionHeader({ icon: Icon, title, subtitle }: { icon: IconType; title: string; subtitle?: string }) {
  return (
    <div className="flex items-center gap-2.5">
      <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-teal-500/10">
        <Icon className="h-3.5 w-3.5 text-teal-700" strokeWidth={1.8} />
      </span>
      <div>
        <p className="text-sm font-semibold text-stone-950">{title}</p>
        {subtitle && <p className="text-xs text-stone-500">{subtitle}</p>}
      </div>
    </div>
  )
}

export function AlertBanner({ tone, title, message }: { tone: 'bad' | 'warning'; title: string; message: string }) {
  const bg = tone === 'bad' ? 'border-rose-200 bg-rose-50/90' : 'border-amber-200 bg-amber-50/90'
  const text = tone === 'bad' ? 'text-rose-700' : 'text-amber-800'
  const sub = tone === 'bad' ? 'text-rose-600' : 'text-amber-700'
  return (
    <div className={`rounded-xl border px-4 py-3 ${bg}`}>
      <div className={`flex items-center gap-2 text-xs font-semibold ${text}`}>
        <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" strokeWidth={1.8} />
        {title}
      </div>
      <p className={`mt-1.5 text-xs leading-relaxed ${sub}`}>{message}</p>
    </div>
  )
}

export function SkipBar({ rows, toneForKey, labelForKey = (key) => key }: { rows: BreakdownRow[]; toneForKey: (key: string) => string; labelForKey?: (key: string) => string }) {
  return (
    <div className="flex h-2 overflow-hidden rounded-full bg-stone-200">
      {rows.map((row) => {
        const percent = row.percent ?? row.pct ?? 0
        return <div key={row.key} className={toneForKey(row.key)} style={{ width: `${percent}%` }} title={`${labelForKey(row.key)}: ${formatNumber(row.count, 0)} (${formatNumber(percent, 1)}%)`} />
      })}
    </div>
  )
}

export function BreakdownList({ rows, color = 'bg-teal-500', labelForKey = (key) => key.replaceAll('_', ' ') }: { rows: BreakdownRow[]; color?: string; labelForKey?: (key: string) => string }) {
  return (
    <div className="grid gap-2">
      {rows.slice(0, 8).map((row) => {
        const percent = row.percent ?? row.pct ?? 0
        return (
          <div key={row.key}>
            <div className="flex items-center justify-between text-xs">
              <span className="font-medium text-stone-700">{labelForKey(row.key)}</span>
              <span className="tabular-nums text-stone-500">{formatNumber(row.count, 0)} · {formatNumber(percent, 1)}%</span>
            </div>
            <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-stone-200">
              <div className={`h-full rounded-full ${color}`} style={{ width: `${percent}%` }} />
            </div>
          </div>
        )
      })}
    </div>
  )
}

export function SortHeader({ label, active, descending, onClick }: { label: string; active: boolean; descending: boolean; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} className={`inline-flex items-center gap-1 transition hover:text-stone-950 ${active ? 'text-stone-950' : 'text-stone-500'}`}>
      {label}
      {active ? (descending ? <ArrowDown className="h-3.5 w-3.5" strokeWidth={1.8} /> : <ArrowUp className="h-3.5 w-3.5" strokeWidth={1.8} />) : <ArrowUpDown className="h-3.5 w-3.5 opacity-50" strokeWidth={1.8} />}
    </button>
  )
}

type IconType = ElementType<{ className?: string; strokeWidth?: number }>

export function ToolbarBtn({ icon: Icon, label, onClick, disabled = false, danger = false }: { icon: IconType; label: string; onClick: () => void; disabled?: boolean; danger?: boolean }) {
  const base = danger ? 'border-rose-200 bg-rose-50 text-rose-700 hover:bg-rose-100' : 'border-stone-900/8 bg-white text-stone-700 hover:bg-stone-950/[0.03]'
  return (
    <button type="button" onClick={onClick} disabled={disabled} title={label} className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition disabled:pointer-events-none disabled:opacity-40 ${base}`}>
      <Icon className="h-3.5 w-3.5" strokeWidth={1.8} />
      {label}
    </button>
  )
}
