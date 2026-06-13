export function SettingsSnapshot({ settings }: { settings: Record<string, string> }) {
  const entries = Object.entries(settings).sort(([left], [right]) => left.localeCompare(right))

  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
      {entries.map(([key, value]) => (
        <div key={key} className="grid gap-1 rounded-2xl bg-white/80 px-4 py-4 shadow-[0_12px_24px_rgba(71,53,29,0.05)]">
          <span className="text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-stone-500">{key}</span>
          <strong className="text-sm font-semibold text-stone-950">{value}</strong>
        </div>
      ))}
    </div>
  )
}
