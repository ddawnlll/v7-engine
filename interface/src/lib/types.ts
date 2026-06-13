export type JsonRecord = Record<string, unknown>

export type LatencyPercentiles = {
  p50_ms?: number
  p95_ms?: number
  p99_ms?: number
}

export type JobQueueDepthByType = {
  ingest_market_snapshot?: number
  analyze_symbol_interval_mode?: number
  persist_signal_artifact?: number
  run_simulation_batch?: number
  refresh_metrics?: number
}

export type ExchangeMetrics = {
  request_count?: number
  failure_count?: number
  failure_rate_pct?: number
  latency?: LatencyPercentiles
  degraded_snapshot_count?: number
}

export type PersistenceMetrics = {
  postgres_latency?: LatencyPercentiles
  mongo_latency?: LatencyPercentiles
}

export type IngestionMetrics = {
  active_snapshot_count?: number
  stale_snapshot_count?: number
  lag_p95_ms?: number
  lag_max_ms?: number
}

export type MultiplierBucket = {
  label?: string
  count?: number
}

export type AdaptiveLearningMetrics = {
  active_scope_count?: number
  eligible_scope_count?: number
  scope_coverage_pct?: number
  stale_scope_count?: number
  degraded_scope_count?: number
  multiplier_distribution?: MultiplierBucket[]
}

export type CalibrationScopeRow = {
  regime?: string
  mode?: string
  total?: number
  labeled?: number
  open?: number
  avg_win_r?: number | null
  avg_loss_r?: number | null
  avg_realized_r?: number | null
  ready_for_calibration?: boolean
  remaining_to_threshold?: number
}

export type CalibrationStatusPayload = {
  ok?: boolean
  summary?: {
    total_signals?: number
    total_labeled?: number
    calibration_threshold?: number
    ready_scope_count?: number
    top_scope?: CalibrationScopeRow | null
  }
  scopes?: CalibrationScopeRow[]
}

export type PaperAccountPayload = {
  profile_id?: string
  resolved_config_hash?: string | null
  account?: JsonRecord
  balance?: number
  default_balance?: number
  portfolio?: JsonRecord
  reconciliation?: JsonRecord
}

export type RuntimeReadinessPayload = {
  active_engine?: string | null
  active_engine_version?: string | null
  champion_version?: string | null
  fallback_active?: boolean
  fallback_reason?: string | null
  shadow_status?: {
    enabled?: boolean
    active?: boolean
    selected_engine?: string | null
    engine_name?: string | null
    engine_version?: string | null
  }
  runtime_state?: 'ready' | 'degraded' | string | null
  runtime_ready?: boolean
  healthy?: boolean
  consecutive_failures?: number
}

export type EngineHealthPayload = {
  status?: string
  uptime_seconds?: number
  db_status?: string
  db_connected?: boolean
  exchange_status?: string
  runtime_status?: string
  degraded_reason?: string | null
  last_error?: JsonRecord | null
  runtime_readiness?: RuntimeReadinessPayload
  profile?: JsonRecord | null
  stream?: JsonRecord | null
  reconciliation?: JsonRecord | null
  queue_depth?: number
  active_workers?: number
  worker_capacity?: number
  worker_utilization_pct?: number
  last_scan_completed_at_utc?: string
  next_scan_at_utc?: string
  last_calibration_run_at_utc?: string
  next_calibration_run_at_utc?: string
  open_orders?: number
  scan_cycle_latency_ms?: LatencyPercentiles
  analysis_latency_ms_per_symbol?: LatencyPercentiles
  queue_depth_by_job_type?: JobQueueDepthByType
  exchange_metrics?: ExchangeMetrics
  persistence_metrics?: PersistenceMetrics
  ingestion_metrics?: IngestionMetrics
  adaptive_learning_metrics?: AdaptiveLearningMetrics
  calibration_summary?: CalibrationStatusPayload['summary']
  scan_control?: ScanControlState | null
  symbol_throttle?: {
    enabled?: boolean
    total_symbols?: number
    total_throttled?: number
    seeded_symbols?: string[]
    rules?: JsonRecord
    throttled_symbols?: Array<{
      symbol?: string
      throttled?: boolean
      reason?: string
      active_rules?: string[]
      cooldown_until_utc?: string | null
      cooldown_remaining_minutes?: number | null
      stop_hit_rate_pct?: number
      consecutive_stop_hits?: number
      microstructure?: JsonRecord
    }>
  }
  self_learning?: {
    active_model_version?: string | null
    status?: string | null
    rollout_stage?: string | null
  }
  analyzer?: {
    active_engine?: string | null
    active_engine_version?: string | null
    request_schema_version?: string | null
    response_schema_version?: string | null
    fallback_count?: number
    last_fallback_reason?: string | null
    last_engine_error?: string | null
  }
  alert_summary?: {
    total_active?: number
    critical?: number
    warning?: number
    info?: number
    items?: OperatorAlertRow[]
  }
}

export type RuntimeProfileReadOnlyExposurePayload = {
  profile?: JsonRecord | null
  health?: JsonRecord | null
  sync?: JsonRecord | null
  stream?: JsonRecord | null
  reconciliation?: JsonRecord | null
  account?: JsonRecord | null
  balances?: JsonRecord[]
  positions?: JsonRecord[]
  open_orders?: JsonRecord[]
  protective_summary?: JsonRecord | null
}

export type RuntimeProfileSettingPreset = {
  preset_id?: string
  label?: string
  description?: string | null
  capabilities?: Record<string, boolean>
  runtime_settings?: Record<string, string>
  risk_settings?: Record<string, string>
}

export type RuntimeProfileSettingsPayload = {
  profile_id?: string
  capabilities?: Record<string, boolean>
  runtime_settings?: Record<string, string>
  risk_settings?: Record<string, string>
  auto_live?: JsonRecord | null
  resolved_config_hash?: string | null
  preset_profiles?: RuntimeProfileSettingPreset[]
}

export type RuntimeProfileSettingsUpdatePayload = {
  profile_id?: string
  capabilities?: Record<string, boolean>
  runtime_settings?: Record<string, string | number | boolean>
  risk_settings?: Record<string, string | number | boolean>
}

export type RuntimeProfileSummary = {
  profile_id?: string
  name?: string | null
  status?: string | null
  runtime_mode?: string | null
  execution_mode?: string | null
  venue?: string | null
  read_only?: boolean
  supports_account_reads?: boolean
  supports_order_placement?: boolean
}

export type RuntimeProfileListPayload = {
  items?: RuntimeProfileSummary[]
  count?: number
}

export type OperatorAlertRow = {
  id?: number
  alert_id?: string
  severity?: string
  kind?: string
  scope?: string
  message?: string
  active?: boolean
  payload?: JsonRecord
  detected_at_utc?: string
}

export type OperatorAlertsPayload = {
  items?: OperatorAlertRow[]
}

export type LogEntry = {
  severity?: string
  category?: string
  reason_code?: string | null
  symbol?: string | null
  message?: string
  timestamp_utc?: string
}

export type LogsPayload = {
  items?: LogEntry[]
}

