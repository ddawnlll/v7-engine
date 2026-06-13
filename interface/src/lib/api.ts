import { getCurrentSettings } from './runtimeSettings'
import { apiRoutes } from './apiRoutes'
import { isManualTrade } from './executionIdentity'
import { profileScopeToApiProfileId } from './profileScope'
import type {
  AnalysisPayload,
  CalibrationStatusPayload,
  DashboardPayload,
  DecisionEventDetailPayload,
  DecisionEventListPayload,
  EngineBehaviorPayload,
  EngineHealthPayload,
  FailureListPayload,
  FailureAnalyticsPayload,
  FailureSummaryPayload,
  CircuitBreakerEventsPayload,
  CircuitBreakerStatePayload,
  JobQueueSnapshot,
  JsonRecord,
  LearningEffectivenessPayload,
  ImprovementAnalyticsPayload,
  LearningProfilePayload,
  LogsPayload,
  MarketOverviewPayload,
  RegistryCandidatesPayload,
  RegistryChampionPayload,
  RegistryModelsPayload,
  ReviewLearningPayload,
  RuntimeReadinessPayload,
  MarketSignalsPayload,
  OperatorAlertsPayload,
  OrdersSnapshot,
  PaperAccountPayload,
  RuntimeProfileSettingsPayload,
  RuntimeProfileSettingsUpdatePayload,
  RuntimeSettingsMetadataPayload,
  PerformancePayload,
  PortfolioPayload,
  QueueScanPayload,
  ScanControlPayload,
  SignalAuditPayload,
  RuntimeSettingsPayload,
  ShadowComparisonPayload,
  SignalPayload,
  SelfLearningMemoriesPayload,
  SelfLearningProfilePayload,
  SelfLearningReplayPayload,
  SelfLearningShadowPayload,
  SelfLearningStatusPayload,
  CreateSimulationPayload,
  SimulationConfidenceHistogramResponse,
  SimulationDecisionTraceResponse,
  SimulationDecisionTraceSummary,
  SimulationDiagnosticsResponse,
  SimulationParityReport,
  SimulationPreset,
  SimulationPresetListResponse,
  SimulationPresetMutationResponse,
  SimulationRunDetail,
  SimulationRunsPayload,
  SimulationWhatIfResponse,
  StorageExportPayload,
  StorageMutationSummary,
  StorageTrashEntry,
  TradeOutcomeListPayload,
  TradeOverviewPayload,
  RuntimeMetricsPayload,
  RuntimeProfileListPayload,
  RuntimeProfileReadOnlyExposurePayload,
  StorageStatusPayload,
  SwingPatchValidationPayload,
  SymbolsPayload,
  TradeAnalyticsPayload,
  TraceSnapshotPayload,
  WeaknessProfilePayload,
} from './types'

type OrderBlotterResponse = {
  items?: Array<JsonRecord & { state?: string; source?: string }>
}

async function readJson<T>(input: RequestInfo | URL, init?: RequestInit): Promise<T> {
  const settings = getCurrentSettings()
  const headers = new Headers(init?.headers ?? {})
  headers.set('X-V3-Engine-Target', settings.engineTarget)
  const response = await fetch(input, {
    ...init,
    headers,
  })
  if (!response.ok) {
    let message = `Request failed with ${response.status}`
    try {
      const payload = await response.json() as { error?: string; message?: string; detail?: string | { msg?: string }[] }
      message = payload.error || payload.message || (typeof payload.detail === 'string' ? payload.detail : Array.isArray(payload.detail) ? payload.detail[0]?.msg : undefined) || message
    } catch {
      try {
        const text = await response.text()
        if (text.trim()) {
          message = text.trim()
        }
      } catch {
        // ignore secondary read failures
      }
    }
    throw new Error(message)
  }
  return response.json() as Promise<T>
}

async function readText(input: RequestInfo | URL, init?: RequestInit): Promise<string> {
  const settings = getCurrentSettings()
  const headers = new Headers(init?.headers ?? {})
  headers.set('X-V3-Engine-Target', settings.engineTarget)
  const response = await fetch(input, {
    ...init,
    headers,
  })
  if (!response.ok) {
    throw new Error((await response.text()) || `Request failed with ${response.status}`)
  }
  return response.text()
}

function isOpenOrderRecord(item: JsonRecord) {
  if (item.is_open === true) return true
  if (String(item.lifecycle_status ?? '').toUpperCase() === 'OPEN') return true
  const closeTimestamp = String(item.close_timestamp ?? item.closed_at_utc ?? '')
  if (closeTimestamp) return false
  const state = String(item.state ?? item.status ?? '').toUpperCase()
  if (['OPEN', 'PENDING', 'ORDERED', 'NEW', 'PARTIALLY_FILLED'].includes(state)) return true
  if (state === 'FILLED') return String(item.execution_mode ?? '').toUpperCase() === 'LIVE'
  return false
}

function mapOrdersSnapshot(response: OrderBlotterResponse): OrdersSnapshot {
  const items = (response.items ?? []) as JsonRecord[]
  const normalized = items.map((item) => ({
    ...item,
    state: item.state ?? item.status,
    lifecycle_status: item.lifecycle_status ?? (isOpenOrderRecord(item) ? 'OPEN' : 'CLOSED'),
    is_open: item.is_open ?? isOpenOrderRecord(item),
  })) as JsonRecord[]
  const openOrders = normalized.filter((item) => Boolean(item.is_open))
  const closedOrders = normalized.filter((item) => !Boolean(item.is_open))
  return {
    open_orders: openOrders,
    closed_orders: closedOrders,
    auto_open_orders: openOrders.filter((item) => !isManualTrade(item as typeof openOrders[number])),
    auto_closed_orders: closedOrders.filter((item) => !isManualTrade(item as typeof closedOrders[number])),
    manual_open_orders: openOrders.filter((item) => isManualTrade(item as typeof openOrders[number])),
    manual_closed_orders: closedOrders.filter((item) => isManualTrade(item as typeof closedOrders[number])),
    open_count: openOrders.length,
    closed_count: closedOrders.length,
    summary: (response as JsonRecord).summary as OrdersSnapshot['summary'],
    open_trade_analysis: (response as JsonRecord).open_trade_analysis as OrdersSnapshot['open_trade_analysis'],
  }
}

