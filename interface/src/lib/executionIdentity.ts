import type { JsonRecord, OrderRow, TradeExecutionIdentity } from './types'

function asUpperText(value: unknown): string | undefined {
  const text = String(value ?? '').trim()
  return text ? text.toUpperCase() : undefined
}

function asText(value: unknown): string | undefined {
  const text = String(value ?? '').trim()
  return text || undefined
}

function normalizeProfileId(value: unknown): string {
  return asText(value) ?? 'paper-main'
}

function resolveExecutionMode(row: JsonRecord, profileId: string): string {
  const explicit = asUpperText(row.execution_mode)
  if (explicit) return explicit
  if (profileId.startsWith('paper-')) return 'PAPER'
  return 'UNKNOWN'
}

function resolveOrigin(row: JsonRecord): string {
  const explicit = asUpperText(row.origin)
  if (explicit) return explicit
  const source = asUpperText(row.source)
  if (source === 'MANUAL') return 'MANUAL'
  if (source === 'AUTO' || source === 'PAPER') return 'AUTO'
  return 'UNKNOWN'
}

function resolveVenue(row: JsonRecord, profileId: string, executionMode: string): string {
  const explicit = asText(row.venue)
  if (explicit) return explicit
  if (executionMode === 'PAPER' || profileId.startsWith('paper-')) return 'paper'
  return 'unknown'
}

export function resolveTradeExecutionIdentity(row: OrderRow): TradeExecutionIdentity {
  const profileId = normalizeProfileId(row.profile_id)
  const executionMode = resolveExecutionMode(row, profileId)
  const origin = resolveOrigin(row)
  const venue = resolveVenue(row, profileId, executionMode)
  return {
    profile_id: profileId,
    scope_type: asText(row.scope_type) ?? 'profile-owned',
    execution_mode: executionMode,
    venue,
    origin,
    account_id: asText(row.account_id),
  }
}

export function isManualTrade(row: OrderRow): boolean {
  return resolveTradeExecutionIdentity(row).origin === 'MANUAL'
}
