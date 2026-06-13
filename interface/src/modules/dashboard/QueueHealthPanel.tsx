import { formatNumber } from '../../lib/format'

export function QueueHealthPanel({
  pending,
  running,
  completed,
  failed,
}: {
  pending: unknown
  running: unknown
  completed: unknown
  failed: unknown
}) {
  const items: Array<[string, unknown]> = [
    ['Pending', pending],
    ['Running', running],
    ['Completed', completed],
    ['Failed', failed],
  ]

  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {items.map(([label, value]) => (
        <div key={label} className="grid gap-1 rounded-2xl bg-white/80 px-4 py-4 shadow-[0_12px_24px_rgba(71,53,29,0.05)]">
          <span className="text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-stone-500">{label}</span>
          <strong className="text-2xl font-semibold tracking-[-0.04em] text-stone-950">{formatNumber(value, 0)}</strong>
        </div>
      ))}
    </div>
  )
}
