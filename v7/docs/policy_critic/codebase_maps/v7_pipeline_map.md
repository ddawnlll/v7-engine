# Codebase Map: V7 Policy Decision Pipeline (v7-engine + v6 inference engine implementation)

## Subsystem Identity
IMPORTANT REALITY CHECK: The v7-engine repo's `v7/src/` directory is EMPTY (only `.gitkeep`). The V7 policy/scoring/calibration/gating implementation does NOT yet exist as code inside this repo. The actual running decision pipeline is the V6 inference engine in the SIBLING repo `/home/erfolg/src/trading-bot/v6/`, which the v7-engine runtime imports (`from v6.engine import EngineManager`, `from v6.contracts.analysis_result import AnalysisResult`). The V7 docs (ai_summary, policy.md, model.md) define the TARGET decision flow; AlphaForge docs + prediction_schema_v1.json define the planned V7-native flow. Below I map both the implemented (V6) flow with file:line refs and the documented (V7) flow.

IMPLEMENTED FLOW (V6 inference engine — the live decision path today):
1. Features: `V6InferenceEngine.infer()` at /home/erfolg/src/trading-bot/v6/engine/inference_engine.py:158. Feature vector extracted from AnalysisRequest via `extract_feature_vector()` (line 147) using `self.feature_columns` from the model artifact. Scope compatibility validated first (line 161, `_validate_scope_compatibility`).
2. Score (GBDT/scorer consumption): `_score_heads_with_calibration()` at inference_engine.py:505. For each head (long/short/no_trade) the XGBoost model produces `raw_probabilities` via `positive_class_probabilities(bundle.model, model_input)` (line 513), then a per-head calibrator transforms them: `calibrated_scores = calibrator.transform(raw_probabilities)` (line 515). Produces `raw_head_scores` {long, short, no_trade} and `calibrated_head_scores` {long, short, no_trade} (lines 248-253). Calibration guard applied at line 518 (`_apply_calibration_guard`) with extrapolation guard.
3. Confidence calibrator: `_resolve_confidence_semantics()` at inference_engine.py:934. Produces `confidence_raw_score`, `confidence_final_score`, `confidence_kind` (values: "legacy_max_head", "no_trade_probability", "actionability_v1", "hybrid_conviction_v1", "hybrid_no_trade_block", "hybrid_setup_gate"). Uses `directional_actionability_score()` (decision_modeling.py:3625) which computes a geometric mean of selected_probability, threshold_clearance, margin_clearance, no_trade_gap_clearance.
4. Hard gate (action selection): `choose_action()` at /home/erfolg/src/trading-bot/v6/training/decision_modeling.py:1461. Gates in order: (a) no_trade_threshold gate — if p_no_trade >= thresholds.no_trade_threshold → NO_TRADE; (b) directional threshold gate — winner must be >= long_threshold/short_threshold; (c) decision_margin gate — margin = winner - alternative must be >= thresholds.decision_margin. If any fails → NO_TRADE with reason_path.
5. Final gate (hybrid deterministic overlay): in `_build_result()` at inference_engine.py:282-349. After choose_action, if hybrid enabled and action is LONG/SHORT: computes `setup_score` via `compute_phase14_setup_score()` (decision_modeling.py:3605, weighted blend of structure_cleanliness, entry_timing_quality, htf_directional_agreement, htf_structure_strength, local_smoothness, stable_state). Then: (a) HARD_BLOCK if recommended action in `request.deterministic_context.blocked_actions` → forced NO_TRADE, constraint_level=HARD_BLOCK, deterministic_block set (line 326-336); (b) setup_score gate — if setup_score < min_setup_score_for_directional → NO_TRADE, constraint_level=WARNING, setup_gate_reason set (line 337-349). Final confidence blended via `blend_hybrid_conviction()` (decision_modeling.py:3653).
6. Final action mapping: inference_engine.py:350-372 maps final_action to RecommendedAction (LONG_NOW/SHORT_NOW/NO_TRADE), Direction, SignalStatus (SIGNAL/NO_TRADE/FILTERED/REJECTED), DecisionStatus (VALID/LOW_CONFIDENCE/BLOCKED).
7. Runtime execution eligibility (NOT in engine): per v7/docs/runtime/runtime_integration.md:308-346, runtime applies a layered gate AFTER the engine result: structural validity → engine actionability (is_actionable) → confidence gate (confidence >= min_confidence) → economic gate (expected_r >= min_expected_r) → timing gate (advisory) → operational hard gate (exchange/cooldown/exposure/kill-switch). This is documented but the runtime execution orchestrator (/home/erfolg/src/v7-engine/runtime/runtime/execution_orchestrator.py) handles execution routing, not policy re-derivation.

