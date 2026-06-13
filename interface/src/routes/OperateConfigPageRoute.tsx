import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { AnimatedRoute } from "../components/ui/AnimatedRoute";
import { EmptyState } from "../components/ui/EmptyState";
import { ProfileScopeBar } from "../components/profile/ProfileScopeBar";
import {
  fetchPaperBalanceForScope,
  fetchRuntimeProfileReadOnlyExposure,
  fetchRuntimeProfileSettings,
  fetchRuntimeSettingsForScope,
  fetchRuntimeSettingsMetadataForScope,
} from "../lib/api";
import { useUpdateRuntimeSettingsMutation } from "../hooks/useUpdateRuntimeSettingsMutation";
import { useUpdateRuntimeProfileSettingsMutation } from "../hooks/useUpdateRuntimeProfileSettingsMutation";
import { useProfileScopeOptions } from "../hooks/useProfileScopeOptions";
import { DEFAULT_PROFILE_SCOPE, normalizeProfileScope, profileScopeToApiProfileId, profileScopeToRuntimeProfileId } from "../lib/profileScope";
import type { ProfileScopeValue, RuntimeSettingControl } from "../lib/types";
import { Search, RefreshCw, Copy, CheckCheck } from "lucide-react";

// ─── group definitions ────────────────────────────────────────────────────────

const PROFILE_SETTING_RUNTIME_KEYS = [
  'AUTONOMOUS_ENABLED',
  'AUTO_LIVE_GLOBAL_KILL_SWITCH',
  'AUTO_LIVE_PROFILE_KILL_SWITCH',
  'AUTO_LIVE_SYMBOL_ALLOWLIST',
  'AUTO_LIVE_MAX_CONCURRENT_POSITIONS',
] as const

const PROFILE_SETTING_RISK_KEYS = [
  'LIVE_RISK_BASIS',
  'LIVE_RISK_PER_TRADE_PCT',
  'LIVE_DEFAULT_ENTRY_R_MULTIPLE',
  'LIVE_MAX_POSITION_R',
  'LIVE_MAX_TOTAL_OPEN_R',
  'LIVE_MAX_DAILY_LOSS_R',
  'LIVE_MAX_LEVERAGE',
] as const

const PROFILE_CAPABILITY_KEYS = [
  'read_only',
  'manual_trading_enabled',
  'auto_trading_enabled',
  'default_for_auto_trading',
] as const

const GROUPS = [
  {
    id: "profile-settings",
    title: "Profile Settings",
    icon: "🪪",
    matchers: [] as string[],
  },
  {
    id: "execution",
    title: "Execution",
    icon: "⚡",
    matchers: ["AUTONOMOUS_", "SCAN_", "WORKER"],
  },
  {
    id: "risk",
    title: "Risk",
    icon: "🛡",
    matchers: ["RISK", "LOSS", "BREAKER", "ENTRY_R", "POSITION_R", "LIVE_MAX_", "LIVE_DEFAULT_ENTRY_R_MULTIPLE", "LIVE_RISK_", "CONFIDENCE"],
  },
  {
    id: "universe",
    title: "Universe",
    icon: "🌐",
    matchers: ["SYMBOL", "INTERVAL", "MODE"],
  },
  {
    id: "learning",
    title: "Learning",
    icon: "🧠",
    matchers: ["LEARNING", "CALIBRATION"],
  },
  {
    id: "engine",
    title: "Engine Binding",
    icon: "⚙️",
    matchers: ["ENGINE", "SHADOW", "V6_"],
  },
  {
    id: "budgeting",
    title: "Request Budgeting",
    icon: "⏱",
    matchers: ["BUDGET", "TIMEOUT"],
  },
];

// ─── helpers ──────────────────────────────────────────────────────────────────

function getGroupEntries(
  settings: Record<string, unknown>,
  matchers: string[],
) {
  return Object.entries(settings).filter(([key]) =>
    matchers.some((m) => key.toUpperCase().includes(m)),
  );
}

function stringifySettings(settings: Record<string, unknown>) {
  return Object.fromEntries(
    Object.entries(settings).map(([key, value]) => [
      key,
      value === null || value === undefined ? "" : String(value),
    ]),
  );
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  const s = String(value);
  return s.length === 0 ? "(empty)" : s;
}

function valueIsList(value: string) {
  return value.includes(",") && value.length > 20;
}

function parseNumber(value: string, fallback = 0) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

function formatUsd(value: number) {
  return `${value.toFixed(value >= 10 ? 2 : 3)} USDT`
}

function splitCsv(value: string) {
  return String(value ?? '').split(',').map((item) => item.trim()).filter(Boolean)
}

function isTruthyString(value: string) {
  return ['1', 'true', 'yes', 'on'].includes(String(value ?? '').toLowerCase())
}

function humanizeCapabilityLabel(key: string) {
  if (key === 'read_only') return 'Read only'
  if (key === 'manual_trading_enabled') return 'Manual live enabled'
  if (key === 'auto_trading_enabled') return 'Auto live enabled'
  if (key === 'default_for_auto_trading') return 'Default for auto routing'
  return key.replaceAll('_', ' ')
}

function formatNumericValue(value: number, unit?: string | null) {
  if (unit === 'percent') return `${value.toFixed(Number.isInteger(value) ? 0 : 2)}%`
  if (unit === 'ratio') return value.toFixed(3)
  if (unit === 'R') return `${value.toFixed(2)}R`
  if (unit === 'x') return `${Math.round(value)}x`
  if (unit === 'seconds') return `${value.toFixed(0)}s`
  if (unit === 'minutes') return `${value.toFixed(0)}m`
  if (unit === 'ms') return `${value.toFixed(0)} ms`
  if (unit === 'usdt') return `${value.toFixed(0)} USDT`
  return Number.isInteger(value) ? String(value) : value.toFixed(2)
}

function normalizeSteppedValue(rawValue: number, min: number, max: number, step: number) {
  const clamped = Math.min(max, Math.max(min, rawValue))
  const normalized = Math.round((clamped - min) / step) * step + min
  return Number(normalized.toFixed(6))
}

