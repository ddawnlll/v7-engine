import type { ReactNode } from 'react'

type PageHeaderProps = {
  eyebrow: string
  title: string
  description: string
  actions?: ReactNode
  meta?: ReactNode
}

export function PageHeader({ eyebrow, title, description, actions, meta }: PageHeaderProps) {
  return (
    <section className="grid gap-5 rounded-[2rem] border border-stone-900/8 bg-white/72 p-6 shadow-[0_24px_64px_rgba(77,62,40,0.08)] backdrop-blur-md lg:grid-cols-[1.6fr_0.85fr] lg:p-7">
      <div className="grid gap-4">
        <div className="grid gap-3">
          <p className="text-[0.72rem] font-semibold uppercase tracking-[0.24em] text-teal-800">{eyebrow}</p>
          <h1 className="max-w-4xl text-3xl font-semibold tracking-[-0.06em] text-stone-950 sm:text-4xl lg:text-[3.4rem]">
            {title}
          </h1>
          <p className="max-w-3xl text-sm leading-7 text-stone-600 sm:text-[0.98rem]">{description}</p>
        </div>
        {actions ? <div className="flex flex-wrap gap-3">{actions}</div> : null}
      </div>
      {meta ? <div className="grid gap-3">{meta}</div> : null}
    </section>
  )
}