DOCUMENTED TARGET FLOW (V7-native, not yet implemented in v7/src):
Per alphaforge/docs/ai_summary__v7_alphaforge_xgb.md sections 12-15 and prediction_schema_v1.json:
features → XGBoost classifier (p_long, p_short, p_no_trade) + regressors (expected_R_long, expected_R_short) → calibration (calibrated_p_long, calibrated_p_short, calibrated_p_no_trade, calibrated_confidence, confidence_kind, reliability_error) → alpha score builder (long_alpha_R = calibrated_p_long * max(expected_R_long,0) * confidence; short_alpha_R = calibrated_p_short * max(expected_R_short,0) * confidence) → V7 policy gates (min_alpha_R, min_confidence, require_expected_R_above, regime modifier, no_trade comparison, portfolio pressure, risk hard gates) → recommended_action. Policy thresholds per mode at ai_summary__v7_alphaforge_xgb.md:928-946 (SWING min_long_alpha_R=0.20, SCALP=0.10, AGGRESSIVE_SCALP=0.06).

## Key Files
- **/home/erfolg/src/trading-bot/v6/engine/inference_engine.py** — Implemented V6 inference engine: feature extraction, head scoring with calibration (_score_heads_with_calibration:505), confidence semantics (_resolve_confidence_semantics:934), hybrid setup-score gate and deterministic hard block (_build_result:235-459). This is the live decision path imported by v7-engine runtime.
- **/home/erfolg/src/trading-bot/v6/training/decision_modeling.py** — Hard gate action selection choose_action() (line 1461): no_trade_threshold gate, directional threshold gate, decision_margin gate. Also directional_actionability_score (3625), compute_phase14_setup_score (3605), blend_hybrid_conviction (3653), low_setup_rejection_strength (3668).
- **/home/erfolg/src/trading-bot/v6/contracts/analysis_result.py** — AnalysisResult contract with exact field names: ScoresSection (confidence, probability, long_score, short_score, no_trade_score, expected_return, expected_drawdown, expected_hold_time, risk_reward_estimate, decision_margin), DecisionSection (recommended_action, direction), StatusSection (signal_status, decision_status, is_actionable), DeterministicInteractionSection (deterministic_alignment, deterministic_warning, deterministic_block, constraint_level, regime_transition_risk), FallbackDegradationSection (fallback_used, runtime_safe_action).
- **/home/erfolg/src/v7-engine/alphaforge/docs/schemas/prediction_schema_v1.json** — V7-native AlphaForge prediction schema (target, not yet implemented): required keys symbol, timestamp, mode, model_scope, p_long, p_short, p_no_trade, expected_R_long, expected_R_short, confidence, confidence_kind, long_alpha_R, short_alpha_R, model_artifact_version. confidence_kinds: calibrated/raw/degraded/unavailable. Regime reason codes: regime_gate_forced_no_trade, regime_blocked_direction, regime_threshold_multiplier_applied.
- **/home/erfolg/src/v7-engine/alphaforge/docs/ai_summary__v7_alphaforge_xgb.md** — Authoritative V7-native decision design: calibration outputs (calibrated_p_long/short/no_trade, calibrated_confidence, confidence_kind, reliability_error — section 12, lines 798-806), alpha score builder formulas (long_alpha_R, short_alpha_R — section 13, lines 830-831), policy alignment thresholds per mode (section 15, lines 928-946), V7 integration contract runtime request path (section 14, lines 849-858).
- **/home/erfolg/src/v7-engine/v7/docs/pipeline/policy.md** — V7 policy authority (docs): 8 decision gates (probability/confidence, no-trade comparison, decision margin, expected-R, cost-adjusted expectancy, adverse-pressure/drawdown, regime consistency, degradation/fallback), regime-aware modifiers (TREND_UP blocks SHORT, TREND_DOWN blocks LONG, TRANSITION require_no_trade), policy_score formula.
- **/home/erfolg/src/v7-engine/v7/docs/ai_summary.md** — V7 dense synthesis: policy config surface (lines 2212-2229: min_confidence, min_expected_r, min_action_probability, max_expected_drawdown, no_trade_margin, score_weights), model output surface (expected_r_long, expected_r_short, p_long_now, p_short_now, p_no_trade), 8 policy gates (section 19.2).
- **/home/erfolg/src/v7-engine/v7/docs/runtime/runtime_integration.md** — Runtime execution eligibility stack (lines 308-346): layered gates AFTER engine result — structural validity, engine actionability, confidence gate, economic gate, timing gate, operational hard gate. Defines actionability vs execution eligibility boundary.
- **/home/erfolg/src/v7-engine/contracts/mappings/alphaforge_to_v7.md** — AlphaForge→V7 handoff bridge: maps AlphaForge evidence (cost_stress, regime_breakdown, no_trade_comparison) to V7 G0-G10 gates. Establishes V7 as final acceptance authority.
- **/home/erfolg/src/v7-engine/runtime/services/analyzer_engine_contract.py** — Runtime-side normalized AnalysisResult contract (Pydantic) with fields: signal_status, direction, confidence, probability, corrected_probability, recommended_action, static_engine_raw_confidence, gate_owner, gate_decision, confidence_gap, decision_payload. This is the runtime-facing adapter shape.
- **/home/erfolg/src/v7-engine/runtime/services/analyzer_engine_adapter.py** — Adapter bridging V6 AnalysisResult to runtime normalized contract; imports v6.engine.EngineManager and v6.contracts. Contains regime display logic (_display_regime:75), human summary formatting with confidence/regime.
- **/home/erfolg/src/v7-engine/v7/src/.gitkeep** — Marker showing v7/src/ is empty — the V7-native policy/calibration/scoring modules (src/v7/alpha/policy_bridge/, scoring/, calibration/) are NOT yet implemented. P7 phase plan documents the intended work.