export type DecisionEventRecord = JsonRecord & {
  identity?: JsonRecord & { decision_event_id?: string; request_id?: string; run_id?: string; timestamp_utc?: string }
  lineage?: JsonRecord & { engine_name?: string; engine_version?: string }
  scope?: JsonRecord & { symbol?: string; interval?: string; mode?: string }
  request_summary?: JsonRecord & { regime_label?: string }
  decision_summary?: JsonRecord & {
    signal_status?: string
    decision_status?: string
    is_actionable?: boolean
    recommended_action?: string
    direction?: string
    confidence?: number
  }
  runtime_interpretation?: JsonRecord & {
    fallback_used?: boolean
    deterministic_alignment?: string
    deterministic_block?: boolean
    degraded_reason?: string
  }
}

export type DecisionEventListPayload = {
  items?: DecisionEventRecord[]
  count?: number
  limit?: number
}

export type DecisionEventDetailPayload = DecisionEventRecord

export type TradeOutcomeRecord = JsonRecord & {
  identity?: JsonRecord & { trade_outcome_id?: string; decision_event_id?: string; timestamp_utc?: string }
  resolution_status?: JsonRecord & { outcome_status?: string; is_final?: boolean }
  realized_outcome?: JsonRecord & { realized_r?: number | null; realized_return?: number | null }
  quality_interpretation?: JsonRecord & { outcome_label?: string; is_good_decision?: boolean | null }
}

export type TradeOutcomeListPayload = {
  items?: TradeOutcomeRecord[]
  count?: number
  limit?: number
}

export type EngineBehaviorPayload = {
  total_events?: number
  fallback_rate?: number
  timeout_rate?: number
  block_rate?: number
  counts?: JsonRecord
  decision_events?: DecisionEventRecord[]
  evaluation?: {
    expectancy?: JsonRecord
    regimes?: { rows?: JsonRecord[] }
  }
}

export type ShadowComparisonPayload = {
  pair_count?: number
  agreement_rate?: number
  divergence_rate?: number
  directional_flip_rate?: number
  pairs?: JsonRecord[]
}

export type ModelArtifactPayload = JsonRecord & {
  model_artifact_version?: string
  engine_name?: string
  engine_version?: string
  role?: string
  dataset_version?: string
  feature_schema_version?: string
  snapshot_builder_version?: string
  training_timestamp_utc?: string
  validation_passed?: boolean
}

export type RegistryChampionPayload = {
  champion?: ModelArtifactPayload | null
  shadow_engine?: string | null
  active_engine?: string | null
  available_engines?: JsonRecord[]
  shadow_engine_selector?: {
    supported?: boolean
    selected_engine?: string | null
    active_engine?: string | null
    available_engines?: JsonRecord[]
  }
}

export type RegistryCandidatesPayload = {
  items?: ModelArtifactPayload[]
  count?: number
  comparisons?: Array<JsonRecord & {
    model_artifact_version?: string
    engine_name?: string
    engine_version?: string
    dataset_version?: string
    training_timestamp_utc?: string
    validation_passed?: boolean
    role?: string
    comparison_to_champion?: {
      champion_model_artifact_version?: string | null
      same_engine_family?: boolean
      same_engine_version?: boolean
      same_dataset_version?: boolean
    }
  }>
}

export type RegistryModelSummaryPayload = ModelArtifactPayload & {
  metrics?: {
    win_rate?: number
    expectancy_r?: number
    sample_size?: number
  }
  promotion_readiness?: JsonRecord & {
    active_eligible?: boolean
    blocking_reasons?: string[]
    classification?: string
    status?: string
  }
  release_eligibility?: JsonRecord & {
    is_release_eligible?: boolean
    is_active_eligible?: boolean
    blocking_reasons?: string[]
    classification?: string
  }
  verification?: JsonRecord & {
    verification_passed?: boolean
    blocking_reasons?: string[]
  }
  comparison_to_champion?: {
    champion_model_artifact_version?: string | null
    same_engine_family?: boolean
    same_engine_version?: boolean
    same_dataset_version?: boolean
    win_rate_delta?: number
    expectancy_r_delta?: number
  }
}

export type RegistryModelsPayload = {
  ok?: boolean
  count?: number
  champion?: ModelArtifactPayload | null
  items?: RegistryModelSummaryPayload[]
}

export type TradeOverviewPayload = {
  engine?: JsonRecord
  summary?: {
    refresh_seconds?: number
    open_trade_count?: number
    last_scan_status?: string
    last_outcome_summary?: JsonRecord | null
  }
}

export type ReviewLearningPayload = {
  training_runs?: JsonRecord[]
  dataset_versions?: JsonRecord[]
  walk_forward_fold_results?: JsonRecord[]
  holdout_summaries?: JsonRecord[]
  calibration_drift?: JsonRecord[]
  candidate_comparisons?: JsonRecord[]
  registry_events?: JsonRecord[]
  prepare_promotion_evidence_route?: string
}

export type RuntimeMetricsPayload = {
  fallback_rate_1h?: number
  fallback_rate_24h?: number
  timeout_rate_24h?: number
  hard_block_rate_24h?: number
  divergence_rate_24h?: number
  shadow_pair_count_24h?: number
  champion_model_age_days?: number | null
  champion_model_artifact_version?: string | null
  pending_outcome_count?: number
  resolved_outcome_count?: number
}

export type TraceSnapshotPayload = {
  items?: JsonRecord[]
  count?: number
  summary?: Record<string, number>
}

export type DashboardPayload = {
  generated_at?: string
  legacy_api_base?: string
  engine?: JsonRecord
  engine_health?: JsonRecord
  job_queue?: {
    pending?: number
    running?: number
    completed?: number
    failed?: number
    items?: JsonRecord[]
  }
  settings?: Record<string, string>
  performance?: {
    summary?: JsonRecord
    breakdown?: Record<string, Record<string, JsonRecord>>
  }
  orders?: {
    open_orders?: JsonRecord[]
    closed_orders?: JsonRecord[]
  }
  trace_logs?: {
    items?: JsonRecord[]
  }
  portfolio?: {
    summary?: JsonRecord
    portfolio?: JsonRecord
    avg_hold_minutes?: number
    daily?: JsonRecord[]
    recent_closed?: JsonRecord[]
    open_positions?: JsonRecord[]
    engine?: JsonRecord
    equity_curve?: JsonRecord[]
  }
  market?: {
    items?: JsonRecord[]
    top_movers?: JsonRecord[]
  }
  simulations?: {
    summary?: {
      recent_runs?: JsonRecord[]
      count?: number
    }
    runs?: JsonRecord[]
  }
  highlights?: {
    top_movers?: JsonRecord[]
    recent_events?: JsonRecord[]
    recent_simulations?: JsonRecord[]
  }
  symbols?: {
    symbols?: string[]
    intervals?: string[]
  }
  alerts?: OperatorAlertsPayload
}

export type SimulationRun = JsonRecord & {
  id?: number
  name?: string
  status?: string
  requested_by?: string
  created_at?: string
  started_at?: string
  finished_at?: string
  parameters?: JsonRecord
  metrics?: JsonRecord
}

export type SimulationResult = JsonRecord & {
  id?: number
  run_id?: number
  symbol?: string
  interval?: string
  mode?: string
  direction?: string
  confidence?: number
  outcome?: string
  realized_r?: number
  details?: JsonRecord
  created_at?: string
}

