type StatusBadgeProps = {
  label: string
  tone?: 'neutral' | 'good' | 'warn' | 'bad'
}

const toneClasses: Record<NonNullable<StatusBadgeProps['tone']>, string> = {
  neutral: 'border-stone-900/10 bg-stone-950/[0.03] text-stone-700',
  good: 'border-teal-800/15 bg-teal-700/8 text-teal-900',
  warn: 'border-amber-700/15 bg-amber-600/10 text-amber-900',
  bad: 'border-rose-700/15 bg-rose-600/10 text-rose-900',
}

export function StatusBadge({ label, tone = 'neutral' }: StatusBadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-3 py-1.5 text-[0.72rem] font-semibold uppercase tracking-[0.16em] ${toneClasses[tone]}`}
    >
      {label}
    </span>
  )
}
