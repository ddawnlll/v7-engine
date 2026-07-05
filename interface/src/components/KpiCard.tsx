import type { ReactNode } from 'react'

type KpiCardProps = {
  label: string
  value: string | number | ReactNode
  detail?: string | ReactNode | null
  icon?: ReactNode
  accent?: string
  className?: string
}

export function KpiCard({ label, value, detail, icon, accent, className = '' }: KpiCardProps) {
  return (
    <div className={`rounded-[1.4rem] border border-stone-900/8 bg-white/84 p-4 ${className}`}>
      <div className="flex items-center justify-between gap-3">
        <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">{label}</p>
        {icon ? <div className="h-4 w-4 text-teal-800">{icon}</div> : null}
      </div>
      <p className={`mt-2 text-2xl font-semibold tracking-[-0.04em] ${accent ?? 'text-stone-950'}`}>{value}</p>
      {detail != null ? (
        <p className="mt-1 text-sm leading-6 text-stone-500">{detail}</p>
      ) : null}
    </div>
  )
}

type KpiCardSimpleProps = {
  label: string
  value: string | number
  detail?: string | null
  accent?: string
}

/** Compact KPI card for use in tight grids — no icon, smaller padding. */
export function KpiCardSimple({ label, value, detail, accent }: KpiCardSimpleProps) {
  return (
    <div className="rounded-[1.3rem] border border-stone-900/8 bg-white/90 p-4">
      <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">{label}</p>
      <p className={`mt-2 text-lg font-semibold leading-6 ${accent ?? 'text-stone-950'}`}>{value}</p>
      {detail != null ? (
        <p className="mt-2 text-sm leading-6 text-stone-500">{detail}</p>
      ) : null}
    </div>
  )
}

/** Inline KPI row — label on left, value on right, optional note below. */
export function KpiCardRow({ label, value, note }: { label: string; value: string | number; note?: string }) {
  return (
    <div className="rounded-[1.3rem] bg-stone-950/[0.03] p-4">
      <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">{label}</p>
      <p className="mt-2 text-sm font-semibold leading-6 text-stone-950">{value}</p>
      {note ? <p className="mt-1 text-sm leading-6 text-stone-500">{note}</p> : null}
    </div>
  )
}