function numberPresets(control?: RuntimeSettingControl | null) {
  switch (control?.key) {
    case 'LIVE_RISK_PER_TRADE_PCT':
      return [0.0025, 0.005, 0.01, 0.02, 0.05]
    case 'LIVE_DEFAULT_ENTRY_R_MULTIPLE':
    case 'LIVE_MAX_POSITION_R':
      return [0.5, 1, 2, 3, 5]
    case 'LIVE_MAX_TOTAL_OPEN_R':
    case 'LIVE_MAX_DAILY_LOSS_R':
      return [1, 2, 3, 4, 6, 8]
    case 'LIVE_MAX_LEVERAGE':
      return [1, 2, 3, 5, 10, 20]
    case 'AUTO_LIVE_MAX_CONCURRENT_POSITIONS':
      return [0, 1, 2, 3, 5, 10]
    case 'AUTONOMOUS_SCAN_WORKERS':
      return [1, 2, 4, 8, 16, 32, 64, 128]
    case 'AUTONOMOUS_SCAN_INTERVAL_SECONDS':
      return [60, 300, 900, 1800, 3600]
    case 'AUTONOMOUS_MONITOR_INTERVAL_SECONDS':
      return [5, 15, 30, 60, 120]
    default:
      return []
  }
}

// ─── copy hook ────────────────────────────────────────────────────────────────

function useCopy() {
  const [copied, setCopied] = useState<string | null>(null);
  function copy(key: string, value: string) {
    navigator.clipboard.writeText(value).then(() => {
      setCopied(key);
      setTimeout(() => setCopied(null), 1500);
    });
  }
  return { copied, copy };
}

// ─── sub-components ───────────────────────────────────────────────────────────

