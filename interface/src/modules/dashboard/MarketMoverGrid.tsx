import { EmptyState } from '../../components/ui/EmptyState'
import { formatNumber, formatPercent, toNumber } from '../../lib/format'
import type { JsonRecord } from '../../lib/types'

export function MarketMoverGrid({ items }: { items: JsonRecord[] }) {
  if (!items.length) {
    return <EmptyState message="Top movers will appear here once the market runtime has enough live data." />
  }

  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
      {items.map((item) => (
        <article key={`${String(item.symbol ?? '--')}-${String(item.interval ?? item.mode ?? 'market')}`} className="flex items-end justify-between gap-3 rounded-2xl bg-white/80 px-4 py-4 shadow-[0_12px_24px_rgba(71,53,29,0.05)]">
          <div className="grid gap-1">
            <strong className="text-base font-semibold text-stone-950">{String(item.symbol ?? '--')}</strong>
            <span className="text-sm text-stone-500">{formatNumber(item.price, 4)}</span>
          </div>
          <div className={`text-sm font-semibold ${toNumber(item.change_pct) >= 0 ? 'text-emerald-700' : 'text-rose-700'}`}>
            {formatPercent(item.change_pct, 2)}
          </div>
        </article>
      ))}
    </div>
  )
}
