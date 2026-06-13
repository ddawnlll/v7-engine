import { useEffect } from 'react'
import { Play, Radar } from 'lucide-react'
import { useForm } from 'react-hook-form'

type ScanJobFormValues = {
  symbols: string[]
  intervals: string[]
  modes: string[]
  scan_workers: number
}

function toggleItem(values: string[], item: string) {
  return values.includes(item) ? values.filter((value) => value !== item) : [...values, item]
}

function ChipGroup({
  label,
  values,
  selected,
  onToggle,
  onSelectAll,
  onClear,
  helper,
}: {
  label: string
  values: string[]
  selected: string[]
  onToggle: (value: string) => void
  onSelectAll: () => void
  onClear: () => void
  helper: string
}) {
  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="grid gap-1">
          <span className="text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-stone-500">{label}</span>
          <small className="text-sm text-stone-500">{helper}</small>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="rounded-full border border-stone-900/8 bg-white px-3 py-1.5 text-xs font-semibold text-stone-700 transition hover:bg-stone-950/[0.03]"
            onClick={onSelectAll}
          >
            Select All
          </button>
          <button
            type="button"
            className="rounded-full border border-stone-900/8 bg-white px-3 py-1.5 text-xs font-semibold text-stone-700 transition hover:bg-stone-950/[0.03]"
            onClick={onClear}
          >
            Clear
          </button>
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        {values.map((value) => {
          const active = selected.includes(value)
          return (
            <button
              key={value}
              type="button"
              className={`rounded-full px-4 py-2.5 text-sm font-semibold transition ${
                active
                  ? 'theme-active-chip'
                  : 'border border-stone-900/8 bg-white text-stone-700 hover:bg-stone-950/[0.03]'
              }`}
              onClick={() => onToggle(value)}
            >
              {value.replaceAll('_', ' ')}
            </button>
          )
        })}
      </div>
    </div>
  )
}

