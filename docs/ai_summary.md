# V7 COMPLETE AI SUMMARY — MACHINE READABLE REFERENCE

## META

This document is a lossless dense synthesis of every V7 markdown file in the repository. It is designed for LLM code agents and AI-assisted engineering workflows. It is NOT for human reading. The entire doc set has been compressed into this single reference preserving all rules, invariants, fields, config surfaces, phase details, contract semantics, pipeline specifications, and ownership boundaries.

**Reading order for an AI:** Read this entire file first. Then consult specific authority docs for implementation details. This file is authoritative only where it directly quotes or faithfully restates authority docs; in case of conflict, the original doc wins.

**File count synthesized:** ~45 markdown files
**Source tree:** /home/erfolg/src/v7-engine/docs/

---

## 1. SYSTEM IDENTITY — VISION (docs/vision.md)

### 1.1 One-Sentence Definition
V7 is a centralized, market-first, simulation-native learned trading engine that optimizes economic quality first, uses calibrated decision outputs, and evaluates long / short / no-trade actions through one runtime-hosted forward-simulation truth layer.

### 1.2 Why V7 Exists
- V6 established: explicit runtime–engine contracts, market-first labeling, unified snapshot thinking, walk-forward evaluation discipline, decision and outcome normalization, validation/verification/rollback discipline.
- V6 accumulated: transition architecture debt across V4/V5/V6, excessive selector and workflow complexity, calibration that became operationally important without being structurally central, backtesting/labeling logic not tightly unified, economic quality not improving relative to complexity, single-state mental model not aligned with 60-symbol centralized engine, excessive change surface for routine edits.

### 1.3 Primary Goal
To produce fewer, higher-quality trading decisions with stronger out-of-sample economic performance under realistic simulation and execution costs.

### 1.4 Success Metrics
**Primary:** Expectancy R (average realized R per executed trade across OOS forward simulation), risk-adjusted return, no-trade quality (correctly avoids low-quality/ambiguous states), calibration quality (model scores reflect actual outcome quality, usable for decision thresholds).
**Secondary:** Symbol consistency (performance not carried by 1-2 symbols), regime consistency (performance does not collapse outside one regime), operational predictability, editability/iteration speed, configuration simplicity.
**Non-metrics (explicit):** Architectural richness, number of subsystems, number of reports, raw classification accuracy, more signals, more complex model topology.

### 1.5 What V7 Is
Contract-compatible learned trading engine, centralized multi-symbol system, market-first learning, simulation-native (runtime-hosted simulation defines truth), calibration-structural decision system, 60-symbol capable, economic-quality-first, mode-scoped (SWING/SCALP/AGGRESSIVE_SCALP with shared platform + separate scope artifacts), editable/configurable/reviewable/testable.

### 1.6 What V7 Is NOT
V4 correction layer, V5 continuation stack, transition-heavy architecture, runtime rewrite, hidden deterministic veto system, confidence-first system with cosmetic calibration, model-accuracy project disconnected from economic reality, doc-heavy architecture exercise, black box with invisible fallbacks, system where small change requires editing many unrelated subsystems.

### 1.7 Six Architectural Layers
1. Runtime: orchestration, scheduling, market-data flow, persistence, execution control, safety.
2. Contract boundary: AnalysisRequest/AnalysisResult/DecisionEvent/TradeOutcome.
3. State and simulation core: canonical market-state construction, runtime-hosted unified forward simulation, unified outcome semantics, unified cost model.
4. Learned decision engine: long/short/no-trade action scores, calibrated decision outputs, uncertainty-aware info, execution-relevant quality signals.
5. Economic policy layer: decision thresholds, no-trade rules, correlation exposure, drawdown gates, position-sizing policy.
6. Review and lifecycle layer: validation, forward simulation, promotion/rollback, artifact versioning, runtime review surfaces.

### 1.8 Strategic Difference From V6
V6 = transition-heavy learned layer. V7 = consolidated economic decision engine. V4 runtime was operational owner, V4 deterministic logic was strong context/safety source, V5 was reused infrastructure. V7 owns its own learning pipeline end to end; legacy systems are compatibility/migration support; deterministic logic is context not governance; simulation is truth layer; economic evaluation is real authority.

### 1.9 Market-First Principle
Market defines outcome truth. Legacy engines do not define ground truth. Labels come from simulated or realized market outcomes. Long, short, and no-trade are evaluated comparatively. Trade quality judged by economic outcome, not agreement with legacy rules.

### 1.10 Unified Simulation Principle
One runtime-hosted simulation engine defines simulated truth for labeling, evaluation, and production outcome interpretation. Label generation, forward evaluation, trade-outcome generation, cost modeling, stop/target/time-exit semantics must share one logic surface. No separate backtesting logic for research vs labeling.

### 1.11 Calibration-Structural Principle
Calibration is part of the decision system, not cosmetic. Raw model scores not directly trusted for action decisions. Calibrated scores are basis for thresholds and policy. Calibration tracked per symbol and regime where justified. Confidence not enough; calibrated reliability matters. Threshold policy aligned to calibrated score distribution. Model without usable calibration is not decision-ready.

### 1.12 No-Trade Is First-Class
NO_TRADE is not absence of signal, not fallback, not default suppressor. It is a real learned action competing with LONG_NOW and SHORT_NOW. Must be represented in labels, evaluation, and policy.

### 1.13 Multi-Symbol Centralization
Designed for 60-symbol universe. Symbol-aware model inputs or evaluation slices. Symbol-level calibration and error analysis. Cross-symbol correlation awareness in decision policy. Batch-oriented inference design.

### 1.14 Cost-Honest Labels
Labels reflect realistic fees, slippage assumptions, entry/exit rules, stop/target/time-exit behavior, comparative action quality between long/short/no-trade. Question is "which action produced best net economic outcome under same simulated rules?" not "did price go up?"

### 1.15 Runtime Boundary Stable
Runtime owns orchestration, execution control, persistence, failure handling, operator control surfaces. Engine owns market-state interpretation, calibrated decision scoring, uncertainty-aware action recommendation.

### 1.16 Deterministic Context Position
Deterministic logic useful as annotation, context, regime hint, explicit warning source, explicit hard block in narrow cases. Must not silently define V7's ceiling. No silent deterministic veto. No hidden suppression of learned opportunity. Deterministic influence visible and reviewable.

### 1.17 Promotion Rule
Candidates promoted only through OOS economic evidence: positive expectancy R across meaningful OOS periods, acceptable drawdown, acceptable no-trade quality, acceptable calibration quality, acceptable symbol/regime stability.

### 1.18 Editability and Speed Principle
Fewer subsystems, fewer hidden policies, one central configuration root, one primary CLI entrypoint, one runtime-hosted simulation truth layer, simpler threshold policy, modular feature/label extensions, minimal required documentation. A change in one concern should ideally edit one primary module + one config surface + one test surface.

### 1.19 V7 Keeps From V6
Explicit request/result/event/outcome contracts, market-first labeling philosophy, unified snapshot/live-replay parity discipline, no-trade as first-class action, explicit fallback visibility, validation/promotion/rollback discipline, no silent deterministic veto.

### 1.20 V7 Deliberately Changes
Transition-heavy → centralized, economic evaluation primary truth (not downstream check), calibration structural (not cosmetic), simulation single truth layer (for labeling + evaluation), multi-symbol thinking native, threshold policy simpler and more explicit, architecture optimized for fast iteration, configuration centralized.

### 1.21 First-Phase Non-Goals
Not about: final model topology lock-in, solving every timeframe/execution style, replacing runtime shell, building giant doc set, adding specialist-routing complexity without evidence, maximizing signals, shipping RL-first engine.
About: defining right success criteria, contracts, runtime-hosted simulation output semantics, centralized architecture, modularity/config rules, system reaching economic quality faster.

---

## 2. ARCHITECTURE (docs/architecture.md)

### 2.1 Architectural Summary
```
one market-state pipeline
→ one simulation truth layer
→ one label/evaluation language
→ one hybrid supervised model
→ one explicit policy layer
→ one portfolio layer
→ one risk gate
→ one runtime boundary
```

### 2.2 Core Architectural Rules
1. One simulation truth layer: same simulation logic defines labels, replay evaluation, paper/live outcome interpretation, no-trade quality, regret, cost-aware trade resolution.
2. One canonical market-state language: live inference, replay, dataset generation, evaluation use same state language.
3. One explicit contract family: AnalysisRequest, AnalysisResult, DecisionEvent, TradeOutcome.
4. One primary model family first: XGBoost-first.
5. Hybrid model outputs first-class: model artifact exposes action probability/classification surfaces AND expected economic quality/regression surfaces.
6. Runtime is not the model: runtime owns orchestration/persistence/safety/fallback/execution eligibility; model produces decision evidence not operational permission.
7. One central configuration root: all behavior routes through unified config system.

### 2.3 Top-Level Layers (11 layers)
1. Raw market data
2. Canonical state construction
3. Simulation and outcome truth
4. Labels and features
5. Dataset and split
6. Hybrid model and calibration
7. Decision policy
8. Portfolio interpretation
9. Risk gating
10. Runtime lifecycle
11. Evaluation and monitoring

### 2.4 Layer Details
**Raw Market Data:** Acquire raw candle history, store canonical raw history, validate gaps/duplicates/corruption/timestamp order, expose consistent historical windows. First-phase: Binance candles, primary 4h, HTF 1d, refinement 1h, universe up to 60 symbols. Raw data remains source-of-truth history; no derived features stored as raw truth; missing/corrupted history explicit.

**Canonical State Construction:** Build one canonical state per symbol per decision timestamp. Attach 4h primary, 1d context, 1h refinement views. Attach volatility/regime/symbol metadata/quality/freshness. Identical semantics to live/replay/dataset/evaluation. Deterministic for same input, no future bars, no runtime-only hidden side channel, missingness explicit.

**Simulation and Outcome Truth:** Compares LONG_NOW, SHORT_NOW, NO_TRADE for same state and future path under same stop/target/horizon/fee/slippage semantics. Computes realized R, fee/slippage adjusted R, MFE/MAE, path quality, regret, saved-loss and missed-opportunity scores, resolution status. Rules: one simulation engine, labels and evaluation share semantics, no unresolved simulation becomes final training label, simulation-family version changes when meaning changes.

**Labels and Features:** Labels derived from simulation truth. Classification labels answer "which action is preferable?" Regression labels answer "how profitable/risky/costly is the action?" Features from canonical state only. Rules: no future leakage, explicit feature schema versioning, explicit label interpretation versioning, compact interpretable first-phase features, shared multi-symbol model bias.

**Dataset and Split:** Temporal and lineage-preserving. Rows contain: symbol, primary interval, timestamp, feature vector, classification targets, regression targets, simulation lineage, label lineage, feature schema lineage. Rules: no random IID primary split, walk-forward evaluation first, unresolved/invalid labels excluded by default, ambiguous rows explicitly handled, symbol weighting prevents silent dominance.

**Hybrid Model and Calibration:** XGBoost-first hybrid supervised model. Artifact shape: shared feature matrix → classification surfaces (P(LONG_NOW), P(SHORT_NOW), P(NO_TRADE)) + regression surfaces (E[R|LONG_NOW], E[R|SHORT_NOW], expected adverse pressure/drawdown, cost-adjusted expectancy). Calibration maps raw scores to reliable probability/confidence. Rules: XGBoost classifiers+regressors both allowed, raw scores not runtime confidence, regression heads are economic evidence not direct execution permission, model family can change without rewriting runtime contracts.

**Decision Policy:** Directional action must pass: probability/confidence gate, no-trade comparison gate, expected-R gate, cost-adjusted expectancy gate, adverse-pressure/drawdown gate, decision-margin gate. Weak/contradictory/degraded/ambiguous → policy selects NO_TRADE explicitly.

**Portfolio:** Handles cross-symbol competition after single-candidate policy outputs. May pass, suppress, down-rank, annotate. First-phase lightweight, not full optimizer. Rules: portfolio is not model training, no hidden portfolio veto, concentration/cluster controls explicit.

**Risk:** Final safety layer before execution eligibility. Handles kill switch, exposure hard limits, duplicate protection, cooldowns, stale/degraded result handling. Rules: hard guards stay hard, model confidence cannot override operational safety, risk blocks visible in lifecycle records.

**Runtime Lifecycle:** Runtime owns request assembly, result validation, event creation, execution eligibility, persistence, outcome lifecycle, fallback visibility, rollback/operational safety. Engine owns hybrid model scoring, calibrated decision evidence, expected-R surfaces, recommended action, timing guidance, degradation visibility.

### 2.5 Truth Hierarchy
When components disagree: 1. simulation truth, 2. realized market outcome truth, 3. contract truth, 4. runtime interpretation truth, 5. model explanation. The model does not define truth by itself.

---

## 3. CONTRACT FAMILY (docs/contracts/README.md)

### 3.1 Family Structure
**Layer A — Atomic lifecycle objects:** AnalysisRequest, AnalysisResult, DecisionEvent, TradeOutcome.
**Layer B — Grouping/orchestration objects:** AnalysisBatchRequest, AnalysisBatchResult, DecisionSession. Layer B is deferred until Layer A is stable.

### 3.2 Atomic Rule
Core semantic unit: one symbol, one primary interval, one evaluated market state, one request, one result, one event, one outcome. Batching/grouping/sessions built AROUND the atomic unit, not instead of it.

### 3.3 Ownership Model
- Engine-facing: AnalysisRequest, AnalysisResult
- System/lifecycle: DecisionEvent, TradeOutcome

### 3.4 Version Fields
- `contract_version`: boundary-family version
- `state_schema_version`: meaning of canonical_state
- `response_schema_version`: meaning of stable result surface
- `event_schema_version`: meaning of normalized event object
- `outcome_schema_version`: meaning of normalized outcome object
- `snapshot_builder_version`: state-construction logic version
- Artifact versions: model_artifact_version, calibration_artifact_version, policy_artifact_version

### 3.5 Generation Rules Per Contract
**Request must define:** atomic scope, canonical state, explicit lineage/versioning, quality/degradation visibility. Must NOT define: execution commands, future truth, multi-symbol aggregation.
**Result must define:** recommended action, confidence, expected R, actionability, execution guidance, degradation visibility. Must NOT define: broker payloads, outcome truth, multi-request aggregation.
**Event must define:** normalized lifecycle record, request/result linkage, runtime interpretation, execution linkage, outcome linkage. Must NOT define: full raw request duplication, full raw result duplication, fill internals.
**Outcome must define:** decision linkage, execution truth, path truth, comparative truth, finality/readiness. Must NOT define: raw label-builder internals, full request/result duplication, hidden hindsight rewrites.

---

## 4. ANALYSISREQUEST CONTRACT (docs/contracts/analysis_request.md)

### 4.1 Purpose
Atomic runtime-to-engine analysis input. Answers: what exact market state and runtime context must be provided so engine can evaluate one market state consistently, safely, and replay-compatibly?

### 4.2 Core Position
V7 keeps V6 request principle (one atomic request, one evaluated market state, one engine response) with four extensions: canonical-state centered, interval-aware through explicit state views, batch/session-aware through lineage fields, lighter than V6.

### 4.3 Top-Level Shape
```
AnalysisRequest
├── contract — versioned contract artifact
├── identity — unique request instance
├── scope — instrument and operating mode
├── canonical_state — fully assembled market state
├── state_views — interval-aware context
├── deterministic_context — structured deterministic annotations
├── runtime_context — runtime-owned analysis context
├── quality_and_freshness — input quality explicit
├── degradation_context — degraded request assembly
├── portfolio_context — optional lightweight portfolio context
├── risk_context — optional lightweight risk context
└── lineage — batch/session connection
```

### 4.4 Contract Section Fields
Required: contract_version, state_schema_version, snapshot_builder_version, request_kind.

request_kind values: live_scan, paper_scan, replay_eval, shadow, validation.

state_schema_version versions meaning of canonical_state subtree: sub-sections, field names/ownership, unit conventions, enum meanings, derived metrics interpretation, required vs optional state elements, live/replay compatibility assumptions.

### 4.5 Identity Section Fields
Required: request_id, timestamp_utc. Recommended: run_id, trace_id. Optional: parent_decision_event_id.

parent_decision_event_id used for re-evaluation of previous decision, watch/follow-up analysis, retry flows, shadow/comparison flows. If fresh first-pass evaluation, should usually be null/omitted.

### 4.6 Scope Section Fields
Required: symbol, requested_trade_mode, model_scope, primary_interval, analysis_mode.
Strongly recommended: context_intervals, refinement_intervals, label_horizon_family (training/evaluation/replay lineage).
Optional: exchange, market_type, base_asset, quote_asset, symbol_class.

Rules: one request targets one model scope (not all scopes competing). primary_interval and label_horizon_family must be compatible with model_scope. Scope is descriptive/routing input only.

### 4.7 Scope Defaults
SWING: primary_interval 4h, context_intervals [1d], refinement_intervals [1h], label_horizon_family swing_horizon.
SCALP: primary_interval 15m, context_intervals [1h], refinement_intervals [5m], label_horizon_family scalp_horizon.
AGGRESSIVE_SCALP: primary_interval 1m or 3m, context_intervals [5m, 15m], refinement_intervals [1m/3m micro context], label_horizon_family immediate_continuation_short_horizon.

### 4.8 Canonical State Section
Most important part. One stable internal structure containing: recent raw market window, derived local state, higher-timeframe context, volatility/regime context, symbol/interval identity, data-quality/freshness metadata, optional runtime-safe context.

Minimal shape: raw_window, derived_state, context, quality, metadata.

**raw_window:** candles (open/high/low/close/volume/close_time_utc), window_length, window_start_utc, window_end_utc. Optional: quote_volume, trade_count, taker_buy_base_volume, taker_buy_quote_volume.
**derived_state:** indicator_state, candle_geometry, volatility_state, structure_state, session_state, cyclical_time_features.
**context:** higher_timeframe (interval, bias, trend_strength, freshness), regime_context (regime_label, volatility_bucket), symbol_context.
**quality:** stale_flag, data_source, data_quality_flags, missing_context_flags, snapshot_validity, partial_state_flag, latest_bar_timestamp_utc, htf_freshness.
**metadata:** symbol, primary_interval, state_timestamp_utc, snapshot_builder_version_seen, state_schema_version_seen.

Rules: deterministic for same visible history, no future leakage, same semantics across live/replay/evaluation/analysis reuse, compact enough to stay inspectable, extensible through additive schema evolution.

### 4.9 State Views Section
Makes interval-aware context explicit. Typical views: primary, higher_timeframe, refinement. One view remains primary. Contextual views explicitly named. Adding new view additive and versioned.

### 4.10 Deterministic Context Section
Runtime-supplied annotation layer. Examples: regime hints, structural annotations, volatility bucket, explicit warning flags, liquidity/risk flags, allowed/blocked action hints. Annotation only; not labels, not future truth, not silent authority. Distinction from canonical_state.context: canonical_state.context describes the market; deterministic_context is runtime-owned interpretation aid.

### 4.11 Runtime Context Section
Runtime-owned analysis context not part of market. Examples: source_context, requested_by, paper_or_live_mode, runtime_phase, engine_budget_hint, engine_timeout_ms.

### 4.12 Quality And Freshness Section
Top-level runtime-visible request surface. Must remain semantically consistent with canonical_state.quality.

### 4.13 Degradation Context Section
Explicit if present. Machine-readable and human-readable. No silent degraded path. Examples: missing HTF context, fallback builder path used, incomplete auxiliary view, partial state, reduced-confidence assembly reason.

### 4.14 Portfolio Context Section
Optional, contextual only. Examples: open-position count, symbol exposure tier, cluster/correlation bucket hint, drawdown state tier, portfolio pressure tier. Not allocation control, ranking control, position sizing, or portfolio engine governance.

### 4.15 Risk Context Section
Optional, advisory only. Examples: cooldown-active flag, exposure-cap-near flag, operational caution tier, runtime risk regime tag. No hidden execution policy, no order-management internals.

### 4.16 Lineage Section
analysis_batch_id, decision_session_id, batch_rank_context (optional). Identity only, not control semantics.

### 4.17 Required Fields
contract.contract_version, contract.state_schema_version, contract.snapshot_builder_version, identity.request_id, identity.timestamp_utc, scope.symbol, scope.requested_trade_mode, scope.model_scope, scope.primary_interval, scope.analysis_mode, canonical_state.

### 4.18 Strongly Recommended
state_views, quality_and_freshness, runtime_context, degradation_context (when degraded), lineage.analysis_batch_id, lineage.decision_session_id.

### 4.19 Must NOT Be In Request
Multiple symbols, multiple independent decision intervals, future outcomes/simulation loops, execution commands, allocation control, hidden debug blobs, runtime execution topology.

### 4.20 Validation Rules
Required fields exist, symbol/requested_trade_mode/model_scope/primary_interval/analysis_mode valid, requested_trade_mode compatible with model_scope, intervals compatible with model_scope, timestamp present/parseable, contract versions supported, canonical_state present/structurally valid, contextual state views not conflict with primary scope, degraded/quality flags internally consistent, no forbidden future-derived fields. Missing required section → runtime should reject before engine routing (unless documented degraded path).

