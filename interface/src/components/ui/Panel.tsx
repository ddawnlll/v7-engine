import type { ReactNode } from 'react'

type PanelProps = {
  eyebrow?: string
  title: string
  actions?: ReactNode
  wide?: boolean
  children: ReactNode
}

export function Panel({ eyebrow, title, actions, wide = false, children }: PanelProps) {
  return (
    <section className={`${wide ? 'lg:col-span-2' : ''} min-w-0 rounded-[1.8rem] border border-stone-900/8 bg-white/74 p-5 shadow-[0_24px_64px_rgba(77,62,40,0.08)] backdrop-blur-md sm:p-6`}>
      <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          {eyebrow ? <p className="mb-2 text-[0.72rem] font-semibold uppercase tracking-[0.22em] text-teal-800">{eyebrow}</p> : null}
          <h2 className="text-[1.55rem] font-semibold tracking-[-0.04em] text-stone-950">{title}</h2>
        </div>
        {actions}
      </div>
      {children}
    </section>
  )
}