export function ScanJobForm({
  onSubmit,
  isSubmitting,
  availableSymbols = [],
  availableIntervals = [],
  availableModes = ['SCALP', 'SWING', 'AGGRESSIVE_SCALP'],
  defaultModes,
  modeIntervalPolicy = {},
}: {
  onSubmit: (values: { symbols: string[]; intervals: string[]; modes: string[]; scan_workers: number }) => void
  isSubmitting: boolean
  availableSymbols?: string[]
  availableIntervals?: string[]
  availableModes?: string[]
  defaultModes?: string[]
  modeIntervalPolicy?: Record<string, string[]>
}) {
  const form = useForm<ScanJobFormValues>({
    defaultValues: {
      symbols: availableSymbols.slice(0, 4),
      intervals: availableIntervals.slice(0, 2),
      modes: defaultModes?.length ? defaultModes : availableModes.slice(0, 2),
      scan_workers: 4,
    },
  })

  const values = form.watch()

  useEffect(() => {
    const currentValues = form.getValues()
    const nextSymbols = currentValues.symbols.length ? currentValues.symbols : availableSymbols.slice(0, 4)
    const nextIntervals = currentValues.intervals.length ? currentValues.intervals : availableIntervals.slice(0, 2)
    const nextModes = currentValues.modes.length ? currentValues.modes : (defaultModes?.length ? defaultModes : availableModes.slice(0, 2))

    if (
      nextSymbols.join('|') === currentValues.symbols.join('|') &&
      nextIntervals.join('|') === currentValues.intervals.join('|') &&
      nextModes.join('|') === currentValues.modes.join('|')
    ) {
      return
    }

    form.reset({
      ...currentValues,
      symbols: nextSymbols,
      intervals: nextIntervals,
      modes: nextModes,
    })
  }, [availableIntervals, availableModes, availableSymbols, defaultModes, form])

  const estimatedTasks = values.symbols.length * values.intervals.length * values.modes.length
  const throughput = Math.max(1, values.scan_workers)
  const estimatedMinutes = estimatedTasks ? Math.max(1, Math.ceil(estimatedTasks / (throughput * 6))) : 0
  const selectedModePolicies = values.modes.map((mode) => ({
    mode,
    allowed: (modeIntervalPolicy[mode] ?? []).filter((interval) => availableIntervals.includes(interval)),
  }))
  const intervalCoverage = availableIntervals.map((interval) => ({
    interval,
    modes: selectedModePolicies.filter((entry) => entry.allowed.includes(interval)).map((entry) => entry.mode),
  }))

  return (
    <form
      className="grid gap-5"
      onSubmit={form.handleSubmit((currentValues) => {
        onSubmit(currentValues)
      })}
    >
      <div className="grid gap-4 rounded-[1.5rem] bg-stone-950/[0.03] p-4">
        <div className="flex items-center gap-3">
          <Radar className="h-4 w-4 text-teal-800" strokeWidth={1.8} />
          <p className="text-sm font-semibold text-stone-900">Scan Builder</p>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {[
            ['Symbols', values.symbols.length],
            ['Intervals', values.intervals.length],
            ['Modes', values.modes.length],
            ['Estimated', estimatedTasks ? `~${estimatedMinutes}m` : '—'],
          ].map(([label, value]) => (
            <div key={String(label)} className="rounded-[1rem] bg-white/90 px-4 py-3 shadow-[0_12px_24px_rgba(71,53,29,0.05)]">
              <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">{label}</p>
              <p className="mt-2 text-xl font-semibold tracking-[-0.04em] text-stone-950">{value}</p>
            </div>
          ))}
        </div>
        <ChipGroup
          label="Symbols"
          values={availableSymbols}
          selected={values.symbols}
          helper="Tap the markets you want included in the next queued scan."
          onToggle={(value) => form.setValue('symbols', toggleItem(values.symbols, value), { shouldValidate: true })}
          onSelectAll={() => form.setValue('symbols', [...availableSymbols], { shouldValidate: true })}
          onClear={() => form.setValue('symbols', [], { shouldValidate: true })}
        />
        <ChipGroup
          label="Intervals"
          values={availableIntervals}
          selected={values.intervals}
          helper="Choose the global interval universe. The engine will only run mode/interval pairs allowed by the policy below."
          onToggle={(value) => form.setValue('intervals', toggleItem(values.intervals, value), { shouldValidate: true })}
          onSelectAll={() => form.setValue('intervals', [...availableIntervals], { shouldValidate: true })}
          onClear={() => form.setValue('intervals', [], { shouldValidate: true })}
        />
        <ChipGroup
          label="Modes"
          values={availableModes}
          selected={values.modes}
          helper="Use the active v3 runtime mode taxonomy."
          onToggle={(value) => form.setValue('modes', toggleItem(values.modes, value), { shouldValidate: true })}
          onSelectAll={() => form.setValue('modes', [...availableModes], { shouldValidate: true })}
          onClear={() => form.setValue('modes', [], { shouldValidate: true })}
        />
        <div className="grid gap-3 rounded-[1.2rem] border border-stone-900/8 bg-white/88 p-4">
          <div className="flex items-center justify-between gap-3">
            <div className="grid gap-1">
              <span className="text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-stone-500">Mode Interval Policy</span>
              <small className="text-sm text-stone-500">This is what the queue runner will actually allow for the currently selected modes.</small>
            </div>
            <span className="rounded-full bg-stone-950/[0.03] px-3 py-1.5 text-xs font-semibold text-stone-600">
              {selectedModePolicies.length} modes selected
            </span>
          </div>
          <div className="grid gap-3 xl:grid-cols-3">
            {selectedModePolicies.length ? selectedModePolicies.map(({ mode, allowed }) => (
              <div key={mode} className="rounded-[1rem] border border-stone-900/8 bg-stone-950/[0.03] p-4">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-sm font-semibold text-stone-950">{mode.replaceAll('_', ' ')}</p>
                  <span className="rounded-full bg-white px-2.5 py-1 text-[0.68rem] font-semibold uppercase tracking-[0.12em] text-stone-600">
                    {allowed.length} intervals
                  </span>
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {allowed.length ? allowed.map((interval) => (
                    <span key={`${mode}-${interval}`} className="rounded-full border border-stone-900/8 bg-white px-3 py-1.5 text-xs font-semibold text-stone-700">
                      {interval}
                    </span>
                  )) : (
                    <span className="text-sm text-stone-500">Falls back to the selected global intervals.</span>
                  )}
                </div>
              </div>
            )) : (
              <div className="rounded-[1rem] border border-dashed border-stone-900/12 px-4 py-4 text-sm text-stone-500 xl:col-span-3">
                Select at least one mode to see its allowed interval set.
              </div>
            )}
          </div>
          <div className="grid gap-2">
            <span className="text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-stone-500">Interval Coverage</span>
            <div className="flex flex-wrap gap-2">
              {intervalCoverage.map(({ interval, modes }) => (
                <div
                  key={`coverage-${interval}`}
                  className={`rounded-full border px-3 py-1.5 text-xs font-semibold ${
                    modes.length
                      ? 'border-teal-900/10 bg-teal-50/80 text-teal-900'
                      : 'border-amber-900/10 bg-amber-50/80 text-amber-900'
                  }`}
                >
                  {interval}
                  <span className="ml-2 opacity-80">
                    {modes.length ? modes.map((mode) => mode.replaceAll('_', ' ')).join(' · ') : 'unused by selected modes'}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="grid gap-3 rounded-[1.5rem] bg-white/82 p-4 shadow-[0_12px_24px_rgba(71,53,29,0.05)]">
        <span className="text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-stone-500">Workers</span>
        <div className="flex flex-wrap gap-2">
          {[1, 2, 4, 8, 16, 32, 64, 128].map((workerCount) => (
            <button
              key={workerCount}
              type="button"
              className={`rounded-full px-4 py-2.5 text-sm font-semibold transition ${
                values.scan_workers === workerCount
                  ? 'theme-active-chip'
                  : 'border border-stone-900/8 bg-white text-stone-700 hover:bg-stone-950/[0.03]'
              }`}
              onClick={() => form.setValue('scan_workers', workerCount)}
            >
              {workerCount} worker{workerCount > 1 ? 's' : ''}
            </button>
          ))}
        </div>
      </div>

      <button
        type="submit"
        className="inline-flex items-center justify-center gap-2 rounded-full bg-stone-950 px-4 py-3 text-sm font-semibold text-stone-50 transition hover:-translate-y-0.5 hover:bg-stone-900 disabled:cursor-not-allowed disabled:opacity-60"
        disabled={isSubmitting || !values.symbols.length || !values.intervals.length || !values.modes.length}
      >
        <Play className="h-4 w-4" strokeWidth={1.8} />
        {isSubmitting ? 'Queueing Scan' : 'Submit Scan Job'}
      </button>
    </form>
  )
}
