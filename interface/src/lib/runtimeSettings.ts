export type TerminologyMode = 'simplified' | 'advanced' | 'developer'
export type NumberPrecision = 2 | 3 | 4 | 'auto'
export type TimeFormatMode = 'relative' | 'absolute' | 'both'
export type EngineTargetMode = 'v4'
export type ThemeMode = 'light' | 'dark'

export type AppSettings = {
  engineTarget: EngineTargetMode
  theme: ThemeMode
  terminology: TerminologyMode
  numberPrecision: NumberPrecision
  timeFormat: TimeFormatMode
  refreshInterval: 30 | 60 | 300 | null
  kpiDeltaWindow: 7 | 14 | 30
  preferredProfileScope: string
  showRawKeys: boolean
  showApiInspector: boolean
}

export const defaultSettings: AppSettings = {
  engineTarget: 'v4',
  theme: 'light',
  terminology: 'advanced',
  numberPrecision: 'auto',
  timeFormat: 'absolute',
  refreshInterval: 60,
  kpiDeltaWindow: 7,
  preferredProfileScope: 'paper-main',
  showRawKeys: false,
  showApiInspector: false,
}

let currentSettings: AppSettings = defaultSettings

export function getCurrentSettings() {
  return currentSettings
}

export function setCurrentSettings(nextSettings: AppSettings) {
  currentSettings = nextSettings
}
