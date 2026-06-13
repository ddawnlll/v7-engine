import { describe, expect, it } from 'vitest'

import { DEFAULT_PROFILE_SCOPE, PROFILE_SCOPE_OPTIONS, buildProfileScopeOptions, getProfileScopeOption, normalizeProfileScope, profileScopeToApiProfileId, profileScopeToRuntimeProfileId, withCurrentProfileScope } from './profileScope'

describe('profileScope helpers', () => {
  it('defaults safely to paper-main', () => {
    expect(normalizeProfileScope(undefined)).toBe(DEFAULT_PROFILE_SCOPE)
    expect(normalizeProfileScope('')).toBe(DEFAULT_PROFILE_SCOPE)
    expect(normalizeProfileScope('unknown-profile')).toBe(DEFAULT_PROFILE_SCOPE)
  })

  it('only exposes enabled concrete profiles to the current API layer', () => {
    const options = buildProfileScopeOptions([
      { profile_id: 'paper-main', execution_mode: 'PAPER', venue: 'INTERNAL_PAPER', read_only: false },
      { profile_id: 'binance-usdm-main', execution_mode: 'LIVE', venue: 'BINANCE_USDM', read_only: true },
    ])
    expect(profileScopeToApiProfileId('paper-main', options)).toBe('paper-main')
    expect(profileScopeToApiProfileId('binance-usdm-main', options)).toBe('binance-usdm-main')
    expect(profileScopeToApiProfileId('all-profiles', options)).toBeUndefined()
    expect(profileScopeToApiProfileId('shared-learning', options)).toBeUndefined()
  })

  it('maps runtime profile scopes directly from available runtime profiles', () => {
    const options = buildProfileScopeOptions([
      { profile_id: 'paper-main', execution_mode: 'PAPER', venue: 'INTERNAL_PAPER', read_only: false },
      { profile_id: 'binance-usdm-main', execution_mode: 'LIVE', venue: 'BINANCE_USDM', read_only: true },
    ])
    expect(profileScopeToRuntimeProfileId('paper-main', options)).toBe('paper-main')
    expect(profileScopeToRuntimeProfileId('binance-usdm-main', options)).toBe('binance-usdm-main')
    expect(profileScopeToRuntimeProfileId('shared-learning', options)).toBeUndefined()
  })

  it('keeps deferred scopes visible while deriving available profiles dynamically', () => {
    const options = buildProfileScopeOptions([
      { profile_id: 'paper-main', execution_mode: 'PAPER', venue: 'INTERNAL_PAPER', read_only: false },
      { profile_id: 'binance-usdm-main', execution_mode: 'LIVE', venue: 'BINANCE_USDM', read_only: true },
    ])
    expect(PROFILE_SCOPE_OPTIONS.some((option) => option.value === 'all-profiles' && !option.enabled)).toBe(true)
    expect(options.some((option) => option.value === 'paper-main' && option.enabled)).toBe(true)
    expect(options.some((option) => option.value === 'binance-usdm-main' && option.enabled)).toBe(true)
    expect(getProfileScopeOption('paper-main', options).kind).toBe('profile')
  })

  it('preserves the current profile search param across shared navigation links', () => {
    expect(withCurrentProfileScope('/trade/portfolio', '?profile=paper-main')).toBe('/trade/portfolio')
    expect(withCurrentProfileScope('/trade/markets?symbol=BTCUSDT', '?profile=paper-main')).toBe('/trade/markets?symbol=BTCUSDT')
    expect(withCurrentProfileScope('/operate/control?profile=binance-usdm-main', '?profile=paper-main')).toBe('/operate/control?profile=binance-usdm-main')
    expect(withCurrentProfileScope('/system/storage', '')).toBe('/system/storage')
  })
})