---

## 5. ANALYSISRESULT CONTRACT (docs/contracts/analysis_result.md)

### 5.1 Purpose
Atomic engine-to-runtime analysis output. Answers: what exact analysis result must engine return so runtime can interpret, review, persist, and safely act on one evaluated market state?

### 5.2 Core Position
One request, one result, one evaluated market state, one explicit runtime-facing decision surface. Preserves: confidence first-class, expected_r first-class, execution guidance/timing explicit, degradation/fallback/deterministic interaction visible. Adds: current entry readiness explicit without complex execution planner.

### 5.3 Request Compatibility Rule
Every valid AnalysisResult corresponds to exactly one valid AnalysisRequest: one request_id, one symbol, one model_scope, one trade_mode, one primary_interval, one engine result surface produced by one scope-compatible artifact.

### 5.4 Top-Level Shape
```
AnalysisResult
├── contract
├── identity
├── request_link
├── status
├── decision
├── scores
├── execution_guidance
├── uncertainty_and_quality
├── deterministic_interaction
├── fallback_and_degradation
├── observability
└── lineage
```

### 5.5 Contract Section
Required: contract_version, response_schema_version, engine_output_version.

### 5.6 Identity Section
Required: request_id, engine_name, engine_version, timestamp_utc.
Recommended: run_id, trace_id, model_scope, trade_mode, model_artifact_version, artifact_id, calibration_artifact_version, calibration_artifact_id, policy_artifact_version.

### 5.7 Request Link Section
Recommended: symbol, model_scope, trade_mode, primary_interval, context_intervals, label_horizon_family, request_contract_version, request_kind_seen.
Consistency rules: request_link.symbol == request.scope.symbol, model_scope == model_scope, trade_mode == requested_trade_mode, primary_interval == primary_interval, identity.request_id == request.identity.request_id, etc.

### 5.8 Status Section
Required: signal_status, decision_status, is_actionable.
signal_status: SIGNAL, NO_TRADE, FILTERED, DEGRADED, ERROR.
decision_status: VALID, LOW_CONFIDENCE, BLOCKED, DEGRADED, FAILED.

### 5.9 Decision Section
Required: recommended_action, direction, decision_summary.
recommended_action: LONG_NOW, SHORT_NOW, NO_TRADE. Action family interpreted inside selected model_scope only.
direction: LONG, SHORT, NONE.

### 5.10 Scores Section
Required (core runtime/economic): confidence, confidence_kind, expected_r.
Strongly recommended: probability, expected_drawdown, risk_reward_estimate, decision_margin, long_score, short_score, no_trade_score.
Optional: raw_confidence, calibrated_confidence, expected_hold_time, expected_edge.
Rules: confidence first-class (runtime may open trades using confidence thresholds), expected_r first-class (economic quality), confidence does NOT mean automatic execution, probability supportive not only decision scalar.

### 5.11 Execution Guidance Section
Required for actionable directional trades (recommended_action LONG_NOW/SHORT_NOW AND is_actionable=true): entry_price, stop_loss, take_profit, time_sensitivity.
Strongly recommended: entry_zone, entry_readiness, entry_valid_for_bars, size_multiplier, risk_expression, execution_notes.
Optional: entry_expiry_utc.

time_sensitivity values: IMMEDIATE, STANDARD, CAN_WAIT, EXPIRING_SOON.
entry_readiness values: READY_NOW, WAIT, CHASING, EXPIRING, MISSED, NOT_APPLICABLE.
entry_valid_for_bars range: 0 to 5 (first convention, capped at 5).

### 5.12 Actionability Matrix
| Case | recommended_action | is_actionable | entry_readiness | Required execution fields | Runtime default |
|---|---|---|---|---|---|
| Valid long | LONG_NOW | true | READY_NOW/WAIT/CHASING/EXPIRING | entry_price, stop_loss, take_profit, time_sensitivity | Eligible for execution gates |
| Valid short | SHORT_NOW | true | same | same | Eligible for execution gates |
| Explicit skip | NO_TRADE | false | NOT_APPLICABLE | none | Do not open trade |
| Low-confidence block | LONG/SHORT | false | optional | optional | Reviewable, not executable |
| Degraded safe skip | any | false | optional | optional | Use runtime_safe_action |
| Error/failure | any | false | optional | none | Reject for execution |

### 5.13 Uncertainty And Quality Section
Recommended: uncertainty_score, uncertainty_type, decision_quality, path_quality_expectation, is_ambiguous, quality_flags.

### 5.14 Deterministic Interaction Section
Recommended: deterministic_alignment, deterministic_warning, deterministic_block, deterministic_disagreement_reason, regime_transition_risk, constraint_level.

### 5.15 Fallback And Degradation Section
Required: fallback_used, degraded_reason.
Strongly recommended: fallback_reason, fallback_source, runtime_safe_action, is_timeout_fallback, is_schema_fallback.

### 5.16 Observability Section
Strongly recommended: analysis_latency_ms, reason_summary, warnings, top_feature_groups, review_tags, contract_strictness_used (STRICT, DEGRADED_ALLOWED, SHADOW_RELAXED).

### 5.17 Lineage Section
Recommended: analysis_batch_id, decision_session_id, batch_rank (optional).

### 5.18 Validation Rules
Required sections/fields exist, request_id matches originating request, symbol/model_scope/trade_mode/primary_interval match if present, artifact_id/calibration_artifact_id scope-compatible with model_scope, recommended_action and direction internally consistent, is_actionable consistent with status/degradation, required execution fields exist for actionable directional trades, confidence/expected_r valid numeric, entry_valid_for_bars in 0..5 if present, entry_readiness legal enum if present, fallback fields internally consistent, contract version supported.

### 5.19 Runtime Impact of Timing Extension (Phase 1-3)
Phase 1 — Contract acceptance: update result validators for entry_readiness/entry_valid_for_bars, update persistence schemas, update logging/review serialization, no hard execution gating.
Phase 2 — Observability only: record fields in DecisionEvent/review surfaces, compare READY_NOW vs later outcome, CHASING vs regret, EXPIRING vs missed-opportunity.
Phase 3 — Optional gating: suppress when entry_readiness=MISSED, weaken when CHASING, require entry_valid_for_bars>0 for certain strategies.
Suggested config: enable_entry_timing_observability, enable_entry_readiness_gate, blocked_entry_readiness_states, min_entry_valid_for_bars, entry_timing_gate_mode.

---

## 6. DECISIONEVENT CONTRACT (docs/contracts/decision_event.md)

### 6.1 Purpose
Atomic system-level normalized decision record created after one AnalysisRequest has been evaluated into one AnalysisResult. Answers: after one atomic request is evaluated into one atomic result, what is the canonical event object the rest of the system should persist, compare, review, and later link to execution and outcomes?

### 6.2 Core Position
DecisionEvent is not emitted by the model. Belongs to one atomic request/result pair. Runtime interpretation is explicit. V7 request/result naming stays aligned. Batch/session lineage first-class. Small timing-readiness echoes from result recorded for audit and later evaluation.

### 6.3 Position In Flow
AnalysisRequest → AnalysisResult → DecisionEvent → optional execution/no-execution path → TradeOutcome

### 6.4 Top-Level Shape
```
DecisionEvent
├── contract
├── identity
├── lineage
├── scope
├── request_summary
├── decision_summary
├── runtime_interpretation
├── execution_linkage
├── outcome_linkage
├── observability
└── optional_extended_metadata
```

### 6.5 Contract Section
Required: event_schema_version, contract_version, request_contract_version, response_schema_version.
Recommended: state_schema_version_seen, snapshot_builder_version_seen.

### 6.6 Identity Section
Required: decision_event_id, request_id, timestamp_utc.
Recommended: run_id, trace_id, comparison_group_id.

### 6.7 Lineage Section
Required: engine_name, engine_version, request_kind, analysis_batch_id (nullable), decision_session_id (nullable).
Strongly recommended: model_scope, trade_mode, model_artifact_version, artifact_id, calibration_artifact_version, calibration_artifact_id, policy_artifact_version.
Optional: portfolio_artifact_version, risk_policy_version, candidate_source, replay_mode, deterministic_annotation_version, batch_rank.

### 6.8 Scope Section
Required: symbol, model_scope, trade_mode, primary_interval, analysis_mode.
Optional: exchange, market_type.

### 6.9 Request Summary Section
Recommended: request_timestamp_utc, state_timestamp_utc, state_window_length, state_schema_version_seen, snapshot_builder_version_seen, state_views_seen, stale_flag, snapshot_validity, data_source, htf_bias, regime_label, regime_confidence, risk_flags, paper_or_live_mode, engine_budget_hint.

### 6.10 Decision Summary Section
Required: signal_status, decision_status, is_actionable, recommended_action, direction.
Strongly recommended: confidence, confidence_kind, expected_r, expected_drawdown, decision_margin, long_score, short_score, no_trade_score, reason_summary.
Timing echo fields: entry_price_seen, stop_loss_seen, take_profit_seen, time_sensitivity_seen, entry_readiness_seen, entry_valid_for_bars_seen.
Optional timing: entry_expiry_utc_seen.

### 6.11 Runtime Interpretation Section
Recommended: runtime_actionability, deterministic_alignment, deterministic_block, fallback_used, degraded_reason, runtime_safe_action, policy_passed, portfolio_blocked, risk_blocked, suppression_reason, should_persist_as_signal, should_surface_to_review.
Timing-related optional: entry_timing_observed, entry_timing_used_for_gate, entry_timing_gate_reason.

### 6.12 Execution Linkage Section
Recommended: execution_path, execution_decision, order_group_id, paper_trade_id, position_id, execution_reference_ids.

### 6.13 Outcome Linkage Section
Recommended: trade_outcome_id, outcome_status, label_status, outcome_horizon_family, outcome_ready_timestamp_utc.

### 6.14 Observability Section
Strongly recommended: analysis_latency_ms, warnings, quality_flags, uncertainty_type, decision_quality, regime_transition_risk, review_tags, payload_references, timing_extension_present, timing_review_tags.
timing_review_tags convention: ready_now, wait_preferred, chasing_entry, expiring_setup, missed_setup.

### 6.15 Consistency Rules
identity.request_id == request.identity.request_id == result.identity.request_id
scope.symbol == request.scope.symbol
scope.model_scope == request.scope.model_scope
scope.primary_interval == request.scope.primary_interval
decision_summary.recommended_action == result.decision.recommended_action
decision_summary.direction == result.decision.direction
decision_summary.is_actionable == result.status.is_actionable
decision_summary.entry_readiness_seen == result.execution_guidance.entry_readiness (when surfaced)
decision_summary.entry_valid_for_bars_seen == result.execution_guidance.entry_valid_for_bars (when surfaced)
lineage consistency for analysis_batch_id and decision_session_id.

---

## 7. TRADEOUTCOME CONTRACT (docs/contracts/trade_outcome.md)

### 7.1 Purpose
Atomic system-level normalized outcome record attached to one DecisionEvent. Answers: after one normalized decision event exists, how should the system represent what eventually happened in a normalized, auditable, replay-compatible, and learning-compatible way?

### 7.2 Core Position
V7 extends V6 outcome in five ways: explicit simulation-family lineage, explicit cost-model/execution-assumption lineage, batch/session-aware grouping, optional evaluation-run/simulation-run identity, stronger decision-time context visibility.

### 7.3 Top-Level Shape
```
TradeOutcome
├── contract
├── identity
├── lineage
├── execution_summary
├── resolution_status
├── realized_outcome
├── path_metrics
├── comparative_outcome
├── quality_and_interpretation
├── observability
└── optional_extended_metadata
```

### 7.4 Contract Section
Required: outcome_schema_version, contract_version, event_schema_version.
Strongly recommended: simulation_family_version, comparative_family_version.

### 7.5 Identity Section
Required: trade_outcome_id, decision_event_id, timestamp_utc.
Recommended: trace_id, comparison_group_id, outcome_family_id.

### 7.6 Lineage Section
Required: request_id, engine_name, engine_version, request_kind, outcome_source.
Strongly recommended: analysis_batch_id, decision_session_id, model_scope, trade_mode, model_artifact_version, artifact_id, calibration_artifact_version, calibration_artifact_id, policy_artifact_version, cost_model_version, fee_model_version, slippage_model_version, execution_assumption_family, simulation_family_id, comparative_family_id.
Optional: candidate_source, replay_mode, paper_or_live_mode, snapshot_builder_version, state_schema_version, feature_schema_version, portfolio_artifact_version, risk_policy_version, evaluation_run_id, simulation_run_id, replay_run_id, monte_carlo_run_id, simulation_profile_version.
outcome_source: LIVE_EXECUTION, PAPER_EXECUTION, REPLAY_PROJECTION, OFFLINE_LABELING, SKIP_EVAL.

### 7.7 Execution Summary Section
Required: execution_path, execution_decision, position_opened.
Recommended: order_group_id, paper_trade_id, position_id, entry_timestamp_utc, exit_timestamp_utc, execution_block_reason.
execution_path: NOT_EXECUTED, PAPER_EXECUTED, LIVE_EXECUTED, REPLAY_ONLY, SKIPPED_BY_RUNTIME, BLOCKED_BY_RUNTIME.
execution_decision: EXECUTED, SKIPPED, BLOCKED, NOT_APPLICABLE.

request_kind × execution_path legality: live_scan→LIVE/PAPER_EXECUTED normal, replay_eval→REPLAY_ONLY normal, replay_eval→LIVE_EXECUTED suspicious, shadow→LIVE_EXECUTED in comparison-only suspicious.

### 7.8 Resolution Status Section
Required: outcome_status, is_final, resolution_reason.
Recommended: outcome_ready_timestamp_utc, pending_horizon_family, invalidity_reason.
outcome_status: PENDING, RESOLVED, PARTIALLY_RESOLVED, INVALIDATED, UNAVAILABLE.
resolution_reason: HORIZON_COMPLETE, TRADE_CLOSED, STOP_HIT, TARGET_HIT, TIME_EXIT, SKIP_EVAL_COMPLETE, DATA_INCOMPLETE, EXECUTION_INCOMPLETE.

### 7.9 Realized Outcome Section
Strongly recommended: best_realized_action, realized_return, realized_r, gross_pnl, net_pnl, fees_paid, slippage_cost, hold_duration_bars, hold_duration_minutes, exit_reason.
Optional audit-echo fields: decision_confidence_seen, decision_confidence_kind_seen, decision_expected_r_seen, decision_margin_seen, entry_readiness_seen, entry_valid_for_bars_seen, time_sensitivity_seen.
best_realized_action: LONG_NOW, SHORT_NOW, NO_TRADE, WAIT_1_BAR_LONG.
exit_reason: STOP_HIT, TARGET_HIT, TIME_EXIT, MANUAL_EXIT, RUNTIME_EXIT, PROJECTED_HORIZON_END, NOT_APPLICABLE.
realized_r should use normalized R-multiple semantics.

### 7.10 Path Metrics Section
Strongly recommended: mfe, mae, mfe_r, mae_r, time_to_mfe, time_to_mae, time_to_target, time_to_stop, target_hit_before_stop, stop_hit_before_target, path_quality_score.
Recommended: path_metric_family_version.

### 7.11 Comparative Outcome Section
Strongly recommended: counterfactual_best_action, counterfactual_second_best_action, regret_score, regret_r, missed_opportunity_score, saved_loss_score, alternative_action_gap.
Recommended no-trade fields: skip_regret_r, skip_saved_loss_r, skip_was_correct, no_trade_counterfactual_quality.

### 7.12 Quality And Interpretation Section
Strongly recommended: outcome_quality (HIGH/MEDIUM/LOW/AMBIGUOUS), outcome_label, is_good_decision, is_good_execution, is_good_no_trade, is_ambiguous, quality_flags.
Recommended: interpretation_version, label_interpretation_version.
outcome_label: CLEAN_LONG_OPPORTUNITY, CLEAN_SHORT_OPPORTUNITY, CORRECT_NO_TRADE, WRONG_DIRECTION, HIGH_REGRET_SKIP, DANGEROUS_TRADE, AMBIGUOUS_STATE, LOW_INFORMATION_STATE.

### 7.13 Observability Section
Strongly recommended: warnings, data_quality_flags, label_quality_flags, horizon_family, stop_logic_version, target_logic_version, cost_model_version_seen, simulation_family_version_seen, decision_policy_version_seen, portfolio_policy_version_seen, risk_policy_version_seen, payload_references, review_tags.
Optional context-seen: decision_time_portfolio_context, decision_time_exposure_tier, decision_time_cluster_pressure, decision_time_drawdown_state.

### 7.14 Creation Timing
Materialized AFTER a DecisionEvent exists and enough info available for at least initial resolution state. Initial record may be PENDING; later updates move to RESOLVED/PARTIALLY_RESOLVED/INVALIDATED. System should not wait until everything is final to create outcome object.

### 7.15 Replay Compatibility
Replay must materialize TradeOutcome using same semantic language as live and paper flows. Replay/live differences in lineage, source, horizon, optional metadata.

### 7.16 Validation Rules
Required sections/fields exist, decision_event_id resolves to valid decision event, execution_summary and resolution_status internally consistent, final outcomes have required realized/comparative fields, pending outcomes not masquerade as final, outcome source and lineage consistent, quality/interpretation labels legal for resolution state, protection from training on unresolved/invalid/mislabeled/inconsistent outcomes.

---

## 8. RUNTIME SIMULATION ENGINE (docs/runtime/simulation_engine.md)

### 8.1 Core Decision
Simulation runs in runtime. Runtime hosts the runtime simulation engine and owns simulation execution. V7 model does NOT own simulation. Pipeline must NOT reimplement a separate simulation engine. Training/labels/evaluation/paper trading/replay/outcomes/Monte Carlo consume runtime-hosted simulation engine through deterministic, side-effect-free adapters or drivers.

### 8.2 Ownership Rules
**Runtime owns:** simulation engine hosting, simulation execution orchestration, paper forward simulation, historical replay driver orchestration, simulation profile selection, simulation run lineage, separation between simulated truth and live execution truth.
**Model does NOT own:** simulation loops, stop/target/time-exit execution, replay execution, Monte Carlo robustness execution, TradeOutcome resolution. Model produces scoring/guidance (LONG_NOW/SHORT_NOW/NO_TRADE, expected-R surfaces, entry/stop/take-profit guidance inside selected model_scope).
**Pipeline consumes:** normalized simulation outputs, labels derived from simulation outputs, replay/evaluation outputs, Monte Carlo robustness summaries when configured. Pipeline may define consumption semantics/validation/lineage/dataset assembly. Must NOT create second label-only or backtest-only simulator.

### 8.3 Operating Modes
1. Paper forward simulation: runtime-owned, used for paper trading and paper outcomes, materializes DecisionEvent/TradeOutcome records without live execution.
2. Historical replay driver: runtime-owned replay over historical data, same runtime simulation engine with replay-safe inputs, must not call live exchange/broker/mutable account-state paths.
3. Training/replay adapter: deterministic side-effect-free adapter used by labels and dataset generation, builds simulation inputs from canonical historical state and future windows, emits versioned simulation outputs.
4. Evaluation replay adapter: deterministic adapter for walk-forward and candidate/baseline evaluation, preserves replay run IDs and simulation profile/version lineage.
5. Monte Carlo robustness mode: robustness/testing mode on top of runtime simulation engine, produces distributional evidence (expected-R distribution, downside risk, target-before-stop probability, stop-before-target probability, tail risk, confidence stability), does NOT replace paper forward simulation/historical replay/live execution truth.

### 8.4 Profiles And Adapters
Must support versioned profiles/adapters: V6 simulation profile, V7 simulation profile, model_scope/trade_mode profiles for SWING/SCALP/AGGRESSIVE_SCALP, cost/fee/slippage/stop/target/horizon profile families. Profile selection and adapter behavior config-driven through unified config system.

### 8.5 Execution Truth vs Simulated Truth
**Execution truth:** what actually happened through live or paper execution lifecycle paths.
**Simulated truth:** projected/counterfactual outcomes from runtime simulation engine.
Rules: live execution side effects must not occur during training/replay/evaluation/Monte Carlo. Replay/training adapters side-effect-free. Simulated outcomes preserve simulation run/profile lineage. Live execution outcomes preserve execution lineage. Monte Carlo evidence diagnostic/distributional, must not masquerade as actual realized outcome.

### 8.6 Required Output Semantics
Long/short/no-trade comparative outcomes, stop/target/time-exit/horizon-end semantics, fee and slippage application, realized R and net economic quality, MFE/MAE and path metrics, unresolved/invalidated status, simulation profile/version lineage, replay/evaluation/Monte Carlo run identity where used.

---

## 9. RUNTIME INTEGRATION (docs/runtime/runtime_integration.md)

