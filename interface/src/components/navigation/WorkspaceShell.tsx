import { NavLink, Outlet, useLocation } from 'react-router-dom'
import type { LucideIcon } from 'lucide-react'

import { withCurrentProfileScope } from '../../lib/profileScope'
import type { WorkspaceTab } from '../../lib/workspaces'

export function WorkspaceShell({
  label,
  description,
  icon: Icon,
  tabs,
}: {
  label: string
  description: string
  icon: LucideIcon
  tabs: WorkspaceTab[]
}) {
  const location = useLocation()

  return (
    <div className="grid gap-4">
      <section className="rounded-[1.7rem] border border-stone-900/8 bg-white/84 px-4 py-4 shadow-[0_18px_40px_rgba(77,62,40,0.08)]">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="grid gap-2">
            <p className="text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-teal-800">Workspace</p>
            <div className="flex flex-wrap items-center gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-stone-950 text-stone-50">
                <Icon className="h-5 w-5" />
              </div>
              <div className="grid gap-1">
                <h1 className="text-2xl font-semibold tracking-[-0.05em] text-stone-950">{label}</h1>
                <p className="text-sm text-stone-500">{description}</p>
              </div>
            </div>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          {tabs.map((tab) => (
            <NavLink
              key={tab.to}
              to={withCurrentProfileScope(tab.to, location.search)}
              className={({ isActive }) =>
                `inline-flex items-center rounded-full px-4 py-2 text-sm font-semibold transition ${
                  isActive
                    ? 'bg-stone-950 text-stone-50'
                    : 'border border-stone-900/8 bg-white text-stone-700 hover:bg-stone-950/[0.03]'
                }`
              }
            >
              {tab.label}
            </NavLink>
          ))}
        </div>
      </section>

      <Outlet />
    </div>
  )
}