export function fetchDashboard() {
  return readJson<DashboardPayload>(apiRoutes.dashboard())
}

export function fetchMarketOverview(limit = 50) {
  const params = new URLSearchParams({ limit: String(limit) })
  return readJson<MarketOverviewPayload>(`${apiRoutes.marketOverview()}?${params.toString()}`)
}

export function fetchSymbols() {
  return readJson<SymbolsPayload>(apiRoutes.symbols())
}

export function fetchMarketSignals(limit = 100) {
  const params = new URLSearchParams({ limit: String(limit) })
  return readJson<MarketSignalsPayload>(`${apiRoutes.marketSignals()}?${params.toString()}`)
}

export function fetchEngineHealthForScope(profileScope?: string) {
  const params = new URLSearchParams()
  const profileId = profileScopeToApiProfileId(profileScope)
  if (profileId) params.set('profile_id', profileId)
  return readJson<EngineHealthPayload>(`${apiRoutes.health()}${params.size ? `?${params.toString()}` : ''}`)
}

export function fetchEngineHealth() {
  return fetchEngineHealthForScope()
}

export function fetchRuntimeProfiles() {
  return readJson<RuntimeProfileListPayload>(apiRoutes.runtimeProfiles())
}

export function fetchRuntimeProfileSettings(profileId: string) {
  return readJson<RuntimeProfileSettingsPayload>(apiRoutes.runtimeProfileSettings(profileId))
}