export type SimulationRunDetail = {
  ok?: boolean
  run?: SimulationRun
  results?: SimulationResult[]
}

export type SimulationRunsPayload = {
  ok?: boolean
  summary?: {
    recent_runs?: SimulationRun[]
    count?: number
    by_status?: Record<string, number>
  }
  runs?: SimulationRun[]
}

export type SimulationEvent = JsonRecord & {
  type?: string
  timestamp?: string
  run_id?: number
  status?: string
  run?: SimulationRun
  results?: SimulationResult[]
  metrics?: JsonRecord
  inserted?: number
  error?: string
}

export type SimulationDecisionTrace = JsonRecord & {
  id?: number
  simulation_run_id?: number
  trace_id?: string
  symbol?: string
  interval?: string
  mode?: string
  timestamp?: string
  direction?: string | null
  confidence?: number | null
  signal_status?: string | null
  selected_action?: string | null
  selected_head?: string | null
  runtime_filter_reason?: string | null
  no_trade_reason?: string | null
  skip_family?: string | null
  fallback_used?: boolean
  fallback_reason?: string | null
  analysis_error?: string | null
  data_error?: string | null
  insufficient_history?: boolean
  entry_price?: number | null
  stop_loss?: number | null
  take_profit?: number | null
  summary?: string | null
  analyzer_metadata?: JsonRecord
  runtime_context?: JsonRecord
  snapshot_metadata?: JsonRecord
  created_at?: string
}

export type SimulationDecisionTraceResponse = {
  ok?: boolean
  run_id?: number
  items?: SimulationDecisionTrace[]
  count?: number
  total?: number
  next_cursor?: number | null
  has_more?: boolean
}

export type SimulationDecisionTraceSummary = {
  ok?: boolean
  run_id?: number
  trace_count?: number
  fallback_count?: number
  by_reason?: Record<string, number>
  by_direction?: Record<string, number>
  by_signal_status?: Record<string, number>
  avg_confidence?: number | null
}

export type SimulationTraceCoverage = {
  has_traces?: boolean
  trace_count?: number
  expected_decision_count?: number | null
  coverage_status?: 'full' | 'partial' | 'missing' | 'unknown' | string
}

export type SimulationConfidenceBucket = {
  bucket_start?: number
  bucket_end?: number
  count?: number
  threshold_in_bucket?: boolean
  buy_count?: number
  sell_count?: number
  no_trade_count?: number
  low_confidence_count?: number
}

export type SimulationHealth = {
  status?: 'GOOD' | 'WARNING' | 'BAD' | 'UNKNOWN' | string
  score?: number | null
  reasons?: string[]
  recommended_actions?: string[]
}

export type SimulationDiagnosticsResponse = {
  ok?: boolean
  run_id?: number
  has_traces?: boolean
  run_status?: string
  trace_coverage?: SimulationTraceCoverage
  decision_distribution?: Record<string, number>
  confidence_summary?: JsonRecord & {
    avg_confidence?: number | null
    median_confidence?: number | null
    p10_confidence?: number | null
    p90_confidence?: number | null
    below_threshold_count?: number
    above_threshold_count?: number
    threshold?: number
  }
  confidence_histogram?: SimulationConfidenceBucket[]
  directional_but_filtered?: JsonRecord & {
    directional_buy_filtered?: number
    directional_sell_filtered?: number
    directional_total_filtered?: number
  }
  directional_filtered_counts?: JsonRecord
  top_blockers?: Array<JsonRecord & { reason?: string; count?: number; percentage?: number; affected_symbols?: string[]; affected_intervals?: string[]; affected_modes?: string[] }>
  per_symbol_summary?: Array<JsonRecord & { symbol?: string; decision_count?: number; buy_count?: number; sell_count?: number; no_trade_count?: number; low_confidence_count?: number; fallback_count?: number; data_error_count?: number; executed_trade_count?: number; total_pnl?: number }>
  per_symbol?: SimulationDiagnosticsResponse['per_symbol_summary']
  per_mode_summary?: Array<JsonRecord & { mode?: string; decision_count?: number; executed_trade_count?: number; filtered_count?: number; avg_confidence?: number | null; fallback_rate?: number; total_pnl?: number }>
  per_mode?: SimulationDiagnosticsResponse['per_mode_summary']
  health?: SimulationHealth
  meta?: JsonRecord
}

export type SimulationConfidenceHistogramResponse = {
  ok?: boolean
  run_id?: number
  has_traces?: boolean
  threshold?: number
  bucket_size?: number
  items?: SimulationConfidenceBucket[]
}

export type SimulationWhatIfResponse = {
  ok?: boolean
  run_id?: number
  available?: boolean
  reason?: string
  estimate_type?: string
  current_min_confidence?: number
  hypothetical_min_confidence?: number
  current_actionable_count?: number
  hypothetical_actionable_count?: number
  additional_directional_candidates?: number
  newly_included_symbols?: string[]
  newly_included_modes?: string[]
  fee_slippage_sensitivity?: JsonRecord
  max_hold_sensitivity?: JsonRecord
  risk_per_trade_estimate?: JsonRecord
}

export type SimulationPreset = {
  id?: number
  name: string
  description?: string | null
  profile_id?: string | null
  symbols: string[]
  intervals: string[]
  modes: string[]
  period_start?: string | null
  period_end?: string | null
  capital?: number | null
  execution_settings?: JsonRecord
  created_by?: string | null
  updated_by?: string | null
  created_at?: string
  updated_at?: string
  is_shared?: boolean
  tags?: string[]
}

export type SimulationPresetListResponse = {
  ok?: boolean
  presets?: SimulationPreset[]
}

export type SimulationPresetMutationResponse = {
  ok?: boolean
  preset?: SimulationPreset
  deleted?: boolean
  preset_id?: number
}

export type SimulationParityReport = {
  ok?: boolean
  run_id?: number
  available?: boolean
  reason?: string
  compared_decision_count?: number
  direction_match_pct?: number | null
  actionability_match_pct?: number | null
  confidence_delta_avg?: number | null
  fallback_rate_delta?: number | null
  no_trade_reason_match_pct?: number | null
  missing_scan_context_count?: number
  missing_sim_context_count?: number
  mismatches?: JsonRecord[]
}

export type PerformanceTimingSummary = {
  count?: number
  avg_ms?: number | null
  min_ms?: number | null
  max_ms?: number | null
  p50_ms?: number | null
  p95_ms?: number | null
  p99_ms?: number | null
  total_ms?: number | null
}

export type PerformanceComponentRow = {
  component_id?: string
  label?: string
  group?: string
  count?: number
  avg_ms?: number | null
  min_ms?: number | null
  max_ms?: number | null
  p50_ms?: number | null
  p95_ms?: number | null
  p99_ms?: number | null
  total_ms?: number | null
}

export type PerformanceDbSummary = {
  query_count?: number
  write_count?: number
  rows_written?: number
  commit_count?: number | null
  rollback_count?: number | null
  connection_wait_avg_ms?: number | null
  total_read_ms?: number | null
  total_write_ms?: number | null
  families?: Record<string, PerformanceTimingSummary>
}

export type PerformanceCacheSummary = {
  market_bundle?: JsonRecord
  htf_trend?: JsonRecord
  self_learning?: JsonRecord
}