## Critic Integration Points
A "V7 Policy Critic" would insert BETWEEN the hard gate (choose_action at decision_modeling.py:1461, which produces the ML-selected action) and the final hybrid deterministic overlay/final action mapping (inference_engine.py:282-372, which applies setup_score gate + deterministic hard block + produces final recommended_action).

Concretely, in the implemented V6 path: after `decision = choose_action(score_row, ...)` at inference_engine.py:182 and before the hybrid block at line 282 (`if final_action in {"LONG", "SHORT"} and getattr(hybrid_cfg, "enabled", False)`). The critic would consume: calibrated_head_scores {long, short, no_trade}, raw_head_scores, confidence_raw_score, confidence_final_score, confidence_kind, decision.action, decision.reason_path, thresholds (long_threshold, short_threshold, no_trade_threshold, decision_margin), setup_score + setup_components, regime (from request.deterministic_context.regime_label / snapshot regime), and the feature_map. It would emit: a critic_score / critic_adjusted_confidence, a critic_gate_decision (PASS/DOWNGRADE/BLOCK), critic_reason_codes, and optionally a critic_adjusted_action (but constrained to NO_TRADE-or-preserve per domain rules). 

In the documented V7-native target path (alphaforge ai_summary section 14-15), the critic inserts between the alpha score builder (long_alpha_R/short_alpha_R) and the V7 policy gates — i.e., after calibration + alpha score computation, before min_alpha_R/min_confidence/regime/portfolio/risk gates. It would consume calibrated_p_long/short/no_trade, expected_R_long/short, long_alpha_R, short_alpha_R, confidence, confidence_kind, regime_state, and emit a critic-adjusted alpha_R or a critic veto signal feeding the policy gate sequence.