export function updateRuntimeProfileSettings(payload: RuntimeProfileSettingsUpdatePayload) {
  const profileId = String(payload.profile_id ?? '')
  const body = {
    capabilities: Object.fromEntries(Object.entries(payload.capabilities ?? {}).filter(([, value]) => value !== undefined)),
    runtime_settings: Object.fromEntries(Object.entries(payload.runtime_settings ?? {}).filter(([, value]) => value !== undefined)),
    risk_settings: Object.fromEntries(Object.entries(payload.risk_settings ?? {}).filter(([, value]) => value !== undefined)),
  }
  return readJson<RuntimeProfileSettingsPayload>(apiRoutes.runtimeProfileSettings(profileId), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function fetchRuntimeProfileReadOnlyExposure(profileId: string) {
  return readJson<RuntimeProfileReadOnlyExposurePayload>(apiRoutes.runtimeProfileReadOnlyExposure(profileId))
}

export function fetchCalibrationStatus(limit = 5000) {
  const params = new URLSearchParams({ limit: String(limit) })
  return readJson<CalibrationStatusPayload>(`${apiRoutes.calibrationStatus()}?${params.toString()}`)
}

export function getFailures(filters?: {
  limit?: number
  offset?: number
  failureSource?: string
  blamedComponent?: string
  severityScore?: number
  dateFrom?: string
  dateTo?: string
  profileScope?: string
}) {
  const params = new URLSearchParams()
  if (filters?.limit != null) params.set('limit', String(filters.limit))
  if (filters?.offset != null) params.set('offset', String(filters.offset))
  if (filters?.failureSource) params.set('failure_source', filters.failureSource)
  if (filters?.blamedComponent) params.set('blamed_component', filters.blamedComponent)
  if (filters?.severityScore != null) params.set('severity_score', String(filters.severityScore))
  if (filters?.dateFrom) params.set('date_from', filters.dateFrom)
  if (filters?.dateTo) params.set('date_to', filters.dateTo)
  const profileId = profileScopeToApiProfileId(filters?.profileScope)
  if (profileId) params.set('profile_id', profileId)
  return readJson<FailureListPayload>(`/api/v3/failures${params.size ? `?${params.toString()}` : ''}`)
}

export function getFailureSummary(filters?: {
  failureSource?: string
  blamedComponent?: string
  severityScore?: number
  dateFrom?: string
  dateTo?: string
}) {
  const params = new URLSearchParams()
  if (filters?.failureSource) params.set('failure_source', filters.failureSource)
  if (filters?.blamedComponent) params.set('blamed_component', filters.blamedComponent)
  if (filters?.severityScore != null) params.set('severity_score', String(filters.severityScore))
  if (filters?.dateFrom) params.set('date_from', filters.dateFrom)
  if (filters?.dateTo) params.set('date_to', filters.dateTo)
  return readJson<FailureSummaryPayload>(`/api/v3/failures/summary${params.size ? `?${params.toString()}` : ''}`)
}

export function getWeaknessProfile(lookbackDays = 30, minConfidence = 0.6) {
  const params = new URLSearchParams({
    lookback_days: String(lookbackDays),
    min_confidence: String(minConfidence),
  })
  return readJson<WeaknessProfilePayload>(`/api/v3/failures/weakness-profile?${params.toString()}`)
}

export function getFailureAnalytics(lookbackDays = 30, mode?: string, minConfidence = 0.6, profileScope?: string) {
  const params = new URLSearchParams({
    lookback_days: String(lookbackDays),
    min_confidence: String(minConfidence),
  })
  const profileId = profileScopeToApiProfileId(profileScope)
  if (mode && mode !== 'ALL') params.set('mode', mode)
  if (profileId) params.set('profile_id', profileId)
  return readJson<FailureAnalyticsPayload>(`/api/v3/failures/analytics?${params.toString()}`)
}

export function exportFailureAnalyticsCsv(lookbackDays = 30, mode?: string, minConfidence?: number, profileScope?: string) {
  const params = new URLSearchParams({
    lookback_days: String(lookbackDays),
  })
  const profileId = profileScopeToApiProfileId(profileScope)
  if (mode && mode !== 'ALL') params.set('mode', mode)
  if (minConfidence != null) params.set('min_confidence', String(minConfidence))
  if (profileId) params.set('profile_id', profileId)
  return readText(`/api/v3/failures/export?${params.toString()}`)
}

export function getLearningProfile(lookbackDays = 30, minConfidence = 0.6) {
  const params = new URLSearchParams({
    lookback_days: String(lookbackDays),
    min_confidence: String(minConfidence),
  })
  return readJson<LearningProfilePayload>(`/api/v3/learning/profile?${params.toString()}`)
}

export function getLearningEffectiveness(lookbackDays = 30, minSamples = 5) {
  const params = new URLSearchParams({
    lookback_days: String(lookbackDays),
    min_samples: String(minSamples),
  })
  return readJson<LearningEffectivenessPayload>(`/api/v3/learning/effectiveness?${params.toString()}`)
}

export function exportLearningCsv(lookbackDays = 30, minConfidence = 0.6, minSamples = 5) {
  const params = new URLSearchParams({
    lookback_days: String(lookbackDays),
    min_confidence: String(minConfidence),
    min_samples: String(minSamples),
  })
  return readText(`/api/v3/learning/export?${params.toString()}`)
}

export function getSwingPatchValidation(lookbackDays = 30, intervalMinMinutes = 60) {
  const params = new URLSearchParams({
    lookback_days: String(lookbackDays),
    interval_min_minutes: String(intervalMinMinutes),
  })
  return readJson<SwingPatchValidationPayload>(`/api/v3/analytics/swing-patch-validation?${params.toString()}`)
}

export function exportSwingPatchValidationCsv(lookbackDays = 30, intervalMinMinutes = 60) {
  const params = new URLSearchParams({
    lookback_days: String(lookbackDays),
    interval_min_minutes: String(intervalMinMinutes),
  })
  return readText(`/api/v3/analytics/swing-patch-validation/export?${params.toString()}`)
}

export function getCircuitBreakerState(lookbackWindow = 10, profileScope?: string) {
  const params = new URLSearchParams({ lookback_window: String(lookbackWindow) })
  const profileId = profileScopeToApiProfileId(profileScope)
  if (profileId) params.set('profile_id', profileId)
  return readJson<CircuitBreakerStatePayload>(`/api/v3/circuit-breaker/state?${params.toString()}`)
}

export function getCircuitBreakerEvents(limit = 50, offset = 0, profileScope?: string) {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  const profileId = profileScopeToApiProfileId(profileScope)
  if (profileId) params.set('profile_id', profileId)
  return readJson<CircuitBreakerEventsPayload>(`/api/v3/circuit-breaker/events?${params.toString()}`)
}

export function resetCircuitBreaker(profileScope?: string) {
  const params = new URLSearchParams()
  const profileId = profileScopeToApiProfileId(profileScope)
  if (profileId) params.set('profile_id', profileId)
  return readJson<CircuitBreakerStatePayload>(`/api/v3/circuit-breaker/reset${params.size ? `?${params.toString()}` : ''}`, { method: 'POST' })
}

export function updateCircuitBreakerSettings(payload: Record<string, string | number>, profileScope?: string) {
  const params = new URLSearchParams()
  const profileId = profileScopeToApiProfileId(profileScope)
  if (profileId) params.set('profile_id', profileId)
  return readJson<{ ok?: boolean; settings?: Record<string, string> }>(`/api/v3/circuit-breaker/settings${params.size ? `?${params.toString()}` : ''}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function getSignal(signalId: string) {
  return readJson<SignalPayload>(`/api/v3/signals/${encodeURIComponent(signalId)}`)
}

export function getSignalAudit(signalId: string) {
  return readJson<SignalAuditPayload>(`/api/v3/signals/${encodeURIComponent(signalId)}/audit`)
}

export function getSelfLearningStatus() {
  return readJson<SelfLearningStatusPayload>('/api/v3/self-learning/status')
}

export function getSelfLearningProfile(lookbackDays = 30) {
  const params = new URLSearchParams({ lookback_days: String(lookbackDays) })
  return readJson<SelfLearningProfilePayload>(`/api/v3/self-learning/profile?${params.toString()}`)
}

export function getSelfLearningMemories(filters?: {
  lookbackDays?: number
  learningRegime?: string
  resultLabel?: string
  symbol?: string
  mode?: string
  limit?: number
}) {
  const params = new URLSearchParams()
  if (filters?.lookbackDays != null) params.set('lookback_days', String(filters.lookbackDays))
  if (filters?.learningRegime) params.set('learning_regime', filters.learningRegime)
  if (filters?.resultLabel) params.set('result_label', filters.resultLabel)
  if (filters?.symbol) params.set('symbol', filters.symbol)
  if (filters?.mode) params.set('mode', filters.mode)
  if (filters?.limit != null) params.set('limit', String(filters.limit))
  return readJson<SelfLearningMemoriesPayload>(`/api/v3/self-learning/memories${params.size ? `?${params.toString()}` : ''}`)
}

export function getSelfLearningReplays(orderId: string) {
  return readJson<SelfLearningReplayPayload>(`/api/v3/self-learning/replays/${encodeURIComponent(orderId)}`)
}

export function getSelfLearningShadow(signalId: string) {
  return readJson<SelfLearningShadowPayload>(`/api/v3/self-learning/shadow/${encodeURIComponent(signalId)}`)
}

export function exportSelfLearningCsv() {
  return readText('/api/v3/self-learning/export?format=csv')
}

export function getTradeAnalytics(
  lookbackDays = 30,
  minSamples = 10,
  filters?: {
    mode?: string
    symbol?: string
    interval?: string
    direction?: string
  },
) {
  const params = new URLSearchParams({
    lookback_days: String(lookbackDays),
    min_samples: String(minSamples),
  })
  if (filters?.mode && filters.mode !== 'ALL') params.set('mode', filters.mode)
  if (filters?.symbol) params.set('symbol', filters.symbol)
  if (filters?.interval && filters.interval !== 'ALL') params.set('interval', filters.interval)
  if (filters?.direction && filters.direction !== 'ALL') params.set('direction', filters.direction)
  return readJson<TradeAnalyticsPayload>(`/api/v3/analytics?${params.toString()}`)
}

export function exportTradeAnalytics(
  lookbackDays = 30,
  filters?: {
    mode?: string
    symbol?: string
    interval?: string
    direction?: string
  },
) {
  const params = new URLSearchParams({
    lookback_days: String(lookbackDays),
  })
  if (filters?.mode && filters.mode !== 'ALL') params.set('mode', filters.mode)
  if (filters?.symbol) params.set('symbol', filters.symbol)
  if (filters?.interval && filters.interval !== 'ALL') params.set('interval', filters.interval)
  if (filters?.direction && filters.direction !== 'ALL') params.set('direction', filters.direction)
  return readText(`/api/v3/analytics/export?${params.toString()}`)
}

export function getImprovementAnalytics(
  lookbackDays = 30,
  minSamples = 10,
  filters?: {
    componentType?: string
    componentStatus?: string
    componentId?: string
    mode?: string
    symbol?: string
    interval?: string
    direction?: string
    regime?: string
  },
) {
  const params = new URLSearchParams({
    lookback_days: String(lookbackDays),
    min_samples: String(minSamples),
  })
  if (filters?.componentType && filters.componentType !== 'ALL') params.set('component_type', filters.componentType)
  if (filters?.componentStatus && filters.componentStatus !== 'ALL') params.set('component_status', filters.componentStatus)
  if (filters?.componentId) params.set('component_id', filters.componentId)
  if (filters?.mode && filters.mode !== 'ALL') params.set('mode', filters.mode)
  if (filters?.symbol) params.set('symbol', filters.symbol)
  if (filters?.interval && filters.interval !== 'ALL') params.set('interval', filters.interval)
  if (filters?.direction && filters.direction !== 'ALL') params.set('direction', filters.direction)
  if (filters?.regime && filters.regime !== 'ALL') params.set('regime', filters.regime)
  return readJson<ImprovementAnalyticsPayload>(`/api/v3/improvements?${params.toString()}`)
}

export function exportImprovementAnalytics(
  lookbackDays = 30,
  minSamples = 10,
  filters?: {
    componentType?: string
    componentStatus?: string
    componentId?: string
    mode?: string
    symbol?: string
    interval?: string
    direction?: string
    regime?: string
  },
) {
  const params = new URLSearchParams({
    lookback_days: String(lookbackDays),
    min_samples: String(minSamples),
  })
  if (filters?.componentType && filters.componentType !== 'ALL') params.set('component_type', filters.componentType)
  if (filters?.componentStatus && filters.componentStatus !== 'ALL') params.set('component_status', filters.componentStatus)
  if (filters?.componentId) params.set('component_id', filters.componentId)
  if (filters?.mode && filters.mode !== 'ALL') params.set('mode', filters.mode)
  if (filters?.symbol) params.set('symbol', filters.symbol)
  if (filters?.interval && filters.interval !== 'ALL') params.set('interval', filters.interval)
  if (filters?.direction && filters.direction !== 'ALL') params.set('direction', filters.direction)
  if (filters?.regime && filters.regime !== 'ALL') params.set('regime', filters.regime)
  return readText(`/api/v3/improvements/export?${params.toString()}`)
}

export async function fetchRuntimeSettingsForScope(profileScope?: string) {
  const params = new URLSearchParams()
  const profileId = profileScopeToApiProfileId(profileScope)
  if (profileId) params.set('profile_id', profileId)
  const payload = await readJson<{ settings?: Record<string, string> }>(`${apiRoutes.settings()}${params.size ? `?${params.toString()}` : ''}`)
  return payload.settings ?? {}
}

export async function fetchRuntimeSettingsMetadataForScope(profileScope?: string) {
  const params = new URLSearchParams()
  const profileId = profileScopeToApiProfileId(profileScope)
  if (profileId) params.set('profile_id', profileId)
  return readJson<RuntimeSettingsMetadataPayload>(`${apiRoutes.settingsMetadata()}${params.size ? `?${params.toString()}` : ''}`)
}

export async function fetchRuntimeSettings() {
  return fetchRuntimeSettingsForScope()
}

export function fetchOperatorAlertsForScope(profileScope?: string) {
  const params = new URLSearchParams()
  const profileId = profileScopeToApiProfileId(profileScope)
  if (profileId) params.set('profile_id', profileId)
  return readJson<OperatorAlertsPayload>(`${apiRoutes.alerts()}${params.size ? `?${params.toString()}` : ''}`)
}

export function fetchOperatorAlerts() {
  return fetchOperatorAlertsForScope()
}

export function fetchLogs(limit = 50, severity = 'ALL') {
  return fetchLogsForScope(limit, severity)
}

export function fetchLogsForScope(limit = 50, severity = 'ALL', profileScope?: string) {
  const params = new URLSearchParams({
    limit: String(limit),
    severity,
  })
  const profileId = profileScopeToApiProfileId(profileScope)
  if (profileId) params.set('profile_id', profileId)
  return readJson<LogsPayload>(`${apiRoutes.logs()}?${params.toString()}`)
}

export function fetchTraces(limit = 250, filters?: { runId?: string; symbol?: string; eventType?: string; decision?: string }) {
  return fetchTracesForScope(limit, filters)
}

export function fetchTracesForScope(limit = 250, filters?: { runId?: string; symbol?: string; eventType?: string; decision?: string; profileScope?: string }) {
  const params = new URLSearchParams({ limit: String(limit) })
  const profileId = profileScopeToApiProfileId(filters?.profileScope)
  if (profileId) params.set('profile_id', profileId)
  if (filters?.runId) params.set('run_id', filters.runId)
  if (filters?.symbol) params.set('symbol', filters.symbol)
  if (filters?.eventType) params.set('event_type', filters.eventType)
  if (filters?.decision) params.set('decision', filters.decision)
  return readJson<TraceSnapshotPayload>(`/api/v3/traces?${params.toString()}`)
}

export async function fetchOrdersForScope(closedLimit = 500, profileScope?: string) {
  const params = new URLSearchParams({ limit: String(closedLimit) })
  const profileId = profileScopeToApiProfileId(profileScope)
  if (profileId) params.set('profile_id', profileId)
  const response = await readJson<OrderBlotterResponse>(`/api/v3/orders?${params.toString()}`)
  return mapOrdersSnapshot(response)
}

export async function fetchOrders(closedLimit = 500) {
  return fetchOrdersForScope(closedLimit)
}

export function closeOrder(orderId: string, closePrice: number, closeReason = 'MANUAL_CLOSE') {
  return readJson<{ ok?: boolean; order?: JsonRecord }>(`/api/v3/orders/${encodeURIComponent(orderId)}/close`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      close_price: closePrice,
      close_reason: closeReason,
    }),
  })
}

export function createManualOrder(payload: JsonRecord) {
  return readJson<{ ok?: boolean; order?: JsonRecord; signal_outcome?: JsonRecord; verification?: JsonRecord }>(`/api/v3/orders`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function closeAllOpenOrders(closeReason = 'MANUAL_BULK_CLOSE') {
  const params = new URLSearchParams({ close_reason: closeReason })
  return readJson<{ ok?: boolean; closed_count?: number; errors?: JsonRecord[]; orders?: JsonRecord[]; portfolio?: JsonRecord }>(`/api/v3/orders/close-all-open?${params.toString()}`, {
    method: 'POST',
  })
}

export function fetchPortfolioForScope(profileScope?: string) {
  const params = new URLSearchParams()
  const profileId = profileScopeToApiProfileId(profileScope)
  if (profileId) params.set('profile_id', profileId)
  return readJson<PortfolioPayload>(`/api/v3/portfolio${params.size ? `?${params.toString()}` : ''}`)
}

export function syncRuntimeProfileReadOnly(profileId: string) {
  return readJson<JsonRecord>(`/api/v3/runtime/profiles/${encodeURIComponent(profileId)}/read-only/sync`, {
    method: 'POST',
  })
}

export function fetchPortfolio() {
  return fetchPortfolioForScope()
}

export function fetchPaperBalanceForScope(profileScope?: string) {
  const params = new URLSearchParams()
  const profileId = profileScopeToApiProfileId(profileScope)
  if (profileId) params.set('profile_id', profileId)
  return readJson<PaperAccountPayload>(`/api/v3/paper/balance${params.size ? `?${params.toString()}` : ''}`)
}

export function fetchPaperBalance() {
  return fetchPaperBalanceForScope()
}

export function depositPaperBalance(amount: number) {
  return readJson<PaperAccountPayload>('/api/v3/paper/deposit', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ amount }),
  })
}

export function resetPaperBalance(balance?: number) {
  return readJson<PaperAccountPayload>('/api/v3/paper/reset', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(balance == null ? {} : { balance }),
  })
}

export function reconcilePaperBalance() {
  return readJson<PaperAccountPayload>('/api/v3/paper/reconcile', {
    method: 'POST',
  })
}

export function fetchPerformance(limit = 120) {
  const params = new URLSearchParams({ limit: String(limit) })
  return readJson<PerformancePayload>(`/api/v3/performance?${params.toString()}`)
}

export function fetchTradeOverview() {
  return readJson<TradeOverviewPayload>(apiRoutes.tradeOverview())
}

export function fetchReviewDecisionEvents(filters?: { runId?: string; symbol?: string; dateFrom?: string; dateTo?: string; limit?: number }) {
  const params = new URLSearchParams()
  if (filters?.runId) params.set('run_id', filters.runId)
  if (filters?.symbol) params.set('symbol', filters.symbol)
  if (filters?.dateFrom) params.set('date_from', filters.dateFrom)
  if (filters?.dateTo) params.set('date_to', filters.dateTo)
  if (filters?.limit != null) params.set('limit', String(filters.limit))
  return readJson<DecisionEventListPayload>(`${apiRoutes.reviewDecisionEvents()}${params.size ? `?${params.toString()}` : ''}`)
}

export function fetchReviewDecisionEvent(eventId: string) {
  return readJson<DecisionEventDetailPayload>(`${apiRoutes.reviewDecisionEvents()}/${encodeURIComponent(eventId)}`)
}

export function fetchReviewTradeOutcomes(filters?: { eventId?: string; outcomeStatus?: string; dateFrom?: string; limit?: number }) {
  const params = new URLSearchParams()
  if (filters?.eventId) params.set('event_id', filters.eventId)
  if (filters?.outcomeStatus) params.set('outcome_status', filters.outcomeStatus)
  if (filters?.dateFrom) params.set('date_from', filters.dateFrom)
  if (filters?.limit != null) params.set('limit', String(filters.limit))
  return readJson<TradeOutcomeListPayload>(`${apiRoutes.reviewTradeOutcomes()}${params.size ? `?${params.toString()}` : ''}`)
}

export function fetchReviewEngineBehavior(filters?: { dateFrom?: string; dateTo?: string }) {
  const params = new URLSearchParams()
  if (filters?.dateFrom) params.set('date_from', filters.dateFrom)
  if (filters?.dateTo) params.set('date_to', filters.dateTo)
  return readJson<EngineBehaviorPayload>(`${apiRoutes.reviewEngineBehavior()}${params.size ? `?${params.toString()}` : ''}`)
}

export function fetchReviewShadowComparison(comparisonGroupId?: string) {
  const params = new URLSearchParams()
  if (comparisonGroupId) params.set('comparison_group_id', comparisonGroupId)
  return readJson<ShadowComparisonPayload>(`${apiRoutes.reviewShadowComparison()}${params.size ? `?${params.toString()}` : ''}`)
}

export function fetchReviewLearning() {
  return readJson<ReviewLearningPayload>(apiRoutes.reviewLearning())
}

export function fetchRuntimeMetrics() {
  return readJson<RuntimeMetricsPayload>(apiRoutes.runtimeMetrics())
}

export function fetchOperateChampion() {
  return readJson<RegistryChampionPayload>(apiRoutes.operateChampion())
}

export function fetchOperateRuntimeStatus() {
  return readJson<RuntimeReadinessPayload & { ok?: boolean }>(apiRoutes.operateRuntimeStatus())
}

export function refreshOperateChampionRuntime() {
  return readJson<RuntimeReadinessPayload & { ok?: boolean; action?: string }>(apiRoutes.operateRuntimeRefreshChampion(), {
    method: 'POST',
  })
}

export function fetchOperateCandidates() {
  return readJson<RegistryCandidatesPayload>(apiRoutes.operateCandidates())
}

export function fetchOperateModels() {
  return readJson<RegistryModelsPayload>(apiRoutes.operateModels())
}

export function promoteOperateCandidate(payload: {
  model_artifact_version: string
  expectancy_delta?: number
  win_rate?: number
  suppression_accuracy?: number
  holdout_period_utc?: string
  paper_outcome_sample_size?: number
  shadow_comparison_run_id?: string | null
}) {
  return readJson<RegistryChampionPayload & { ok?: boolean }>(apiRoutes.operatePromote(), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function rollbackOperateChampion(reason = 'manual rollback from interface') {
  return readJson<RegistryChampionPayload & { ok?: boolean }>(apiRoutes.operateRollback(), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason }),
  })
}

export function updateOperateShadowEngine(shadowEngine: string | null) {
  return readJson<RegistryChampionPayload & { ok?: boolean; settings?: Record<string, string> }>(apiRoutes.operateShadowEngine(), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ shadow_engine: shadowEngine }),
  })
}

export function fetchSimulations(limit = 50) {
  const params = new URLSearchParams({ limit: String(limit) })
  return readJson<SimulationRunsPayload>(`${apiRoutes.simulations()}?${params.toString()}`)
}

export function fetchSimulationRun(runId: number) {
  return readJson<SimulationRunDetail>(apiRoutes.simulationRun(runId))
}

export function fetchSimulationPresets(limit = 100) {
  const params = new URLSearchParams({ limit: String(limit) })
  return readJson<SimulationPresetListResponse>(`${apiRoutes.simulationPresets()}?${params.toString()}`)
}

export function createSimulationPreset(payload: Omit<SimulationPreset, 'id' | 'created_at' | 'updated_at'>) {
  return readJson<SimulationPresetMutationResponse>(apiRoutes.simulationPresets(), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function updateSimulationPreset(presetId: number, payload: Partial<SimulationPreset>) {
  return readJson<SimulationPresetMutationResponse>(apiRoutes.simulationPreset(presetId), {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function deleteSimulationPreset(presetId: number) {
  return readJson<SimulationPresetMutationResponse>(apiRoutes.simulationPreset(presetId), { method: 'DELETE' })
}

export function createSimulation(payload: CreateSimulationPayload) {
  return readJson<SimulationRunDetail>(apiRoutes.simulations(), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function stopSimulation(runId: number) {
  return readJson<SimulationRunDetail>(apiRoutes.simulationStop(runId), { method: 'POST' })
}

export function forceStopSimulation(runId: number) {
  return readJson<SimulationRunDetail & { force_stopped?: boolean }>(apiRoutes.simulationForceStop(runId), { method: 'POST' })
}

export function fetchSimulationDecisionTraces(runId: number, filters?: {
  symbol?: string
  interval?: string
  mode?: string
  direction?: string
  signal_status?: string
  runtime_filter_reason?: string
  reason?: string
  fallback_used?: boolean
  min_confidence?: number
  max_confidence?: number
  start_ts?: string
  end_ts?: string
  limit?: number
  cursor?: number | null
  sort?: 'asc' | 'desc'
  errors_only?: boolean
}) {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(filters ?? {})) {
    if (value == null || value === '' || key === 'errors_only') continue
    params.set(key, String(value))
  }
  return readJson<SimulationDecisionTraceResponse>(`${apiRoutes.simulationDecisionTraces(runId)}${params.size ? `?${params.toString()}` : ''}`)
}

export function fetchSimulationDecisionTraceSummary(runId: number) {
  return readJson<SimulationDecisionTraceSummary>(apiRoutes.simulationDecisionTraceSummary(runId))
}

export function fetchSimulationDiagnostics(runId: number) {
  return readJson<SimulationDiagnosticsResponse>(apiRoutes.simulationDiagnostics(runId))
}

export function fetchSimulationConfidenceHistogram(runId: number) {
  return readJson<SimulationConfidenceHistogramResponse>(apiRoutes.simulationConfidenceHistogram(runId))
}

export function fetchSimulationWhatIf(runId: number, params?: {
  min_confidence?: number
  fees_bps?: number
  slippage_bps?: number
  max_hold_bars?: number
  risk_per_trade?: number
}) {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value != null) query.set(key, String(value))
  }
  return readJson<SimulationWhatIfResponse>(`${apiRoutes.simulationWhatIf(runId)}${query.size ? `?${query.toString()}` : ''}`)
}

export function fetchSimulationParityReport(runId: number) {
  return readJson<SimulationParityReport>(apiRoutes.simulationParityReport(runId))
}

export function simulationExportUrl(runId: number, params?: { target?: string; format?: string; limit?: number }) {
  const query = new URLSearchParams()
  if (params?.target) query.set('target', params.target)
  if (params?.format) query.set('format', params.format)
  if (params?.limit != null) query.set('limit', String(params.limit))
  return `${apiRoutes.simulationExports(runId)}${query.size ? `?${query.toString()}` : ''}`
}

export function fetchSimulationExport(runId: number, params?: { target?: string; format?: 'json' | 'csv' | 'jsonl'; limit?: number }) {
  const format = params?.format ?? 'json'
  const url = simulationExportUrl(runId, params)
  return format === 'json' ? readJson<JsonRecord>(url) : readText(url)
}

export function submitSimulationFailureAnalysis(runId: number, params?: { persist?: boolean; profile_id?: string }) {
  const query = new URLSearchParams()
  if (params?.persist != null) query.set('persist', String(params.persist))
  if (params?.profile_id) query.set('profile_id', params.profile_id)
  return readJson<JsonRecord>(`${apiRoutes.simulationFailureAnalysis(runId)}${query.size ? `?${query.toString()}` : ''}`, { method: 'POST' })
}

export function fetchJobsForScope(limit = 200, profileScope?: string) {
  const params = new URLSearchParams({ limit: String(limit) })
  const profileId = profileScopeToApiProfileId(profileScope)
  if (profileId) params.set('profile_id', profileId)
  return readJson<JobQueueSnapshot>(`/api/v3/scans?${params.toString()}`)
}

export function fetchJobs(limit = 200) {
  return fetchJobsForScope(limit)
}

export function fetchScanControl() {
  return readJson<ScanControlPayload>(apiRoutes.scansControl())
}

export function queueLegacyScan(payload: QueueScanPayload) {
  return readJson<JsonRecord & { run_id?: string }>('/api/v3/scans', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      symbols: payload.symbols,
      intervals: payload.intervals,
      modes: payload.modes,
      scan_workers: payload.scan_workers,
      requested_by: 'interface',
      profile_id: payload.profile_id,
    }),
  }).then((result) => ({
    ok: true,
    job: {
      id: result.run_id ?? '--',
    },
  }))
}

export function retryFailedJobs(limit = 25) {
  return readJson<{ ok?: boolean; retried?: number; job_ids?: number[] }>('/api/v3/jobs/retry', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ limit }),
  })
}

export function pauseScans(requestedBy = 'interface', profileScope?: string) {
  const params = new URLSearchParams({ requested_by: requestedBy })
  const profileId = profileScopeToApiProfileId(profileScope)
  if (profileId) params.set('profile_id', profileId)
  return readJson<ScanControlPayload>(`/api/v3/scans/control/pause?${params.toString()}`, {
    method: 'POST',
  })
}

export function resumeScans(requestedBy = 'interface', profileScope?: string) {
  const params = new URLSearchParams({ requested_by: requestedBy })
  const profileId = profileScopeToApiProfileId(profileScope)
  if (profileId) params.set('profile_id', profileId)
  return readJson<ScanControlPayload>(`/api/v3/scans/control/resume?${params.toString()}`, {
    method: 'POST',
  })
}

export function stopScans(requestedBy = 'interface', profileScope?: string) {
  const params = new URLSearchParams({ requested_by: requestedBy })
  const profileId = profileScopeToApiProfileId(profileScope)
  if (profileId) params.set('profile_id', profileId)
  return readJson<ScanControlPayload>(`/api/v3/scans/control/stop?${params.toString()}`, {
    method: 'POST',
  })
}

export function stopAllScans(requestedBy = 'interface', profileScope?: string) {
  const params = new URLSearchParams({ requested_by: requestedBy })
  const profileId = profileScopeToApiProfileId(profileScope)
  if (profileId) params.set('profile_id', profileId)
  return readJson<ScanControlPayload & { affected_run_ids?: string[] }>(`/api/v3/scans/control/stop-all?${params.toString()}`, {
    method: 'POST',
  })
}

export function forceStopAllScans(requestedBy = 'interface', profileScope?: string) {
  const params = new URLSearchParams({ requested_by: requestedBy })
  const profileId = profileScopeToApiProfileId(profileScope)
  if (profileId) params.set('profile_id', profileId)
  return readJson<ScanControlPayload & { affected_run_ids?: string[]; aborted?: boolean }>(`/api/v3/scans/control/force-stop-all?${params.toString()}`, {
    method: 'POST',
  })
}

export function triggerScanNow(profileScope?: string) {
  const params = new URLSearchParams()
  const profileId = profileScopeToApiProfileId(profileScope)
  if (profileId) params.set('profile_id', profileId)
  return readJson<ScanControlPayload & { trigger?: JsonRecord }>(`${apiRoutes.scansTrigger()}${params.size ? `?${params.toString()}` : ''}`, {
    method: 'POST',
  })
}

export function updateRuntimeSettings(payload: RuntimeSettingsPayload) {
  const { profile_id, settings: nestedSettings, resolved_config_hash: _resolvedConfigHash, ...rest } = payload
  const params = new URLSearchParams()
  if (profile_id) params.set('profile_id', String(profile_id))
  const source = nestedSettings ?? rest
  const settings = Object.fromEntries(
    Object.entries(source)
      .filter(([, value]) => value !== undefined)
      .map(([key, value]) => [
        key,
        Array.isArray(value) ? value.join(',') : String(value),
      ]),
  )
  return readJson<{ ok?: boolean; settings?: Record<string, string> }>(`/api/v3/settings${params.size ? `?${params.toString()}` : ''}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings),
  })
}