export type PerformanceConcurrencySummary = {
  scan_workers?: number
  fetch_worker_capacity?: number
  analysis_worker_capacity?: number
  max_concurrent_fetches?: number
  avg_concurrent_fetches?: number | null
  queue_wait_avg_ms?: number | null
  db_connection_wait_avg_ms?: number | null
  completed_tasks?: number
  remaining_tasks?: number
  analysis_serialized?: boolean
}

export type PerformanceRecentScanRow = {
  run_id?: string
  status?: string
  requested_by?: string
  duration_ms?: number | null
  analysis_avg_ms?: number | null
  analysis_min_ms?: number | null
  analysis_max_ms?: number | null
  analysis_count?: number
  market_fetch_avg_ms?: number | null
  market_fetch_min_ms?: number | null
  market_fetch_max_ms?: number | null
  market_fetch_count?: number
  completed_tasks?: number
  total_tasks?: number
  created_orders?: number
  started_at_utc?: string
  finished_at_utc?: string | null
  composition?: JsonRecord
  component_breakdown?: PerformanceComponentRow[]
  top_components?: PerformanceComponentRow[]
  db?: PerformanceDbSummary
  caches?: PerformanceCacheSummary
  concurrency?: PerformanceConcurrencySummary
  scope?: JsonRecord
  debug?: JsonRecord
  stages?: JsonRecord
}

export type PerformanceAnalytics = {
  scan_runs?: PerformanceTimingSummary
  analysis?: PerformanceTimingSummary
  market_fetch?: PerformanceTimingSummary
  status_counts?: Record<string, number>
  recent_scans?: PerformanceRecentScanRow[]
  component_breakdown?: PerformanceComponentRow[]
  slow_components?: PerformanceComponentRow[]
  db?: PerformanceDbSummary
  caches?: PerformanceCacheSummary
  concurrency?: PerformanceConcurrencySummary
}

export type PerformancePayload = {
  ok?: boolean
  snapshot?: JsonRecord
  history?: JsonRecord[]
  analytics?: PerformanceAnalytics
}

export type CreateSimulationPayload = {
  name?: string
  requested_by?: string
  period_start: string
  period_end: string
  symbols: string[]
  intervals: string[]
  modes: string[]
  capital: number
  risk_per_trade_pct?: number
  max_hold_bars?: number | null
  min_confidence?: number | null
  scan_step_bars?: number
  scan_workers?: number
  time_forward_step_bars?: number
  simulation_profile_id?: string | null
  simulation_profile?: JsonRecord
  execution_settings?: JsonRecord
}

export type QueueScanPayload = {
  symbols: string[]
  intervals: string[]
  modes: string[]
  scan_workers: number
  profile_id?: string
}

export type RuntimeSettingsPayload = {
  profile_id?: string
  resolved_config_hash?: string | null
  settings?: Record<string, string>
} & Record<string, string | string[] | boolean | Record<string, string> | null | undefined>

export type RuntimeSettingOption = {
  value: string
  label: string
  description?: string | null
}

export type RuntimeSettingControl = {
  key: string
  label: string
  description?: string | null
  group: string
  control: 'boolean' | 'enum' | 'multi_enum' | 'number' | 'readonly' | string
  min_value?: number | null
  max_value?: number | null
  step?: number | null
  unit?: string | null
  options?: RuntimeSettingOption[]
}

export type RuntimeSettingsMetadataPayload = {
  profile_id?: string
  controls?: RuntimeSettingControl[]
  catalogs?: Record<string, string[]>
}

export type FailureRecord = {
  id?: number
  order_id?: string
  signal_id?: string | null
  symbol?: string | null
  interval?: string | null
  mode?: string | null
  realized_r?: number | null
  failure_source?: string
  blamed_component?: string
  severity_score?: number
  confidence?: number
  classification?: string
  explanation?: string
  improvement?: string
  created_at_utc?: string
}

export type FailureAnalyticsSummary = {
  total_losses_analyzed?: number
  total_losses?: number
  avg_realized_r?: number
  top_failure_source?: string | null
  top_failure_source_count?: number
  top_blamed_component?: string | null
  top_blamed_component_count?: number
}

export type FailureBreakdownRow = {
  label?: string
  count?: number
  percent?: number
}

export type FailureMatrixPayload = {
  sources?: string[]
  components?: string[]
  cells?: Record<string, Record<string, number>>
}

export type FailureSeverityRow = {
  severity?: number
  count?: number
  percent?: number
}

export type FailureSeverityDistribution = {
  items?: FailureSeverityRow[]
  avg_severity?: number
  avg_confidence?: number
}

export type FailureImprovementRow = {
  failure_source?: string
  blamed_component?: string
  weight_score?: number
  count?: number
  avg_severity?: number
  avg_confidence?: number
  improvement?: string
}

export type FailureAnalyticsMeta = {
  generated_at?: string
  has_meaningful_heatmap?: boolean
  all_filtered_out_by_confidence?: boolean
}

export type FailureAnalyticsPayload = {
  ok?: boolean
  filters?: {
    lookback_days?: number
    mode?: string | null
    min_confidence?: number
  }
  summary?: FailureAnalyticsSummary
  source_breakdown?: FailureBreakdownRow[]
  component_breakdown?: FailureBreakdownRow[]
  source_component_matrix?: FailureMatrixPayload
  severity_distribution?: FailureSeverityDistribution
  ranked_improvements?: FailureImprovementRow[]
  recent_failures?: FailureRecord[]
  meta?: FailureAnalyticsMeta
}

export type CircuitBreakerState = {
  status?: 'OPEN' | 'CLOSED' | 'DEGRADED' | string
  reason?: string
  triggered_at?: string
  auto_resume_at?: string | null
  failure_rate?: number
  consecutive_losses?: number
  active_rules?: string[]
  degraded_multiplier?: number
  lookback_window?: number
  enabled?: boolean
  manual_mode?: 'AUTO' | 'FORCE_OPEN' | 'FORCE_CLOSED' | string
  is_manual_override?: boolean
  session_breakdown?: Record<string, number>
  time_of_day_breakdown?: Record<string, number>
}

export type CircuitBreakerEvent = {
  id?: number
  status?: string
  reason?: string
  failure_rate?: number
  consecutive_losses?: number
  triggered_at_utc?: string
  resolved_at_utc?: string | null
  auto_resume_at_utc?: string | null
  active_rules?: string[]
}

export type CircuitBreakerStatePayload = {
  ok?: boolean
  state?: CircuitBreakerState
}

export type CircuitBreakerEventsPayload = {
  ok?: boolean
  items?: CircuitBreakerEvent[]
}

export type LearningCalibrationBucket = {
  label?: string
  sample_size?: number
  avg_predicted_confidence?: number
  realized_win_rate?: number
  multiplier?: number
}

export type LearningPenaltyRow = {
  label?: string
  kind?: string
  component?: string
  penalty?: number
  count?: number
  avg_severity?: number
  avg_confidence?: number
  top_failure_source?: string | null
}