### 9.1 Core Position
V7 runtime should NOT be rewritten from scratch right now. Runtime is: orchestration shell, execution shell, persistence shell, safety shell, lifecycle materialization shell. Engine stack owns market-state interpretation, score generation, confidence, expected R, recommended action, timing guidance, uncertainty/degradation visibility. Runtime owns orchestration/execution/persistence/lifecycle/runtime-hosted simulation engine execution/paper trading/replay/training-replay adapters/evaluation adapters/execution eligibility/safety gates/request assembly/result validation/event creation/outcome attachment/operational safeguards/scope_router selection/artifact selection and scope compatibility validation/blocking scope_mismatch to visible safe behavior.

### 9.2 Integration Flow
```
Market/Data State → Request Builder → AnalysisRequest → Scope Router (requested_trade_mode/model_scope) → Scope-Compatible Artifact Selection → Engine → AnalysisResult → Result Validator → Runtime Interpretation → DecisionEvent → Execution Eligibility → Execution/No Execution → TradeOutcome
```

### 9.3 Runtime Responsibilities
1. Request assembly: constructs valid AnalysisRequest from data state, config, optional portfolio/risk context, batch/session context.
2. Result validation: verifies returned AnalysisResult matches request, structurally valid, has required fields, internally consistent actionability and execution guidance.
3. Runtime interpretation: classify result further (actionable vs review-only, blocked vs degraded, persist vs skip, execution eligible vs not).
4. Event creation: create DecisionEvent immediately after valid normalized result exists.
5. Execution eligibility: apply operational gates before order placement.
6. Outcome lifecycle: create/update TradeOutcome as lifecycle information becomes available.
7. Simulation hosting: host/run runtime simulation engine for paper forward simulation, historical replay, training/replay adapters, evaluation replay adapters, Monte Carlo robustness mode. Adapter paths must be deterministic, side-effect-free, and must not call live exchange/broker/mutable account-state behavior.

### 9.4 Boundary Rules
**Engine must NOT own:** broker order submission, persistence schemas, trade outcome materialization, event creation, execution ledgers.
**Runtime must NOT own:** re-deriving model scores, silently rewriting engine decision, inventing hidden action semantics, replacing contract-defined fields with ad hoc local logic.

### 9.5 Actionability vs Execution Eligibility
**Engine actionability** comes from result-side fields: recommended_action, is_actionable, confidence, expected_r, timing guidance, degradation fields.
**Runtime execution eligibility** comes from operational gates: exchange availability, duplicate prevention, cooldowns, account state, risk hard limits, position constraints, runtime kill switches.
Rule: result may be economically actionable but operationally not executable. Runtime must record that distinction explicitly.

### 9.6 Recommended Execution Eligibility Stack (layered gates)
1. Structural validity: request/result match, required fields exist, no illegal values.
2. Engine actionability: is_actionable==true, recommended_action in {LONG_NOW, SHORT_NOW}.
3. Confidence gate: confidence >= min_confidence.
4. Economic gate: expected_r >= min_expected_r, optional expected_drawdown <= max_expected_drawdown.
5. Timing gate: initially advisory (inspect entry_readiness, entry_valid_for_bars), later optional hard gate (disallow MISSED, optionally disallow/down-rank CHASING).
6. Operational hard gate: exchange healthy, no duplicate position conflict, cooldown clear, not blocked by account/risk controls.

### 9.7 Minimum Runtime Changes
**Request side:** support V7 request shape (requested_trade_mode/model_scope), support runtime simulation profile lineage where request context used by replay/training adapters, support canonical_state, support batch/session lineage, preserve request versions.
**Result side:** support V7 result shape, validate timing extension fields, persist confidence/expected_r/timing fields.
**Event side:** create V7 DecisionEvent, include timing echoes from result, include runtime interpretation, include execution eligibility outcome.
**Outcome side:** create V7 TradeOutcome, include batch/session lineage, include optional evaluation_run_id/simulation_run_id/replay_run_id/monte_carlo_run_id, include runtime simulation profile/version and cost/simulation lineage if available.
**Observability side:** log actionability and execution eligibility separately, log timing extension fields, log suppression reasons explicitly.

### 9.8 Rollout Order
Phase 1: accept V7 request/result, validate, persist, create event/outcome objects.
Phase 2: add actionability gating, expected-R gating, timing observability.
Phase 3: add optional timing gating, expand event/outcome summaries, harden review/analytics surfaces.
Phase 4: runtime rework only after V7 contract family and pipeline are stable.

---

## 10. FALLBACK POLICY (docs/runtime/fallback_policy.md)

### 10.1 Core Position
Fallbacks are allowed. Hidden fallbacks are forbidden. Every fallback must be explicit, observable, testable, attributable to config/governed policy.

### 10.2 Fallback Taxonomy
1. Request degradation: missing HTF context, partial canonical state, stale data.
2. Artifact degradation: missing calibration artifact, stale policy artifact, unavailable portfolio context family, missing model_scope artifact, incompatible/non-scope-compatible artifact, scope_mismatch between request/artifact/calibration/policy.
3. Runtime context degradation: incomplete account state, incomplete exposure state, monitoring/telemetry lag.
4. Execution eligibility degradation: exchange state uncertain, duplicate-position state uncertain, kill-switch state uncertain.

### 10.3 Fallback Severity Priority (most conservative wins)
1. Hard execution safety uncertainty
2. Risk uncertainty
3. Portfolio uncertainty
4. Calibration/artifact uncertainty
5. Request quality degradation

### 10.4 Allowed Fallback Behavior
**Request side allowed:** continue with explicit degradation_context, preserve quality flags, mark stale/partial state. **Not allowed:** silently pretending degraded state is normal state.
**Calibration side allowed:** use explicit raw-confidence fallback only if policy allows, surface confidence_kind accordingly. **Not allowed:** silently passing raw confidence as calibrated confidence.
**Policy/result side allowed:** emit safe no-trade or degraded-safe interpretation, emit runtime_safe_action. **Not allowed:** silently forcing directional action from incomplete surfaces, silently falling back from one model_scope to another without explicit configured authority and visible safe behavior. Missing/incompatible model_scope artifact is explicit fallback/failure condition (usually NO_TRADE or SKIP).
**Runtime side allowed:** block execution, skip execution, persist reviewable event, create pending outcome. **Not allowed:** execute on unsafe fallback path without explicit authority.

### 10.5 Preferred Safe Actions
First-phase: NO_TRADE, SKIP, HOLD (preserve existing managed state until normal control resumes or separate explicit position-management rule applies). HOLD is not "take new risk." HOLD is conservative continuity.

### 10.6 Event/Outcome Recording Rule
If fallback/degradation affected behavior: DecisionEvent must record it (fallback_used, degraded_reason, runtime_safe_action, suppression_reason, runtime_actionability downgraded if applicable). TradeOutcome must remain compatible (non-execution, blocked execution, replay-only evaluation, pending/unavailable real outcome).

### 10.7 Artifact Staleness Rule
Config-governed. Policy defines at minimum: staleness unit (wall-clock age, bar age, release/version age), allowed stale-use modes (allowed, allowed with downgrade, forbidden).

### 10.8 Minimum Runtime Rules
1. Invalid input ≠ no-trade.
2. Degraded input ≠ normal input.
3. Missing artifact ≠ low confidence.
4. If unsure whether execution safe, safe non-execution is default unless explicit policy says otherwise.

---

## 11. DEPLOYMENT SAFETY (docs/runtime/deployment_safety.md)

### 11.1 Core Position
Deployment safety comes after contract correctness, simulation correctness, evaluation correctness. Do not use deployment complexity to compensate for weak contract or truth-layer discipline.

### 11.2 Rollout Modes
1. Replay-only: simulation verification, offline evaluation, regression testing.
2. Paper: live-ish operational validation, event/outcome lifecycle validation, actionability vs execution-eligibility review.
3. Shadow: V7 observes live state, records decisions, does not control execution authority. Optional for general experimentation. For first live-eligible release family, shadow treated as required unless explicit release authority waives it.
4. Live-eligible: only after contract family works, evaluation passes, monitoring in place, rollback exists, kill switch exists.

### 11.3 Minimum Deployment Gates
- request/result/event/outcome contract flow valid
- runtime-hosted simulation engine/simulated-truth layer in use
- candidate clears evaluation gate
- confidence surface calibrated or explicitly treated as uncalibrated
- no-trade quality reviewed
- fallback policy configured
- runtime safe actions defined
- monitoring baselines exist
- rollback path tested
- kill switch operational

### 11.4 Monitoring Baseline Rule
One promoted reference artifact family designated as primary baseline. One previous promoted baseline retained for regression comparison. Baseline windows and retention rules config-governed.

### 11.5 Promotion vs Live Eligibility
**Evaluation promotion gate:** is this artifact family good enough to become new promoted reference candidate?
**Live-eligibility gate:** even if promoted, is it operationally safe to influence live execution?
Model family may be: evaluation-promoted but only paper-eligible, evaluation-promoted and shadow-eligible, evaluation-promoted and live-eligible.
Eligibility per model_scope: SWING live eligibility does NOT imply SCALP live eligibility, SCALP does NOT imply AGGRESSIVE_SCALP.

### 11.6 Kill Switch Rules
At least: global kill switch, symbol-local or strategy-local disable where practical, execution disable without losing request/result/event recording, safe behavior under kill-switch activation. Kill switch activation blocks execution, preserves event visibility, emits monitoring-visible kill-switch state. Must not look like unexplained drop in activity.

### 11.7 Rollback Rules
Revert compatible artifact bundles per model_scope: promoted model family, promoted calibration family, promoted policy family where relevant. Preserves dependency compatibility. Model family rollback requiring matching calibration family → rollback together. Rollback changes forward authority, not past records.

### 11.8 Monitoring Preconditions (before live-eligible)
- fallback/degraded rates visible
- confidence/expected-R distributions visible
- no-trade rate visible
- actionability vs execution-eligibility gap visible
- outcome finality lag visible
- baseline comparisons exist
- kill-switch state visible in monitoring

### 11.9 Timing Extension Safety Rule
entry_readiness and entry_valid_for_bars remain observability-first by default. Must not become hard live gate unless: monitoring evidence exists, evaluation supports change, gating mode config-enabled.

---

## 12. PIPELINE SIMULATION (docs/pipeline/simulation.md)

### 12.1 Core Decision
One simulation truth layer across: label generation, OOS evaluation, runtime paper trading, historical replay, production-side outcome normalization. No separate cost model for labels vs evaluation.

### 12.2 Inputs
decision timestamp, symbol, primary interval, canonical market state lineage, future candle path, horizon family, stop family, target family, time-exit family, fee model, slippage model, simulation-family version. Optional: execution assumption family, entry timing annotation, replay/paper/live mode metadata.

### 12.3 Outputs
One comparative output family: long outcome, short outcome, no-trade outcome, exit reason, realized R net of costs, gross R before costs, fees and slippage cost, MFE/MAE, path quality score, saved-loss score, missed-opportunity score, regret relative to best action, resolution status, invalidity reason if applicable.

### 12.4 Exit Families
First-phase: STOP_HIT, TARGET_HIT, TIME_EXIT, HORIZON_END, UNRESOLVED, INVALIDATED.

### 12.5 No-Trade Rules
First-class, not absence of simulation. Must classify no-trade quality: correct no-trade, saved loss, missed opportunity, ambiguous no-trade. Required for classification labels, regression labels, calibration, evaluation.

### 12.6 Entry Timing Annotation Rule
First-phase: metadata only. Preserved for audit and later analysis. Must not silently shift canonical entry price or change first-phase action family. Timing-aware alternative entries require new simulation-family version.

### 12.7 Unresolved and Invalidated
UNRESOLVED: future window incomplete but may still complete. INVALIDATED: required future data cannot be completed safely/consistently. Default: unresolved remains unresolved until horizon completes. If still incomplete after 2×horizon → mark invalidated unless config overrides. Immediately invalidate known corrupted/irrecoverable future data.

### 12.8 Cost Model Rules
Must include: fee assumption, slippage assumption, net realized R after costs. Recommended version surfaces: cost_model_version, fee_model_version, slippage_model_version.

### 12.9 Rules
1. Market-first truth: evaluate market path, not legacy runtime actions.
2. Comparative truth: long, short, and no-trade evaluated together.
3. Cost-aware truth: fees and slippage mandatory.
4. Path-aware truth: terminal return alone not enough.
5. Pending is legal: incomplete windows stay unresolved.
6. Version meaning changes: stop/target/cost/horizon changes bump versions.

---

## 13. PIPELINE LABELS (docs/pipeline/labels.md)

### 13.1 Core Decision
Labels derived from single simulation truth layer. First-phase design explicitly hybrid: classification labels define action preference, regression labels define economic quality and risk. Market-first, cost-aware, comparative, no-trade aware.

### 13.2 Classification Label Fields
best_action_label (LONG_NOW/SHORT_NOW/NO_TRADE/AMBIGUOUS_STATE), second_best_action_label, long_success_label, short_success_label, no_trade_quality_label, skip_was_correct, label_validity, ambiguity_reason.

### 13.3 Regression Label Fields
long_realized_r_net, short_realized_r_net, long_realized_r_gross, short_realized_r_gross, long_cost_r, short_cost_r, long_mae_r, short_mae_r, long_mfe_r, short_mfe_r, regret_r, saved_loss_score, missed_opportunity_score, path_quality_score.

### 13.4 Lineage Fields
label_interpretation_version, simulation_family_version, cost_model_version, horizon_family_version.

### 13.5 Ambiguity Rule
If gap between best and second-best action below configured ambiguity threshold: set label_validity=AMBIGUOUS, best_action_label=AMBIGUOUS_STATE, preserve regression targets if valid, exclude from strict action-classification training by default unless config explicitly allows soft-label use. Do not force artificial action winners.

### 13.6 Unresolved/Invalid Rule
Unresolved simulation → label remains unresolved, strict supervised training excludes the row. Invalidated simulation → label invalid, invalidity reason preserved, strict supervised training excludes the row. No silent coercion.

### 13.7 Path Quality Buckets
HIGH (path_quality_score >= 0.70), MEDIUM (0.40 <= score < 0.70), LOW (score < 0.40). Thresholds config-driven and versioned.

### 13.8 skip_was_correct Rule
true when best action is NO_TRADE, or both directional actions fail minimum acceptable realized-R threshold, or saved-loss score exceeds configured threshold and no-trade preferred.

### 13.9 Config Surface Families
label interpretation version, minimum acceptable R, ambiguity threshold, no-trade correctness thresholds, saved-loss threshold, missed-opportunity threshold, path-quality thresholds, invalid/ambiguous filtering policy, regression target clipping policy.

---

## 14. PIPELINE FEATURES (docs/pipeline/features.md)

### 14.1 Core Decision
Features produced from canonical state only. Same feature row feeds both classification and regression heads. No separate feature pipelines for action classification vs economic regression in first phase.

### 14.2 Recommended Feature Groups
**4h primary decision features:** returns, candle geometry, range structure, volatility, momentum, trend/range state, local support/resistance distance where available.
**1d higher-timeframe context:** HTF trend alignment, HTF volatility regime, HTF range compression/expansion, HTF structure quality.
**1h refinement/timing context:** local momentum pressure, entry-zone distance, short-term volatility pressure, entry readiness indicators, local invalidation pressure. (Refinement/context features, not separate first-phase primary 1h model universe.)
**Global context:** symbol identity, session/time features, data-quality flags, missingness flags, regime metadata.

### 14.3 Rules
1. Canonical-state only.
2. No future bars, future labels, or outcome echoes.
3. Stable naming and grouping.
4. Missingness is explicit.
5. First phase stays boring and interpretable.
6. Features support shared multi-symbol modeling.
7. Feature semantics identical for training, replay, live inference.

### 14.4 Normalization Family
First-phase: fit on training split only, global across approved training universe, robust centering/scaling for continuous features where needed, no per-symbol normalization in first phase unless explicitly versioned later. Normalization lineage explicit when applied.

### 14.5 Missing Context Rules
HTF unavailable → emit fallback numeric values (preserve schema stability), emit explicit missing flags, keep degradation visible downstream. 1h refinement unavailable → preserve primary 4h features, emit 1h-missing flags, policy/runtime may degrade timing guidance or actionability based on config.

### 14.6 Symbol Identity Encoding
First-phase: compact one-hot encoding over approved symbol universe. If approved universe changes materially, bump feature schema or symbol-encoding family version.

### 14.7 Config Surface Families
feature schema version, enabled feature groups, normalization family, symbol-encoding family, missingness handling rules, feature clipping/winsorization rules, approved symbol metadata.

---

## 15. PIPELINE DATASET (docs/pipeline/dataset.md)

### 15.1 Core Decision
Valid V7 dataset row contains: canonical state lineage, feature row, classification labels, regression labels, simulation lineage, version lineage. No row valid without traceable upstream lineage.

### 15.2 Dataset Row Fields
feature vector, classification target fields, regression target fields, sample weights, symbol, primary interval, timestamp, feature schema version, label interpretation version, simulation family version, dataset family version, row validity status, exclusion reason where applicable.

### 15.3 Target Families
**Classification:** best_action_label, long_success_label, short_success_label, no_trade_quality_label.
**Regression:** long_realized_r_net, short_realized_r_net, long_mae_r, short_mae_r, long_mfe_r, short_mfe_r, regret_r, saved_loss_score, missed_opportunity_score, optional clipped/normalized target variants.

### 15.4 Rules
1. Temporal correctness: no future leakage across train/validation/test.
2. Shared-family rows: support one shared model family across symbols.
3. Symbol balance matters: no silent dominance by high-row-count symbols.
4. Unresolved rows stay out of strict supervised training by default.
5. Ambiguous rows explicit and excluded from hard action-classification training by default.
6. Split by time first, not IID random shuffle.
7. Preserve lineage for every row.
8. Classification and regression target availability tracked separately.

### 15.5 Symbol Balancing
First-phase: inverse-frequency sample weights by symbol, capped per-symbol row contribution before export. Default: preserve full row set, attach inverse-frequency symbol weights, cap only when symbol massively dominates corpus.

### 15.6 Walk-Forward Split Strategy
6 folds, minimum train window 12 months, validation window per fold 2 months, optional holdout/test tail after validation 1 month, advance window by validation length. No IID-style random split for primary evaluation.

### 15.7 Partial Target Policy
Rows may have valid classification targets but invalid regression targets, or opposite. Default: strict model training uses only rows valid for target head being trained. Row validity head-specific. Excluded rows preserve exclusion reason. No silent target imputation for labels.

### 15.8 Dataset Versioning Rule
Bump dataset_family_version when materially: feature schema meaning changes, label interpretation meaning changes, simulation family meaning changes, target transformation policy changes, symbol-universe policy changes, split family meaning changes, row validity policy changes.

---

## 16. PIPELINE MODEL (docs/pipeline/model.md)

### 16.1 Core Decision
XGBoost-first hybrid supervised decision model. Action selection is classification-first. Economic quality is regression-first. Both outputs exposed as first-class decision surfaces.

### 16.2 First-Phase Scope
One shared multi-symbol model family. No per-symbol model families. Primary decision interval 4h, HTF 1d, refinement 1h. Target universe up to 60 symbols. One fused decision surface per atomic request.

### 16.3 Output Surface
**Classification:** p_long_now, p_short_now, p_no_trade, classification_margin, optional per-action raw scores.
**Regression:** expected_r_long, expected_r_short, expected_drawdown_long/expected_mae_long, expected_drawdown_short/expected_mae_short, expected_cost_adjusted_r_long, expected_cost_adjusted_r_short, optional path-quality estimates.
**Metadata:** feature schema version, label version, model family version, target family version, training dataset version, calibration requirement flag.

### 16.4 Recommended Implementation Shape
First phase may use separate XGBoost models per target head:
```
classification:
  action_classifier or binary heads: LONG_NOW / SHORT_NOW / NO_TRADE
regression:
  long_expected_r_regressor
  short_expected_r_regressor
  long_adverse_pressure_regressor
  short_adverse_pressure_regressor
  optional cost_adjusted_expectancy_regressors
```

### 16.5 Rules
1. Shared model first: no per-symbol families in first phase.
2. Hybrid output first: classification and regression surfaces both first-class.
3. Compact artifact surface: outputs must stay calibratable and policy-wrappable.
4. Stable lineage: every artifact versioned and traceable.
5. No hidden runtime semantics: model recommends; runtime decides execution eligibility.
6. No regression-only decisioning: regression supports economic gates; policy still compares calibrated action evidence.
7. No raw-score trust: calibration must distinguish raw and calibrated surfaces.

### 16.6 Early Stopping Policy
Explicit validation folds from dataset split family. Early stopping enabled by default. Monitored validation objective per target head. Separate monitored metrics for classification and regression. Do not train to exhaustion by default.

### 16.7 Hyperparameter Surface
max_depth, n_estimators, learning_rate, min_child_weight, subsample, colsample_bytree, reg_alpha, reg_lambda, early_stopping_rounds, target-specific objectives, target-specific sample weighting.