export function fetchStorageStatus(profileScope?: string) {
  const params = new URLSearchParams()
  const profileId = profileScopeToApiProfileId(profileScope)
  if (profileId) params.set('profile_id', profileId)
  return readJson<StorageStatusPayload>(`/api/v3/storage/status${params.size ? `?${params.toString()}` : ''}`)
}

export function exportStorage(store: 'postgres', profileScope?: string) {
  const params = new URLSearchParams({ store })
  const profileId = profileScopeToApiProfileId(profileScope)
  if (profileId) params.set('profile_id', profileId)
  return readJson<StorageExportPayload>(`/api/v3/storage/export?${params.toString()}`, {
    method: 'POST',
  })
}

export function importStorage(store: 'postgres', payload: JsonRecord, dryRun = false, confirmPhrase?: string) {
  const params = new URLSearchParams({ store, dry_run: String(dryRun) })
  if (confirmPhrase) params.set('confirm_phrase', confirmPhrase)
  return readJson<StorageMutationSummary>(`/api/v3/storage/import?${params.toString()}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function seedStorage(store: 'postgres', mode: 'seed' | 'all' | 'real', confirmPhrase?: string) {
  const params = new URLSearchParams({ store, mode })
  if (confirmPhrase) params.set('confirm_phrase', confirmPhrase)
  return readJson<StorageMutationSummary>(`/api/v3/storage/seed?${params.toString()}`, {
    method: 'POST',
  })
}

export function clearStorage(store: 'postgres', keepSettings = false, profileScope?: string, confirmPhrase?: string) {
  const params = new URLSearchParams({ store, keep_settings: String(keepSettings) })
  if (confirmPhrase) params.set('confirm_phrase', confirmPhrase)
  const profileId = profileScopeToApiProfileId(profileScope)
  if (profileId) params.set('profile_id', profileId)
  return readJson<StorageMutationSummary>(`/api/v3/storage/clear?${params.toString()}`, {
    method: 'POST',
  })
}

export function clearStorageComponents(store: 'postgres', components: string[], profileScope?: string, confirmPhrase?: string) {
  const params = new URLSearchParams({ store })
  if (confirmPhrase) params.set('confirm_phrase', confirmPhrase)
  const profileId = profileScopeToApiProfileId(profileScope)
  if (profileId) params.set('profile_id', profileId)
  return readJson<StorageMutationSummary>(`/api/v3/storage/clear-components?${params.toString()}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ components }),
  })
}