export type LearningProfile = {
  generated_at?: string
  lookback_days?: number
  min_confidence?: number
  status?: string
  samples?: {
    total_closed_trades?: number
    analyzed_losses?: number
    minimum_closed_trades?: number
    minimum_failures?: number
    learning_enabled?: boolean
  }
  confidence_calibration?: {
    active?: boolean
    buckets?: LearningCalibrationBucket[]
  }
  entry_penalties?: {
    active?: boolean
    global_penalty?: number
    early_entry_failure_rate?: number
    avg_confidence?: number
    significance_score?: number
  }
  stop_loss_adjustments?: {
    active?: boolean
    base_multiplier?: number
    min_multiplier?: number
    max_multiplier?: number
    stop_loss_failure_rate?: number
    avg_failure_severity?: number
    avg_confidence?: number
    expanding_volatility_bonus?: number
  }
  regime_stability?: {
    active?: boolean
    label?: string
    damping_multiplier?: number
    dominant_regime?: string | null
    dominant_regime_share?: number
    unique_regimes?: number
    counts?: Record<string, number>
  }
  component_penalties?: {
    active?: boolean
    items?: LearningPenaltyRow[]
  }
  hard_rejection_rules?: {
    active?: boolean
    dominant_cluster_ratio?: number
    reject_if_entry_risk_gte?: number
    reject_if_confidence_lte?: number
  }
  active_adjustments?: {
    learning_active?: boolean
    confidence_calibration?: boolean
    entry_penalty?: boolean
    stop_loss_adjustment?: boolean
    component_penalties?: boolean
    hard_rejection?: boolean
    regime_stability?: boolean
  }
  top_penalties?: LearningPenaltyRow[]
}

export type LearningProfilePayload = {
  ok?: boolean
  active?: boolean
  sample_size?: number
  top_penalties?: LearningPenaltyRow[]
  calibration_data?: LearningCalibrationBucket[]
  effectiveness_summary?: LearningEffectivenessReport
  profile?: LearningProfile
}

export type LearningEffectivenessRow = {
  adjustment_id?: string
  label?: string
  status?: 'IMPROVING' | 'NEUTRAL' | 'DEGRADING' | 'INSUFFICIENT_DATA' | string
  trades_before?: number
  trades_after?: number
  win_rate_before?: number
  win_rate_after?: number
  avg_r_before?: number
  avg_r_after?: number
  loss_severity_before?: number
  loss_severity_after?: number
  applied_since?: string | null
  confidence?: number
  status_reason?: string
}

export type LearningEffectivenessReport = {
  generated_at?: string
  lookback_days?: number
  min_samples?: number
  overall_health_score?: number
  total_trades_before?: number
  total_trades_after?: number
  total_closed_trades?: number
  status_counts?: Record<string, number>
  health_score?: number
  adjustments?: LearningEffectivenessRow[]
  flagged_adjustments?: Array<{
    adjustment_id?: string
    reason?: string
    recommendation?: string
  }>
}

export type LearningEffectivenessPayload = {
  ok?: boolean
  report?: LearningEffectivenessReport
}

export type FailureListPayload = {
  ok?: boolean
  count?: number
  total?: number
  limit?: number
  offset?: number
  items?: FailureRecord[]
}

export type FailureSummaryPayload = {
  ok?: boolean
  summary?: {
    total?: number
    counts_by_failure_source?: Record<string, number>
    counts_by_blamed_component?: Record<string, number>
    average_severity_score?: number
    average_confidence?: number
    top_weakness?: {
      failure_source?: string
      blamed_component?: string
      count?: number
    } | null
  }
}

export type WeaknessRankedComponent = {
  blamed_component?: string
  count?: number
  avg_severity?: number
  avg_confidence?: number
  weight_score?: number
  top_failure_source?: string | null
  best_improvement?: string
}

export type WeaknessRankedSource = {
  failure_source?: string
  count?: number
  avg_severity?: number
  weight_score?: number
  top_component?: string | null
  best_improvement?: string
  components?: WeaknessRankedComponent[]
}

export type WeaknessProfilePayload = {
  ok?: boolean
  profile?: {
    generated_at?: string
    lookback_days?: number
    min_confidence?: number
    total_losses_analyzed?: number
    top_failure_source?: string | null
    top_blamed_component?: string | null
    ranked_sources?: WeaknessRankedSource[]
    ranked_components?: WeaknessRankedComponent[]
  }
}

export type ProfileScopeValue = string

export type ProfileScopeOption = {
  value: ProfileScopeValue
  profile_id?: string
  label: string
  kind: 'aggregate' | 'shared-learning' | 'profile'
  enabled: boolean
  description?: string
}

export type TradeExecutionIdentity = {
  profile_id: string
  scope_type?: string
  execution_mode: string
  venue: string
  origin: string
  account_id?: string
}

export type OrderRow = JsonRecord & {
  id?: number
  order_id?: string
  profile_id?: string
  scope_type?: string
  execution_mode?: string
  venue?: string
  origin?: string
  account_id?: string
  source?: string
  symbol?: string
  interval?: string
  mode?: string
  direction?: string
  status?: string
  lifecycle_status?: string
  is_open?: boolean
  close_reason?: string
  open_timestamp?: string
  close_timestamp?: string
  entry?: number
  sl?: number
  tp?: number
  last_price?: number
  close_price?: number
  realized_r?: number
  unrealized_r?: number | null
  expected_r?: number | null
  position_side?: string
  holding_minutes?: number
  estimated_duration?: string | null
  timing_status?: string
  timing_estimate?: JsonRecord | null
  progress?: JsonRecord | null
  timing_progress?: JsonRecord | null
  signal_payload?: JsonRecord
  learning?: JsonRecord
  learning_adjustments?: JsonRecord
  confidence_before_learning?: number
  confidence_after_learning?: number
  probability_before_learning?: number
  probability_after_learning?: number
  signal_id?: string
}

export type SignalAuditTrail = {
  signal_id?: string
  captured_at?: string
  mode?: string
  regime?: string
  trend?: string
  session_label?: string
  circuit_breaker_state?: string
  factor_scores?: Record<string, number>
  threshold_checks?: Array<{ name?: string; threshold?: number; value?: number; passed?: boolean }>
  probability_components?: Record<string, number>
  learning_adjustments_applied?: Array<{ source?: string; multiplier?: number; reason?: string }>
  confidence_before_learning?: number
  confidence_after_learning?: number
  probability_before_learning?: number
  probability_after_learning?: number
  entry_price?: number
  stop_loss?: number
  take_profit?: number
  risk_reward?: number
  expected_value?: number
}

export type SignalPayload = {
  ok?: boolean
  signal?: JsonRecord & {
    signal_id?: string
    audit?: SignalAuditTrail
    audit_summary?: {
      confidence_before_learning?: number
      confidence_after_learning?: number
      circuit_breaker_state?: string
      learning_adjustments_applied?: number
    }
  }
}

export type SignalAuditPayload = {
  ok?: boolean
  audit?: SignalAuditTrail
}

