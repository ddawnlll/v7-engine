import { motion } from 'framer-motion'
import {
  Activity,
  BarChart3,
  BriefcaseBusiness,
  Clock3,
  type LucideIcon,
  Radar,
  ShieldCheck,
} from 'lucide-react'

import type { SummaryCardItem } from '../../lib/types'

function toneClasses(tone: string) {
  if (tone === 'tone-good') return 'border-emerald-700/20'
  if (tone === 'tone-warn') return 'border-amber-700/25'
  if (tone === 'tone-bad') return 'border-rose-700/20'
  return 'border-stone-900/10'
}

const iconMap: Record<string, LucideIcon> = {
  activity: Activity,
  bar_chart: BarChart3,
  briefcase: BriefcaseBusiness,
  clock: Clock3,
  radar: Radar,
  shield: ShieldCheck,
}

export function SummaryCards({ items }: { items: SummaryCardItem[] }) {
  return (
    <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-6" aria-label="Summary metrics">
      {items.map((card, index) => {
        const Icon = card.icon ? iconMap[card.icon] : undefined
        return (
        <motion.article
          key={card.label}
          className={`rounded-[1.4rem] border bg-white/75 p-4 shadow-[0_18px_44px_rgba(71,53,29,0.08)] backdrop-blur-md ${toneClasses(card.tone)}`}
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 * index, duration: 0.28 }}
        >
          <div className="flex items-center justify-between gap-3">
            <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">{card.label}</p>
            {Icon ? <Icon className="h-4 w-4 text-stone-500" strokeWidth={1.8} /> : null}
          </div>
          <p className="mt-2 text-2xl font-semibold tracking-[-0.04em] text-stone-950">{card.value}</p>
          <p className="mt-2 text-sm text-stone-500">{card.note}</p>
        </motion.article>
        )
      })}
    </section>
  )
}