export function clearStorageGroup(store: 'postgres', groupId: string, profileScope?: string, confirmPhrase?: string) {
  const params = new URLSearchParams({ store, group_id: groupId })
  if (confirmPhrase) params.set('confirm_phrase', confirmPhrase)
  const profileId = profileScopeToApiProfileId(profileScope)
  if (profileId) params.set('profile_id', profileId)
  return readJson<StorageMutationSummary>(`/api/v3/storage/clear-group?${params.toString()}`, {
    method: 'POST',
  })
}

export function fetchStorageTrash() {
  return readJson<StorageTrashEntry[]>('/api/v3/storage/trash')
}

export function deleteStorageTrashEntry(trashId: string, confirmPhrase: string) {
  const params = new URLSearchParams({ confirm_phrase: confirmPhrase })
  return readJson<{ trash_id?: string; deleted_forever?: boolean }>(`/api/v3/storage/trash/${encodeURIComponent(trashId)}?${params.toString()}`, {
    method: 'DELETE',
  })
}

export function fetchMarketAnalysis(symbol: string, interval: string, mode: string) {
  const params = new URLSearchParams({ symbol, interval, mode })
  return readJson<AnalysisPayload>(`${apiRoutes.analyze()}?${params.toString()}`)
}

export function fetchKlines(symbol: string, interval: string, limit = 120) {
  const params = new URLSearchParams({
    symbol,
    interval,
    limit: String(limit),
  })
  return readJson<JsonRecord[]>(`${apiRoutes.klines()}?${params.toString()}`)
}

