import { Check, Code2, Gauge, Languages, RefreshCw, RotateCcw } from 'lucide-react'

import { AnimatedRoute } from '../components/ui/AnimatedRoute'
import { useSettings } from '../contexts/SettingsContext'
import type { TermKey } from '../lib/terminology'

const previewKeys: TermKey[] = [
  'net_r',
  'win_rate',
  'max_drawdown',
  'profit_factor',
  'realized_r',
  'engine_thread',
  'regime',
]

function ChoicePill({
  active,
  label,
  description,
  onClick,
}: {
  active: boolean
  label: string
  description: string
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-[1.25rem] border px-4 py-3 text-left transition ${
        active
          ? 'theme-active-chip'
          : 'border-stone-900/8 bg-white text-stone-700 hover:bg-stone-950/[0.03]'
      }`}
    >
      <div className="text-sm font-semibold">{label}</div>
      <div className={`mt-1 text-sm leading-6 ${active ? 'text-stone-300' : 'text-stone-500'}`}>{description}</div>
    </button>
  )
}

export function SettingsRoute() {
  const { settings, updateSettings, resetSettings, term, rawKey } = useSettings()

  return (
    <AnimatedRoute>
      <div className="grid gap-4">
        <section className="rounded-[1.7rem] border border-stone-900/8 bg-white/84 px-4 py-4 shadow-[0_18px_40px_rgba(77,62,40,0.08)]">
          <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
            <div className="grid gap-2">
              <p className="text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-teal-800">Preferences</p>
              <h1 className="text-3xl font-semibold tracking-[-0.05em] text-stone-950">Personal preferences for this interface.</h1>
              <p className="max-w-3xl text-sm leading-7 text-stone-500">
                These settings are local to this machine and only affect how the interface looks and behaves for this operator.
              </p>
            </div>
            <div className="flex items-center gap-2 text-sm text-teal-900">
              <Check className="h-4 w-4" strokeWidth={1.8} />
              Saved automatically
            </div>
          </div>
        </section>

        <section className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
          <div className="grid gap-4">
            <div className="rounded-[1.6rem] border border-stone-900/8 bg-white/82 p-5 shadow-[0_18px_40px_rgba(77,62,40,0.08)]">
              <div className="mb-4 grid gap-1">
                <p className="text-sm font-semibold uppercase tracking-[0.18em] text-stone-500">Scope</p>
                <h2 className="text-xl font-semibold text-stone-950">Interface-Only Preferences</h2>
              </div>
              <div className="rounded-[1.25rem] border border-teal-900/10 bg-[linear-gradient(135deg,rgba(16,98,91,0.08),rgba(255,255,255,0.96))] px-4 py-4">
                <p className="text-sm font-semibold text-stone-950">Runtime behavior is configured elsewhere.</p>
                <p className="mt-2 text-sm leading-7 text-stone-500">
                  Trading behavior, engine flags, and runtime thresholds belong in <code>Operate &gt; Config</code>. This page only controls local display and workflow preferences.
                </p>
              </div>
            </div>

            <div className="rounded-[1.6rem] border border-stone-900/8 bg-white/82 p-5 shadow-[0_18px_40px_rgba(77,62,40,0.08)]">
              <div className="mb-4 flex items-center gap-3">
                <Languages className="h-5 w-5 text-teal-800" strokeWidth={1.8} />
                <div>
                  <p className="text-sm font-semibold uppercase tracking-[0.18em] text-stone-500">Display</p>
                  <h2 className="mt-1 text-xl font-semibold text-stone-950">Terminology Mode</h2>
                </div>
              </div>
              <p className="mb-4 text-sm leading-7 text-stone-500">
                Controls how trading, portfolio, and engine labels appear throughout the app.
              </p>
              <div className="grid gap-3 md:grid-cols-3">
                <ChoicePill
                  active={settings.terminology === 'simplified'}
                  label="Simplified"
                  description="Plain English labels with no assumed trading jargon."
                  onClick={() => updateSettings({ terminology: 'simplified' })}
                />
                <ChoicePill
                  active={settings.terminology === 'advanced'}
                  label="Advanced"
                  description="Standard trading and quant terminology."
                  onClick={() => updateSettings({ terminology: 'advanced' })}
                />
                <ChoicePill
                  active={settings.terminology === 'developer'}
                  label="Developer"
                  description="Raw backend field names and payload-oriented language."
                  onClick={() => updateSettings({ terminology: 'developer' })}
                />
              </div>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <div className="rounded-[1.6rem] border border-stone-900/8 bg-white/82 p-5 shadow-[0_18px_40px_rgba(77,62,40,0.08)]">
                <div className="mb-4 flex items-center gap-3">
                  <Gauge className="h-5 w-5 text-teal-800" strokeWidth={1.8} />
                  <div>
                    <p className="text-sm font-semibold uppercase tracking-[0.18em] text-stone-500">Display</p>
                    <h2 className="mt-1 text-lg font-semibold text-stone-950">Number Precision</h2>
                  </div>
                </div>
                <div className="grid gap-2 sm:grid-cols-2">
                  {[2, 3, 4, 'auto'].map((value) => (
                    <ChoicePill
                      key={String(value)}
                      active={settings.numberPrecision === value}
                      label={String(value).toUpperCase()}
                      description={value === 'auto' ? 'Use each panel’s preferred precision.' : `${value} decimal places across metrics.`}
                      onClick={() => updateSettings({ numberPrecision: value as 2 | 3 | 4 | 'auto' })}
                    />
                  ))}
                </div>
              </div>

              <div className="rounded-[1.6rem] border border-stone-900/8 bg-white/82 p-5 shadow-[0_18px_40px_rgba(77,62,40,0.08)]">
                <div className="mb-4 flex items-center gap-3">
                  <RefreshCw className="h-5 w-5 text-teal-800" strokeWidth={1.8} />
                  <div>
                    <p className="text-sm font-semibold uppercase tracking-[0.18em] text-stone-500">Display</p>
                    <h2 className="mt-1 text-lg font-semibold text-stone-950">Time Format</h2>
                  </div>
                </div>
                <div className="grid gap-2">
                  <ChoicePill
                    active={settings.timeFormat === 'relative'}
                    label="Relative"
                    description='Show timestamps like "3 minutes ago".'
                    onClick={() => updateSettings({ timeFormat: 'relative' })}
                  />
                  <ChoicePill
                    active={settings.timeFormat === 'absolute'}
                    label="Absolute"
                    description='Show timestamps like "14:32:01".'
                    onClick={() => updateSettings({ timeFormat: 'absolute' })}
                  />
                  <ChoicePill
                    active={settings.timeFormat === 'both'}
                    label="Both"
                    description='Show "14:32:01 (3m ago)" side by side.'
                    onClick={() => updateSettings({ timeFormat: 'both' })}
                  />
                </div>
              </div>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <div className="rounded-[1.6rem] border border-stone-900/8 bg-white/82 p-5 shadow-[0_18px_40px_rgba(77,62,40,0.08)]">
                <div className="mb-4 flex items-center gap-3">
                  <RefreshCw className="h-5 w-5 text-teal-800" strokeWidth={1.8} />
                  <div>
                    <p className="text-sm font-semibold uppercase tracking-[0.18em] text-stone-500">Data</p>
                    <h2 className="mt-1 text-lg font-semibold text-stone-950">Dashboard Refresh Interval</h2>
                  </div>
                </div>
                <div className="grid gap-2 sm:grid-cols-2">
                  {[
                    { value: 30, label: '30s', description: 'Fast polling for active operator work.' },
                    { value: 60, label: '60s', description: 'Balanced refresh and lower churn.' },
                    { value: 300, label: '5m', description: 'Light-touch monitoring cadence.' },
                    { value: null, label: 'Manual only', description: 'Disable auto-refresh and use refresh buttons.' },
                  ].map((choice) => (
                    <ChoicePill
                      key={String(choice.label)}
                      active={settings.refreshInterval === choice.value}
                      label={choice.label}
                      description={choice.description}
                      onClick={() => updateSettings({ refreshInterval: choice.value as 30 | 60 | 300 | null })}
                    />
                  ))}
                </div>
              </div>

              <div className="rounded-[1.6rem] border border-stone-900/8 bg-white/82 p-5 shadow-[0_18px_40px_rgba(77,62,40,0.08)]">
                <div className="mb-4 flex items-center gap-3">
                  <Gauge className="h-5 w-5 text-teal-800" strokeWidth={1.8} />
                  <div>
                    <p className="text-sm font-semibold uppercase tracking-[0.18em] text-stone-500">Data</p>
                    <h2 className="mt-1 text-lg font-semibold text-stone-950">KPI Delta Window</h2>
                  </div>
                </div>
                <div className="grid gap-2 sm:grid-cols-3">
                  {[7, 14, 30].map((value) => (
                    <ChoicePill
                      key={value}
                      active={settings.kpiDeltaWindow === value}
                      label={`${value} days`}
                      description="Used for trend deltas and comparison ribbons."
                      onClick={() => updateSettings({ kpiDeltaWindow: value as 7 | 14 | 30 })}
                    />
                  ))}
                </div>
              </div>
            </div>

            <div className="rounded-[1.6rem] border border-stone-900/8 bg-white/82 p-5 shadow-[0_18px_40px_rgba(77,62,40,0.08)]">
              <div className="mb-4 flex items-center gap-3">
                <Code2 className="h-5 w-5 text-teal-800" strokeWidth={1.8} />
                <div>
                  <p className="text-sm font-semibold uppercase tracking-[0.18em] text-stone-500">Developer</p>
                  <h2 className="mt-1 text-xl font-semibold text-stone-950">Debug Preferences</h2>
                </div>
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <ChoicePill
                  active={settings.showRawKeys}
                  label="Show Raw Payload Keys"
                  description="Show backend field names in muted text beneath key labels where supported."
                  onClick={() => updateSettings({ showRawKeys: !settings.showRawKeys })}
                />
                <ChoicePill
                  active={settings.showApiInspector}
                  label="API Response Inspector"
                  description="Enable raw dashboard payload inspection on developer-focused screens."
                  onClick={() => updateSettings({ showApiInspector: !settings.showApiInspector })}
                />
              </div>
            </div>
          </div>

          <div className="grid gap-4">
            <div className="rounded-[1.6rem] border border-stone-900/8 bg-[linear-gradient(180deg,rgba(255,255,255,0.9),rgba(248,244,236,0.95))] p-5 shadow-[0_18px_40px_rgba(77,62,40,0.08)]">
              <h2 className="text-xl font-semibold tracking-[-0.04em] text-stone-950">Live Preview</h2>
              <p className="mt-2 text-sm leading-7 text-stone-500">
                Switch modes and see how core metrics change before you keep working elsewhere.
              </p>
              <div className="mt-4 grid gap-3">
                {previewKeys.map((key) => (
                  <div key={key} className="rounded-[1.2rem] border border-stone-900/8 bg-white/85 px-4 py-3">
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-sm font-semibold text-stone-950">{rawKey(key)}</span>
                      <span className="text-sm text-stone-400">→</span>
                      <span className="text-sm font-semibold text-teal-900">{term(key)}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-[1.6rem] border border-stone-900/8 bg-white/82 p-5 shadow-[0_18px_40px_rgba(77,62,40,0.08)]">
              <h2 className="text-xl font-semibold tracking-[-0.04em] text-stone-950">Current Configuration</h2>
              <div className="mt-4 grid gap-3">
                {Object.entries(settings).map(([key, value]) => (
                  <div key={key} className="flex items-center justify-between rounded-[1.2rem] bg-stone-950/[0.03] px-4 py-3">
                    <span className="text-sm font-medium text-stone-600">{key}</span>
                    <span className="font-mono text-sm text-stone-950">{String(value)}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-[1.6rem] border border-stone-900/8 bg-white/82 p-5 shadow-[0_18px_40px_rgba(77,62,40,0.08)]">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <h2 className="text-xl font-semibold tracking-[-0.04em] text-stone-950">Reset</h2>
                  <p className="mt-2 text-sm leading-7 text-stone-500">
                    Return terminology, time formatting, precision, and developer helpers to their defaults.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={resetSettings}
                  className="inline-flex items-center gap-2 rounded-full bg-stone-950 px-5 py-3 text-sm font-semibold text-stone-50 transition hover:-translate-y-0.5 hover:bg-stone-900"
                >
                  <RotateCcw className="h-4 w-4" strokeWidth={1.8} />
                  Reset to defaults
                </button>
              </div>
            </div>
          </div>
        </section>
      </div>
    </AnimatedRoute>
  )
}
