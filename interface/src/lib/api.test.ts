import { afterEach, describe, expect, it, vi } from 'vitest'

import { fetchEngineHealthForScope, fetchOrdersForScope, fetchPortfolioForScope, fetchReviewDecisionEvent, fetchReviewDecisionEvents, fetchOperateRuntimeStatus, refreshOperateChampionRuntime, updateOperateShadowEngine, queueLegacyScan, fetchOperateModels, fetchRuntimeProfileReadOnlyExposure, fetchRuntimeProfileSettings, fetchRuntimeProfiles, updateRuntimeProfileSettings, syncRuntimeProfileReadOnly, fetchSimulationDecisionTraces, fetchSimulationDiagnostics, fetchSimulationWhatIf, fetchSimulationParityReport, simulationExportUrl, fetchSimulationPresets, createSimulationPreset, updateSimulationPreset, deleteSimulationPreset } from './api'
import { apiRoutes } from './apiRoutes'

describe('queueLegacyScan', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('sends scan_workers to the backend payload', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ run_id: 'scan-123' }),
    })
    vi.spyOn(globalThis, 'fetch' as never).mockImplementation(fetchMock as never)

    await queueLegacyScan({
      symbols: ['BTCUSDT'],
      intervals: ['15m'],
      modes: ['SWING'],
      scan_workers: 32,
    })

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(init.method).toBe('POST')
    expect(JSON.parse(String(init.body))).toMatchObject({
      symbols: ['BTCUSDT'],
      intervals: ['15m'],
      modes: ['SWING'],
      scan_workers: 32,
      requested_by: 'interface',
    })
  })

  it('builds SIM-1 simulation analytics routes and query params', async () => {
    expect(apiRoutes.simulationPresets()).toBe('/api/v3/simulation-presets')
    expect(apiRoutes.simulationPreset(3)).toBe('/api/v3/simulation-presets/3')
    expect(apiRoutes.simulationDecisionTraces(7)).toBe('/api/v3/simulations/7/decision-traces')
    expect(apiRoutes.simulationDiagnostics(7)).toBe('/api/v3/simulations/7/diagnostics')
    expect(apiRoutes.simulationConfidenceHistogram(7)).toBe('/api/v3/simulations/7/confidence-histogram')
    expect(apiRoutes.simulationWhatIf(7)).toBe('/api/v3/simulations/7/what-if')
    expect(apiRoutes.simulationParityReport(7)).toBe('/api/v3/simulations/7/parity-report')
    expect(simulationExportUrl(7, { target: 'decision_traces', format: 'jsonl', limit: 10 })).toContain('/api/v3/simulations/7/exports?')
    expect(simulationExportUrl(7, { target: 'decision_traces', format: 'jsonl', limit: 10 })).toContain('format=jsonl')
  })

  it('fetches SIM-1 simulation analytics with expected query params', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ok: true, items: [] }) })
    vi.spyOn(globalThis, 'fetch' as never).mockImplementation(fetchMock as never)

    await fetchSimulationDecisionTraces(7, { symbol: 'BTCUSDT', reason: 'low_confidence', fallback_used: true, min_confidence: 10, cursor: 5 })
    await fetchSimulationDiagnostics(7)
    await fetchSimulationWhatIf(7, { min_confidence: 25, fees_bps: 4 })
    await fetchSimulationParityReport(7)

    expect(String(fetchMock.mock.calls[0]?.[0])).toContain('/api/v3/simulations/7/decision-traces')
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain('symbol=BTCUSDT')
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain('reason=low_confidence')
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain('fallback_used=true')
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain('cursor=5')
    expect(String(fetchMock.mock.calls[1]?.[0])).toBe('/api/v3/simulations/7/diagnostics')
    expect(String(fetchMock.mock.calls[2]?.[0])).toContain('/api/v3/simulations/7/what-if')
    expect(String(fetchMock.mock.calls[2]?.[0])).toContain('min_confidence=25')
    expect(String(fetchMock.mock.calls[3]?.[0])).toBe('/api/v3/simulations/7/parity-report')
  })

  it('fetches backend-managed simulation presets', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ok: true }) })
    vi.spyOn(globalThis, 'fetch' as never).mockImplementation(fetchMock as never)

    await fetchSimulationPresets(25)
    await createSimulationPreset({ name: 'Preset A', symbols: ['BTCUSDT'], intervals: ['1h'], modes: ['SCALP'], execution_settings: {}, tags: [] })
    await updateSimulationPreset(3, { name: 'Preset B' })
    await deleteSimulationPreset(3)

    expect(String(fetchMock.mock.calls[0]?.[0])).toBe('/api/v3/simulation-presets?limit=25')
    expect(String(fetchMock.mock.calls[1]?.[0])).toBe('/api/v3/simulation-presets')
    expect((fetchMock.mock.calls[1]?.[1] as RequestInit).method).toBe('POST')
    expect(String(fetchMock.mock.calls[2]?.[0])).toBe('/api/v3/simulation-presets/3')
    expect((fetchMock.mock.calls[2]?.[1] as RequestInit).method).toBe('PATCH')
    expect(String(fetchMock.mock.calls[3]?.[0])).toBe('/api/v3/simulation-presets/3')
    expect((fetchMock.mock.calls[3]?.[1] as RequestInit).method).toBe('DELETE')
  })

  it('builds review decision-events query params against the centralized v3 route', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items: [], count: 0, limit: 10 }),
    })
    vi.spyOn(globalThis, 'fetch' as never).mockImplementation(fetchMock as never)

    await fetchReviewDecisionEvents({ runId: 'run-1', symbol: 'BTCUSDT', limit: 10 })

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(String(url)).toContain('/api/v3/review/decision-events')
    expect(String(url)).toContain('run_id=run-1')
    expect(String(url)).toContain('symbol=BTCUSDT')
    expect(String(url)).toContain('limit=10')
    expect(String(url)).not.toContain('/v6/')
  })

  it('fetches a single decision-event detail from the centralized v3 route', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ identity: { decision_event_id: 'devt-1' } }),
    })
    vi.spyOn(globalThis, 'fetch' as never).mockImplementation(fetchMock as never)

    await fetchReviewDecisionEvent('devt-1')

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(String(url)).toContain('/api/v3/review/decision-events/devt-1')
    expect(String(url)).not.toContain('/v6/')
  })

  it('fetches runtime readiness through the centralized operate route', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true, active_engine: 'v6_decision_engine', runtime_state: 'ready' }),
    })
    vi.spyOn(globalThis, 'fetch' as never).mockImplementation(fetchMock as never)

    await fetchOperateRuntimeStatus()

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(String(url)).toContain('/api/v3/operate/runtime/status')
    expect(String(url)).not.toContain('/v6/')
  })

  it('fetches sortable model selection rows through the operate models route', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true, count: 1, items: [] }),
    })
    vi.spyOn(globalThis, 'fetch' as never).mockImplementation(fetchMock as never)

    await fetchOperateModels()

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(String(url)).toContain('/api/v3/operate/registry/models')
  })

  it('refreshes the runtime champion through the centralized operate route', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true, action: 'refresh_champion', runtime_state: 'ready' }),
    })
    vi.spyOn(globalThis, 'fetch' as never).mockImplementation(fetchMock as never)

    await refreshOperateChampionRuntime()

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(String(url)).toContain('/api/v3/operate/runtime/refresh-champion')
    expect(init.method).toBe('POST')
  })

  it('prefers explicit trade identity fields over weak source heuristics', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        items: [
          { order_id: 'ord-1', status: 'OPEN', origin: 'MANUAL', execution_mode: 'PAPER', venue: 'paper', profile_id: 'paper-main', source: 'PAPER' },
          { order_id: 'ord-2', status: 'CLOSED', source: 'MANUAL', profile_id: 'paper-main' },
          { order_id: 'ord-3', status: 'OPEN', source: 'PAPER', profile_id: 'paper-main' },
        ],
      }),
    })
    vi.spyOn(globalThis, 'fetch' as never).mockImplementation(fetchMock as never)

    const payload = await fetchOrdersForScope(1000, 'paper-main')

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(String(url)).toContain('/api/v3/orders')
    expect(String(url)).toContain('profile_id=paper-main')
    expect(payload.manual_open_orders).toHaveLength(1)
    expect(payload.manual_closed_orders).toHaveLength(1)
    expect(payload.auto_open_orders).toHaveLength(1)
  })

  it('treats live filled orders without close timestamps as open positions', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        items: [
          { order_id: 'live-1', status: 'FILLED', execution_mode: 'LIVE', venue: 'BINANCE_USDM', profile_id: 'binance-usdm-main', origin: 'AUTO', source: 'AUTO' },
        ],
      }),
    })
    vi.spyOn(globalThis, 'fetch' as never).mockImplementation(fetchMock as never)

    const payload = await fetchOrdersForScope(1000, 'binance-usdm-main')

    expect(payload.open_orders!).toHaveLength(1)
    expect(payload.closed_orders!).toHaveLength(0)
    expect(payload.open_orders![0]?.lifecycle_status).toBe('OPEN')
    expect(payload.open_orders![0]?.is_open).toBe(true)
  })

  it('posts explicit live sync requests through the runtime profile sync route', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true, sync: { status: 'SYNCED' } }),
    })
    vi.spyOn(globalThis, 'fetch' as never).mockImplementation(fetchMock as never)

    await syncRuntimeProfileReadOnly('binance-usdm-main')

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(String(url)).toContain('/api/v3/runtime/profiles/binance-usdm-main/read-only/sync')
    expect(init.method).toBe('POST')
  })

  it('passes profile scope to scoped portfolio and health requests', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true }),
    })
    vi.spyOn(globalThis, 'fetch' as never).mockImplementation(fetchMock as never)

    await fetchPortfolioForScope('paper-main')
    await fetchEngineHealthForScope('paper-main')

    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain('/api/v3/portfolio?profile_id=paper-main')
    expect(String(fetchMock.mock.calls[1]?.[0])).toContain('/api/v3/health?profile_id=paper-main')
  })

  it('fetches available runtime profiles through the runtime profile route', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items: [{ profile_id: 'paper-main' }], count: 1 }),
    })
    vi.spyOn(globalThis, 'fetch' as never).mockImplementation(fetchMock as never)

    await fetchRuntimeProfiles()

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(String(url)).toContain('/api/v3/runtime/profiles')
  })

  it('fetches grouped profile settings through the runtime profile settings route', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ profile_id: 'binance-usdm-main', capabilities: { auto_trading_enabled: false } }),
    })
    vi.spyOn(globalThis, 'fetch' as never).mockImplementation(fetchMock as never)

    await fetchRuntimeProfileSettings('binance-usdm-main')

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(String(url)).toContain('/api/v3/runtime/profiles/binance-usdm-main/settings')
  })

  it('updates grouped profile settings through the runtime profile settings route', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ profile_id: 'binance-usdm-main', capabilities: { auto_trading_enabled: true } }),
    })
    vi.spyOn(globalThis, 'fetch' as never).mockImplementation(fetchMock as never)

    await updateRuntimeProfileSettings({
      profile_id: 'binance-usdm-main',
      capabilities: { auto_trading_enabled: true },
      runtime_settings: { AUTONOMOUS_ENABLED: 'true' },
      risk_settings: { LIVE_RISK_PER_TRADE_PCT: 0.02 },
    })

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(String(url)).toContain('/api/v3/runtime/profiles/binance-usdm-main/settings')
    expect(init.method).toBe('POST')
    expect(JSON.parse(String(init.body))).toMatchObject({
      capabilities: { auto_trading_enabled: true },
      runtime_settings: { AUTONOMOUS_ENABLED: 'true' },
      risk_settings: { LIVE_RISK_PER_TRADE_PCT: 0.02 },
    })
  })

  it('fetches profile-scoped read-only runtime exposure through the runtime profile route', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ profile: { profile_id: 'binance-usdm-main' }, health: { exchange_status: 'connected' } }),
    })
    vi.spyOn(globalThis, 'fetch' as never).mockImplementation(fetchMock as never)

    await fetchRuntimeProfileReadOnlyExposure('binance-usdm-main')

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(String(url)).toContain('/api/v3/runtime/profiles/binance-usdm-main/read-only/exposure')
  })

  it('updates shadow engine through the centralized operate route', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true, shadow_engine: 'v5' }),
    })
    vi.spyOn(globalThis, 'fetch' as never).mockImplementation(fetchMock as never)

    await updateOperateShadowEngine('v5')

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(String(url)).toContain('/api/v3/operate/shadow-engine')
    expect(String(url)).not.toContain('/v6/')
    expect(init.method).toBe('POST')
    expect(JSON.parse(String(init.body))).toMatchObject({ shadow_engine: 'v5' })
  })
})