export function fetchV5Overview() {
  return readJson<{
    ok: boolean
    active_model_version: string | null
    active_action_version: string | null
    shadow_mode_enabled: boolean
    dataset_size: number
    memory_count: number
    last_training: string
    last_promotion: string | null
  }>('/api/v3/v5/overview')
}

export function fetchV5Models() {
  return readJson<{ ok: boolean; models: any[] }>('/api/v3/v5/models')
}

export function fetchV5Memory() {
  return readJson<{
    ok: boolean
    memory_row_count: number
    embedding_coverage: string
    retrieval_health: string
    oldest_record: string | null
    newest_record: string | null
  }>('/api/v3/v5/memory')
}

export function fetchV5Comparison() {
  return readJson<{ ok: boolean; report: any; is_meaningful: boolean; v5_outperforms: boolean }>('/api/v3/v5/comparison')
}

export function fetchV5Readiness() {
  return readJson<{ ok: boolean; readiness_state: string }>('/api/v3/v5/readiness')
}

export function promoteV5() {
  return readJson<{ ok: boolean; success?: boolean }>('/api/v3/v5/promote', { method: 'POST' })
}

export function rollbackV5() {
  return readJson<{ ok: boolean; success?: boolean }>('/api/v3/v5/rollback', { method: 'POST' })
}

export function fetchV5GateReport() {
  return readJson<{
    ok: boolean
    metrics: {
      suppression_rate: number
      suppression_accuracy: number
      rescue_rate: number
      rescue_accuracy: number
      trade_frequency_delta: number
      calibration_error: number
    }
  }>('/api/v3/v5/gate-report')
}

export function fetchV5GateCalibration() {
  return readJson<{ ok: boolean; buckets: any[] }>('/api/v3/v5/gate-calibration')
}
