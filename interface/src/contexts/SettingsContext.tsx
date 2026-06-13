import { createContext, useContext, useEffect, useMemo, useState } from 'react'

import { toast } from 'sonner'

import {
  defaultSettings,
  setCurrentSettings,
  type AppSettings,
} from '../lib/runtimeSettings'
import { resolveTerm, terminologyMap, type TermKey } from '../lib/terminology'

const STORAGE_KEY = 'app_settings'

type SettingsContextValue = {
  settings: AppSettings
  updateSettings: (patch: Partial<AppSettings>) => void
  resetSettings: () => void
  term: (key: TermKey) => string
  rawKey: (key: TermKey) => string
  settingsSignature: string
}

const SettingsContext = createContext<SettingsContextValue | null>(null)

function loadSettings(): AppSettings {
  if (typeof window === 'undefined') return defaultSettings
  try {
    const storage = window.localStorage
    if (!storage || typeof storage.getItem !== 'function') {
      return defaultSettings
    }
    const raw = storage.getItem(STORAGE_KEY)
    if (!raw) return defaultSettings
    const parsed = JSON.parse(raw) as Partial<AppSettings> & { engineTarget?: string }
    return {
      ...defaultSettings,
      ...parsed,
      engineTarget: 'v4',
    } as AppSettings
  } catch {
    return defaultSettings
  }
}

export function SettingsProvider({ children }: { children: React.ReactNode }) {
  const [settings, setSettings] = useState<AppSettings>(loadSettings)
  const [hydrated, setHydrated] = useState(false)

  useEffect(() => {
    setCurrentSettings(settings)
  }, [settings])

  useEffect(() => {
    if (typeof document === 'undefined') {
      return
    }
    document.documentElement.dataset.theme = settings.theme
    document.documentElement.style.colorScheme = settings.theme
  }, [settings.theme])

  useEffect(() => {
    if (!hydrated) {
      setHydrated(true)
      return
    }
    const storage = typeof window === 'undefined' ? null : window.localStorage
    if (!storage || typeof storage.setItem !== 'function') {
      return
    }
    storage.setItem(STORAGE_KEY, JSON.stringify(settings))
    toast.success('Preferences updated', {
      description: 'Your settings were saved locally and applied across the interface.',
      duration: 1400,
    })
  }, [hydrated, settings])

  const value = useMemo<SettingsContextValue>(() => ({
    settings,
    updateSettings: (patch) => {
      setSettings((current) => ({ ...current, ...patch }))
    },
    resetSettings: () => {
      setSettings(defaultSettings)
    },
    term: (key) => resolveTerm(key, settings.terminology),
    rawKey: (key) => terminologyMap[key].developer,
    settingsSignature: JSON.stringify(settings),
  }), [settings])

  return <SettingsContext.Provider value={value}>{children}</SettingsContext.Provider>
}

export function useSettings() {
  const context = useContext(SettingsContext)
  if (!context) {
    throw new Error('useSettings must be used within SettingsProvider')
  }
  return context
}
