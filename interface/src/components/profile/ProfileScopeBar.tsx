import type { ProfileScopeOption, ProfileScopeValue } from '../../lib/types'

export function ProfileScopeBar({
  options,
  value,
  onChange,
}: {
  options: ProfileScopeOption[]
  value: ProfileScopeValue
  onChange: (nextValue: ProfileScopeValue) => void
}) {
  return (
    <section className="rounded-[1.4rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_14px_30px_rgba(77,62,40,0.06)]">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="grid gap-1">
          <p className="text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-teal-800">Profile scope</p>
          <p className="text-sm text-stone-500">Page-level profile context for profile-owned runtime views. Global navigation and system chrome stay outside this scope.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {options.map((option) => {
            const selected = option.value === value
            return (
              <button
                key={option.value}
                type="button"
                disabled={!option.enabled}
                onClick={() => onChange(option.value)}
                title={option.description}
                className={`rounded-full px-3 py-2 text-sm font-semibold transition ${
                  selected
                    ? 'bg-stone-950 text-stone-50'
                    : option.enabled
                      ? 'border border-stone-900/8 bg-white text-stone-700 hover:bg-stone-950/[0.03]'
                      : 'border border-dashed border-stone-900/10 bg-stone-100/70 text-stone-400'
                }`}
              >
                {option.label}
              </button>
            )
          })}
        </div>
      </div>
    </section>
  )
}