### 16.8 Artifact Publishing Flow
Training may produce: candidate artifacts, rejected artifacts, promotable artifacts. Successful training may publish candidate artifact. Promotion controlled by evaluation and release policy. Failed/invalid runs must not publish promotable artifacts.

---

## 17. PIPELINE TRAINING (docs/pipeline/training.md)

### 17.1 Core Decision
Hybrid supervised training: classification heads for action selection, regression heads for economic quality, calibration artifacts for runtime-facing confidence. Training does NOT decide live execution eligibility. It produces candidate artifacts for evaluation.

### 17.2 Training Flow
Canonical Market State → Feature Engineering → Simulation Truth → Hybrid Labels (classification + regression) → Temporal Dataset/Walk-Forward Folds → XGBoost Hybrid Training (classifier heads: P(LONG_NOW), P(SHORT_NOW), P(NO_TRADE) + regressor heads: E[R|LONG_NOW], E[R|SHORT_NOW], expected adverse pressure, cost-adjusted expectancy) → Calibration Fit → Policy Evaluation → Candidate Artifact → Walk-Forward/Economic Evaluation → Promotion Review.

### 17.3 Rules
1. Training rows must be temporally valid.
2. Calibration rows must not be same rows used for core model fitting.
3. Classification and regression heads may use different valid row subsets.
4. Sample weighting must be explicit and reproducible.
5. Early stopping is default.
6. No unresolved or invalid labels in strict training.
7. No candidate promotion during training.
8. Failed target heads degrade explicitly; not silently omitted.

### 17.4 Objective Families
**Classification:** action multi-class objective, or separate binary objectives for long/short/no-trade. Chosen family config-declared and reflected in artifact metadata.
**Regression:** squared error for expected R, absolute error for robust expected R variants, quantile-style objectives where supported and explicitly versioned. Target clipping/transformation must be versioned.

### 17.5 Validation During Training
Track: classification log loss/AUC/precision by action, no-trade classification quality, regression MAE/RMSE by target, expected-R sign quality, economic monotonicity checks by predicted bucket, symbol/regime coverage. Training metrics are not promotion evidence by themselves.

---

## 18. PIPELINE CALIBRATION (docs/pipeline/calibration.md)

### 18.1 Core Decision
Calibration is first-class stage. Raw model scores not enough because runtime and policy may gate on confidence and actionability.

### 18.2 First-Phase Scope
Global calibration first. No per-symbol calibration family in first phase. No per-regime calibration family. Symbol/regime breakdowns evaluated, not automatically split into calibration families.

### 18.3 Inputs
Raw classification outputs, raw regression outputs where relevant, validation/calibration-eligible data, calibration config, calibration family version.

### 18.4 Outputs
Calibrated action probabilities, calibrated confidence, confidence_kind, reliability metrics, calibration lineage, mapped score surfaces where approved.

### 18.5 Classification Calibration
Primary calibration to: p_long_now, p_short_now, p_no_trade, decision confidence, action margin confidence. Runtime-facing confidence must clearly identify: raw, calibrated, degraded, unavailable.

### 18.6 Regression Reliability
Not calibrated same way as probabilities, but reliability must be measured. First-phase checks: predicted expected-R bucket vs realized average R, sign correctness by bucket, error distribution by symbol/regime, adverse-pressure prediction quality, cost-adjusted expectancy bucket quality. If weak → policy must be able to degrade or ignore affected economic gate explicitly.

### 18.7 Calibration Split Rule
Must use calibration-eligible validation slice distinct from core model fitting rows. May share same walk-forward family as evaluation but: must not be fit on same rows used for model fitting, must remain traceable as separate calibration slice.

### 18.8 Recalibration Policy
Produce new calibration artifact when: new candidate model family intended for evaluation, calibration config changes materially, monitoring detects calibration drift beyond configured limit, classification output semantics change.

### 18.9 Rules
1. Runtime confidence matters.
2. Raw scores are not calibrated confidence.
3. Global first.
4. Reliability measured before trusted.
5. Calibration meaning changes are versioned.
6. Regression reliability issues degrade economic gates explicitly.

---

## 19. PIPELINE POLICY (docs/pipeline/policy.md)

### 19.1 Core Decision
Policy is where learned evidence becomes a decision. Combines: calibrated action probabilities, calibrated confidence, expected R estimates, adverse-pressure estimates, cost-adjusted expectancy, no-trade quality, decision margins, timing/refinement signals.

### 19.2 Decision Gates (directional action must pass all)
1. Probability/confidence gate
2. No-trade comparison gate
3. Decision margin gate
4. Expected-R gate
5. Cost-adjusted expectancy gate
6. Adverse-pressure/drawdown gate
7. Degradation/fallback gate

If any required gate fails → policy selects NO_TRADE or degraded-safe behavior.

### 19.3 Tie-Break Rule
1. Evaluate directional actions against gates.
2. If both fail → NO_TRADE.
3. If one passes and beats NO_TRADE by configured margin → select it.
4. If both pass → choose better policy score after economic quality adjustment.
5. If long/short too close → NO_TRADE.

### 19.4 Policy Score
policy_score(action) = calibrated_action_probability_component + expected_r_component - adverse_pressure_component - friction_component + path_quality_component - uncertainty_penalty. Exact weights in config, versioned.

### 19.5 Timing Extension Rule
entry_readiness and entry_valid_for_bars are policy-derived first phase. May use: 1h refinement features, entry-zone distance, local momentum pressure, time-sensitivity heuristics, margin decay signals if configured. Advisory-first, not primary action targets.

### 19.6 Failure/Fallback
If policy cannot safely produce clean actionable decision: emit NO_TRADE or degraded-safe behavior, preserve fallback/degradation visibility, do not emit confident but structurally incomplete actions.

### 19.7 Config Surface Families
minimum action probability, minimum confidence, minimum expected R, minimum cost-adjusted expectancy, drawdown/adverse-pressure limits, no-trade thresholds, policy score weights, decision margin, timing extension enablement, degraded-result behavior.

---

## 20. PIPELINE PORTFOLIO (docs/pipeline/portfolio.md)

### 20.1 Core Decision
Designed for centralized multi-symbol world. Portfolio logic first-class but lightweight in first phase. Not the model and not a full optimizer.

### 20.2 Inputs
Policy-approved candidate results, action probabilities, expected R by action, confidence, current portfolio context, exposure state, symbol cluster/correlation metadata, portfolio config.

### 20.3 Outputs
pass/suppress/down-rank/annotate, portfolio interpretation, suppression reason if blocked, ranking metadata where relevant, portfolio pressure score where configured.

### 20.4 Ranking Rule (first-phase)
1. Policy-approved actionability
2. Expected-R quality
3. Cost-adjusted expectancy
4. Confidence as secondary ordering
5. Portfolio pressure adjustments
6. Deterministic tie-break by symbol order only as last resort

Use suppression instead of down-ranking when: hard portfolio cap exceeded, cluster concentration breaches configured limits, portfolio context degraded and config requires safe non-execution.

### 20.5 Rules
1. Portfolio is not the model.
2. Portfolio suppression must be visible.
3. Portfolio should not hide risk vetoes.
4. Lightweight first phase.
5. Regression expected-R can inform ranking but cannot override hard caps.

### 20.6 Cluster Definition (first-phase)
Approved manual groupings, stable correlation-based groups computed offline and versioned. Do not compute ad hoc runtime clusters without versioned grouping family.

### 20.7 Portfolio Context Unavailable Rule
Degrade explicitly. Default first-phase behavior: safe non-execution unless config explicitly allows lighter fallback. Do not silently assume zero portfolio pressure.

### 20.8 Config Surface Families
max open positions, exposure caps, cluster grouping rules, portfolio suppression thresholds, ranking family, portfolio context fallback behavior.

---

## 21. PIPELINE RISK (docs/pipeline/risk.md)

### 21.1 Core Decision
Risk separate from model, calibration, policy, and portfolio. Trade can be economically attractive and still operationally unsafe.

### 21.2 Stage Order (first-phase)
1. Policy
2. Portfolio
3. Risk
4. Runtime execution eligibility

If both portfolio and risk block: preserve both signals when available. Treat risk as final hard gate when block is risk-hard.

### 21.3 Rules
1. No hidden risk veto.
2. Hard guards stay hard.
3. Model confidence and expected R cannot override operational limits.
4. Keep risk readable.
5. Separate economic actionability from execution eligibility.

### 21.4 Recommended First-Phase Controls
Global kill switch, cooldown after loss/major event, max gross exposure, max per-symbol exposure, max cluster exposure, duplicate-position protection, stale-result rejection, degraded-result safe action rules, minimum account/context integrity requirements.

### 21.5 Cooldown Rule
Configurable by: trigger family, duration in bars or minutes, scope (global, symbol-local, direction-local).

### 21.6 Duplicate Protection
Detect at minimum: same symbol same direction existing open position, same symbol same direction already accepted decision in same batch/session where duplication forbidden.

### 21.7 Degraded Result Handling
If classification surfaces valid but regression surfaces degraded, policy may already select no-trade. If such result reaches risk, risk must still see degradation flag. If risk context unavailable → degrade explicitly, prefer safe non-execution when required by config.

### 21.8 Config Surface Families
kill-switch settings, cooldown rules, exposure hard limits, stale-result limits, degraded-result behavior, duplicate protection rules, minimum context requirements.

---

## 22. PIPELINE EVALUATION (docs/pipeline/evaluation.md)

### 22.1 Core Decision
Economic-quality-first evaluation. Not judged by accuracy/confidence/hit rate alone. Judged by: realized R, expectancy, regret, no-trade quality, calibration quality, regression reliability, path quality, symbol/regime stability, safety behavior.

### 22.2 Walk-Forward Family (first-phase)
6 folds, minimum train window 12 months, validation window 2 months, optional holdout tail 1 month. Dataset owns fold construction. Evaluation owns fold consumption and interpretation.

### 22.3 Metric Families
**Economic:** realized R, net expectancy, profit factor, max drawdown, average trade R, cost-adjusted R, regret distribution, saved-loss/missed-opportunity quality.
**Classification:** action accuracy where meaningful, precision/recall by action, no-trade classification quality, confusion matrix for LONG/SHORT/NO_TRADE, action probability bucket quality.
**Regression:** MAE/RMSE for expected R heads, sign correctness for expected R, predicted-R bucket vs realized-R average, adverse-pressure error, cost-adjusted expectancy error, symbol/regime regression breakdowns.
**Calibration:** reliability error, confidence bucket behavior, no-trade calibration quality, forward-period stability.

### 22.4 No-Trade Quality
Must measure: correct skip, saved loss, missed opportunity, over-suppression, under-suppression. Model that avoids all trades may look safe but is not automatically good.

### 22.5 Ablation Requirement
First-phase interval-view ablation: 4h only, 4h + 1d, 4h + 1d + 1h. 1h refinement must prove value through evidence.

### 22.6 Promotion Gate (never single scalar)
Minimum gate families: realized-R quality threshold, no-trade quality threshold, calibration quality threshold, regression reliability threshold, symbol/regime stability threshold, no critical safety regression, no unacceptable portfolio/risk suppression regression. Threshold values in config.

### 22.7 Replay vs Live Evidence Rule
Replay-only evidence may justify: candidate continuation, deeper review, paper deployment. Live-eligible authority should not rely on replay alone when release policy requires paper/live evidence.

### 22.8 Baseline Policy
Compare candidates against: 1. current promoted baseline model family, 2. last accepted evaluation baseline for same evaluation family. When candidate promoted → becomes new promoted baseline, previous baseline retained per artifact policy.

---

## 23. PIPELINE MONITORING (docs/pipeline/monitoring.md)

### 23.1 Core Decision
Must observe both model quality surfaces and system lifecycle surfaces. For hybrid modeling: action probability drift, expected-R drift, regression reliability drift, calibration drift, no-trade/action mix drift.

### 23.2 Recommended Monitoring Families (minimum first-phase)
- request/result validation failure rate
- fallback/degraded rate
- calibrated confidence distribution
- action probability distribution
- expected-R distribution
- expected adverse-pressure distribution
- no-trade rate
- long/short/no-trade action mix
- actionability vs execution-eligibility gap
- symbol and regime coverage
- interval-view coverage integrity
- 1h refinement availability rate
- timing-extension distribution
- outcome finality lag
- feature drift
- regression reliability drift

### 23.3 Calibration Drift
Monitor: reliability error, confidence bucket realized quality, no-trade confidence quality, per-symbol/per-regime reliability breakdowns. Confidence used in runtime requires reliability evidence.

### 23.4 Regression Drift
Monitor: predicted expected-R bucket vs realized average R, expected-R sign quality, adverse-pressure prediction quality, cost-adjusted expectancy bucket quality, error distribution by symbol/regime. If degrades → policy may need to raise economic gates, ignore affected heads, or degrade to no-trade.

### 23.5 Feature Drift
Feature distribution shift, missingness-rate shift, HTF availability shift, 1h refinement availability shift, symbol mix shift.

### 23.6 Timing Extension Decision Rule
May move from observability-only to gating-enabled only when: timing states show stable predictive usefulness across multiple windows, CHASING/MISSED states repeatedly correspond to worse outcomes, evidence crosses configured promotion threshold. Until then, entry_timing_used_for_gate should remain false.

### 23.7 Outcome Finality Lag
Track: median lag, tail lag, unresolved fraction by horizon family. If exceeds thresholds → raise data-quality/pipeline-health signal, do not treat missing outcomes as stable absence.

### 23.8 Baseline Update Policy
Monitoring baselines reference: 1. current promoted artifact family, 2. previous promoted artifact family, 3. optional longer historical aggregate baselines. When promotion occurs, promoted artifact becomes new primary monitoring baseline.

---

## 24. LLM WORKING RULES (docs/v7_llm_rules.md)

### 24.1 Core Position
V7 optimized for: local changes, explicit boundaries, small analyzable files, deterministic behavior, easy test execution, measurable quality at every layer. Main rule: code agent should understand one concern by reading one primary doc, one primary module, one config surface, one test surface.

### 24.2 LLM Working Rules
1. Read authority first (task-specific authority doc → relevant contract docs → runtime/policy doc → existing config surface → implementation files → tests).
2. Inspect before editing (classify files as KEEP/COMPLETE/FINISH/FIX/REPLACE/REMOVE/INSPECT_FURTHER).
3. Preserve valid work (keep working code, finish partial, fix incorrect, replace only when clearly conflicts with authority).
4. Do not invent semantics (if behavior not defined by authority docs/contracts/runtime policy/config defaults/existing implementation patterns → stop and report ambiguity).
5. One concern, one primary edit path (touch one primary module + one config surface + one test surface).
6. Config is the only control surface (any new threshold/toggle/constant/ratio/window/runtime setting must go through central config system).
7. Hidden fallbacks forbidden (if system degrades/skips/falls back → must be explicit, observable, testable).
8. Every non-trivial change must be tested.
9. Highest-risk test first.
10. Prefer simple Python over framework cleverness (explicit functions, small classes, direct data flow, typed structures; avoid decorator-heavy hidden behavior, runtime monkey patching, side-effectful global module initialization, implicit registry mutation).

### 24.3 Repository Shape (recommended)
```
src/
  v7/
    cli/
    config/
    contracts/
    state/
    simulation/
    features/
    labels/
    dataset/
    model/
    calibration/
    policy/
    portfolio/
    risk/
    runtime/
    evaluation/
    monitoring/
tests/
  unit/
  integration/
  regression/
configs/
docs/v7/
```

### 24.4 Maximum File Size Guidance
**Docs:** ideal 600-1500 words, soft 2000, hard 2500.
**Python:** ideal 150-350 lines, soft 500, hard 700.
**Tests:** ideal 120-300 lines, soft 400, hard 550.

### 24.5 Python Writing Rules
Prefer explicit modules (one job per module). Prefer pure functions where possible. Keep orchestration thin. Use type hints everywhere practical. Use typed structures for contracts/config/state/records. Avoid deep inheritance (composition over inheritance). Avoid hidden mutable global state. Function size: ideal 10-35 lines, soft 50, hard 80. Parameter lists: ideal 3-6, soft 8, beyond that use typed context object. Prefer stable naming mapping directly to docs.

### 24.6 Formatting and Tooling
Required: ruff, black, pytest, mypy/pyright for core typed surfaces. Line length 100. Imports grouped/sorted automatically. Docstrings only where they add value. Comments explain why, not what. Structured logging preferred, no noisy debug spam in core loops, logs expose degradation/fallback/state transitions.

### 24.7 Error Handling Rules
1. Fail early on invalid config (raise immediately).
2. Use explicit domain errors where useful (small number of meaningful exception classes per core subsystem).
3. Do not silently swallow errors (return structured degradation/fallback info where appropriate).
4. Separate invalid input from expected no-action behavior (invalid state ≠ no trade, degraded request ≠ successful normal path).

### 24.8 Test Strategy
**Unit:** isolated pure logic (cost calculations, stop/target resolution, threshold gating, label comparison, feature transforms, config validation).
**Integration:** boundaries between modules (request→state→features, model→calibration→policy, decision event→outcome linkage, config loader→resolved config).
**Regression:** when bug fixed, preserve with focused regression test.
**Contract:** every core contract tests required/forbidden/optional fields, versioning behavior, serialization round-trip.
**Golden-path simulation:** stop hit first, target hit first, timeout exit, fee/slippage effect, long vs short vs no-trade comparative outcome.

### 24.9 Quality Measurement Levels
A. Code quality: lint/format/type-check/test pass, function/file size compliance, import cycle absence.
B. Contract quality: stable field definitions, no hidden required fields, explicit optionality, clear versioning, schema/serialization tests.
C. Simulation quality: deterministic same-input results, cost-model correctness, outcome path correctness, counterfactual consistency, parity between labeling and evaluation semantics.
D. Model pipeline quality: feature schema stability, training/inference schema parity, calibration metrics, no-trade quality, symbol/regime breakdowns, forward evaluation metrics.
E. Documentation quality: file size within limits, low repetition, explicit ownership boundaries, explicit out-of-scope sections, stable terminology reuse.

### 24.10 Fixture Rules
Preferred: synthetic candle windows, synthetic state objects, tiny model stubs, tiny config fixtures, tiny outcome scenarios. Avoid: giant historical datasets in unit tests, hidden shared fixtures that do too much, flaky time-dependent fixtures, live network calls.

### 24.11 Documentation Writing Rules (per technical doc)
Sections: Purpose, In Scope, Out of Scope, Authority, Inputs, Outputs, Invariants, Rules, Failure/Fallback, Config Surface, Interfaces/Integration Points, Test Requirements, Non-Goals, Links. One document = one concern. Do not repeat semantic definitions across many docs. Link rather than restate. State forbidden changes explicitly. State ownership explicitly.

---

## 25. DOC WRITING GUIDE (docs/v7_doc_writing_guide.md)

### 25.1 Core Position
V7 docs must be written for execution, not decoration. Help human/LLM quickly answer: what this document controls, what it does not control, what is stable, what can change, what other docs are authoritative, what implementation work is allowed, what assumptions are forbidden.