The cleanest insertion point in BOTH flows is: post-calibration, post-hard-gate, pre-final-action-emission. The critic must NOT replace the hard gate or the final deterministic/risk hard block; it sits between them as an additional evidence-adjustment/down-rank layer.

## Available Reward Signals for Offline RL Training
V7 currently exposes (or is designed to expose) these signals usable for offline RL training:
1. realized_r / realized_R (R-multiple net of costs) — from TradeOutcome.realized_outcome.realized_r; the primary economic reward. Simulation owns this (simulation/engine/engine.py).
2. long_realized_r_net, short_realized_r_net — per-action net R from simulation labels (v7/docs/pipeline/labels.md section 13.3).
3. regret_r, saved_loss_score, missed_opportunity_score — comparative outcome signals from TradeOutcome.comparative_outcome (contract section 7.11). These are natural RL reward shaping signals.
4. mfe_r, mae_r, path_quality_score — path metrics (TradeOutcome.path_metrics, section 7.10).
5. cost-adjusted expectancy / expected_cost_adjusted_r — economic gate signal (model output surface, v7/docs/pipeline/model.md section 16.3).
6. calibrated_confidence + reliability_error — calibration quality signal (can serve as confidence-aware reward weight).
7. decision_margin (abs(p_long - p_short)) — action separation signal, already produced at inference_engine.py:429.
8. no_trade_quality_label / skip_was_correct — no-trade correctness signal (labels section 13.2).
9. expectancy_r, win_rate — evaluation metrics (v6 evaluation/expectancy_eval.py).
10. G3 cost_stress survival — from AlphaForge validation_report cost_stress field (contracts/schemas/alphaforge/validation_report.schema.json); binary cost-resilience signal.
11. regime_breakdown per-regime realized R — from AlphaForge mode_research_report (regime_breakdown field); regime-conditioned reward.
12. hybrid_conviction / setup_score — the blended confidence signal (inference_engine.py:294-323); could serve as a critic-training target.

For offline RL, the richest tuple is (features, calibrated_scores, confidence, decision, regime, realized_r, regret_r, saved_loss_score, path_quality_score) — all present in the DecisionEvent + TradeOutcome contract lineage.