function CapabilityRow({
  rowKey,
  value,
  description,
  onChange,
  disabled = false,
}: {
  rowKey: string;
  value: boolean;
  description: string;
  onChange: (value: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-3 transition hover:border-zinc-700">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-[0.65rem] font-semibold uppercase tracking-[0.18em] text-zinc-500">
            {humanizeCapabilityLabel(rowKey)}
          </p>
          <p className="mt-1 text-xs text-zinc-500">{description}</p>
        </div>
        <button
          type="button"
          onClick={() => onChange(!value)}
          disabled={disabled}
          className={`inline-flex min-w-[5.5rem] items-center justify-center rounded-md px-3 py-1.5 text-xs font-semibold transition ${
            value
              ? 'bg-teal-500 text-zinc-950 hover:bg-teal-400'
              : 'border border-zinc-800 bg-zinc-950 text-zinc-300 hover:border-zinc-700'
          } ${disabled ? 'opacity-50' : ''}`}
        >
          {value ? 'Enabled' : 'Disabled'}
        </button>
      </div>
    </div>
  )
}

function ConfigRow({
  rowKey,
  value,
  control,
  onCopy,
  copied,
  onChange,
  disabled = false,
  currentBalance,
}: {
  rowKey: string;
  value: string;
  control?: RuntimeSettingControl | null;
  onCopy: () => void;
  copied: boolean;
  onChange: (value: string) => void;
  disabled?: boolean;
  currentBalance?: number | null;
}) {
  const isEmpty = value.length === 0;
  const isLiveRiskPerTrade = rowKey === 'LIVE_RISK_PER_TRADE_PCT';
  const isLiveDefaultEntryRMultiple = rowKey === 'LIVE_DEFAULT_ENTRY_R_MULTIPLE';
  const isLiveMaxPositionR = rowKey === 'LIVE_MAX_POSITION_R';
  const isLiveMaxLeverage = rowKey === 'LIVE_MAX_LEVERAGE';
  const options = control?.options ?? [];
  const selectedItems = splitCsv(value);
  const numericValue = parseNumber(value, control?.min_value ?? 0);
  const minValue = Number(control?.min_value ?? 0);
  const maxValue = Number(control?.max_value ?? Math.max(minValue, numericValue || 0));
  const stepValue = Number(control?.step ?? 1);
  const canRenderNumber = control?.control === 'number' && Number.isFinite(minValue) && Number.isFinite(maxValue) && Number.isFinite(stepValue) && stepValue > 0;
  const sliderValue = canRenderNumber
    ? normalizeSteppedValue(numericValue || minValue, minValue, maxValue, stepValue)
    : numericValue;
  const updateNumber = (next: number) => onChange(String(normalizeSteppedValue(next, minValue, maxValue, stepValue)));

  return (
    <div className="group relative rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-3 transition hover:border-zinc-700">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <p className="text-[0.65rem] font-semibold uppercase tracking-[0.18em] text-zinc-500 select-all">
            {rowKey}
          </p>
          <p className="mt-1 text-sm font-semibold text-zinc-100">{control?.label ?? rowKey}</p>
          {control?.description ? <p className="mt-1 text-xs leading-6 text-zinc-500">{control.description}</p> : null}

          {control?.control === 'boolean' ? (
            <div className="mt-3 flex flex-wrap gap-2">
              {[
                { next: 'true', label: 'Enabled' },
                { next: 'false', label: 'Disabled' },
              ].map((option) => (
                <button
                  key={option.next}
                  type="button"
                  onClick={() => onChange(option.next)}
                  disabled={disabled}
                  className={`rounded-md px-3 py-1.5 text-xs font-semibold transition ${
                    value === option.next
                      ? 'bg-teal-500 text-zinc-950'
                      : 'border border-zinc-800 bg-zinc-950 text-zinc-300 hover:border-zinc-700'
                  } ${disabled ? 'opacity-50' : ''}`}
                >
                  {option.label}
                </button>
              ))}
            </div>
          ) : null}

          {control?.control === 'enum' ? (
            <div className="mt-3 flex flex-wrap gap-2">
              {options.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => onChange(option.value)}
                  disabled={disabled}
                  className={`rounded-md px-3 py-1.5 text-xs font-semibold transition ${
                    value === option.value
                      ? 'bg-teal-500 text-zinc-950'
                      : 'border border-zinc-800 bg-zinc-950 text-zinc-300 hover:border-zinc-700'
                  } ${disabled ? 'opacity-50' : ''}`}
                >
                  {option.label}
                </button>
              ))}
            </div>
          ) : null}

          {control?.control === 'multi_enum' ? (
            <div className="mt-3 space-y-2">
              <div className="flex flex-wrap gap-2">
                {options.map((option) => {
                  const active = selectedItems.includes(option.value)
                  return (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => {
                        const next = active
                          ? selectedItems.filter((item) => item !== option.value)
                          : [...selectedItems, option.value]
                        onChange(next.join(','))
                      }}
                      disabled={disabled}
                      className={`rounded-md px-3 py-1.5 text-xs font-semibold transition ${
                        active
                          ? 'bg-teal-500 text-zinc-950'
                          : 'border border-zinc-800 bg-zinc-950 text-zinc-300 hover:border-zinc-700'
                      } ${disabled ? 'opacity-50' : ''}`}
                    >
                      {option.label}
                    </button>
                  )
                })}
              </div>
              <div className="flex flex-wrap gap-1">
                {selectedItems.length > 0 ? selectedItems.map((item) => (
                  <span key={item} className="rounded-md bg-zinc-800 px-2 py-0.5 text-xs font-medium text-zinc-300">{item}</span>
                )) : <span className="text-xs text-zinc-500">Nothing selected.</span>}
              </div>
            </div>
          ) : null}

          {canRenderNumber ? (
            <div className="mt-3 space-y-3">
              <div className="flex items-center justify-between gap-3 text-xs text-zinc-400">
                <span>Selected value</span>
                <span className="font-mono text-teal-400">{isLiveRiskPerTrade ? `${(sliderValue * 100).toFixed(2)}%` : formatNumericValue(sliderValue, control?.unit)}</span>
              </div>
              <input
                type="range"
                min={String(minValue)}
                max={String(maxValue)}
                step={String(stepValue)}
                value={String(sliderValue)}
                onChange={(event) => updateNumber(Number(event.target.value))}
                disabled={disabled}
                className="w-full accent-teal-500"
              />
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => updateNumber(sliderValue - stepValue)}
                  disabled={disabled || sliderValue <= minValue}
                  className="rounded-md border border-zinc-800 bg-zinc-950 px-3 py-1.5 text-xs font-semibold text-zinc-300 transition hover:border-zinc-700 disabled:opacity-40"
                >
                  − Step
                </button>
                <button
                  type="button"
                  onClick={() => updateNumber(sliderValue + stepValue)}
                  disabled={disabled || sliderValue >= maxValue}
                  className="rounded-md border border-zinc-800 bg-zinc-950 px-3 py-1.5 text-xs font-semibold text-zinc-300 transition hover:border-zinc-700 disabled:opacity-40"
                >
                  + Step
                </button>
                {numberPresets(control).filter((preset) => preset >= minValue && preset <= maxValue).map((preset) => (
                  <button
                    key={preset}
                    type="button"
                    onClick={() => updateNumber(preset)}
                    disabled={disabled}
                    className={`rounded-md px-3 py-1.5 text-xs font-semibold transition ${
                      Math.abs(sliderValue - preset) < stepValue / 2
                        ? 'bg-teal-500 text-zinc-950'
                        : 'border border-zinc-800 bg-zinc-950 text-zinc-300 hover:border-zinc-700'
                    } ${disabled ? 'opacity-50' : ''}`}
                  >
                    {control?.key === 'LIVE_RISK_PER_TRADE_PCT' ? `${(preset * 100).toFixed(preset < 0.01 ? 2 : 1)}%` : formatNumericValue(preset, control?.unit)}
                  </button>
                ))}
              </div>
              <div className="text-[0.7rem] font-mono text-zinc-500">
                Range: {formatNumericValue(minValue, control?.unit)} → {formatNumericValue(maxValue, control?.unit)} · step {formatNumericValue(stepValue, control?.unit)}
              </div>
              {isLiveRiskPerTrade ? (
                <div className="rounded-md border border-teal-500/20 bg-teal-500/5 px-3 py-2 text-xs text-zinc-300">
                  <div className="font-semibold text-teal-400">1R preview</div>
                  {currentBalance != null ? (
                    <>
                      <div className="mt-1">Current balance: <span className="font-mono">{formatUsd(currentBalance)}</span></div>
                      <div className="mt-1">1R ≈ <span className="font-mono text-zinc-100">{formatUsd(currentBalance * sliderValue)}</span></div>
                      <div className="mt-1 text-zinc-400">1R is your allowed loss budget for one 1R trade.</div>
                    </>
                  ) : (
                    <div className="mt-1 text-zinc-500">Balance preview unavailable.</div>
                  )}
                </div>
              ) : null}
              {isLiveMaxLeverage ? (
                <div className="rounded-md border border-teal-500/20 bg-teal-500/5 px-3 py-2 text-xs text-zinc-300">
                  Orders are blocked if required notional would exceed this leverage cap.
                </div>
              ) : null}
              {isLiveDefaultEntryRMultiple ? (
                <div className="rounded-md border border-teal-500/20 bg-teal-500/5 px-3 py-2 text-xs text-zinc-300">
                  Used when a signal does not provide entry_r_multiple.
                </div>
              ) : null}
              {isLiveMaxPositionR ? (
                <div className="rounded-md border border-teal-500/20 bg-teal-500/5 px-3 py-2 text-xs text-zinc-300">
                  A single position cannot exceed this R cap.
                </div>
              ) : null}
            </div>
          ) : null}

          {(!control || control.control === 'readonly') ? (
            <div className="mt-3 space-y-2">
              <div className={`rounded-md border border-zinc-800 bg-zinc-950 px-3 py-2 font-mono text-sm ${isEmpty ? 'text-zinc-600 italic' : 'text-zinc-100'}`}>
                {formatValue(value)}
              </div>
              <p className="text-xs text-amber-400">Runtime has not published an interactive control for this key yet, so it is shown read-only.</p>
            </div>
          ) : null}
        </div>
        <button
          type="button"
          onClick={onCopy}
          title="Copy value"
          className="mt-0.5 shrink-0 rounded-md p-1.5 text-zinc-600 opacity-0 transition hover:bg-zinc-800 hover:text-zinc-300 group-hover:opacity-100"
        >
          {copied ? (
            <CheckCheck className="h-3.5 w-3.5 text-teal-400" strokeWidth={1.8} />
          ) : (
            <Copy className="h-3.5 w-3.5" strokeWidth={1.8} />
          )}
        </button>
      </div>
    </div>
  );
}