export type SelfLearningStatusPayload = {
  ok?: boolean
  status?: {
    generated_at?: string
    memory_records_built?: number
    memory_count?: number
    replay_count?: number
    policy_example_count?: number
    expectancy_profile_count?: number
    shadow_decision_count?: number
  }
  self_learning_runtime?: {
    storage_layout?: JsonRecord
    backend_health?: JsonRecord
    active_model_version?: string | null
    candidate_model_version?: string | null
    previous_active_model_version?: string | null
    pinned_model_version?: string | null
    training_dataset_size?: number
    current_readiness_state?: string
    training_trigger?: {
      should_train?: boolean
      reasons?: string[]
      new_closed_trades?: number
      regime_coverage_count?: number
      last_training_completed_at_utc?: string | null
      last_training_run_id?: number | null
      thresholds?: JsonRecord
    }
    latest_comparison?: {
      status?: string
      recommendation?: string
      findings?: string[]
      metrics?: JsonRecord
    }
    memory?: {
      memory_row_count?: number
      retrieval_health?: JsonRecord
    }
    latest_dataset?: JsonRecord | null
  }
  runs?: Array<{
    id?: number
    run_type?: string
    status?: string
    started_at_utc?: string
    completed_at_utc?: string | null
    samples_processed?: number
    notes?: string
  }>
}

export type SelfLearningMemory = {
  id?: number
  signal_id?: string
  order_id?: string | null
  learning_regime?: string
  regime_confidence?: number
  regime_stability_score?: number
  regime_version?: string
  context?: JsonRecord
  outcome?: JsonRecord
  summary_text?: string
  embedding?: string | null
  result_label?: string
  realized_r?: number | null
  mae?: number | null
  mfe?: number | null
  hold_minutes?: number | null
  decay_weight?: number
  created_at_utc?: string
}

export type SelfLearningProfilePayload = {
  ok?: boolean
  generated_at?: string | null
  regime_counts?: Record<string, number>
  expectancy_profiles?: Array<{
    id?: number
    learning_regime?: string
    lookback_days?: number
    samples?: number
    expected_r?: number
    stop_hit_probability?: number
    target_hit_probability?: number
    avg_mae?: number | null
    avg_mfe?: number | null
    avg_hold_minutes?: number | null
    created_at_utc?: string
  }>
  top_recommended_actions_by_regime?: Array<{
    learning_regime?: string
    action_label?: string
    count?: number
    avg_realized_r?: number
  }>
  recent_shadow_decisions?: Array<{
    signal_id?: string
    generated_at_utc?: string
    recommended_action?: string
    support_samples?: number
    expected_reward?: number | null
    uncertainty_score?: number
    learning_regime?: string
    similar_case_count?: number
    reason_summary?: string
    payload?: JsonRecord
  }>
}

export type SelfLearningMemoriesPayload = {
  ok?: boolean
  items?: SelfLearningMemory[]
  count?: number
}

export type SelfLearningReplayPayload = {
  ok?: boolean
  order_id?: string
  items?: Array<{
    id?: number
    order_id?: string
    signal_id?: string
    action_label?: string
    is_actual_action?: boolean
    learning_regime?: string
    realized_r?: number | null
    mae?: number | null
    mfe?: number | null
    hold_minutes?: number | null
    outperformed_actual?: boolean
    delta_r_vs_actual?: number | null
    created_at_utc?: string
  }>
  best_action?: JsonRecord | null
  actual_action?: JsonRecord | null
}

export type SelfLearningShadowPayload = {
  ok?: boolean
  decision?: {
    id?: number
    signal_id?: string
    generated_at_utc?: string
    recommended_action?: string
    support_samples?: number
    expected_reward?: number | null
    uncertainty_score?: number
    learning_regime?: string
    similar_case_count?: number
    reason_summary?: string
    payload?: JsonRecord
  } | null
}

export type TradeAnalyticsGroupRow = {
  label?: string
  trades?: number
  win_rate?: number
  avg_realized_r?: number
  net_r?: number
  profit_factor?: number
  max_drawdown_r?: number
  avg_hold_minutes?: number
  stop_hit_pct?: number
  target_hit_pct?: number
  time_exit_pct?: number
  expectancy_score?: number
  reliability?: 'STABLE' | 'BUILDING_SAMPLE' | 'LOW_SAMPLE' | string
  provisional?: boolean
  reason_summary?: string
}

export type TradeAnalyticsPayload = {
  ok?: boolean
  filters?: {
    lookback_days?: number
    min_samples?: number
    mode?: string | null
    symbol?: string | null
    interval?: string | null
    direction?: string | null
    timezone?: string
  }
  overview?: {
    total_closed_trades?: number
    win_rate?: number
    avg_realized_r?: number
    net_r?: number
    profit_factor?: number
    best_mode?: string | null
    worst_mode?: string | null
    best_setup_method?: string | null
    worst_setup_method?: string | null
  }
  leaderboards?: {
    best_modes?: TradeAnalyticsGroupRow[]
    worst_modes?: TradeAnalyticsGroupRow[]
    best_setup_methods?: TradeAnalyticsGroupRow[]
    worst_setup_methods?: TradeAnalyticsGroupRow[]
    provisional_modes?: TradeAnalyticsGroupRow[]
    provisional_setup_methods?: TradeAnalyticsGroupRow[]
  }
  timing?: {
    by_session?: TradeAnalyticsGroupRow[]
    by_hour_of_day?: TradeAnalyticsGroupRow[]
    by_day_of_week?: TradeAnalyticsGroupRow[]
    session_hour_heatmap?: Record<string, Record<string, number>>
    timezone?: string
  }
  symbols?: {
    best_symbols?: TradeAnalyticsGroupRow[]
    worst_symbols?: TradeAnalyticsGroupRow[]
    best_symbol_intervals?: TradeAnalyticsGroupRow[]
    worst_symbol_intervals?: TradeAnalyticsGroupRow[]
    best_intervals?: TradeAnalyticsGroupRow[]
    worst_intervals?: TradeAnalyticsGroupRow[]
  }
  market_conditions?: {
    by_regime?: TradeAnalyticsGroupRow[]
    by_trend?: TradeAnalyticsGroupRow[]
    by_volatility_bucket?: TradeAnalyticsGroupRow[]
  }
  direction?: {
    by_direction?: TradeAnalyticsGroupRow[]
  }
  confidence_buckets?: Array<{
    label?: string
    trades?: number
    win_rate?: number
    avg_realized_r?: number
    avg_raw_confidence?: number
    avg_calibrated_confidence?: number
  }>
  confidence_monotonicity?: {
    pre_learning?: { status?: string; score?: number | null; buckets?: JsonRecord[] }
    post_learning?: { status?: string; score?: number | null; buckets?: JsonRecord[] }
  }
  exit_quality?: {
    stop_hit_rate?: number
    target_hit_rate?: number
    time_exit_rate?: number
    avg_hold_minutes?: number
    mfe_available?: boolean
    mae_available?: boolean
  }
  recommendations?: {
    scale_up_methods?: TradeAnalyticsGroupRow[]
    reduce_or_pause_methods?: TradeAnalyticsGroupRow[]
    strongest_sessions?: TradeAnalyticsGroupRow[]
    weakest_sessions?: TradeAnalyticsGroupRow[]
    strongest_hours?: TradeAnalyticsGroupRow[]
    weakest_hours?: TradeAnalyticsGroupRow[]
    tighten_confidence_buckets?: Array<{
      label?: string
      trades?: number
      win_rate?: number
      avg_realized_r?: number
    }>
  }
  validation_dashboards?: {
    stop_hit_rate?: JsonRecord
    time_stop_rate?: JsonRecord
  }
  symbol_throttles?: {
    enabled?: boolean
    total_throttled?: number
    throttled_symbols?: JsonRecord[]
    seeded_symbols?: string[]
    rules?: JsonRecord
  }
  comparison?: {
    improving_methods?: Array<{ label?: string; delta_avg_r?: number; current?: TradeAnalyticsGroupRow; prior?: TradeAnalyticsGroupRow }>
    decaying_methods?: Array<{ label?: string; delta_avg_r?: number; current?: TradeAnalyticsGroupRow; prior?: TradeAnalyticsGroupRow }>
    worsening_methods?: Array<{ label?: string; delta_avg_r?: number; current?: TradeAnalyticsGroupRow; prior?: TradeAnalyticsGroupRow }>
    emerging_methods?: Array<{ label?: string }>
    edge_decay_warning?: boolean
  }
  audit_analytics?: {
    available?: boolean
    threshold_pass_frequency?: Record<string, Record<string, number>>
    factor_score_distributions?: Record<string, Record<string, number>>
    learning_adjustments_presence?: Record<string, Record<string, number>>
    circuit_breaker_impact?: Record<string, Record<string, number>>
  }
  meta?: {
    generated_at?: string
    total_rows?: number
    timezone?: string
    has_audit_data?: boolean
  }
}

