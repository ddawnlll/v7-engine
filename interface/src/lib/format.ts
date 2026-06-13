import { getCurrentSettings } from './runtimeSettings'

export function toNumber(value: unknown, fallback = 0) {
  const num = Number(value)
  return Number.isFinite(num) ? num : fallback
}

export function formatNumber(value: unknown, digits = 2) {
  const num = Number(value)
  if (!Number.isFinite(num)) return '--'
  const settings = getCurrentSettings()
  const resolvedDigits = settings.numberPrecision === 'auto' ? digits : settings.numberPrecision
  if (Math.abs(num) >= 1000) {
    return num.toLocaleString('en-US', { maximumFractionDigits: resolvedDigits })
  }
  return num.toFixed(resolvedDigits)
}

export function formatPercent(value: unknown, digits = 1) {
  const num = Number(value)
  if (!Number.isFinite(num)) return '--'
  const settings = getCurrentSettings()
  const resolvedDigits = settings.numberPrecision === 'auto' ? digits : Math.min(settings.numberPrecision, 4)
  return `${num.toFixed(resolvedDigits)}%`
}

export function formatTime(value: unknown) {
  if (!value) return '--'
  const date = new Date(String(value))
  if (Number.isNaN(date.getTime())) return String(value)
  const settings = getCurrentSettings()
  const relative = formatRelativeTime(date)
  const absolute = date.toLocaleString()
  if (settings.timeFormat === 'relative') return relative
  if (settings.timeFormat === 'both') return `${absolute} (${relative})`
  return absolute
}

export function compactNumber(value: unknown) {
  const num = Number(value)
  if (!Number.isFinite(num)) return '--'
  return new Intl.NumberFormat('en-US', {
    notation: 'compact',
    maximumFractionDigits: 2,
  }).format(num)
}

export function statusTone(status: string | undefined) {
  if (!status) return 'tone-neutral'
  if (status === 'healthy' || status === 'COMPLETED') return 'tone-good'
  if (status === 'warning' || status === 'PENDING' || status === 'RUNNING') return 'tone-warn'
  if (status === 'degraded' || status === 'FAILED' || status === 'DEAD_LETTER') return 'tone-bad'
  return 'tone-neutral'
}

function formatRelativeTime(date: Date) {
  const seconds = Math.round((Date.now() - date.getTime()) / 1000)
  const absSeconds = Math.abs(seconds)
  if (absSeconds < 60) return `${absSeconds}s ${seconds >= 0 ? 'ago' : 'from now'}`
  const minutes = Math.round(absSeconds / 60)
  if (minutes < 60) return `${minutes}m ${seconds >= 0 ? 'ago' : 'from now'}`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours}h ${seconds >= 0 ? 'ago' : 'from now'}`
  const days = Math.round(hours / 24)
  return `${days}d ${seconds >= 0 ? 'ago' : 'from now'}`
}