### 25.2 Primary Writing Principles
1. Write for authority, not prose beauty (direct statements, short sections, named rules, explicit invariants, explicit non-goals).
2. One document, one primary job.
3. Define scope explicitly (what's in scope, out of scope, allowed to define, must be defined elsewhere).
4. Prefer explicit lists over buried rules.
5. Stable meaning first, examples second.
6. Additive evolution over silent mutation.

### 25.3 LLM-Optimized Writing Rules
1. Put decision-bearing content early (Purpose, Core Position, In/Out Scope, Hard Rules/Invariants, Structure/Fields/Interfaces, Failure/Fallback, Links).
2. Use stable section names across files (Purpose, Core Position, In Scope, Out of Scope, Inputs, Outputs, Rules, Invariants, Failure/Fallback, Versioning, Relationship To Other Documents, Bottom Line).
3. Keep paragraphs short (one idea per paragraph, one rule per bullet, one semantic block per section).
4. Name constraints explicitly (must, must not, should, should not, in scope, out of scope, forbidden, required, additive only).
5. Separate semantic layers clearly (vision, architecture, config, contract, implementation plan, runtime policy, report output).
6. Avoid pronoun-heavy writing (prefer AnalysisRequest must include... over it should include...).
7. Use semantic repetition, not textual repetition (short reminder + link to primary authority, not full redefinition).
8. Optimize for chunk retrieval (any 10-30 line chunk carries meaning).

### 25.4 Avoid
Doc hell through phase explosion (one roadmap + one implementation plan + generated reports in separate area). Same rule copied across many docs (one authority, rest link). Hidden authority (follow-up note becomes real source of truth). Mixed stable/unstable content. Vague ownership. Giant wall-of-text sections.

---

## 26. IMPLEMENTATION PHASES (docs/implementation/)

### 26.1 Master Plan (docs/implementation/master_plan.md)
**Stable decisions:** contract-first with atomic lifecycle family, one simulation truth layer, XGBoost-first, centralized/multi-symbol/runtime-engine separated, runtime owns assembly/validation/lifecycle/persistence/execution safety, engine owns state-interpretation/scoring/confidence/expected-R/timing/degradation, first-phase action family compact (LONG/SHORT/NO_TRADE).
**Resolved hybrid strategy:** classification surface (action probabilities) + regression surface (expected_r_long/short, optional adverse/cost-adjusted) + policy surface (calibrated probability + expected-R + risk gates).
**Scope rule:** one shared training framework with separate model_scope artifacts (SWING/SCALP/AGGRESSIVE_SCALP). Do not train one universal artifact across incompatible scopes. First implementation may stage SWING first.
**Hard dependencies:** Phase 1→0, 2→1, 3→2, 4→2+3, 5→4, 6→5, 7→6, 8→5+6+7, 9→8.
**Soft iteration loops:** Phase5↔6, 6↔8, 7↔8.
**Global success criteria:** typed contracts validate hybrid outputs, runtime simulation powers labels/evaluation/outcomes/replay/paper/Monte Carlo through side-effect-free adapters, labels include classification+regression targets, datasets preserve target lineage and exclude unresolved/invalid, feature/dataset surfaces leakage-safe, hybrid XGBoost baseline trains and loads scope-compatible artifacts, calibrated confidence available or explicitly downgraded, expected-R reliability measured and visible, policy emits compact normalized decisions using probability+expected-R+risk gates, portfolio/risk blocks explicit, runtime persists hybrid score snapshots in decision lifecycle records, evaluation compares candidate vs baseline economically and by hybrid-surface quality, deployment safety gates/rollback bundles/kill switch testable.

### 26.2 Phase 0 — Repo Alignment & Hybrid Foundations
**Goal:** create module skeletons, config skeleton, contract types, test scaffolding.
**Workstream A — Repository Skeleton:** src/v7/ with concern-focused subpackages (contracts, config, simulation, labels, features, dataset, model, calibration, policy, portfolio, risk, runtime, evaluation, monitoring). Model package ready for action classifier artifacts, expected-R regressor artifacts, model-suite bundle metadata, scope-compatible artifact loading. Contract package ready for action probabilities, expected-R-by-action fields, risk/economic estimates, confidence kind and calibration lineage.
**Workstream B — Config Foundations:** one V7 config family. Minimum config groups: system, symbols, model_scope, simulation, labels, features, dataset, model, calibration, policy, portfolio, risk, evaluation, deployment. Hybrid config must express enabled model_scope values, action-classification target family, regression target family, XGBoost classifier/regressor hyperparameters, per-surface early stopping metrics, calibration method for classifier confidence, expected-R reliability review settings, policy gates for confidence/expected-R/drawdown/no-trade margin. Merge order: checked-in defaults → environment config overlay → local developer override (if explicitly enabled) → environment variables → explicit CLI/runtime overrides. Unknown keys fail by default.
**Workstream C — Typed Foundations:** ValidationError, ConfigError, ArtifactCompatibilityError. Reusable helpers: to_dict(obj), from_dict(payload), validate_or_raise(obj).
**Workstream D — Test Scaffolding:** package import smoke tests, config load tests, unknown config key failure tests, typed helper round-trip tests, bootstrap pytest path.
**Pre-run audit:** confirm only one V7 package root exists, confirm central config can express hybrid output settings, confirm no separate hidden config controls model outputs, confirm tests run locally.

### 26.3 Phase 1 — Contracts & Hybrid Validation
**Goal:** implement four V7 lifecycle contracts as typed runtime surfaces, make hybrid model outputs explicit and validateable.
**Workstream A — Typed Contract Objects:** AnalysisRequest (request_id, contract_version, symbol, model_scope, requested_trade_mode, primary_interval, context_intervals, refinement_intervals, state_timestamp_utc, feature_schema_version, label_horizon_family, simulation_profile_version, runtime_context, degradation/missingness flags). AnalysisResult must support hybrid surfaces: result_id, request_id, contract_version, response_schema_version, model_scope, artifact_id, calibration_artifact_id, recommended_action, is_actionable, action_probabilities (LONG/SHORT/NO_TRADE), confidence, confidence_kind, expected_r_by_action (LONG/SHORT), expected_drawdown_r_by_action, expected_cost_adjusted_r_by_action, policy_gate_status, policy_reason_codes, entry_readiness, entry_valid_for_bars, degradation_flags. DecisionEvent must snapshot final decision and supporting hybrid surfaces. TradeOutcome must support comparison between projected probabilities, projected expected R, realized outcome R, exit reason, no-trade/missed-opportunity/saved-loss.
**Workstream B — Contract Validation:** check required field presence, enum legality, numeric bounds, probabilities sum within configured tolerance, no negative/impossible probabilities, expected-R numeric or explicitly unavailable, model_scope compatibility, artifact/calibration/policy bundle compatibility, timing extension bounds, actionability vs execution eligibility separation. Timing defaults: entry_valid_for_bars integer 0-5, entry_readiness legal enum only. Hybrid validation: recommended_action in {LONG/SHORT/NO_TRADE}, action_probabilities include all three, if directional action actionable its expected-R surface present unless degraded, raw confidence never mislabeled as calibrated.
**Workstream C — Serialization/Round-Trip:** obj.to_dict(), ContractType.from_dict(payload). Version compatibility: major contract-family mismatch fails, same-family newer minor versions may load only if active required fields exist, unknown optional fields preserved or explicitly ignored.
**Pre-run audit:** no active V7 flow depends on unvalidated dict payloads, all hybrid result fields have defined names/types, scope mismatch cannot silently fall through to another artifact, raw vs calibrated confidence distinction test-covered.

### 26.4 Phase 2 — Runtime Simulation, Replay & Monte Carlo
**Goal:** standardize runtime-hosted simulation engine used by labels/evaluation/replay/paper/outcomes/Monte Carlo.
**Workstream A — Runtime Simulation Engine Standardization:** evaluate LONG/SHORT/NO_TRADE. Minimum outputs: realized_r_long, realized_r_short, no_trade_outcome_quality, saved_loss_score, missed_opportunity_score, best_action, second_best_action, action_gap_r, resolution status.
**Workstream B — Profiles, Costs, Exit, Horizon:** versioned config families for simulation_profile_version, runtime_simulation_adapter_version, cost_model_version, fee_model_version, slippage_model_version, horizon_family, stop_family, target_family, time_exit_family, invalidation_multiplier. Default: unresolved remains unresolved while approved future window may complete; becomes invalidated after 2×configured horizon length; immediate invalidation for irrecoverable/corrupted future data.
**Workstream C — Side-Effect-Free Adapters:** training/replay adapter, evaluation replay adapter, historical replay driver, paper forward simulation driver. Outputs preserve simulation_run_id, replay_run_id, simulation_profile_version, cost_model_version, horizon_family, model_scope.
**Workstream D — Path Metrics and Monte Carlo:** mfe_r, mae_r, time_to_mfe, time_to_mae, path_quality_score. Monte Carlo: expected-R distribution, downside risk, target-before-stop probability, stop-before-target probability, tail risk, confidence stability. Monte Carlo diagnostic/distributional, does not replace realized simulation truth. Timing annotations metadata-only in first phase.

### 26.5 Phase 3 — Hybrid Labels & Outcome Semantics
**Goal:** convert runtime simulation outputs into hybrid supervised target family.
**Workstream A — Classification Label Builder:** best_action_label in {LONG/SHORT/NO_TRADE/AMBIGUOUS_STATE}, second_best_action, action_gap_r, regret_r, skip_was_correct, saved_loss_score, missed_opportunity_score, path_quality_bucket, label_validity.
**Workstream B — Regression Target Builder:** expected_r_target_long = realized_r_long, expected_r_target_short = realized_r_short. Optional: adverse_r_target_long = mae_r_long, cost_adjusted_r_target_long = net_realized_r_long, etc. Directional regression targets valid only when corresponding simulated directional action resolved. Invalid/unresolved → marked invalid, not coerced to zero.
**Workstream C — Ambiguity & Path Quality:** default ambiguity_gap_r_threshold = 0.15, path_quality_high = 0.70, medium = 0.40, min_acceptable_directional_realized_r = 0.25.
**Workstream D — TradeOutcome Alignment:** outcome_label, is_good_decision, is_good_no_trade, realized_vs_projected_r_error.
**Pre-run audit:** no unresolved simulation becomes valid training target, ambiguous states not forcibly coerced, regression targets not fake-filled with zeros, labels consume runtime simulation adapter outputs only, no label-only simulator exists.

### 26.6 Phase 4 — Features & Hybrid Dataset
**Goal:** turn canonical state and hybrid labels into leakage-safe feature rows and walk-forward dataset families.
**Workstream A — Feature Builder:** 4h primary features, 1d HTF context, 1h refinement/timing, symbol identity/metadata, regime/volatility, missingness/degradation flags. One fused row per evaluated market state.
**Workstream B — Normalization & Schema:** fit statistics on training window only, apply to that fold's validation/calibration/holdout, fit separately per fold, do not reuse across folds unless explicitly versioned.
**Workstream C — Hybrid Dataset Assembly:** each row includes row_id, symbol, model_scope, primary_interval, context_intervals, refinement_intervals, state_timestamp_utc, feature_schema_version, label_interpretation_version, simulation_profile_version, cost_model_version, slippage_model_version, horizon_family, simulation_run_id, replay_run_id, monte_carlo_run_id (when configured), dataset_family_version, classification_target, classification_target_validity, expected_r_target_long/short, expected_r_target_long/short_validity, optional adverse/cost-adjusted targets, sample_weight, symbol_weight. Per-target validity: row can be valid for classification but invalid for one regression target. Scope rule: do not mix model_scope/primary clock/label horizon inside one supervised dataset family.
**Workstream D — Splits and Symbol Balancing:** fold_count=6, min_train_window=12m, validation_window=2m, holdout_window=1m. Balancing: inverse-frequency sample weights, cap max relative symbol weight ratio at 5.0, hard row caps only if weighting fails.
**Pre-run audit:** features use canonical state only, dataset rows preserve simulation adapter lineage, regression targets not fake-filled, target validity masks present, no single symbol dominates rows/weights silently, dataset assembly has no live execution side effects.

### 26.7 Phase 5 — XGBoost Hybrid Model Baseline
**Goal:** train first V7 hybrid model baseline and publish candidate artifacts.
**Workstream A — Hybrid Baseline Trainer:** Default first baseline per activated model_scope: Action classifier (XGBoost multiclass, target best_action_label, classes LONG/SHORT/NO_TRADE, output action_probabilities), Long expected-R regressor (XGBoost regressor, target expected_r_target_long, output expected_r_long), Short expected-R regressor (similar). Optional: adverse-R, cost-adjusted-R regressors only if target quality adequate. Non-goals: do not start with three unrelated binary classifiers, do not make regression only decision source, do not let expected-R regressors directly bypass policy, do not bundle incompatible scopes in one model.
**Workstream B — Reproducibility & Early Stopping:** classifier: mlogloss, expected-R regressors: rmse. Hyperparameters: max_depth, n_estimators, learning_rate, min_child_weight, subsample, colsample_bytree, reg_alpha, reg_lambda, early_stopping_rounds, objective/metric by head.
**Workstream C — Artifact Publishing:** bundle includes model_scope, action_classifier_artifact, expected_r_long/short_artifact, optional risk_regressor_artifacts, feature_schema_version, label_interpretation_version, simulation_profile_version, training_dataset_version, head_metrics, training_run_id, status="candidate", promotable=False. Phase 5 may publish candidate artifacts only. Phase 8 may mark evaluation-promotable. Phase 9 may mark live-eligible.
**Recommended latency targets:** atomic inference p95 ≤ 50ms, 60-symbol scan p95 ≤ 5s.

### 26.8 Phase 6 — Calibration, Expected-R Reliability & Policy
**Goal:** turn raw hybrid model outputs into calibrated, policy-shaped decision surfaces matching AnalysisResult.
**Workstream A — Classification Calibration:** per model_scope. Calibration slice: training window = model fit, first half validation = early stopping/model selection, second half validation = calibration fit, holdout tail untouched for evaluation. Outputs: calibrated action probabilities, calibrated confidence, confidence_kind, reliability metrics, calibration lineage.
**Workstream B — Expected-R Reliability Review:** MAE/RMSE by fold, signed bias by fold, rank correlation predicted vs realized R, bucketed realized-R by predicted-R bucket, long/short separate quality, symbol/regime slices. Outputs: expected_r_kind, expected_r_reliability_grade, per-head error summaries, fallback/downgrade reason if unreliable.
**Workstream C — Decision Policy Core:** Directional action actionable only if: confidence gate passes, action probability beats no-trade by configured margin, expected-R gate passes, drawdown/adverse gate passes (if enabled), expected-R surface not degraded beyond configured tolerance. If confidence passes but expected-R fails → NO_TRADE. If expected-R passes but confidence fails → NO_TRADE. If long/short too close → NO_TRADE.
**Workstream D — Timing Advisory Surface:** entry_readiness (READY_NOW, WAIT, CHASING, EXPIRING, MISSED), entry_valid_for_bars (0-5). Timing policy-derived from score surfaces, entry-zone geometry, simple bounded heuristics. Not first-phase learned primary target.
**Pre-run audit:** calibration used separate calibration-eligible rows, expected-R reliability summary exists, no-trade explicitly selectable, confidence vs expected-R conflict rules test-covered, raw expected-R cannot be treated as trusted when degraded, timing hard gate disabled by default.

### 26.9 Phase 7 — Portfolio, Risk & Runtime Integration
**Goal:** integrate hybrid policy outputs into runtime lifecycle, portfolio interpretation, risk gates, DecisionEvent, and TradeOutcome flows.
**Workstream A — Portfolio & Risk Controls:** Portfolio consumes recommended action, action probabilities, confidence, expected-R by action, drawdown/adverse estimates, portfolio context, cluster/concentration config. Risk consumes portfolio-interpreted candidate, account/exposure state, risk config, degradation state. Combined block rule: if both block → portfolio_blocked=true, risk_blocked=true, primary suppression reason is risk if risk block is hard.
**Workstream B — Runtime Request/Result Flow:** build valid AnalysisRequest, route by requested_trade_mode/model_scope, load scope-compatible model/calibration/policy bundle, reject invalid AnalysisResult, preserve actionability vs execution eligibility, surface fallback/degradation visibly, consume runtime simulation engine for paper forward simulation and historical replay. Runtime rejects/degrades when: action probabilities missing/invalid, expected-R required for chosen direction but missing, confidence kind misrepresented, artifact/calibration/policy bundle scope-incompatible, policy gate status missing.
**Workstream C — Event & Outcome Lifecycle:** DecisionEvent persists requested scope, artifact bundle lineage, action probabilities, expected-R surfaces, expected-R reliability state, policy gates, portfolio/risk interpretation, degradation/fallback state. TradeOutcome allows realized R comparison, projected-vs-realized R error, projected confidence bucket review, no-trade missed-opportunity/saved-loss review. Outcome states: PENDING → RESOLVED | PARTIALLY_RESOLVED | INVALIDATED | UNAVAILABLE.
**Pre-run audit:** runtime does not bypass result validation, fallback signals visible in event creation, portfolio/risk blocks distinguishable downstream, timing extension advisory by default, hybrid surfaces persisted for evaluation.

### 26.10 Phase 8 — Hybrid Evaluation & Monitoring
**Goal:** prove whether V7's hybrid model, calibration, policy, runtime flow, and monitoring surfaces are economically useful and operationally trustworthy.
**Workstream A — Hybrid Evaluation Core:** Economic metrics (realized R, average R, distributional R, profit factor, max drawdown, regret, no-trade correctness, missed opportunity, saved loss, path quality). Classification metrics (action confusion matrix, directional precision/recall, no-trade precision/recall, calibrated confidence buckets, class distribution stability). Regression metrics (expected-R MAE/RMSE, signed bias, long/short error, predicted-R bucket realized-R quality, rank correlation, expected-R gate quality). Ablation metrics (4h-only, 4h+1d, 4h+1d+1h, classifier-only vs hybrid policy, probability gate only vs probability+expected-R gate).
**Workstream B — Promotion Evidence:** Default first implementation thresholds: candidate mean realized-R improves over baseline by at least +0.10, calibration error not worsen by more than 0.01, no-trade correctness not degrade by more than 1.0%, expected-R rank quality non-negative and above configured minimum, no critical safety regression. Promotion never rely on one scalar.
**Workstream C — Monitoring Core:** Aggregate by model_scope: confidence distribution, expected-R distribution, realized-R by predicted-R bucket, fallback/degraded rate, actionability vs execution-eligibility gap, no-trade rate, outcome finality lag, feature drift, symbol/regime coverage, harmful symbol-side cohorts, simulation unresolved/invalidated rate, replay/paper divergence where measurable, timing-extension usefulness.
**Workstream D — Drift & Timing Evidence:** continuous_feature_drift=PSI, missingness_shift=absolute_rate_delta, symbol_mix_shift=total_variation_distance, expected_r_distribution_shift=bucket_delta. Timing remains advisory-only unless at least 3 consecutive evaluation windows agree, each relevant timing state has enough samples, CHASING/MISSED materially underperform READY_NOW, coverage loss stays within configured tolerance.

### 26.11 Phase 9 — Deployment Safety & Release Readiness
**Goal:** turn functioning and measured V7 hybrid system into release-ready system with safety gates, rollback, kill switch, controlled rollout modes.
**Workstream A — Rollout Modes:** replay-only, paper, shadow, live-eligible. Release authority requires one named release owner + one named runtime/control reviewer. Shadow waiver requires both approvals + written rationale.
**Workstream B — Hybrid Bundle Rollback:** Active release authority is scope-compatible bundle: model_scope, action_classifier_artifact, expected_r_long/short_artifact, optional risk_regressor_artifacts, calibration_artifact, expected_r_reliability_artifact, policy_artifact, feature_schema_version, label_interpretation_version, simulation_profile_version. Rollback must restore compatible bundle. Do not permit partial activation of incompatible classifier/regressor/calibration/policy combinations.
**Workstream C — Kill Switch & Execution Disable:** While active: requests may still be built, results may still be recorded (if policy allows), DecisionEvent creation available, execution blocked, TradeOutcome remains compatible with non-execution/unavailable outcome.
**Workstream D — Live-Eligibility Gate:** evaluation_pass, hybrid_surface_quality_pass, monitoring_baseline_ready, fallback_policy_ready, kill_switch_ready, rollback_ready, bundle_compatibility_pass. Hybrid-specific: calibrated confidence present or explicitly downgraded by policy, expected-R reliability above configured minimum or policy downgrades expected-R use, no classifier/regressor artifact mismatch, no stale calibration/reliability artifact. Timing gate default: entry_timing_gate_enabled = False.
**Pre-deploy audit:** kill switch operational end to end, rollback operational end to end, evaluation gate passed on real candidate evidence, hybrid-surface quality gate passed, monitoring baseline designated and retained, release authority named and documented, live eligibility distinct from candidate promotion, rollback bundle compatibility preserved.

---

## 27. EXECUTOR SUPPORT PACK

### 27.1 Executor Prompt Pack (docs/v7_executor_support_pack/executor_prompt_pack.md)
Five reusable prompts: Generic V7 Phase Executor, Phase-Specific Executor, Contract-Heavy Task Executor, Runtime Integration Executor, Evaluation/Release Executor. Each defines authority order, pre-coding inspection requirements, implementation rules, minimum deliverables, final response format. These are execution wrappers around the real authority set, not authority docs themselves.

### 27.2 Naming & Path Consistency (docs/v7_executor_support_pack/naming_and_path_consistency.md)
**Canonical object names:** AnalysisRequest, AnalysisResult, DecisionEvent, TradeOutcome. No alternate spellings/aliases (avoid: RequestPayload, DecisionRecord, TradeLabelOutcome, InferenceResultV7).
**Canonical stage names:** simulation, labels, features, dataset, model, calibration, policy, portfolio, risk, runtime, evaluation, monitoring. No duplicates (avoid: scoring for policy, guards for risk, allocator for portfolio).
**Python modules:** snake_case, PascalCase classes, explicit suffixes only when meaningful (_validator, _builder, _config, _types).
**Test modules:** test_<module_or_behavior>.py.
**Path references in docs:** repo-relative (contracts/analysis_request.md, runtime/runtime_integration.md, pipeline/simulation.md).
**Version naming:** version fields in data, not version prefixes in module names (use contract_version, response_schema_version, simulation_family_version; avoid v7_analysis_request_validator.py unless needed for v6/v7 coexistence).

### 27.3 Phase-to-Doc Authority Matrix (docs/v7_executor_support_pack/phase_to_doc_authority_matrix.md)
Priority order for any implementation task: 1. phase plan itself, 2. most specific matching V7 authority doc, 3. related contract doc if lifecycle objects involved, 4. runtime/pipeline docs for integration behavior, 5. root docs for high-level direction only. Root docs do NOT override specific contract or phase semantics. Phase 7 is highest-risk for authority drift. Cross-cutting: config decisions → current repo config implementation + phase plan config sections + relevant stage doc. Naming/path → README.md + v7_doc_writing_guide.md + master_plan.md + naming_and_path_consistency.md. LLM execution behavior → v7_llm_rules.md.

---

## 28. COMPLETE CONFIG SURFACE INDEX

### 28.1 System Config
enabled model_scope values (SWING/SCALP/AGGRESSIVE_SCALP), action-classification target family, regression target family, approved symbol universe, model_scope defaults (intervals, horizons).

### 28.2 Simulation Config
simulation_profile_version, cost_model_version, fee_model_version, slippage_model_version, horizon_family, stop_family, target_family, time_exit_family, invalidation_multiplier, model_scope profiles.

### 28.3 Labels Config
label_interpretation_version, minimum_acceptable_R, ambiguity_gap_r_threshold, no_trade_correctness_thresholds, saved_loss_threshold, missed_opportunity_threshold, path_quality_high_threshold (0.70), path_quality_medium_threshold (0.40), invalid/ambiguous filtering policy, regression_target_clipping_policy, min_acceptable_directional_realized_r (0.25).

### 28.4 Features Config
feature_schema_version, enabled_feature_groups, normalization_family, symbol_encoding_family, missingness_handling_rules, feature_clipping_winsorization_rules, approved_symbol_metadata.

### 28.5 Dataset Config
split_family (fold_count=6, min_train_window=12m, validation_window=2m, holdout_window=1m), allowed_symbol_universe, row_validity_rules, classification_target_inclusion_rules, regression_target_inclusion_rules, balancing/weighting_rules (inverse-frequency, cap_ratio=5.0), target_clipping_transformation_rules, partial_row_exception_policy.

### 28.6 Model Config
model_family (XGBoost), target_head_enablement, objectives (classification: multi-class/binary; regression: squared/absolute/quantile), hyperparameters (max_depth, n_estimators, learning_rate, min_child_weight, subsample, colsample_bytree, reg_alpha, reg_lambda, early_stopping_rounds), sample_weights, target_clipping_transformation, calibration_split, artifact_publishing_rules.

### 28.7 Calibration Config
calibration_family, calibration_split_rules, fallback_behavior, classification_calibration_method, regression_reliability_thresholds, publishing_rules, recalibration_thresholds.

### 28.8 Policy Config
minimum_action_probability, minimum_confidence, minimum_expected_r, minimum_cost_adjusted_expectancy, drawdown/adverse_pressure_limits, no_trade_thresholds, policy_score_weights, decision_margin, timing_extension_enablement, degraded_result_behavior, blocked_entry_readiness_states, min_entry_valid_for_bars, entry_timing_gate_mode.

### 28.9 Portfolio Config
max_open_positions, exposure_caps, cluster_grouping_rules, portfolio_suppression_thresholds, ranking_family, portfolio_context_fallback_behavior.

### 28.10 Risk Config
kill_switch_settings, cooldown_rules (trigger_family, duration, scope), exposure_hard_limits, stale_result_limits, degraded_result_behavior, duplicate_protection_rules, minimum_context_requirements.

### 28.11 Deployment Config
rollout_mode, promotion_gate_family, kill_switch_settings, rollback_authority, live_eligibility_toggles, timing_gate_enablement, degraded_result_live_behavior, baseline_retention_rules, entry_timing_gate_enabled (default: False).

### 28.12 Monitoring Config
monitoring_windows, drift_thresholds, alert_thresholds, regression_reliability_thresholds, timing_observability_enablement, slice_definitions, baseline_retention, outcome_lag_thresholds, continuous_feature_drift_method (PSI), missingness_shift_method (absolute_rate_delta), symbol_mix_shift_method (total_variation_distance), expected_r_distribution_shift_method (bucket_delta).

### 28.13 Runtime Config (integration-specific)
min_confidence, min_expected_r, max_expected_drawdown, enable_entry_timing_observability, enable_entry_readiness_gate, blocked_entry_readiness_states, min_entry_valid_for_bars, runtime_safe_action_on_degraded_result.

---

## 29. COMPLETE INVARIANT INDEX

1. **Atomicity invariant:** one atomic request/result/event/outcome per (symbol, primary_interval, evaluated_market_state).
2. **Scope invariant:** one atomic request targets exactly one model_scope; no averaged scope outputs.
3. **Simulation truth layer invariant:** same simulation logic defines labels, evaluation, replay, paper, outcomes, Monte Carlo.
4. **No future leakage invariant:** features from canonical state only; no future bars/labels/outcome echoes.
5. **No unresolved training invariant:** unresolved/invalid simulation outputs cannot enter strict supervised training.
6. **No silent fallback invariant:** every fallback explicit, observable, testable, attributable.
7. **No hidden deterministic veto invariant:** deterministic logic visible and reviewable; cannot silently suppress learned decisions.
8. **No-trade first-class invariant:** NO_TRADE is a real learned action, not absence of signal or fallback.
9. **Config single-source invariant:** all thresholds/settings/constants through unified config system; no hidden config mutation.
10. **Calibration-structural invariant:** raw model scores not directly trusted; calibration separate from model fitting.
11. **Economic-quality-first invariant:** promotion requires economic quality evidence, not architecture novelty.
12. **Runtime-engine boundary invariant:** runtime never re-derives model scores; engine never runs simulation or submits orders.
13. **Actionability vs execution eligibility invariant:** result may be actionable but operationally not executable; distinction explicit.
14. **Replay/live parity invariant:** replay and live use same contract semantics; differences explicit in lineage.
15. **Versioning invariant:** when meaning changes materially, version field is bumped; no silent semantic drift.
16. **Ambiguity explicit invariant:** ambiguous states not forced into artificial action winners.
17. **Target validity invariant:** classification and regression target availability tracked separately; per-target validity explicit.
18. **Scope-compatibility invariant:** model/calibration/policy artifacts must be scope-compatible; scope_mismatch must be rejected or visibly degraded.
19. **Timing advisory-first invariant:** entry_readiness/entry_valid_for_bars advisory by default; hard gating requires evidence.
20. **Promotion distinct from live invariant:** evaluation-promoted ≠ live-eligible; per-scope promotion enforced.
21. **Monte Carlo diagnostic invariant:** Monte Carlo outputs distributional evidence only; not actual realized outcome.
22. **Side-effect-free adapter invariant:** training/replay/evaluation adapters must NOT have live execution side effects.
23. **Raw vs calibrated confidence invariant:** confidence_kind must be explicit; raw confidence cannot be mislabeled as calibrated.
24. **Execution truth vs simulated truth invariant:** both useful but not identical; lineage distinguishes them.
25. **Outcome materialization timing invariant:** outcome created when lifecycle begins to matter (PENDING state allowed), not only when final.
26. **Symbol balancing invariant:** no silent symbol dominance; weighting/capping prevents pathological concentration.
27. **Walk-forward split invariant:** split by time first, not IID random; no temporal leakage across folds.
28. **Simulation profile versioning invariant:** profile changes (cost/horizon/stop/target) bump version; labels and evaluation trace the version.
29. **Backend independence invariant:** no broker/exchange internals in core contracts.
30. **Model output surface invariant:** classification AND regression both first-class; hybrid decision policy uses both.

---

## 30. COMPLETE TEST REQUIREMENT INDEX (by phase/doc)

### 30.1 Contract Tests (Phase 1)
- Required/optional field tests for all four contracts
- Hybrid AnalysisResult shape tests
- Action probability validation tests (sum within tolerance, no negative)
- Expected-R availability tests
- Confidence kind tests (raw vs calibrated distinction)
- Request/result/event/outcome linkage tests
- Scope-compatible artifact bundle tests
- Timing field validation tests (entry_valid_for_bars 0-5, entry_readiness enum)
- Serialization round-trip tests
- Unknown/unsupported version rejection
- Scope mismatch rejection

### 30.2 Simulation Tests (Phase 2)
- Stop-hit before target
- Target-hit before stop
- Time exit
- Horizon-end unresolved
- Invalidated after missing data window (2×horizon)
- Fee/slippage reduces R correctly
- MFE/MAE correctness
- No-trade saved-loss and missed-opportunity outputs
- Adapter side-effect isolation (no live execution)
- V6/V7 profile selection versioning
- Monte Carlo output distinguishable from realized truth
- Long/short/no-trade comparative parity

### 30.3 Labels Tests (Phase 3)
- Best-action assignment
- No-trade correctness
- Ambiguity threshold behavior
- Long expected-R target creation
- Short expected-R target creation
- Unresolved simulation exclusion
- Regression target lineage preservation
- Path-quality bucket mapping (HIGH/MEDIUM/LOW thresholds)
- Regret consistency
- Outcome alignment (outcome_label, is_good_decision)
- Invalid rows preserve invalidity reason
- Cost-adjusted R targets match cost model

### 30.4 Feature/Dataset Tests (Phase 4)
- Deterministic transform for same input
- No future leakage
- Schema stability
- HTF fallback + flags
- 1h refinement absence visible
- Symbol one-hot stability
- Training-only normalization statistics
- Per-fold normalization separation
- Schema mismatch failure
- Walk-forward split integrity
- Unresolved row exclusion
- Per-target validity handling (classification valid but regression invalid)
- Symbol-weight reproducibility
- Dataset-family version bump triggers work

### 30.5 Model Tests (Phase 5)
- Small training run completes
- Artifact bundle loads
- Inference over sample rows works
- Classifier probabilities exist for all three actions
- Long expected-R output exists
- Short expected-R output exists
- Target validity masks respected
- Early stopping path works
- Fixed-seed sanity test
- Failed run does not publish promotable state
- Candidate vs promotable states distinct

### 30.6 Calibration/Policy Tests (Phase 6)
- Calibration artifact load
- Raw vs calibrated confidence distinction preserved
- Missing/stale calibration fallback visibility
- Expected-R reliability metrics
- Expected-R degraded policy behavior (downgrade visible)
- Long/short/no-trade selection
- Confidence vs expected-R conflict (confidence passes but expected-R fails → NO_TRADE)
- No-trade positive selection (not fallback)
- Timing field legality and bounds (0-5, enum values)
- Ambiguous long/short selects NO_TRADE
- Regression-head missingness degrades visibly

### 30.7 Portfolio/Risk/Runtime Tests (Phase 7)
- Concentration suppression works
- Cluster suppression visible
- Rank vs suppress deterministic
- Expected-R influences ranking only within allowed caps
- portfolio_blocked mapping correct
- Unavailable context degrades visibly
- Hard block visibility
- Cooldown behavior
- Duplicate protection
- Stale result block
- Degraded result handling
- Actionability vs execution-eligibility separation
- Portfolio-before-risk ordering preserved
- Request builder correctness
- Hybrid result validation rejection
- Scope mismatch fallback
- Event materialization
- Outcome pending→update
- Fallback/suppression propagation matrix

### 30.8 Evaluation/Monitoring Tests (Phase 8)
- Walk-forward split integrity
- Baseline comparison (candidate vs baseline)
- No-trade metric correctness
- Calibration metric correctness
- Expected-R metric correctness (MAE/RMSE, sign, bucket quality)
- Predicted-R bucket aggregation
- Classifier-only vs hybrid policy ablation
- Fallback/degradation aggregation
- Actionability/execution gap metric
- Outcome lag metric
- Feature drift aggregation (PSI, rate delta, TVD)
- Timing usefulness aggregation
- Baseline update/replacement logic
- Incomplete slice handling (marked incomplete)
- Symbol/regime slicing reproducibility

### 30.9 Deployment Safety Tests (Phase 9)
- Paper mode lifecycle recording
- Shadow mode behavior
- Live-eligibility rejection for incomplete candidates
- Kill switch blocks execution
- Kill switch lifecycle recording remains intact
- Rollback changes active authority
- Rollback preserves dependency compatibility (hybrid bundle integrity)
- Incompatible partial activation rejected
- Stale calibration rejected or downgraded
- Stale expected-R reliability rejected or downgraded
- Timing hard-gate disabled by default
- Non-execution outcome semantics valid under kill switch

---

## 31. COMPLETE PIPELINE DATA FLOW (for AI reference)

### 31.1 Data Flow End to End
1. Raw market data (Binance candles) → validated raw history
2. Canonical state construction (one per symbol per decision timestamp, 4h primary + 1d HTF + 1h refinement)
3. Runtime simulation engine (compares LONG/SHORT/NO_TRADE under same stop/target/horizon/fee/slippage, produces comparative outputs with realized R, MFE/MAE, path quality, regret, saved-loss, missed-opportunity)
4. Label builder (classification: best_action_label, long/short/no-trade quality; regression: long/short realized R net/gross, MFE/MAE, regret, saved-loss, path quality)
5. Feature builder (canonical state only: 4h features + 1d HTF features + 1h refinement features + symbol identity + regime/volatility + missingness flags)
6. Dataset assembly (temporal walk-forward rows with lineage, per-target validity masks, symbol weights)
7. Hybrid model training (XGBoost multiclass classifier + XGBoost long/short expected-R regressors + optional risk regressors)
8. Calibration (global per scope: calibrated action probabilities, calibrated confidence, reliability metrics)
9. Expected-R reliability review (MAE/RMSE, signed bias, rank correlation, bucket quality)
10. Policy gates (confidence + probability + expected-R + drawdown + no-trade margin + timing advisory)
11. Portfolio interpretation (cross-symbol competition: pass/suppress/down-rank by expected-R, confidence, concentration caps)
12. Risk gating (kill switch, cooldowns, exposure limits, duplicate protection, stale/degraded handling)
13. Runtime integration (request builder → scope router → artifact selection → engine → result validator → runtime interpretation → DecisionEvent → execution eligibility → TradeOutcome)
14. Evaluation (walk-forward economic metrics + classification metrics + regression metrics + calibration metrics + ablation)
15. Monitoring (drift: feature/calibration/regression/action-mix/outcome-lag/fallback-rate)
16. Deployment safety (replay → paper → shadow → live-eligible; rollback bundles; kill switch)

### 31.2 Key Ownership Map
| Component | Owns | Does Not Own |
|---|---|---|
| Runtime | Orchestration, execution, persistence, safety, simulation hosting, scope_router, artifact selection, request assembly, result validation, event/outcome lifecycle, fallback visibility, kill switch | Model scoring, simulation loops, label generation, dataset assembly |
| Engine | Market-state interpretation, score generation, confidence, expected R, action recommendation, timing guidance, uncertainty/degradation | Broker submission, persistence, event creation, outcome materialization, simulation |
| Simulation layer (runtime) | Economic truth computation | Model training, live execution |
| Labels | Converting simulation to supervised targets | Model training, simulation execution |
| Features | Canonical state → model-ready features | Label generation, simulation |
| Dataset | Temporal lineage-preserving row assembly | Model training, feature engineering |
| Model | Action probabilities + expected-R estimates | Simulation, runtime gates, promotion |
| Calibration | Raw → calibrated confidence | Model fitting, policy thresholds |
| Policy | Calibrated scores → normalized decision | Runtime execution gates |
| Portfolio | Cross-symbol competition | Model training, risk hard gates |
| Risk | Final safety layer | Model scoring, policy decisions |
| Evaluation | Evidence-based quality measurement | Promotion authority, live eligibility |
| Monitoring | Drift, health, lifecycle signals | Alerting infrastructure, promotion decisions |
| Deployment safety | Rollout modes, rollback, kill switch | Contract semantics, model training |

---

## 32. COMPLETE ENUM AND FIELD VALUE INDEX

### 32.1 AnalysisRequest Field Values
- request_kind: live_scan, paper_scan, replay_eval, shadow, validation
- requested_trade_mode: SWING, SCALP, AGGRESSIVE_SCALP
- model_scope: SWING, SCALP, AGGRESSIVE_SCALP
- analysis_mode: live, paper, replay, validation, shadow
- snapshot_validity: VALID, DEGRADED, INVALID
- data_source: fresh_exchange, historical_store, replayed, degraded
- data_quality_flags: GAP_DETECTED, DUPLICATE_DETECTED, CORRUPTION_DETECTED, TIMESTAMP_ORDER_ISSUE, LOW_VOLUME, SPARSE_DATA
- missing_context_flags: HTF_UNAVAILABLE, REFINEMENT_UNAVAILABLE, REGIME_UNAVAILABLE, VOLATILITY_UNAVAILABLE
- stale_flag: true, false
- partial_state_flag: true, false
- htf_freshness: FRESH, STALE, UNAVAILABLE

### 32.2 AnalysisResult Field Values
- signal_status: SIGNAL, NO_TRADE, FILTERED, DEGRADED, ERROR
- decision_status: VALID, LOW_CONFIDENCE, BLOCKED, DEGRADED, FAILED
- recommended_action: LONG_NOW, SHORT_NOW, NO_TRADE
- direction: LONG, SHORT, NONE
- confidence_kind: RAW, CALIBRATED, DEGRADED, UNAVAILABLE
- time_sensitivity: IMMEDIATE, STANDARD, CAN_WAIT, EXPIRING_SOON
- entry_readiness: READY_NOW, WAIT, CHASING, EXPIRING, MISSED, NOT_APPLICABLE
- entry_valid_for_bars: integer 0-5 (first convention, capped at 5)
- contract_strictness_used: STRICT, DEGRADED_ALLOWED, SHADOW_RELAXED
- uncertainty_type: EPISTEMIC, ALEATORIC, MIXED, UNKNOWN
- decision_quality: HIGH, MEDIUM, LOW, DEGRADED
- path_quality_expectation: CLEAN_ENOUGH, NOISY, DANGEROUS, UNCERTAIN
- deterministic_alignment: ALIGNED, NEUTRAL, CONFLICTING, UNAVAILABLE
- deterministic_warning: values depend on deterministic logic implemented
- constraint_level: ADVISORY, SOFT_BLOCK, HARD_BLOCK
- runtime_safe_action: NO_TRADE, SKIP, HOLD

### 32.3 DecisionEvent Field Values
- runtime_actionability: ACTIONABLE, REVIEW_ONLY, NOT_ACTIONABLE, DEGRADED
- execution_path: NOT_EXECUTED, PAPER_EXECUTED, LIVE_EXECUTED, REPLAY_ONLY, SKIPPED_BY_RUNTIME, BLOCKED_BY_RUNTIME
- execution_decision: EXECUTED, SKIPPED, BLOCKED, NOT_APPLICABLE
- outcome_status: PENDING, RESOLVED, PARTIALLY_RESOLVED, INVALIDATED, UNAVAILABLE
- label_status: NOT_LABELED, LABELED, PENDING, INVALID
- comparison_group_id: optional string for cross-comparison
- timing_review_tags: ready_now, wait_preferred, chasing_entry, expiring_setup, missed_setup

### 32.4 TradeOutcome Field Values
- outcome_source: LIVE_EXECUTION, PAPER_EXECUTION, REPLAY_PROJECTION, OFFLINE_LABELING, SKIP_EVAL
- execution_path: NOT_EXECUTED, PAPER_EXECUTED, LIVE_EXECUTED, REPLAY_ONLY, SKIPPED_BY_RUNTIME, BLOCKED_BY_RUNTIME
- execution_decision: EXECUTED, SKIPPED, BLOCKED, NOT_APPLICABLE
- outcome_status: PENDING, RESOLVED, PARTIALLY_RESOLVED, INVALIDATED, UNAVAILABLE
- resolution_reason: HORIZON_COMPLETE, TRADE_CLOSED, STOP_HIT, TARGET_HIT, TIME_EXIT, SKIP_EVAL_COMPLETE, DATA_INCOMPLETE, EXECUTION_INCOMPLETE
- best_realized_action: LONG_NOW, SHORT_NOW, NO_TRADE, WAIT_1_BAR_LONG
- exit_reason: STOP_HIT, TARGET_HIT, TIME_EXIT, MANUAL_EXIT, RUNTIME_EXIT, PROJECTED_HORIZON_END, NOT_APPLICABLE
- outcome_quality: HIGH, MEDIUM, LOW, AMBIGUOUS
- outcome_label: CLEAN_LONG_OPPORTUNITY, CLEAN_SHORT_OPPORTUNITY, CORRECT_NO_TRADE, WRONG_DIRECTION, HIGH_REGRET_SKIP, DANGEROUS_TRADE, AMBIGUOUS_STATE, LOW_INFORMATION_STATE

### 32.5 Simulation Enum Values
- family identifiers: simulation_family_version, cost_model_version, fee_model_version, slippage_model_version, horizon_family, stop_family, target_family, time_exit_family
- exit_reason: STOP_HIT, TARGET_HIT, TIME_EXIT, HORIZON_END, UNRESOLVED, INVALIDATED
- no_trade_quality: CORRECT_NO_TRADE, SAVED_LOSS, MISSED_OPPORTUNITY, AMBIGUOUS_NO_TRADE
- simulation_profile: V6_SIMULATION_PROFILE, V7_SIMULATION_PROFILE, SWING_PROFILE, SCALP_PROFILE, AGGRESSIVE_SCALP_PROFILE
- resolution_status: RESOLVED, UNRESOLVED, INVALIDATED

### 32.6 Label Enum Values
- best_action_label: LONG_NOW, SHORT_NOW, NO_TRADE, AMBIGUOUS_STATE
- label_validity: VALID, AMBIGUOUS, UNRESOLVED, INVALID
- no_trade_quality_label: CORRECT_SKIP, SAVED_LOSS, MISSED_OPPORTUNITY, AMBIGUOUS
- path_quality_bucket: HIGH, MEDIUM, LOW
- skip_was_correct: true, false

### 32.7 Feature Enum Values
- view_types: primary, higher_timeframe, refinement
- interval_presence: AVAILABLE, FALLBACK, MISSING
- symbol_encoding: compact one-hot (first phase), future: learned embeddings
- normalization: training-window-global (first phase), future: per-symbol

### 32.8 Dataset Enum Values
- row_validity: FULLY_VALID, CLASSIFICATION_ONLY, REGRESSION_ONLY, EXCLUDED
- split_assignment: TRAIN, VALIDATION, HOLDOUT, CALIBRATION
- walk_forward_fold: fold_0 through fold_5 (6 folds default)

### 32.9 Model Enum Values
- model_family: XGBOOST (first phase)
- objective_type: multi_softprob (classification), reg:squarederror, reg:absoluteerror, reg:quantileerror (regression)
- head_type: ACTION_CLASSIFIER, EXPECTED_R_REGRESSOR, ADVERSE_PRESSURE_REGRESSOR, COST_ADJUSTED_REGRESSOR
- artifact_status: CANDIDATE, REJECTED, PROMOTABLE, PROMOTED, RETIRED

### 32.10 Calibration Enum Values
- confidence_kind: RAW, CALIBRATED, DEGRADED, UNAVAILABLE
- calibration_method: PLATT_SCALING, ISOTONIC_REGRESSION, TEMPERATURE_SCALING, BETA_CALIBRATION (first phase default: config-driven)
- reliability_grade: TRUSTED, ACCEPTABLE, WEAK, UNRELIABLE
- regression_reliability_status: TRUSTED, DEGRADED, UNRELIABLE

### 32.11 Policy Enum Values
- gate_status: PASSED, FAILED, DEGRADED, NOT_EVALUATED
- recommended_action: LONG_NOW, SHORT_NOW, NO_TRADE
- policy_reason_codes: see section 19.2 (7 gates)
- tie_break_reason: CONFIDENCE_BEAT, ECONOMIC_QUALITY_BEAT, NO_TRADE_PREFERRED

### 32.12 Portfolio Enum Values
- portfolio_action: PASS, SUPPRESS, DOWN_RANK, ANNOTATE
- suppression_reason: MAX_POSITIONS_REACHED, CLUSTER_CAP_EXCEEDED, CONCENTRATION_LIMIT, PORTFOLIO_CONTEXT_DEGRADED
- ranking_criteria: ACTIONABILITY, EXPECTED_R, COST_ADJUSTED_EXPECTANCY, CONFIDENCE, PORTFOLIO_PRESSURE, SYMBOL_ORDER (last resort)

### 32.13 Risk Enum Values
- risk_action: PASS, BLOCK, DEGRADE
- risk_block_reason: KILL_SWITCH_ACTIVE, COOLDOWN_ACTIVE, EXPOSURE_LIMIT_EXCEEDED, DUPLICATE_POSITION, STALE_RESULT, DEGRADED_RESULT, ACCOUNT_CONTEXT_INSUFFICIENT
- cooldown_scope: GLOBAL, SYMBOL_LOCAL, DIRECTION_LOCAL

---

## 33. COMPLETE CROSS-REFERENCE TABLE (doc-to-doc)

| Topic | Primary Authority Doc(s) | Supporting Docs | Implementation Phase |
|---|---|---|---|
| System vision/strategy | vision.md | README.md, architecture.md | Phase 0 (context) |
| System architecture | architecture.md | vision.md, contracts/README.md | Phase 0 (context) |
| LLM working rules | v7_llm_rules.md | v7_doc_writing_guide.md | All phases |
| Doc writing standards | v7_doc_writing_guide.md | v7_llm_rules.md | All phases (doc updates) |
| Contract family strategy | contracts/README.md | analysis_request.md, analysis_result.md, decision_event.md, trade_outcome.md | Phase 1 |
| AnalysisRequest | contracts/analysis_request.md | architecture.md, runtime/runtime_integration.md | Phase 1 |
| AnalysisResult | contracts/analysis_result.md | pipeline/policy.md, pipeline/calibration.md | Phase 1 (with timing extension from revision) |
| DecisionEvent | contracts/decision_event.md | runtime/runtime_integration.md, pipeline/portfolio.md, pipeline/risk.md | Phase 1 |
| TradeOutcome | contracts/trade_outcome.md | pipeline/labels.md, pipeline/simulation.md, pipeline/evaluation.md | Phase 1 |
| Simulation engine | runtime/simulation_engine.md | pipeline/simulation.md | Phase 2 |
| Pipeline simulation | pipeline/simulation.md | runtime/simulation_engine.md, contracts/trade_outcome.md | Phase 2 |
| Labels | pipeline/labels.md | pipeline/simulation.md, contracts/trade_outcome.md | Phase 3 |
| Features | pipeline/features.md | contracts/analysis_request.md, pipeline/dataset.md | Phase 4 |
| Dataset | pipeline/dataset.md | pipeline/features.md, pipeline/labels.md | Phase 4 |
| Model | pipeline/model.md | pipeline/dataset.md, pipeline/training.md | Phase 5 |
| Training | pipeline/training.md | pipeline/dataset.md, pipeline/model.md | Phase 5 |
| Calibration | pipeline/calibration.md | pipeline/model.md, pipeline/policy.md, contracts/analysis_result.md | Phase 6 |
| Policy | pipeline/policy.md | pipeline/calibration.md, contracts/analysis_result.md | Phase 6 |
| Portfolio | pipeline/portfolio.md | pipeline/policy.md, contracts/decision_event.md | Phase 7 |
| Risk | pipeline/risk.md | pipeline/portfolio.md, runtime/runtime_integration.md | Phase 7 |
| Runtime integration | runtime/runtime_integration.md | contracts/*.md, runtime/fallback_policy.md | Phase 7 |
| Fallback policy | runtime/fallback_policy.md | runtime/deployment_safety.md | Phase 7 |
| Evaluation | pipeline/evaluation.md | pipeline/model.md, pipeline/calibration.md, pipeline/policy.md | Phase 8 |
| Monitoring | pipeline/monitoring.md | contracts/*.md, pipeline/evaluation.md | Phase 8 |
| Deployment safety | runtime/deployment_safety.md | runtime/fallback_policy.md, pipeline/monitoring.md | Phase 9 |
| Roadmap/sequencing | roadmap.md | implementation/master_plan.md | All phases |
| Master plan | implementation/master_plan.md | all phase_*.md files | All phases |
| Executor prompts | executor_prompt_pack.md | phase_to_doc_authority_matrix.md | All phases |
| Naming/path standards | naming_and_path_consistency.md | README.md, v7_doc_writing_guide.md | All phases |
| Authority matrix | phase_to_doc_authority_matrix.md | master_plan.md | All phases |

---

## 34. COMPLETE TERM GLOSSARY

| Term | Definition |
|---|---|
| V7 | Next-generation trading engine; centralized, market-first, simulation-native |
| V6 | Previous-generation learned trading engine; transition architecture |
| AnalysisRequest | Atomic runtime-to-engine input contract |
| AnalysisResult | Atomic engine-to-runtime output contract |
| DecisionEvent | Atomic normalized lifecycle record after request→result |
| TradeOutcome | Atomic normalized consequence record for one DecisionEvent |
| model_scope | Operating mode (SWING, SCALP, AGGRESSIVE_SCALP) with own intervals/horizon/artifact |
| SWING | Primary 4h, HTF 1d, refinement 1h, swing horizon labels |
| SCALP | Primary 15m, HTF 1h, refinement 5m, scalp horizon labels |
| AGGRESSIVE_SCALP | Primary 1m/3m, HTF 5m+15m, immediate/very short horizon |
| Runtime simulation engine | Runtime-hosted simulation that defines economic truth for all downstream stages |
| Canonical state | Standardized market state per symbol per timestamp for live/replay/evaluation |
| Hybrid supervised model | Model with classification heads (action selection) AND regression heads (economic quality) |
| XGBoost-first | First-phase model family preference; not target-type restriction |
| Calibration | Maps raw model scores to reliable probability/confidence surfaces |
| Policy | Decision layer combining calibrated probability + expected-R + risk gates |
| NO_TRADE | First-class action; system must know when not to trade |
| expected_r | Expected R-multiple (economic quality estimate) |
| R-multiple | Normalized risk-reward measure (realized return / initial risk) |
| MFE/MAE | Maximum Favorable/Adverse Excursion (path quality metrics) |
| Walk-forward | Temporal split-based evaluation with sequential train/validation/holdout folds |
| Side-effect-free adapter | Simulation adapter for training/evaluation with no live execution effects |
| Monte Carlo robustness | Distributional simulation mode for expected-R distribution, downside risk, etc. |
| scope_mismatch | When requested_trade_mode and model_scope are incompatible |
| Actionability | Engine-side determination that a result is economically actionable |
| Execution eligibility | Runtime-side determination that execution is operationally safe |
| entry_readiness | Timing signal: whether setup is ready, chasing, expiring, or missed |
| entry_valid_for_bars | How many future analysis bars the entry thesis is expected to remain valid (0-5) |
| Scope router | Runtime component selecting model_scope before inference |
| atomic unit | One symbol, one primary interval, one evaluated market state, one request/result/event/outcome |
| Layer A | Atomic lifecycle objects (AnalysisRequest, AnalysisResult, DecisionEvent, TradeOutcome) |
| Layer B | Grouping objects (AnalysisBatchRequest, AnalysisBatchResult, DecisionSession) — deferred |
| Contract versioning | contract_version, state_schema_version, response_schema_version, event_schema_version, outcome_schema_version, snapshot_builder_version |
| Artifact versioning | model_artifact_version, calibration_artifact_version, policy_artifact_version |
| PENDING | Initial outcome state when lifecycle begins but resolution not yet complete |
| RESOLVED | Final outcome state with complete resolution |
| INVALIDATED | Outcome that cannot be completed safely/consistently |
| Regret | Difference between realized outcome and counterfactual best action |
| Saved loss | Correct no-trade when directional actions would have lost |
| Missed opportunity | Incorrect no-trade when a directional action succeeded |
| Path quality | Composite measure of MFE/MAE/target-hit/stop-hit timing |
| Symbol balancing | Inverse-frequency weights to prevent high-row-count symbol dominance |
| Kill switch | Runtime safety mechanism to block all execution immediately |
| Rollback | Reverting to previous compatible artifact bundle per model_scope |
| Shadow mode | V7 observes live state, records decisions, does not control execution |
| Paper mode | Live-ish operational validation with paper execution |
| Replay-only | Simulation verification/offline evaluation mode |
| Live-eligible | Release stage where V7 may influence real execution |
| Hybrid artifact bundle | Scope-compatible set: classifier + regressors + calibration + reliability + policy |
| Episode | (Context note: used in V6, intentionally avoided in V7 in favor of atomic lifecycle objects) |

---

## 35. COMPLETE ERROR AND EXCEPTION REFERENCE

### 35.1 Domain Exception Classes
| Exception | Purpose | Raised By |
|---|---|---|
| ValidationError | Contract validation failure | Contract validators |
| ConfigError | Invalid/missing config | Config loader |
| ArtifactCompatibilityError | Incompatible artifact bundle | Runtime, model loader |
| SimulationError | Simulation failure/corruption | Simulation engine |
| LabelGenerationError | Label derivation failure | Label builder |
| FeatureTransformError | Feature computation failure | Feature builder |
| DatasetAssemblyError | Dataset row assembly failure | Dataset builder |
| TrainingError | Model training failure | Model training |
| CalibrationError | Calibration fitting failure | Calibration module |
| PolicyError | Policy computation failure | Policy module |
| PortfolioError | Portfolio interpretation failure | Portfolio module |
| RiskError | Risk gate failure | Risk module |
| RuntimeIntegrationError | Runtime lifecycle flow failure | Runtime integration |
| MonitoringError | Monitoring metric failure | Monitoring module |
| DeploymentSafetyError | Release gate failure | Deployment safety |

### 35.2 Error Handling Rules (recap)
- Fail early on invalid config (raise immediately)
- Use explicit domain errors (small number of meaningful exception classes per subsystem)
- Do not silently swallow errors (return structured degradation/fallback info where appropriate)
- Separate invalid input from expected no-action behavior
- Invalid request ≠ no-trade (no-trade is a valid decision; invalid request is an error)
- Missing artifact ≠ low confidence (missing artifact is degradation; low confidence is valid model output)

### 35.3 Recovery Strategies
- Config load failure → system must not start
- Contract validation failure → reject before engine routing; log detailed reason
- Simulation unresolved → keep as PENDING; do not use as final training label
- Simulation invalidated → mark INVALIDATED; exclude from training
- Calibration missing → use raw scores with explicit confidence_kind=DEGRADED; policy may degrade gates
- Expected-R unreliable → policy degrades economic gates; may downgrade to NO_TRADE
- Portfolio context unavailable → safe non-execution default; explicit degradation
- Risk context unavailable → safe non-execution default; explicit degradation
- Kill switch active → block execution; preserve lifecycle recording
- Artifact stale → config-governed: allowed, allowed-with-downgrade, forbidden

---

## 36. COMPLETE VALIDATION RULE REFERENCE (by lifecycle stage)

### 36.1 Request Validation (pre-engine)
1. Required fields exist (contract_version, state_schema_version, snapshot_builder_version, request_id, timestamp_utc, symbol, requested_trade_mode, model_scope, primary_interval, analysis_mode, canonical_state)
2. symbol is in approved universe
3. requested_trade_mode and model_scope are valid and compatible
4. primary_interval, context_intervals, refinement_intervals compatible with model_scope
5. analysis_mode is valid enum
6. timestamp_utc is parseable UTC
7. contract_version is supported
8. canonical_state is present and structurally valid (raw_window, derived_state, context, quality, metadata subsections)
9. state_views do not conflict with primary scope
10. degraded/quality flags internally consistent
11. No forbidden future-derived fields present
12. If requested_trade_mode != model_scope → scope_mismatch; reject or route to documented degraded-safe path

### 36.2 Result Validation (pre-runtime-consumption)
1. Required sections/fields exist
2. request_id matches originating request
3. symbol/model_scope/trade_mode/primary_interval in request_link (if present) match originating request
4. artifact_id/calibration_artifact_id scope-compatible with model_scope
5. recommended_action and direction internally consistent (LONG→LONG, SHORT→SHORT, NO_TRADE→NONE)
6. is_actionable consistent with status and degradation fields
7. Required execution fields exist for actionable directional trades (entry_price, stop_loss, take_profit, time_sensitivity)
8. confidence is present and valid numeric (0 to 1 range)
9. expected_r is present and valid numeric
10. action_probabilities present for all three actions, sum within configured tolerance, no negative values
11. entry_valid_for_bars (if present) integer in 0..5
12. entry_readiness (if present) legal enum
13. fallback fields internally consistent
14. contract_version and response_schema_version supported
15. If directional action is actionable, its expected-R surface must be present unless result explicitly degraded
16. Raw confidence not mislabeled as calibrated confidence (confidence_kind must be honest)

### 36.3 Event Validation (pre-persist)
1. Required sections/fields exist
2. request lineage resolvable (request_id exists and matches origin)
3. result-derived decision fields internally consistent with originating AnalysisResult
4. execution_path and execution_decision do not contradict decision_summary.is_actionable
5. fallback_used and degraded interpretation fields internally consistent
6. deterministic block/alignment fields not contradict visible actionability
7. outcome linkage fields use legal state transitions
8. batch/session lineage consistent with originating request/result when present
9. timing echoes (if present) match originating result fields
10. model_scope/artifact/calibration/policy lineage present and consistent

### 36.4 Outcome Validation (pre-persist)
1. Required sections/fields exist
2. decision_event_id resolves to valid DecisionEvent
3. execution_summary and resolution_status internally consistent
4. Final outcomes have required realized/comparative fields where mandated
5. Pending outcomes do not masquerade as final
6. outcome_source and live/paper/replay lineage not contradictory
7. quality/interpretation labels legal for given resolution state
8. evaluation_run_id/simulation_run_id/replay_run_id/monte_carlo_run_id (if present) well-formed and consistent with lineage context
9. Protection: system must NOT train on unresolved/invalid/mislabeled/inconsistent outcomes

### 36.5 Dataset Validation (pre-training)
1. No temporal leakage across train/validation/test folds
2. All rows have traceable upstream lineage (feature_schema, label_interpretation, simulation_family versions)
3. Unresolved/invalid labels excluded from strict training (or explicitly flagged)
4. Ambiguous rows not forced into hard classification targets
5. Symbol weighting reproducible and not silently dominated
6. Classification and regression target availability tracked separately
7. Target clipping/transformation versioned
8. Walk-forward fold boundaries respected (train < validation < holdout strictly temporal)
9. No single symbol dominates row count or weight silently (cap at configured ratio)
10. Dataset_family_version bumped when meaning changes materially

### 36.6 Model Validation (post-training)
1. Artifact bundle loads correctly
2. Inference produces all expected outputs (action probabilities for 3 actions, expected_r_long, expected_r_short)
3. Action probabilities sum to approximately 1.0
4. Expected-R values are numeric (not NaN/Inf)
5. Artifact metadata preserves dataset, feature, label, and simulation lineage
6. Candidate artifacts are not marked promotable
7. Failed/invalid runs did not publish promotable artifacts
8. All target heads present and valid (or explicitly degraded)

### 36.7 Calibration Validation
1. Calibration used slice distinct from model fitting rows
2. Raw vs calibrated confidence surfaces distinguishable
3. Calibration artifact loads with reliability metrics
4. confidence_kind correctly surfaced (CALIBRATED vs RAW vs DEGRADED vs UNAVAILABLE)
5. Expected-R reliability summary exists with per-head error metrics
6. Unreliable expected-R can be downgraded visibly via config
7. Stale/missing calibration detectable and actionable

### 36.8 Policy Validation
1. Directional action only emitted when ALL gates pass (or explicit degraded path)
2. confidence-only cannot override failed economic gate
3. expected-R-only cannot override failed confidence gate
4. NO_TRADE selected positively (not as fallback absence of decision)
5. Long/short tie (too close) selects NO_TRADE
6. Timing fields bounded and legal (entry_valid_for_bars 0-5, entry_readiness legal enum)
7. Fallback/degraded paths preserve visibility

### 36.9 Portfolio/Risk Validation
1. Portfolio suppression explicit and traceable to reason
2. Risk blocks explicit and traceable to reason (hard/soft distinction clear)
3. portfolio_blocked and risk_blocked flags set correctly in DecisionEvent
4. Expected-R/probability context preserved through suppression (not lost)
5. Actionability vs execution-eligibility gap measurable
6. Portfolio before risk stage ordering preserved
7. Kill switch blocks execution; lifecycle recording persists

---

## 37. COMPLETE CONFIG LOADER SPECIFICATION

### 37.1 Merge Order
1. Checked-in defaults (lowest priority)
2. Environment config overlay
3. Local developer override (only if explicitly enabled)
4. Environment variables
5. Explicit CLI/runtime overrides (highest priority)

### 37.2 Key Behaviors
- Unknown keys fail by default (strict mode)
- Config validation at load time (fail early)
- Typed config objects with explicit defaults
- No hidden or implicit config mutation
- One authoritative config root (no parallel systems)
- Config families map to pipeline stages
- All thresholds, toggles, constants, ratios, windows, runtime settings go through config

### 37.3 Config Group Structure (recommended)
```
system:
  model_scopes:
    - SWING
    - SCALP
    - AGGRESSIVE_SCALP
  approved_symbols:
    ...
  model_scope_defaults:
    SWING:
      primary_interval: 4h
      context_intervals: [1d]
      refinement_intervals: [1h]
      label_horizon_family: swing_horizon
    SCALP:
      primary_interval: 15m
      context_intervals: [1h]
      refinement_intervals: [5m]
      label_horizon_family: scalp_horizon
    AGGRESSIVE_SCALP:
      primary_interval: 1m
      context_intervals: [5m, 15m]
      refinement_intervals: [1m]
      label_horizon_family: immediate_continuation_short_horizon

simulation:
  profile_version: ...
  cost_model_version: ...
  fee_model_version: ...
  slippage_model_version: ...
  horizon_family: ...
  stop_family: ...
  target_family: ...
  time_exit_family: ...
  invalidation_multiplier: 2.0

labels:
  interpretation_version: ...
  ambiguity_gap_r_threshold: 0.15
  path_quality_high_threshold: 0.70
  path_quality_medium_threshold: 0.40
  min_acceptable_directional_realized_r: 0.25
  saved_loss_threshold: ...
  missed_opportunity_threshold: ...

features:
  schema_version: ...
  normalization_family: ...
  symbol_encoding_family: ...
  enabled_groups:
    - primary_4h
    - htf_1d
    - refinement_1h
    - global

dataset:
  split_family: ...
  fold_count: 6
  min_train_window_days: 365
  validation_window_days: 60
  holdout_window_days: 30
  symbol_weight_cap_ratio: 5.0
  exclude_ambiguous_rows: true
  exclude_unresolved_rows: true

model:
  family: xgboost
  classification_objective: multi_softprob
  regression_objective: reg:squarederror
  hyperparameters:
    max_depth: 6
    n_estimators: 1000
    learning_rate: 0.05
    min_child_weight: 1
    subsample: 0.8
    colsample_bytree: 0.8
    reg_alpha: 0.1
    reg_lambda: 1.0
    early_stopping_rounds: 50
  early_stopping_metric_classification: mlogloss
  early_stopping_metric_regression: rmse

calibration:
  family: ...
  method: isontonic_regression
  split_ratio: 0.5  # of validation window
  recalibration_threshold_drift: 0.02

policy:
  min_confidence: 0.60
  min_expected_r: 0.50
  min_action_probability: 0.40
  max_expected_drawdown: -2.0
  no_trade_margin: 0.10
  score_weights:
    probability_component: 0.40
    expected_r_component: 0.35
    adverse_pressure_component: -0.15
    friction_component: -0.05
    path_quality_component: 0.05
    uncertainty_penalty: 0.00  # config-driven
  timing_advisory_enabled: true
  timing_hard_gate_enabled: false
  blocked_entry_readiness_states:
    - MISSED
  min_entry_valid_for_bars: 0

portfolio:
  max_open_positions: 10
  cluster_exposure_cap: 3
  symbol_concentration_cap: 2
  context_fallback_behavior: safe_non_execution

risk:
  kill_switch_enabled: true
  cooldown_duration_bars: 12
  cooldown_scope: symbol_local
  max_gross_exposure: 1.0
  max_per_symbol_exposure: 0.2
  max_cluster_exposure: 0.4
  duplicate_protection_enabled: true
  stale_result_max_age_bars: 5
  degraded_result_action: safe_non_execution

evaluation:
  min_promotion_r_improvement: 0.10
  max_calibration_error_regression: 0.01
  max_no_trade_degradation_pct: 1.0
  min_expected_r_rank_quality: 0.0
  ablation_test_enabled: true
  baseline_retention_count: 2

monitoring:
  drift_detection_enabled: true
  continuous_feature_drift_method: PSI
  missingness_shift_method: absolute_rate_delta
  symbol_mix_shift_method: total_variation_distance
  expected_r_distribution_shift_method: bucket_delta
  timing_gate_promotion_windows: 3
  min_samples_per_timing_state: 30
  outcome_lag_threshold_hours: 72

deployment:
  rollout_mode: replay
  shadow_required_for_first_live: true
  entry_timing_gate_enabled: false
  kill_switch_blocks_execution: true
  kill_switch_preserves_recording: true
  rollback_preserves_compatibility: true
```

---

## 38. COMPLETE TEST COMMAND REFERENCE

```bash
# Top-level verification
ruff check .
black --check .
mypy src
pytest -q

# Unit tests
pytest tests/unit -q
pytest tests/unit/contracts -q
pytest tests/unit/simulation -q
pytest tests/unit/labels -q
pytest tests/unit/features -q
pytest tests/unit/dataset -q
pytest tests/unit/model -q
pytest tests/unit/calibration -q
pytest tests/unit/policy -q
pytest tests/unit/portfolio -q
pytest tests/unit/risk -q
pytest tests/unit/runtime -q
pytest tests/unit/evaluation -q
pytest tests/unit/monitoring -q

# Integration tests
pytest tests/integration -q
pytest tests/integration/test_analysis_flow.py -q
pytest tests/integration/test_simulation_label_flow.py -q
pytest tests/integration/test_training_evaluation_flow.py -q
pytest tests/integration/test_deployment_safety.py -q

# Regression tests
pytest tests/regression -q

# Filtered tests
pytest -k "calibration and not slow" -q
pytest -k "hybrid and not integration" -q
pytest -k "contract_validation" -q

# Slow/integration/regression marks
pytest -m "not slow" -q
pytest -m "slow" -q
pytest -m "integration" -q
pytest -m "regression" -q
```

---

## 39. COMPLETE PRIORITY AND SEQUENCING RULES

### 39.1 Implementation Priority (by phase dependency)
1. Phase 0 (no dependencies)
2. Phase 1 (needs Phase 0)
3. Phase 2 (needs Phase 1 — contracts for simulation lineage)
4. Phase 3 (needs Phase 2 — simulation outputs for labels)
5. Phase 4 (needs Phases 2+3 — features + labels for dataset)
6. Phase 5 (needs Phase 4 — dataset for training)
7. Phase 6 (needs Phase 5 — model for calibration/policy)
8. Phase 7 (needs Phase 6 — policy for integration)
9. Phase 8 (needs Phases 5+6+7 — model/calibration/policy/runtime for evaluation)
10. Phase 9 (needs Phase 8 — evaluation for deployment safety)

### 39.2 Soft Iteration Loops (allowed without breaking dependency chain)
- Phase 5 ↔ Phase 6: return from policy/calibration to model when classification calibration error remains high, expected-R regression quality too weak, probability/expected-R conflict policy cannot stabilize, no-trade distribution pathological after calibration+policy.
- Phase 6 ↔ Phase 8: return from evaluation to calibration/policy when promotion failure caused by threshold/policy behavior, expected-R gate blocks too many profitable trades or allows too many negative expectancy trades, confidence vs expected-R conflict causes bad behavior, timing advisory shows no measurable value.
- Phase 7 ↔ Phase 8: return from evaluation to runtime integration when actionability vs execution-eligibility gap above tolerance, fallback/degraded paths dominate beyond health thresholds, lifecycle objects carry hybrid outputs incorrectly, portfolio/risk suppression hides expected-R/probability context.

### 39.3 Promotion Gate Sequence (per model_scope)
1. Candidate artifact (Phase 5)
2. Evaluation-promotable (Phase 8) — evidence-based
3. Live-eligible (Phase 9) — operational safety gates passed

### 39.4 Rollout Mode Sequence
1. Replay-only
2. Paper
3. Shadow (required for first live-eligible release unless waived)
4. Live-eligible

### 39.5 Timing Extension Gating Sequence
1. Phase 1: contract acceptance (validate, persist, log, no hard gates)
2. Phase 2: observability only (compare READY_NOW vs outcome, CHASING vs regret, EXPIRING vs missed-opportunity)
3. Phase 3: optional gating only after evidence (suppress MISSED, optionally down-rank CHASING, require entry_valid_for_bars>0)

### 39.6 Truth Hierarchy (when components disagree)
1. Simulation truth
2. Realized market outcome truth
3. Contract truth
4. Runtime interpretation truth
5. Model explanation

### 39.7 Fallback Severity Priority (most conservative wins)
1. Hard execution safety uncertainty
2. Risk uncertainty
3. Portfolio uncertainty
4. Calibration/artifact uncertainty
5. Request quality degradation

---

## 40. COMPLETE FILE AND MODULE NAMING CONVENTIONS

### 40.1 Python Module Names
```
src/v7/
  __init__.py
  contracts/
    __init__.py
    analysis_request.py
    analysis_request_validator.py
    analysis_result.py
    analysis_result_validator.py
    decision_event.py
    decision_event_validator.py
    trade_outcome.py
    trade_outcome_validator.py
    types.py  # common enums, version types
  config/
    __init__.py
    loader.py
    schema.py
    defaults.py
  state/
    __init__.py
    canonical_state.py
    state_builder.py
    views.py
  simulation/
    __init__.py
    engine.py
    profiles.py
    adapters.py
    monte_carlo.py
  features/
    __init__.py
    builder.py
    groups.py
    normalization.py
  labels/
    __init__.py
    classification.py
    regression.py
    ambiguity.py
    path_quality.py
  dataset/
    __init__.py
    builder.py
    splits.py
    weighting.py
    versioning.py
  model/
    __init__.py
    trainer.py
    artifact.py
    inference.py
    heads.py
  calibration/
    __init__.py
    classifier_calibration.py
    regression_reliability.py
    artifact.py
  policy/
    __init__.py
    core.py
    gates.py
    score.py
    timing.py
  portfolio/
    __init__.py
    core.py
    clusters.py
    suppression.py
  risk/
    __init__.py
    core.py
    cooldowns.py
    exposure.py
    kill_switch.py
  runtime/
    __init__.py
    request_builder.py
    result_validator.py
    scope_router.py
    event_materializer.py
    outcome_materializer.py
    execution_eligibility.py
  evaluation/
    __init__.py
    walk_forward.py
    metrics.py
    promotion.py
    ablation.py
  monitoring/
    __init__.py
    drift.py
    health.py
    timing.py
    baseline.py
  cli/
    __init__.py
    main.py
    commands/
```

### 40.2 Test Module Names
```
tests/
  unit/
    contracts/
      test_analysis_request_validation.py
      test_analysis_result_validation.py
      test_decision_event_validation.py
      test_trade_outcome_validation.py
      test_contract_roundtrip.py
    simulation/
      test_stop_target_exits.py
      test_cost_model.py
      test_no_trade_outputs.py
      test_mfe_mae.py
      test_adapter_side_effects.py
      test_monte_carlo.py
    labels/
      test_classification_labels.py
      test_regression_targets.py
      test_ambiguity.py
      test_path_quality.py
    features/
      test_feature_groups.py
      test_normalization.py
      test_missing_context.py
      test_symbol_encoding.py
    dataset/
      test_no_leakage.py
      test_walk_forward_splits.py
      test_symbol_balancing.py
      test_per_target_validity.py
    model/
      test_training_smoke.py
      test_artifact_bundle.py
      test_inference.py
      test_early_stopping.py
    calibration/
      test_calibration_artifact.py
      test_raw_vs_calibrated.py
      test_regression_reliability.py
    policy/
      test_action_selection.py
      test_confidence_vs_expected_r.py
      test_timing_legality.py
      test_no_trade_positive_selection.py
    portfolio/
      test_suppression.py
      test_cluster_limits.py
      test_ranking.py
    risk/
      test_kill_switch.py
      test_cooldowns.py
      test_duplicate_protection.py
      test_stale_result.py
    runtime/
      test_request_builder.py
      test_result_validator.py
      test_scope_router.py
      test_event_materialization.py
      test_outcome_lifecycle.py
      test_execution_eligibility.py
    evaluation/
      test_walk_forward_integrity.py
      test_baseline_comparison.py
      test_no_trade_metrics.py
      test_ablation.py
    monitoring/
      test_drift_metrics.py
      test_timing_usefulness.py
      test_outcome_lag.py
  integration/
    test_analysis_flow.py
    test_simulation_label_flow.py
    test_feature_dataset_flow.py
    test_training_evaluation_flow.py
    test_contract_lifecycle.py
    test_deployment_safety.py
  regression/
    test_fixed_bugs.py
```

---

## 41. COMPLETE ARCHITECTURAL DIAGRAM (textual)

```
+------------------+     +-------------------+     +----------------------+
| Raw Market Data  |---->| Canonical State   |---->| Runtime Simulation   |
| (Binance candles)|     | Construction      |     | Engine (truth layer) |
+------------------+     +-------------------+     +----------+-----------+
                                                                |
                                                                v
                                        +-----------------------+
                                        | Comparative Outputs   |
                                        | (LONG/SHORT/NO_TRADE) |
                                        | realized_R, MFE/MAE,  |
                                        | path_quality, regret, |
                                        | saved_loss, missed_op |
                                        +-----------+-----------+
                                                    |
                          +-------------------------+-------------------------+
                          |                                                   |
                          v                                                   v
            +-------------+------------+                     +----------------+
            | Classification Labels   |                     | Regression      |
            | best_action_label,      |                     | Targets         |
            | no_trade_quality,       |                     | expected_r_long,|
            | skip_was_correct        |                     | expected_r_short|
            +-------------+-----------+                     +-------+--------+
                          |                                         |
                          +-----------+-----------------------------+
                                      |
                                      v
                        +-------------+-------------+
                        | Feature Builder           |
                        | (4h + 1d + 1h + global)   |
                        +-------------+-------------+
                                      |
                                      v
                        +-------------+-------------+
                        | Dataset Assembly          |
                        | (walk-forward folds,      |
                        |  symbol weights,          |
                        |  per-target validity)     |
                        +-------------+-------------+
                                      |
                                      v
                  +-------------------+-------------------+
                  | XGBoost Hybrid Training               |
                  | - Action Classifier (LONG/SHORT/NO)   |
                  | - Long Expected-R Regressor           |
                  | - Short Expected-R Regressor          |
                  | - Optional: Adverse/Cost-Adjusted     |
                  +-------------------+-------------------+
                                      |
                                      v
                  +-------------------+-------------------+
                  | Calibration (global per scope)        |
                  | - Calibrated action probabilities     |
                  | - Calibrated confidence               |
                  | - Expected-R reliability review       |
                  +-------------------+-------------------+
                                      |
                                      v
                  +-------------------+-------------------+
                  | Policy Gates                          |
                  | - probability >= min                  |
                  | - expected_r >= min                   |
                  | - drawdown <= max                     |
                  | - no-trade margin satisfied           |
                  | - timing advisory                     |
                  +-------------------+-------------------+
                                      |
                                      v
                  +-------------------+-------------------+
                  | Portfolio Interpretation              |
                  | (pass/suppress/down-rank per symbol)  |
                  +-------------------+-------------------+
                                      |
                                      v
                  +-------------------+-------------------+
                  | Risk Gate                             |
                  | (kill switch, cooldowns, exposure,    |
                  |  duplicate protection, stale/degraded)|
                  +-------------------+-------------------+
                                      |
                                      v
                  +-------------------+-------------------+
                  | Runtime Integration                   |
                  | Request Builder -> Scope Router ->    |
                  | Artifact Selection -> Engine ->       |
                  | Result Validator -> Runtime Interp -> |
                  | DecisionEvent -> Execution Eligibility|
                  | -> TradeOutcome                       |
                  +-------------------+-------------------+
                                      |
                                      v
                  +-------------------+-------------------+
                  | Evaluation & Monitoring               |
                  | - Walk-forward economic metrics       |
                  | - Classification/regression quality   |
                  | - Calibration drift                   |
                  | - Feature drift                       |
                  | - Outcome lag                         |
                  | - Promotion evidence                  |
                  +-------------------+-------------------+
                                      |
                                      v
                  +-------------------+-------------------+
                  | Deployment Safety                     |
                  | - Replay -> Paper -> Shadow -> Live   |
                  | - Rollback bundles                    |
                  | - Kill switch                         |
                  +-------------------+-------------------+
```

---

## 42. COMPLETE CONTRACT FIELD MAP (cross-file consistency)

### 42.1 AnalysisRequest → Consistency Targets
| AnalysisRequest Field | Must Match In | Condition |
|---|---|---|
| request_id | AnalysisResult.identity.request_id, DecisionEvent.identity.request_id, TradeOutcome.lineage.request_id | Always |
| scope.symbol | AnalysisResult.request_link.symbol, DecisionEvent.scope.symbol | Always |
| scope.model_scope | AnalysisResult.request_link.model_scope, DecisionEvent.scope.model_scope | Always |
| scope.requested_trade_mode | AnalysisResult.request_link.trade_mode | When both present |
| scope.primary_interval | AnalysisResult.request_link.primary_interval, DecisionEvent.scope.primary_interval | Always |
| contract.contract_version | AnalysisResult.request_link.request_contract_version, DecisionEvent.contract.request_contract_version | Always |
| lineage.analysis_batch_id | AnalysisResult.lineage.analysis_batch_id, DecisionEvent.lineage.analysis_batch_id, TradeOutcome.lineage.analysis_batch_id | When present |
| lineage.decision_session_id | AnalysisResult.lineage.decision_session_id, DecisionEvent.lineage.decision_session_id, TradeOutcome.lineage.decision_session_id | When present |

### 42.2 AnalysisResult → Consistency Targets
| AnalysisResult Field | Must Match In | Condition |
|---|---|---|
| request_id | AnalysisRequest.identity.request_id, DecisionEvent.identity.request_id, TradeOutcome.lineage.request_id | Always |
| identity.engine_name | DecisionEvent.lineage.engine_name, TradeOutcome.lineage.engine_name | Always |
| identity.engine_version | DecisionEvent.lineage.engine_version, TradeOutcome.lineage.engine_version | Always |
| decision.recommended_action | DecisionEvent.decision_summary.recommended_action | Always |
| decision.direction | DecisionEvent.decision_summary.direction | Always |
| status.is_actionable | DecisionEvent.decision_summary.is_actionable | Always |
| scores.confidence | DecisionEvent.decision_summary.confidence | When surfaced |
| scores.expected_r | DecisionEvent.decision_summary.expected_r | When surfaced |
| execution_guidance.entry_readiness | DecisionEvent.decision_summary.entry_readiness_seen | When surfaced |
| execution_guidance.entry_valid_for_bars | DecisionEvent.decision_summary.entry_valid_for_bars_seen | When surfaced |

### 42.3 DecisionEvent → Consistency Targets
| DecisionEvent Field | Must Match In | Condition |
|---|---|---|
| decision_event_id | TradeOutcome.identity.decision_event_id | Always |
| identity.request_id | AnalysisRequest.identity.request_id, AnalysisResult.identity.request_id, TradeOutcome.lineage.request_id | Always |
| decision_summary.confidence | TradeOutcome.realized_outcome.decision_confidence_seen | When stored |
| decision_summary.expected_r | TradeOutcome.realized_outcome.decision_expected_r_seen | When stored |
| decision_summary.entry_readiness_seen | TradeOutcome.realized_outcome.entry_readiness_seen | When stored |
| decision_summary.entry_valid_for_bars_seen | TradeOutcome.realized_outcome.entry_valid_for_bars_seen | When stored |
| lineage.analysis_batch_id | TradeOutcome.lineage.analysis_batch_id | When present |
| lineage.decision_session_id | TradeOutcome.lineage.decision_session_id | When present |

---

## END OF AI SUMMARY

This document contains the complete lossless synthesis of every V7 markdown file in the repository. It is designed as a fast single-file reference for AI context loading. Every rule, invariant, field, config surface, phase detail, contract semantic, pipeline specification, and ownership boundary from the original 45+ markdown files has been preserved.

**When to use this file:**
- Initial AI context loading before any implementation
- Quick reference during implementation to find the right values, enums, or config keys
- Cross-checking consistency across contracts, pipeline stages, and phases
- Understanding the full system without reading all 45+ files

**When to consult original docs:**
- When implementing a specific phase and need exact acceptance criteria
- When the summary's condensed form loses nuance
- When there is any ambiguity about ownership boundaries
- When field-level details must be verified against the authority doc

**Canonical file paths for original docs:**
- docs/vision.md
- docs/architecture.md
- docs/roadmap.md
- docs/README.md
- docs/v7_llm_rules.md
- docs/v7_doc_writing_guide.md
- docs/contracts/README.md
- docs/contracts/analysis_request.md
- docs/contracts/analysis_result.md
- docs/contracts/decision_event.md
- docs/contracts/trade_outcome.md
- docs/runtime/simulation_engine.md
- docs/runtime/runtime_integration.md
- docs/runtime/fallback_policy.md
- docs/runtime/deployment_safety.md
- docs/pipeline/simulation.md
- docs/pipeline/training.md
- docs/pipeline/labels.md
- docs/pipeline/features.md
- docs/pipeline/dataset.md
- docs/pipeline/model.md
- docs/pipeline/calibration.md
- docs/pipeline/policy.md
- docs/pipeline/portfolio.md
- docs/pipeline/risk.md
- docs/pipeline/evaluation.md
- docs/pipeline/monitoring.md
- docs/implementation/master_plan.md
- docs/implementation/phase_0_repo_alignment_and_foundations.md
- docs/implementation/phase_1_contracts_and_validation.md
- docs/implementation/phase_2_simulation_truth_layer.md
- docs/implementation/phase_3_labels_and_outcome_semantics.md
- docs/implementation/phase_4_features_and_dataset.md
- docs/implementation/phase_5_model_baseline.md
- docs/implementation/phase_6_calibration_and_policy.md
- docs/implementation/phase_7_portfolio_risk_and_runtime_integration.md
- docs/implementation/phase_8_evaluation_and_monitoring.md
- docs/implementation/phase_9_deployment_safety_and_release.md
- docs/v7_executor_support_pack/executor_prompt_pack.md
- docs/v7_executor_support_pack/naming_and_path_consistency.md
- docs/v7_executor_support_pack/phase_to_doc_authority_matrix.md