export type SwingPatchValidationCheck = {
  key?: string
  passed?: boolean
  severity?: string
  reason?: string
}

export type SwingPatchValidationPayload = {
  ok?: boolean
  validator_id?: string
  generated_at?: string
  baseline?: {
    baseline_id?: string
    captured_at?: string
    sample_notes?: string[]
  } & JsonRecord
  run_source?: string
  sample_size?: number
  overall_status?: 'PASS' | 'PARTIAL' | 'FAIL' | string
  hard_gates?: Record<string, boolean>
  checks?: SwingPatchValidationCheck[]
  pass_fail_reasons?: string[]
  stops?: {
    stop_hit_count?: number
    stop_too_tight_count?: number
    stop_too_tight_pct?: number
    stop_structurally_wrong_count?: number
    stop_structurally_wrong_pct?: number
    avg_stop_distance_atr?: number | null
    avg_structure_gap_atr?: number | null
    delta_vs_bad_baseline?: Record<string, number>
    pass?: boolean
  }
  stale_exits?: {
    swing_early_stale_exit_count?: number
    swing_1h_plus_early_stale_exit_count?: number
    swing_time_stop_count?: number
    delta_vs_bad_baseline?: Record<string, number>
    pass?: boolean
  }
  regimes?: {
    counts?: Record<string, number>
    win_rates?: Record<string, number>
    distribution_shift_ok?: boolean
    delta_vs_bad_baseline?: Record<string, number>
    pass?: boolean
  }
  confidence?: {
    accepted_signal_count_before?: number
    accepted_signal_count_after?: number
    bucket_calibration_gap?: number | null
    bucket_70_80_gap?: number | null
    component_penalty_affected_count?: number
    low_confidence_flood_flag?: boolean
    delta_vs_bad_baseline?: Record<string, number>
    pass?: boolean
  }
  release_recommendation?: string
}

export type ImprovementAnalyticsComponentRow = {
  component_id?: string
  label?: string
  component_type?: string
  status?: string
  version?: string
  owner?: string
  trades_affected?: number
  wins?: number
  losses?: number
  win_rate?: number
  avg_realized_r?: number
  net_r?: number
  profit_factor?: number
  avg_hold_minutes?: number
  stop_hit_pct?: number
  target_hit_pct?: number
  max_drawdown_r?: number
  expectancy_delta_vs_baseline?: number
  confidence_delta_vs_baseline?: number
  sample_reliability?: string
  provisional?: boolean
  failure_source_distribution?: Record<string, number>
  blamed_component_distribution?: Record<string, number>
}

export type ImprovementAnalyticsPayload = {
  ok?: boolean
  filters?: {
    lookback_days?: number
    min_samples?: number
    component_type?: string | null
    component_status?: string | null
    component_id?: string | null
    mode?: string | null
    symbol?: string | null
    interval?: string | null
    direction?: string | null
    regime?: string | null
  }
  overview?: {
    total_registered_components?: number
    active_components?: number
    experimental_components?: number
    components_changed_in_window?: number
    promoted_components_in_window?: number
    rolled_back_components_in_window?: number
    best_improving_component?: string | null
    worst_degrading_component?: string | null
  }
  recent_changes?: {
    items?: Array<{
      change_id?: string
      change_type?: string
      component_id?: string
      effective_from_run_id?: string
      effective_at_utc?: string
      change_reason?: string
      author?: string
      old_value?: JsonRecord | null
      new_value?: JsonRecord | null
    }>
    by_component?: Record<string, JsonRecord[]>
    by_change_type?: Record<string, number>
  }
  component_registry?: {
    items?: Array<{
      component_id?: string
      component_type?: string
      component_name?: string
      version?: string
      status?: string
      owner?: string
      description?: string
      default_params?: JsonRecord
      ui_label?: string
      module_path?: string
      object_name?: string
      implementation_fingerprint?: string
      introduced_at_utc?: string
      deprecated_at_utc?: string | null
      created_at_utc?: string
      updated_at_utc?: string
      first_seen?: string
      last_seen?: string
    }>
  }
  component_impact?: {
    by_component?: ImprovementAnalyticsComponentRow[]
    ranked_components?: ImprovementAnalyticsComponentRow[]
    provisional_components?: ImprovementAnalyticsComponentRow[]
    by_component_type?: Array<{ label?: string; trades_affected?: number; avg_realized_r?: number }>
    by_status?: Array<{ label?: string; trades_affected?: number; avg_realized_r?: number }>
    by_version?: Array<{ label?: string; trades_affected?: number; avg_realized_r?: number }>
  }
  change_impact?: {
    items?: Array<{
      change_id?: string
      change_type?: string
      component_id?: string
      trades_before?: number
      trades_after?: number
      avg_r_before?: number
      avg_r_after?: number
      expectancy_delta?: number
      confounded?: boolean
      sample_reliability?: string
    }>
  }
  combination_impact?: {
    best_combinations?: Array<{ label?: string; trades_affected?: number; avg_realized_r?: number; sample_reliability?: string; provisional?: boolean }>
    worst_combinations?: Array<{ label?: string; trades_affected?: number; avg_realized_r?: number; sample_reliability?: string; provisional?: boolean }>
  }
  contextual_impact?: {
    by_mode?: Array<{ label?: string; trades?: number; avg_realized_r?: number; win_rate?: number; sample_reliability?: string; provisional?: boolean }>
    by_regime?: Array<{ label?: string; trades?: number; avg_realized_r?: number; win_rate?: number; sample_reliability?: string; provisional?: boolean }>
    by_direction?: Array<{ label?: string; trades?: number; avg_realized_r?: number; win_rate?: number; sample_reliability?: string; provisional?: boolean }>
    by_session?: Array<{ label?: string; trades?: number; avg_realized_r?: number; win_rate?: number; sample_reliability?: string; provisional?: boolean }>
    by_confidence_bucket?: Array<{ label?: string; trades?: number; avg_realized_r?: number; win_rate?: number; sample_reliability?: string; provisional?: boolean }>
  }
  recommendations?: {
    promote_now?: Array<{ component_id?: string; label?: string; action?: string; reason_summary?: string; avg_realized_r?: number; expectancy_delta_vs_baseline?: number; sample_reliability?: string }>
    keep_experimental?: Array<{ component_id?: string; label?: string; action?: string; reason_summary?: string; avg_realized_r?: number; expectancy_delta_vs_baseline?: number; sample_reliability?: string }>
    pause_or_rollback?: Array<{ component_id?: string; label?: string; action?: string; reason_summary?: string; avg_realized_r?: number; expectancy_delta_vs_baseline?: number; sample_reliability?: string }>
    investigate?: Array<{ component_id?: string; label?: string; action?: string; reason_summary?: string; avg_realized_r?: number; expectancy_delta_vs_baseline?: number; sample_reliability?: string }>
  }
  operator_alerts?: Array<{ severity?: string; message?: string }>
  comparison?: {
    improving_components?: Array<{ label?: string; delta_avg_r?: number }>
    degrading_components?: Array<{ label?: string; delta_avg_r?: number }>
    emerging_components?: Array<{ label?: string; delta_avg_r?: number }>
    recently_broken_components?: Array<{ label?: string; delta_avg_r?: number }>
    edge_decay_warning?: boolean
  }
  rollout_measurement?: {
    current_window?: JsonRecord
    prior_window?: JsonRecord
    frozen_config_snapshot?: JsonRecord
  }
  meta?: {
    generated_at?: string
    total_rows?: number
  }
}