## Domain Boundary Constraints
Per CLAUDE.md and profitability_thesis.md, a V7 Policy Critic MUST NOT:
1. Invent alpha. AlphaForge discovers alpha; V7 owns policy acceptance. The critic must not generate new features or alpha signals — it only adjusts/down-ranks existing calibrated evidence.
2. Override risk hard gates. Model confidence must NOT override risk gates (CLAUDE.md forbidden actions). The critic cannot force execution past kill_switch, cooldown, exposure limits, or duplicate protection (runtime/runtime_integration.md operational hard gate, layer 6).
3. Bypass simulation economic truth. Simulation owns cost/horizon/exit semantics. The critic must not recompute realized R, costs, or labels (truth hierarchy: simulation > realized > contract > runtime > model).
4. Make final trade decisions outside V7. V7 owns final trade decisions; AlphaForge does not. The critic is part of V7 policy, so this is satisfied if it lives in v7/alpha/policy_bridge, but it must not emit execution commands (runtime owns execution eligibility).
5. Override the deterministic hard block. The HARD_BLOCK path (inference_engine.py:326-336) and constraint_level=HARD_BLOCK are operational safety; the critic must not downgrade a hard block to advisory.
6. Add new trading modes or actions. Action space is locked to LONG_NOW/SHORT_NOW/NO_TRADE (DEC-002). The critic may only select among these or down-rank to NO_TRADE.
7. Change locked timeframe stacks without contradiction evidence.
8. Silently suppress. Per no-hidden-veto invariant (#7) and regime override visibility (ai_summary section 6A.2), any critic suppression must be explicit, observable, testable — emit reason codes (e.g., critic_gate_forced_no_trade) into AnalysisResult.deterministic_interaction and DecisionEvent.
9. Treat backtest pass as live promotion evidence. Critic outputs are policy evidence, not promotion authority (evaluation owns promotion via G0-G10).
10. Let model confidence override policy. The critic consumes confidence but must not make confidence-only the execution condition (runtime_integration.md moves away from confidence>=min_confidence=>execute toward layered gates).

## Fields Produced/Consumed
- `confidence (ScoresSection.confidence — final calibrated/hybrid confidence, inference_engine.py:422)`
- `probability (ScoresSection.probability — calibrated probability of selected head, inference_engine.py:423)`
- `long_score (calibrated p_long, inference_engine.py:424)`
- `short_score (calibrated p_short, inference_engine.py:425)`
- `no_trade_score (calibrated p_no_trade, inference_engine.py:426)`
- `decision_margin (abs(p_long - p_short), inference_engine.py:429)`
- `confidence_kind (string: legacy_max_head/no_trade_probability/actionability_v1/hybrid_conviction_v1/hybrid_no_trade_block/hybrid_setup_gate, inference_engine.py:262-304)`
- `confidence_raw_score (raw head confidence before calibration/hybrid blend, inference_engine.py:280,934)`
- `confidence_final_score (final confidence after calibration/hybrid blend, inference_engine.py:281,934)`
- `recommended_action (LONG_NOW/SHORT_NOW/NO_TRADE, DecisionSection, inference_engine.py:352-362)`
- `direction (LONG/SHORT/NONE, inference_engine.py:352-362)`
- `is_actionable (StatusSection, =decision.executed, inference_engine.py:413)`
- `signal_status (SIGNAL/NO_TRADE/FILTERED/REJECTED/DEGRADED/ERROR, inference_engine.py:354-372)`
- `decision_status (VALID/LOW_CONFIDENCE/BLOCKED/DEGRADED/FAILED, inference_engine.py:355-372)`
- `deterministic_alignment (ALIGNED/NEUTRAL/WARNED/HARD_BLOCKED, inference_engine.py:327-338)`
- `constraint_level (NONE/WARNING/HARD_BLOCK, inference_engine.py:328-339)`
- `deterministic_block (string reason, inference_engine.py:329)`
- `deterministic_warning (string reason, inference_engine.py:341)`
- `setup_score (hybrid setup quality, decision_modeling.py:3605)`
- `ml_conviction_score (directional actionability, inference_engine.py:395)`
- `final_hybrid_conviction (blended confidence, inference_engine.py:396)`
- `hybrid_gate_triggered (bool, inference_engine.py:397)`
- `hybrid_gate_reason (string, inference_engine.py:398)`
- `regime (from request.deterministic_context.regime_label / snapshot.regime, analyzer_engine_adapter.py:75-96)`
- `regime_transition_risk (DeterministicInteractionSection, analysis_result.py:154)`
- `runtime_safe_action (NO_TRADE/SKIP/HOLD, FallbackDegradationSection, analysis_result.py:168)`
- `fallback_used (bool, analysis_result.py:164)`
- `expected_R_long / expected_R_short (AlphaForge prediction_schema_v1.json — TARGET V7-native, not yet in v6)`
- `expected_r_long / expected_r_short (V7 docs target, v7/docs/pipeline/model.md:83-84)`
- `long_alpha_R / short_alpha_R (AlphaForge target, ai_summary__v7_alphaforge_xgb.md:830-831)`
- `calibrated_confidence (AlphaForge target, ai_summary__v7_alphaforge_xgb.md:802)`
- `calibrated_p_long / calibrated_p_short / calibrated_p_no_trade (AlphaForge target, ai_summary__v7_alphaforge_xgb.md:799-801)`
- `no_trade_margin (V7 policy config key only, v7/docs/ai_summary.md:2217 — NOT a produced field)`
- `cost_stress (AlphaForge validation_report/mode_research_report schema field, contracts/mappings/alphaforge_to_v7.md:19,33)`
- `expected_return (ScoresSection, v6 contract — R-multiple expected return, analysis_result.py:113)`
- `expected_drawdown (ScoresSection, analysis_result.py:114)`

## Notes
FIELD EXISTENCE AUDIT (fields the task asked about):
- expected_R_LONG / expected_R_SHORT (uppercase): EXIST only in AlphaForge prediction_schema_v1.json (lines 13-14) and ai_summary__v7_alphaforge_xgb.md — these are TARGET V7-native fields, NOT yet implemented in any .py code. The lowercase expected_r_long/expected_r_short appear in V7 docs (pipeline/model.md, ai_summary.md) as planned regression head outputs. The implemented V6 engine does NOT produce these — it produces long_score/short_score (calibrated probabilities) and expected_return (single value), not per-direction expected R.
- raw_confidence: NOT a standalone field name. The implemented fields are confidence_raw_score / confidence_final_score (inference_engine.py:280-281) inside score_breakdown, and static_engine_raw_confidence in the runtime adapter contract (analyzer_engine_contract.py:64).
- calibrated_confidence: EXISTS only as a TARGET in AlphaForge docs (ai_summary__v7_alphaforge_xgb.md:802) and in swing_patch_validation_service.py (as avg_calibrated_confidence in validation buckets). The implemented engine uses confidence_final_score + confidence_kind instead.
- no_trade_margin: EXISTS only as a POLICY CONFIG KEY (v7/docs/ai_summary.md:2217), not as a produced/consumed decision field. It is a threshold, not a signal.
- cost_stress: EXISTS as an AlphaForge evidence field in validation_report.schema.json and mode_research_report.schema.json, mapped to V7 G5 gate (alphaforge_to_v7.md:19,33). Not produced by the inference engine.
- regime: EXISTS as a context input (request.deterministic_context.regime_label, snapshot.regime, market_context.regime) consumed by analyzer_engine_adapter.py:75-96 (_display_regime). Not a produced field by the model. Regime policy modifiers are documented (v7_mode_centric_architecture.md section 5.4) but the regime gate implementation in v6 is the deterministic blocked_actions / setup_score path, not a separate regime_gate module.
- proposed_action: DOES NOT EXIST anywhere in the codebase or docs.
- bad_trade_probability: DOES NOT EXIST anywhere in the codebase or docs.
- model_disagreement: DOES NOT EXIST anywhere in the codebase or docs.
- recent_prediction_error: DOES NOT EXIST anywhere in the codebase or docs.

KEY ARCHITECTURAL FACT: The v7-engine repo is in a docs-first design-lock phase. v7/src/ is empty. The actual decision pipeline runs through the V6 engine (sibling repo /home/erfolg/src/trading-bot/v6/), imported by runtime/services/analyzer_engine_adapter.py. The V7-native policy_bridge/scoring/calibration modules (alphaforge/docs/phase_plans/P7) are PLANNED but not implemented. Any PolicyCritic implementation would be greenfield in v7/src/v7/alpha/policy_bridge/ and would need to wire into the runtime adapter path that currently delegates to V6.

The hard gate (choose_action) and the final gate (hybrid deterministic overlay in _build_result) are BOTH inside the V6 engine, not separated into distinct V7 modules. The "between hard gate and final gate" insertion point is therefore inside inference_engine.py:182-282, which would require either patching V6 or building the V7 policy_bridge to replace that segment of the flow.