// ─── main page ────────────────────────────────────────────────────────────────

export function OperateConfigPageRoute() {
  const [searchParams, setSearchParams] = useSearchParams()
  const { options: profileScopeOptions } = useProfileScopeOptions()
  const profileScope = normalizeProfileScope(searchParams.get('profile'), profileScopeOptions)
  const scopedProfileId = profileScopeToApiProfileId(profileScope, profileScopeOptions) ?? DEFAULT_PROFILE_SCOPE
  const runtimeProfileId = profileScopeToRuntimeProfileId(profileScope, profileScopeOptions) ?? scopedProfileId
  const isLiveReadOnlyScope = runtimeProfileId !== DEFAULT_PROFILE_SCOPE
  const settingsQuery = useQuery({
    queryKey: ["runtime-settings", "operate-config", profileScope],
    queryFn: () => fetchRuntimeSettingsForScope(profileScope),
    refetchOnWindowFocus: false,
  });
  const settingsMetadataQuery = useQuery({
    queryKey: ['runtime-settings-metadata', 'operate-config', profileScope],
    queryFn: () => fetchRuntimeSettingsMetadataForScope(profileScope),
    refetchOnWindowFocus: false,
  })
  const paperBalanceQuery = useQuery({
    queryKey: ["paper-balance", "operate-config", profileScope],
    queryFn: () => fetchPaperBalanceForScope(profileScope),
    refetchOnWindowFocus: false,
    enabled: !isLiveReadOnlyScope,
  })
  const liveReadOnlyExposureQuery = useQuery({
    queryKey: ['runtime-profile-read-only-exposure', 'operate-config', runtimeProfileId],
    queryFn: () => fetchRuntimeProfileReadOnlyExposure(runtimeProfileId),
    refetchOnWindowFocus: false,
    enabled: isLiveReadOnlyScope,
  })
  const profileSettingsQuery = useQuery({
    queryKey: ['runtime-profile-settings', 'operate-config', runtimeProfileId],
    queryFn: () => fetchRuntimeProfileSettings(runtimeProfileId),
    refetchOnWindowFocus: false,
  })
  const settings = (settingsQuery.data ?? {}) as Record<string, unknown>;
  const sourceSettings = useMemo(() => stringifySettings(settings), [settings]);
  const settingControlByKey = useMemo(
    () => Object.fromEntries((settingsMetadataQuery.data?.controls ?? []).map((control) => [control.key, control])),
    [settingsMetadataQuery.data?.controls],
  )
  const updateSettingsMutation = useUpdateRuntimeSettingsMutation();
  const updateProfileSettingsMutation = useUpdateRuntimeProfileSettingsMutation();
  const { copied, copy } = useCopy();

  const [activeGroup, setActiveGroup] = useState(GROUPS[0].id);
  const [search, setSearch] = useState("");
  const [settingsDraft, setSettingsDraft] = useState<Record<string, string>>({});
  const [capabilityDraft, setCapabilityDraft] = useState<Record<string, boolean>>({})
  const sourceProfileOptions = profileScopeOptions.filter((option) => option.enabled && option.kind === 'profile' && option.value !== profileScope)
  const [importSourceProfile, setImportSourceProfile] = useState<ProfileScopeValue>((sourceProfileOptions[0]?.value ?? DEFAULT_PROFILE_SCOPE) as ProfileScopeValue)
  const importSourceSettingsQuery = useQuery({
    queryKey: ['runtime-settings', 'operate-config', 'import-source', importSourceProfile],
    queryFn: () => fetchRuntimeSettingsForScope(importSourceProfile),
    refetchOnWindowFocus: false,
    enabled: Boolean(importSourceProfile) && importSourceProfile !== profileScope,
  })

  useEffect(() => {
    if (!sourceProfileOptions.some((option) => option.value === importSourceProfile)) {
      setImportSourceProfile((sourceProfileOptions[0]?.value ?? DEFAULT_PROFILE_SCOPE) as ProfileScopeValue)
    }
  }, [importSourceProfile, sourceProfileOptions]);

  useEffect(() => {
    setSettingsDraft((current) => {
      if (Object.keys(current).length === 0) return sourceSettings;
      return current;
    });
  }, [sourceSettings]);

  const sourceCapabilities = useMemo(
    () => Object.fromEntries(PROFILE_CAPABILITY_KEYS.map((key) => [key, Boolean(profileSettingsQuery.data?.capabilities?.[key])])),
    [profileSettingsQuery.data?.capabilities],
  )

  useEffect(() => {
    setSettingsDraft(sourceSettings)
    setCapabilityDraft(sourceCapabilities)
  }, [profileScope]);

  useEffect(() => {
    setCapabilityDraft((current) => {
      if (Object.keys(current).length === 0) return sourceCapabilities
      return current
    })
  }, [sourceCapabilities])

  const profileSettingsEntries = useMemo(() => ([
    ...PROFILE_SETTING_RUNTIME_KEYS.map((key) => [key, settings[key]] as [string, unknown]),
    ...PROFILE_SETTING_RISK_KEYS.map((key) => [key, settings[key]] as [string, unknown]),
  ]), [settings])

  // group entries with counts
  const groupData = useMemo(
    () =>
      GROUPS.map((g) => ({
        ...g,
        entries: g.id === 'profile-settings' ? profileSettingsEntries : getGroupEntries(settings, g.matchers),
      })),
    [profileSettingsEntries, settings],
  );

  // current group or search-filtered global view
  const isSearching = search.trim().length > 0;
  const searchResults = useMemo(() => {
    if (!isSearching) return [];
    const term = search.trim().toUpperCase();
    return Object.entries(settings).filter(
      ([key, value]) =>
        key.toUpperCase().includes(term) ||
        String(value).toUpperCase().includes(term),
    );
  }, [isSearching, search, settings]);

  const activeGroupData = groupData.find((g) => g.id === activeGroup);
  const totalKeys = Object.keys(settings).length + PROFILE_CAPABILITY_KEYS.length;
  const settingsDirty =
    JSON.stringify(settingsDraft) !== JSON.stringify(sourceSettings);
  const capabilitiesDirty = JSON.stringify(capabilityDraft) !== JSON.stringify(sourceCapabilities)
  const dirty = settingsDirty || capabilitiesDirty
  const currentBalance = liveReadOnlyExposureQuery.data?.account?.available_balance != null
    ? Number(liveReadOnlyExposureQuery.data.account.available_balance)
    : paperBalanceQuery.data?.balance != null
      ? Number(paperBalanceQuery.data.balance)
      : Number(settingsDraft.PAPER_DEFAULT_BALANCE ?? 0)

  const applyImportedSettings = (mode: 'all' | 'group') => {
    const imported = stringifySettings((importSourceSettingsQuery.data ?? {}) as Record<string, unknown>)
    const nextEntries = mode === 'all'
      ? Object.entries(imported)
      : Object.entries(imported).filter(([key]) => activeGroupData?.entries.some(([groupKey]) => groupKey === key))
    if (nextEntries.length === 0) return
    setSettingsDraft((current) => ({
      ...current,
      ...Object.fromEntries(nextEntries),
    }))
  }

  const presetProfiles = profileSettingsQuery.data?.preset_profiles ?? []

  const applyPresetProfile = (presetId: string) => {
    const preset = presetProfiles.find((item) => item.preset_id === presetId)
    if (!preset) return
    setSettingsDraft((current) => ({
      ...current,
      ...Object.fromEntries([
        ...Object.entries(preset.runtime_settings ?? {}),
        ...Object.entries(preset.risk_settings ?? {}),
      ].filter(([, value]) => value != null)),
    }))
    if (Object.keys(preset.capabilities ?? {}).length > 0) {
      setCapabilityDraft((current) => ({
        ...current,
        ...preset.capabilities,
      }))
    }
  }

  const restoreRuntimeDefaults = () => applyPresetProfile('runtime-defaults')

  const savePending = updateSettingsMutation.isPending || updateProfileSettingsMutation.isPending

  const handleSave = async () => {
    try {
      if (settingsDirty) {
        await updateSettingsMutation.mutateAsync({ ...settingsDraft, profile_id: scopedProfileId })
      }
      if (capabilitiesDirty) {
        await updateProfileSettingsMutation.mutateAsync({
          profile_id: runtimeProfileId,
          capabilities: capabilityDraft,
        })
      }
    } catch {
      return
    }
  }

  const handleRefresh = () => {
    void Promise.all([settingsQuery.refetch(), settingsMetadataQuery.refetch(), profileSettingsQuery.refetch()])
  }

  const isLoading =
    (settingsQuery.isLoading && !settingsQuery.data) ||
    (settingsMetadataQuery.isLoading && !settingsMetadataQuery.data) ||
    (profileSettingsQuery.isLoading && !profileSettingsQuery.data);

  if (isLoading) {
    return (
      <AnimatedRoute>
        <EmptyState message="Loading runtime config..." />
      </AnimatedRoute>
    );
  }

  return (
    <AnimatedRoute>
      <div className="flex min-h-screen flex-col gap-4 bg-zinc-950 p-4 font-mono text-zinc-100">
        <ProfileScopeBar
          options={profileScopeOptions}
          value={profileScope}
          onChange={(nextValue) => {
            const nextParams = new URLSearchParams(searchParams)
            nextParams.set('profile', nextValue)
            setSearchParams(nextParams)
          }}
        />

        {/* ── HEADER ── */}
        <header className="border border-zinc-800 px-6 py-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-[0.6rem] font-semibold uppercase tracking-[0.22em] text-teal-500">
                Operate · Config
              </p>
              <h1 className="mt-1 text-2xl font-bold tracking-tight text-zinc-100">
                Runtime Configuration
              </h1>
              <p className="mt-0.5 text-sm text-zinc-500">
                Live settings grouped by operational ownership
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => {
                  setSettingsDraft(sourceSettings)
                  setCapabilityDraft(sourceCapabilities)
                }}
                disabled={!dirty || savePending}
                className="inline-flex items-center gap-1.5 rounded-md border border-zinc-800 bg-zinc-900 px-3 py-1.5 text-xs font-medium text-zinc-400 transition hover:bg-zinc-800 hover:text-zinc-200 disabled:opacity-40"
              >
                Reset
              </button>
              <button
                type="button"
                onClick={() => { void handleSave() }}
                disabled={!dirty || savePending}
                className="inline-flex items-center gap-1.5 rounded-md bg-teal-500 px-3 py-1.5 text-xs font-semibold text-zinc-950 transition hover:bg-teal-400 disabled:opacity-40"
              >
                {savePending ? "Saving…" : "Save changes"}
              </button>
              <span className="text-xs text-zinc-500">
                {dirty ? "Unsaved changes" : "All changes saved"}
              </span>
              <span
                className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-semibold ${
                  settingsQuery.isFetching
                    ? "bg-amber-500/10 text-amber-400"
                    : "bg-teal-500/10 text-teal-400"
                }`}
              >
                <span
                  className={`h-1.5 w-1.5 rounded-full ${settingsQuery.isFetching ? "bg-amber-400 animate-pulse" : "bg-teal-400"}`}
                />
                {settingsQuery.isFetching
                  ? "Refreshing…"
                  : `${totalKeys} keys loaded`}
              </span>
              <button
                type="button"
                onClick={handleRefresh}
                disabled={settingsQuery.isFetching || settingsMetadataQuery.isFetching || profileSettingsQuery.isFetching}
                className="inline-flex items-center gap-1.5 rounded-md border border-zinc-800 bg-zinc-900 px-3 py-1.5 text-xs font-medium text-zinc-400 transition hover:bg-zinc-800 hover:text-zinc-200 disabled:opacity-40"
              >
                <RefreshCw
                  className={`h-3.5 w-3.5 ${(settingsQuery.isFetching || settingsMetadataQuery.isFetching || profileSettingsQuery.isFetching) ? "animate-spin" : ""}`}
                  strokeWidth={1.8}
                />
                Refresh
              </button>
            </div>
          </div>

          <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
            <div className="relative max-w-sm">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-zinc-600"
              strokeWidth={1.8}
            />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search keys or values…"
              className="h-9 w-full rounded-lg bg-zinc-900 pl-9 pr-4 text-xs text-zinc-200 outline-none ring-1 ring-zinc-800 placeholder:text-zinc-600 focus:ring-teal-700/60 transition"
            />
            {search && (
              <button
                type="button"
                onClick={() => setSearch("")}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-[0.6rem] text-zinc-500 hover:text-zinc-300"
              >
                ✕
              </button>
            )}
            </div>

            <div className="grid gap-4">
              <div className="rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-3">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="text-[0.6rem] font-semibold uppercase tracking-[0.18em] text-teal-500">Config profiles</p>
                    <p className="mt-1 text-xs text-zinc-500">Apply a backend-published settings posture to the current draft. Nothing is saved until you press save changes.</p>
                  </div>
                  <button
                    type="button"
                    onClick={restoreRuntimeDefaults}
                    disabled={savePending || !presetProfiles.some((preset) => preset.preset_id === 'runtime-defaults')}
                    className="inline-flex h-10 items-center gap-1.5 rounded-md border border-zinc-800 bg-zinc-950 px-3 py-1.5 text-xs font-medium text-zinc-300 transition hover:bg-zinc-800 disabled:opacity-40"
                  >
                    Return to defaults
                  </button>
                </div>
                <div className="mt-3 grid gap-3 lg:grid-cols-2">
                  {presetProfiles.map((preset) => (
                    <button
                      key={preset.preset_id}
                      type="button"
                      onClick={() => applyPresetProfile(String(preset.preset_id ?? ''))}
                      disabled={savePending}
                      className="rounded-lg border border-zinc-800 bg-zinc-950 px-4 py-3 text-left transition hover:border-teal-600/40 hover:bg-zinc-900 disabled:opacity-40"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <div className="text-sm font-semibold text-zinc-100">{preset.label}</div>
                          {preset.description ? <div className="mt-1 text-xs leading-6 text-zinc-500">{preset.description}</div> : null}
                        </div>
                        <div className="text-[0.65rem] uppercase tracking-[0.16em] text-teal-400">Apply</div>
                      </div>
                    </button>
                  ))}
                </div>
              </div>

              <div className="rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-3">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="text-[0.6rem] font-semibold uppercase tracking-[0.18em] text-teal-500">Profile import</p>
                    <p className="mt-1 text-xs text-zinc-500">Copy some settings or all settings from another profile into the current draft before saving.</p>
                  </div>
                  <div className="text-xs text-zinc-500">Editing profile: <span className="font-semibold text-zinc-200">{scopedProfileId}</span></div>
                </div>
                <div className="mt-3 flex flex-wrap items-end gap-3">
                  <label className="min-w-[14rem] flex-1 text-xs text-zinc-400">
                    <span className="mb-1 block uppercase tracking-[0.14em] text-zinc-500">Import from profile</span>
                    <select
                      value={importSourceProfile}
                      onChange={(e) => setImportSourceProfile(e.target.value as ProfileScopeValue)}
                      className="h-10 w-full rounded-md border border-zinc-800 bg-zinc-950 px-3 text-sm text-zinc-100 outline-none transition focus:border-teal-700/60"
                    >
                      {sourceProfileOptions.map((option) => (
                        <option key={option.value} value={option.value}>{option.label}</option>
                      ))}
                    </select>
                  </label>
                  <button
                    type="button"
                    onClick={() => applyImportedSettings('group')}
                    disabled={!activeGroupData || importSourceSettingsQuery.isLoading || sourceProfileOptions.length === 0}
                    className="inline-flex h-10 items-center gap-1.5 rounded-md border border-zinc-800 bg-zinc-950 px-3 py-1.5 text-xs font-medium text-zinc-300 transition hover:bg-zinc-800 disabled:opacity-40"
                  >
                    Import current group
                  </button>
                  <button
                    type="button"
                    onClick={() => applyImportedSettings('all')}
                    disabled={importSourceSettingsQuery.isLoading || sourceProfileOptions.length === 0}
                    className="inline-flex h-10 items-center gap-1.5 rounded-md bg-teal-500 px-3 py-1.5 text-xs font-semibold text-zinc-950 transition hover:bg-teal-400 disabled:opacity-40"
                  >
                    Import all settings
                  </button>
                </div>
                {sourceProfileOptions.length === 0 ? (
                  <p className="mt-2 text-xs text-zinc-500">No other enabled profiles are available to import from.</p>
                ) : importSourceSettingsQuery.isLoading ? (
                  <p className="mt-2 text-xs text-zinc-500">Loading import source settings…</p>
                ) : (
                  <p className="mt-2 text-xs text-zinc-500">Source profile <span className="font-semibold text-zinc-300">{importSourceProfile}</span> loaded with {Object.keys(importSourceSettingsQuery.data ?? {}).length} keys.</p>
                )}
              </div>
            </div>
          </div>

        </header>

        {/* ── BODY: sidebar + content ── */}
        {/*
          ASCII:
          ┌─────────────────┬────────────────────────────────────┐
          │  GROUP NAV      │  SETTINGS PANEL                    │
          │  200px sticky   │  flex-1, scrollable                │
          │                 │                                    │
          │  ● Execution 12 │  section title + count             │
          │  ○ Risk       4 │  grid of ConfigRow cards           │
          │  ○ Universe   6 │                                    │
          │  ...            │                                    │
          └─────────────────┴────────────────────────────────────┘
        */}
        <div
          className="flex flex-1 overflow-hidden"
          style={{ minHeight: "calc(100vh - 160px)" }}
        >
          {/* sidebar */}
          <nav className="flex w-52 shrink-0 flex-col border-r border-zinc-800 bg-zinc-950 py-4">
            <p className="px-4 pb-2 text-[0.6rem] font-semibold uppercase tracking-widest text-zinc-600">
              Groups
            </p>
            {groupData.map((g) => {
              const active = !isSearching && activeGroup === g.id;
              return (
                <button
                  key={g.id}
                  type="button"
                  onClick={() => {
                    setActiveGroup(g.id);
                    setSearch("");
                  }}
                  className={`flex items-center justify-between px-4 py-2.5 text-left transition ${
                    active
                      ? "border-l-2 border-l-teal-400 bg-zinc-900 text-zinc-100"
                      : "border-l-2 border-l-transparent text-zinc-500 hover:bg-zinc-900/60 hover:text-zinc-300"
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <span className="text-sm">{g.icon}</span>
                    <span className="text-xs font-medium">{g.title}</span>
                  </div>
                  <span
                    className={`rounded-md px-1.5 py-0.5 text-[0.6rem] font-bold tabular-nums ${
                      active
                        ? "bg-teal-500/15 text-teal-400"
                        : g.entries.length > 0
                          ? "bg-zinc-800 text-zinc-400"
                          : "text-zinc-700"
                    }`}
                  >
                    {g.entries.length}
                  </span>
                </button>
              );
            })}

            <div className="mt-auto border-t border-zinc-800 px-4 pt-4">
              <div className="rounded-lg bg-zinc-900 px-3 py-3">
                <p className="text-[0.6rem] uppercase tracking-widest text-zinc-600">
                  Total keys
                </p>
                <p className="mt-1 text-2xl font-bold tabular-nums text-zinc-200">
                  {totalKeys}
                </p>
              </div>
            </div>
          </nav>

          {/* main settings area */}
          <main className="flex-1 overflow-y-auto p-6">
            {/* ── SEARCH RESULTS ── */}
            {isSearching ? (
              <div>
                <div className="mb-4 flex items-center justify-between gap-3">
                  <div>
                    <h2 className="text-base font-bold text-zinc-200">
                      Search results
                    </h2>
                    <p className="text-xs text-zinc-500">
                      {searchResults.length} key
                      {searchResults.length !== 1 ? "s" : ""} matching{" "}
                      <span className="text-zinc-300">"{search}"</span>
                    </p>
                  </div>
                </div>
                {searchResults.length === 0 ? (
                  <div className="rounded-xl border border-dashed border-zinc-800 p-8 text-center">
                    <p className="text-sm text-zinc-500">
                      No keys or values matched{" "}
                      <span className="text-zinc-300">"{search}"</span>.
                    </p>
                  </div>
                ) : (
                  <div className="grid gap-2">
                    {searchResults.map(([key]) => (
                      <ConfigRow
                        key={key}
                        rowKey={key}
                        control={settingControlByKey[key]}
                        value={settingsDraft[key] ?? ""}
                        onCopy={() => copy(key, settingsDraft[key] ?? "")}
                        copied={copied === key}
                        onChange={(nextValue) =>
                          setSettingsDraft((current) => ({
                            ...current,
                            [key]: nextValue,
                          }))
                        }
                        disabled={savePending}
                        currentBalance={currentBalance}
                      />
                    ))}
                  </div>
                )}
              </div>
            ) : /* ── GROUP VIEW ── */
            activeGroupData ? (
              <div>
                <div className="mb-5 flex items-start justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-xl">{activeGroupData.icon}</span>
                      <h2 className="text-xl font-bold tracking-tight text-zinc-100">
                        {activeGroupData.title}
                      </h2>
                      <span className="rounded-md bg-teal-500/10 px-2 py-0.5 text-xs font-bold text-teal-400">
                        {activeGroupData.entries.length} keys
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-zinc-500">
                      Matched by:{" "}
                      {activeGroupData.matchers.map((m) => (
                        <code
                          key={m}
                          className="ml-1 rounded bg-zinc-800 px-1.5 py-0.5 text-[0.65rem] text-zinc-400"
                        >
                          {m}
                        </code>
                      ))}
                    </p>
                  </div>
                </div>

                {activeGroupData.id === 'profile-settings' ? (
                  <div className="space-y-6">
                    <section className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <p className="text-[0.65rem] font-semibold uppercase tracking-[0.18em] text-teal-500">Auto-live posture</p>
                          <h3 className="mt-1 text-lg font-semibold text-zinc-100">{String(profileSettingsQuery.data?.auto_live?.posture ?? 'UNKNOWN').replaceAll('_', ' ')}</h3>
                          <p className="mt-1 text-xs text-zinc-500">This grouped surface keeps runtime capability flags and profile-scoped live policy settings together without changing storage ownership.</p>
                        </div>
                        <div className="flex flex-wrap gap-2 text-xs">
                          <span className={`rounded-md px-2.5 py-1 ${isTruthyString(settingsDraft.AUTONOMOUS_ENABLED ?? '') ? 'bg-teal-500/10 text-teal-400' : 'bg-zinc-800 text-zinc-400'}`}>Loop {isTruthyString(settingsDraft.AUTONOMOUS_ENABLED ?? '') ? 'enabled' : 'disabled'}</span>
                          <span className={`rounded-md px-2.5 py-1 ${capabilityDraft.manual_trading_enabled ? 'bg-teal-500/10 text-teal-400' : 'bg-zinc-800 text-zinc-400'}`}>Manual live {capabilityDraft.manual_trading_enabled ? 'enabled' : 'disabled'}</span>
                          <span className={`rounded-md px-2.5 py-1 ${capabilityDraft.auto_trading_enabled ? 'bg-teal-500/10 text-teal-400' : 'bg-zinc-800 text-zinc-400'}`}>Auto live {capabilityDraft.auto_trading_enabled ? 'enabled' : 'disabled'}</span>
                          <span className={`rounded-md px-2.5 py-1 ${capabilityDraft.read_only ? 'bg-amber-500/10 text-amber-400' : 'bg-zinc-800 text-zinc-400'}`}>Read only {capabilityDraft.read_only ? 'on' : 'off'}</span>
                        </div>
                      </div>
                      <div className="mt-4 flex flex-wrap gap-2">
                        {(profileSettingsQuery.data?.auto_live?.reason_codes as string[] | undefined)?.length ? (
                          (profileSettingsQuery.data?.auto_live?.reason_codes as string[]).map((code) => (
                            <span key={code} className="rounded-md border border-amber-500/20 bg-amber-500/10 px-2.5 py-1 text-xs text-amber-300">{code}</span>
                          ))
                        ) : (
                          <span className="rounded-md border border-teal-500/20 bg-teal-500/10 px-2.5 py-1 text-xs text-teal-300">No current auto-live blockers reported</span>
                        )}
                      </div>
                      <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                        <div className="rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-3">
                          <p className="text-[0.65rem] uppercase tracking-[0.16em] text-zinc-500">Kill switches</p>
                          <p className="mt-1 text-sm text-zinc-200">Global {isTruthyString(settingsDraft.AUTO_LIVE_GLOBAL_KILL_SWITCH ?? '') ? 'ON' : 'OFF'} · Profile {isTruthyString(settingsDraft.AUTO_LIVE_PROFILE_KILL_SWITCH ?? '') ? 'ON' : 'OFF'}</p>
                        </div>
                        <div className="rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-3">
                          <p className="text-[0.65rem] uppercase tracking-[0.16em] text-zinc-500">Allowlist</p>
                          <p className="mt-1 text-sm text-zinc-200">{splitCsv(settingsDraft.AUTO_LIVE_SYMBOL_ALLOWLIST ?? '').length || 0} symbols configured</p>
                        </div>
                        <div className="rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-3">
                          <p className="text-[0.65rem] uppercase tracking-[0.16em] text-zinc-500">Concurrency</p>
                          <p className="mt-1 text-sm text-zinc-200">Max {settingsDraft.AUTO_LIVE_MAX_CONCURRENT_POSITIONS ?? '0'} positions</p>
                        </div>
                        <div className="rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-3">
                          <p className="text-[0.65rem] uppercase tracking-[0.16em] text-zinc-500">Risk per trade</p>
                          <p className="mt-1 text-sm text-zinc-200">{settingsDraft.LIVE_RISK_PER_TRADE_PCT ?? '0'} basis · max open R {settingsDraft.LIVE_MAX_TOTAL_OPEN_R ?? '0'}</p>
                        </div>
                      </div>
                    </section>

                    <section>
                      <h3 className="mb-3 text-sm font-semibold uppercase tracking-[0.18em] text-zinc-500">Capability posture</h3>
                      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
                        {PROFILE_CAPABILITY_KEYS.map((key) => (
                          <CapabilityRow
                            key={key}
                            rowKey={key}
                            value={Boolean(capabilityDraft[key])}
                            description={key === 'read_only'
                              ? 'Blocks manual and autonomous execution changes.'
                              : key === 'manual_trading_enabled'
                                ? 'Required for manual live routing.'
                                : key === 'auto_trading_enabled'
                                  ? 'Required for autonomous live routing.'
                                  : 'Marks the selected profile as the live auto-routing target.'}
                            onChange={(nextValue) => setCapabilityDraft((current) => ({ ...current, [key]: nextValue }))}
                            disabled={savePending}
                          />
                        ))}
                      </div>
                    </section>

                    <section>
                      <h3 className="mb-3 text-sm font-semibold uppercase tracking-[0.18em] text-zinc-500">Runtime & autonomous settings</h3>
                      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                        {PROFILE_SETTING_RUNTIME_KEYS.map((key) => (
                          <ConfigRow
                            key={key}
                            rowKey={key}
                            control={settingControlByKey[key]}
                            value={settingsDraft[key] ?? ''}
                            onCopy={() => copy(key, settingsDraft[key] ?? '')}
                            copied={copied === key}
                            onChange={(nextValue) => setSettingsDraft((current) => ({ ...current, [key]: nextValue }))}
                            disabled={savePending}
                            currentBalance={currentBalance}
                          />
                        ))}
                      </div>
                    </section>

                    <section>
                      <h3 className="mb-3 text-sm font-semibold uppercase tracking-[0.18em] text-zinc-500">Risk settings</h3>
                      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                        {PROFILE_SETTING_RISK_KEYS.map((key) => (
                          <ConfigRow
                            key={key}
                            rowKey={key}
                            control={settingControlByKey[key]}
                            value={settingsDraft[key] ?? ''}
                            onCopy={() => copy(key, settingsDraft[key] ?? '')}
                            copied={copied === key}
                            onChange={(nextValue) => setSettingsDraft((current) => ({ ...current, [key]: nextValue }))}
                            disabled={savePending}
                            currentBalance={currentBalance}
                          />
                        ))}
                      </div>
                    </section>
                  </div>
                ) : activeGroupData.entries.length === 0 ? (
                  <div className="rounded-xl border border-dashed border-zinc-800 p-8 text-center">
                    <p className="text-sm text-zinc-500">
                      No runtime settings matched this group's matchers.
                    </p>
                    <p className="mt-1 text-xs text-zinc-600">
                      This group will populate once the runtime reports keys
                      containing: {activeGroupData.matchers.join(", ")}
                    </p>
                  </div>
                ) : (
                  <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                    {activeGroupData.entries.map(([key]) => (
                      <ConfigRow
                        key={key}
                        rowKey={key}
                        control={settingControlByKey[key]}
                        value={settingsDraft[key] ?? ""}
                        onCopy={() => copy(key, settingsDraft[key] ?? "")}
                        copied={copied === key}
                        onChange={(nextValue) =>
                          setSettingsDraft((current) => ({
                            ...current,
                            [key]: nextValue,
                          }))
                        }
                        disabled={savePending}
                        currentBalance={currentBalance}
                      />
                    ))}
                  </div>
                )}

                {/* uncategorised keys in THIS group that might be wide/long */}
                {activeGroupData.id !== 'profile-settings' && activeGroupData.entries.some(([, v]) =>
                  valueIsList(formatValue(v)),
                ) && (
                  <p className="mt-4 text-[0.65rem] text-zinc-600">
                    List values are shown as pills. Click any copy icon to grab
                    the raw comma-separated string.
                  </p>
                )}
              </div>
            ) : null}
          </main>
        </div>
      </div>
    </AnimatedRoute>
  );
}