export type OrdersSnapshot = {
  auto_open_orders?: OrderRow[]
  auto_closed_orders?: OrderRow[]
  manual_open_orders?: OrderRow[]
  manual_closed_orders?: OrderRow[]
  open_orders?: OrderRow[]
  closed_orders?: OrderRow[]
  open_count?: number
  closed_count?: number
  summary?: {
    open?: number
    closed?: number
    total?: number
    net_r?: number
    open_expected_r?: number
    expected_net_r?: number
  }
  open_trade_analysis?: JsonRecord
}

export type PortfolioPayload = {
  profile_id?: string
  account_id?: string
  generated_at?: string
  summary?: JsonRecord
  portfolio?: JsonRecord
  paper_account?: JsonRecord
  account?: JsonRecord
  balances?: JsonRecord[]
  pnl_assets?: JsonRecord[]
  venue_positions?: JsonRecord[]
  venue_open_orders?: JsonRecord[]
  avg_hold_minutes?: number
  daily?: JsonRecord[]
  recent_closed?: JsonRecord[]
  open_positions?: JsonRecord[]
  engine?: JsonRecord
  equity_curve?: JsonRecord[]
}

export type JobItem = JsonRecord & {
  id?: number | string
  job_type?: string
  status?: string
  priority?: number
  requested_by?: string
  worker_id?: string
  run_id?: string
  payload?: JsonRecord
  result?: JsonRecord
  error_text?: string
  created_at?: string
  scheduled_for?: string
  started_at?: string
  finished_at?: string
  attempt_count?: number
  max_attempts?: number
}

export type JobQueueSnapshot = {
  items?: JobItem[]
  summary?: Record<string, number>
  pending?: number
  running?: number
  completed?: number
  paused?: number
  stopped?: number
  failed?: number
  dead_letter?: number
  control?: ScanControlState
}

export type ScanControlState = {
  desired_state?: 'RUNNING' | 'PAUSED' | string
  stop_requested?: boolean
  active_run_id?: string | null
  active_requested_by?: string | null
  active_status?: 'IDLE' | 'RUNNING' | 'PAUSED' | 'STOPPING' | string
  current_task?: JsonRecord | null
  updated_at_utc?: string
  progress_updated_at_utc?: string | null
  last_progress_completed_tasks?: number
  last_run_id?: string | null
  last_action?: string | null
  last_finished_status?: string | null
}

export type ScanControlPayload = {
  ok?: boolean
  state?: ScanControlState
}

export type ScanEvent = JsonRecord & {
  type: string
  timestamp: string
  profile_id: string
  run_id: string
  symbol?: string
  interval?: string
  mode?: string
  stage?: string
  reason_code?: string
  message?: string | null
  job_id?: string
  queue_depth?: number
  queue_limit?: number
  worker_capacity?: number
  running_jobs?: number
  queue_wait_ms?: number | null
  status?: string
  total_tasks?: number
  completed_tasks?: number
  remaining_tasks?: number
  percent_complete?: number
  queue_metrics?: JsonRecord
}

export type StorageBackendStatus = {
  backend?: string
  healthy?: boolean
  detail?: string | null
  counts?: Record<string, number>
  sizes?: Record<string, number>
  total_size_bytes?: number
}

export type StorageStatusPayload = {
  generated_at?: string
  postgres?: StorageBackendStatus
  state?: {
    mode?: string
    label?: string
    note?: string
  }
  clear_groups?: Array<{
    group_id?: string
    label?: string
    description?: string
    components?: string[]
  }>
}

export type StorageMutationSummary = {
  store?: string
  mode?: string
  counts?: Record<string, number>
  current_counts?: Record<string, number>
  delta_counts?: Record<string, number>
  dry_run?: boolean
  cleared_components?: string[]
  cleared_group?: string | null
}

export type StorageTrashEntry = {
  trash_id?: string
  archived_at?: string | null
  expires_at?: string | null
  operation?: string | null
  profile_id?: string | null
  components?: string[]
  counts?: Record<string, number>
  path?: string | null
}

export type StorageExportPayload = {
  exported_at?: string
  store?: string
  kind?: string
  counts?: Record<string, number>
  state?: JsonRecord
  runtime_settings?: Record<string, string>
  candles?: JsonRecord[]
  scan_runs?: JsonRecord[]
  signals?: JsonRecord[]
  orders?: JsonRecord[]
  fills?: JsonRecord[]
  positions?: JsonRecord[]
  portfolio_snapshots?: JsonRecord[]
  alerts?: JsonRecord[]
  failures?: JsonRecord[]
}

export type MarketOverviewPayload = {
  items?: JsonRecord[]
  top_movers?: JsonRecord[]
  symbols?: string[]
  intervals?: string[]
}

export type SymbolsPayload = {
  symbols?: string[]
  intervals?: string[]
}

export type MarketSignalsPayload = {
  items?: JsonRecord[]
}

export type AnalysisPayload = JsonRecord & {
  direction?: string
  confidence?: number
  reason_text?: string
  no_trade_reason?: string
  summary?: string
  regime?: string
  regime_detail?: string
  trend?: string
  risk_reward?: number
  entry_price?: number
  entry_zone_low?: number
  entry_zone_high?: number
  stop_loss?: number
  take_profit?: number
  expected_duration?: string
  recommended_size?: string
  advanced_analysis?: JsonRecord
  entry?: number
  sl?: number
  tp?: number
  snapshot?: JsonRecord
  ticker?: JsonRecord
}

export type SummaryCardItem = {
  label: string
  value: string
  note: string
  tone: string
  icon?: string
}

export type AlertSeverity = 'critical' | 'warning' | 'info'

export type AlertItem = {
  id: string
  title: string
  message: string
  severity: AlertSeverity
  route: string
  timestamp?: string
  unread?: boolean
}
