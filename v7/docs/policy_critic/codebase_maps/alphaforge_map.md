# Codebase Map: AlphaForge (alpha discovery authority) — XGBoost/GBDT scorer, label engine, feature surface, calibration

## Subsystem Identity
AlphaForge is currently SPEC-ONLY: alphaforge/src/ contains only a .gitkeep; no scorer/calibrator/label-engine source is implemented yet. The authoritative decision flow is defined in alphaforge/docs/ai_summary__v7_alphaforge_xgb.md and contracts, planned for implementation under src/v7/alpha/ in phases P5 (training), P6 (calibration+scoring), P9 (drift monitoring).

Flow (per symbol, timestamp, mode — SCALP/AGGRESSIVE_SCALP/SWING):
1. Canonical State Builder builds point-in-time state from multi-timeframe stack (1m/5m/15m/1h/4h/1d).
2. Shared Feature Engine produces primary/context/refinement interval features + unsupervised context features (anomaly_score, regime_id, reconstruction_error, isolation_forest_score).
3. V7 Simulation Label Adapter consumes SimulationOutput (economic truth owned by simulation/) and produces labels: best_action_label (LONG_NOW/SHORT_NOW/NO_TRADE/AMBIGUOUS_STATE), y_reg_long=long_R_net, y_reg_short=short_R_net, mae/adverse-pressure targets. Labels are cost-net (fee+slippage; funding DEFERRED).
4. Mode-specific XGBoost bundle trains: action_classifier (LONG/SHORT/NO_TRADE) + long_expected_R_regressor + short_expected_R_regressor + long/short adverse_pressure_regressor + optional path_quality_regressor. Walk-forward splits (6 folds, 12mo train / 2mo val).
5. Calibration & Reliability Layer maps raw XGBoost scores → calibrated_p_long/calibrated_p_short/calibrated_p_no_trade + calibrated_confidence + confidence_kind + reliability_error + expected-R reliability buckets (predicted bucket vs realized avg R, sign correctness, adverse pressure reliability).
6. Alpha Score Builder computes:
   long_alpha_R = calibrated_p_long * max(expected_R_long, 0) * confidence
   short_alpha_R = calibrated_p_short * max(expected_R_short, 0) * confidence
   directional_edge_R = (calibrated_p_long * expected_R_long) - (calibrated_p_short * expected_R_short)
   and emits recommended_alpha_action.
7. Output row (alpha_prediction_table / v7_alpha_prediction_row schema) is delivered to V7 as an AnalysisResult. V7 then applies policy/portfolio/risk/execution-eligibility gates — V7 owns the final trade decision. AlphaForge RECOMMENDS; V7 DECIDES.

The prediction row required keys (prediction_schema_v1.json): symbol, timestamp, mode, model_scope, p_long, p_short, p_no_trade, expected_R_long, expected_R_short, confidence, confidence_kind, long_alpha_R, short_alpha_R, model_artifact_version. confidence_kind ∈ {calibrated, raw, degraded, unavailable}. probability_sum_tolerance=0.02. Monitoring slices required: model_preferred_no_trade, regime_forced_no_trade, risk_forced_no_trade, fallback_safe_no_trade.

## Key Files
- **/home/erfolg/src/v7-engine/alphaforge/docs/ai_summary__v7_alphaforge_xgb.md** — Canonical dense synthesis: scorer architecture, calibration outputs, alpha score formulas, prediction row fields, policy thresholds, phase plan. Sections 7.5 (alpha_prediction_table), 11 (training design), 12 (calibration+reliability), 13 (alpha score builder), 14 (V7 integration contract with example payload/output).
- **/home/erfolg/src/v7-engine/alphaforge/docs/schemas/prediction_schema_v1.json** — Runtime prediction row schema: required keys (p_long/p_short/p_no_trade, expected_R_long/short, confidence, confidence_kind, long_alpha_R, short_alpha_R), confidence_kinds enum, monitoring slices, deterministic regime interaction fields.
- **/home/erfolg/src/v7-engine/alphaforge/docs/label_contract.md** — Label engine spec: SimulationOutput → AlphaForgeLabel mapping. Label fields: long_R_net/short_R_net, long/short_mfe_R/mae_R, saved_loss_score, missed_opportunity_score, no_trade_quality, best_action_label, label_validity, cost-aware gross/net fields. Funding DEFERRED hold.
- **/home/erfolg/src/v7-engine/alphaforge/docs/feature_contract.md** — Feature surface spec: FeatureSetSpec, feature groups (Returns/Volatility/ATR/Momentum/Volume/Breakout/Lead-Lag/Regime/Cost-Proxy), required metadata, leakage rules, mode-specific timeframe stacks.
- **/home/erfolg/src/v7-engine/alphaforge/docs/model_artifact_contract.md** — ModelArtifact + CalibrationCandidate formats. CalibrationCandidate carries calibration_method (isotonic/platt/beta/none), calibration_metrics (expected_calibration_error/ECE, maximum_calibration_error/MCE, brier_score, reliability_curve, sharpness), confidence_bins, status (CALIBRATED/UNCALIBRATED/UNRELIABLE).
- **/home/erfolg/src/v7-engine/alphaforge/docs/handoff_to_v7.md** — V7HandoffPackage contract: how AlphaForge delivers evidence to V7 G0-G10 gates. recommended_status (REVIEW_REQUIRED/SHADOW_READY/PROMOTION_CANDIDATE). V7 is final authority.
- **/home/erfolg/src/v7-engine/alphaforge/docs/validation_contract.md** — Walk-forward/OOS/cost-stress/overfit detection validation contract.
- **/home/erfolg/src/v7-engine/contracts/schemas/alphaforge/validation_report.schema.json** — ValidationReport schema: overfit_risk_flags includes calibration_degradation (LOW/MEDIUM/HIGH), train_oos_gap, fold_instability, top_feature_dominance, purge_violation_detected, overfit_risk_overall. Verdict enum includes FAIL_OVERFIT/FAIL_COST/FAIL_REGIME/FAIL_OOS.
- **/home/erfolg/src/v7-engine/alphaforge/docs/phase_plans/P5__xgboost_hybrid_model_training.md** — P5 phase plan: mode-specific XGBoost classifier + expected-R regressors + artifact bundles + training metrics. Not started.
- **/home/erfolg/src/v7-engine/alphaforge/docs/phase_plans/P6__calibration_reliability_and_alpha_score_builder.md** — P6 phase plan: P6.A probability calibration, P6.B regression reliability (expected-R bucket vs realized, sign correctness, adverse pressure reliability), P6.C alpha score builder (long_alpha_R/short_alpha_R/recommended_alpha_action), P6.D calibration tests. File scope src/v7/alpha/calibration/** and src/v7/alpha/scoring/**. Not started.
- **/home/erfolg/src/v7-engine/alphaforge/docs/phase_plans/P9__deployment_monitoring_drift_promotion_and_rollback.md** — P9 phase plan: prediction drift, feature drift, anomaly score drift monitoring; kill switch; rollback bundles. Not started.
- **/home/erfolg/src/v7-engine/alphaforge/docs/configs/v7_alpha_defaults.json** — AlphaForge defaults config.
- **/home/erfolg/src/v7-engine/alphaforge/src/.gitkeep** — Placeholder — no AlphaForge source code is implemented yet. Implementation target is src/v7/alpha/{calibration,scoring,model,features,labels,anomaly,...} per ai_summary section 17.

## Critic Integration Points
A PolicyCritic sits between AlphaForge's alpha-evidence output and V7's final policy/risk gate. It would consume the AnalysisResult/alpha_prediction_row fields AlphaForge emits and produce a critic score / veto / threshold-modifier BEFORE V7 applies hard risk gates and final acceptance. Concrete plug-in point: after the Alpha Score Builder (src/v7/alpha/scoring/**, P6.C) emits long_alpha_R/short_alpha_R/recommended_alpha_action/confidence/confidence_kind, and before V7 policy_bridge applies min_long_alpha_R/min_confidence/require_expected_R_above thresholds (ai_summary section 15).

Inputs a PolicyCritic would consume from AlphaForge:
- calibrated_p_long / calibrated_p_short / p_no_trade (action probabilities)
- expected_R_long / expected_R_short (and cost-adjusted/drawdown variants in alpha_prediction_table: expected_cost_adjusted_R_long/short, expected_drawdown_R_long/short)
- confidence + confidence_kind (calibrated/raw/degraded/unavailable — critic must downweight degraded/unavailable)
- long_alpha_R / short_alpha_R / directional_edge_R
- classification_margin
- recommended_alpha_action
- reliability_error + expected-R bucket reliability (sign correctness, adverse pressure reliability) — critic can suppress when reliability weak
- calibration_artifact_version / model_artifact_version (lineage for staleness)
- unsupervised context features: anomaly_score, volume_anomaly_score, liquidity_shock_score, reconstruction_error, isolation_forest_score, regime_id, volatility_cluster (OOD/ regime-shift signals)
- overfit_risk_flags.calibration_degradation from ValidationReport (offline critic feature)
- deterministic_disagreement_reason (already exists on V7 AnalysisResult side — a model-vs-deterministic disagreement signal the critic can read)

A critic would NOT re-derive alpha; it would modulate confidence/alpha_R or force confidence_kind=degraded / recommend no-trade when reliability_error, reconstruction_error, calibration_degradation, or anomaly_score indicate the model is in an unreliable region.

## Available Reward Signals for Offline RL Training
AlphaForge-side signals usable as critic features or offline-RL training targets (most are specified but not yet computed — implementation pending P6/P9):

1. Reliability error (regression reliability): predicted expected-R bucket vs realized average R gap — ai_summary section 12 'reliability_error' and 'action_bucket_realized_R'. Usable as a per-bucket prediction-error signal.
2. Calibration error metrics: expected_calibration_error (ECE), maximum_calibration_error (MCE), brier_score, per-bin deviation (predicted - actual outcome rate) — model_artifact_contract.md CalibrationCandidate. Usable as confidence-quality reward features.
3. calibration_degradation (LOW/MEDIUM/HIGH) — validation_report.schema.json overfit_risk_flags. Offline signal that calibration is drifting.
4. Sign correctness by bucket / adverse pressure reliability — ai_summary section 12. Penalize predictions where sign is wrong in the expected-R bucket.
5. reconstruction_error / isolation_forest_score / anomaly_score / volume_anomaly_score / liquidity_shock_score — unsupervised context features (ai_summary section 8.5). OOD/anomaly reward signals: high reconstruction_error ⇒ distribution shift ⇒ critic penalty.
6. Prediction drift / feature drift / anomaly score drift — P9 phase plan (not implemented). Would yield recent-prediction-error / drift reward signals.
7. confidence_kind transitions (calibrated→degraded/unavailable) — a discrete reward signal indicating model reliability collapse; V7 fallback_policy.md already routes on this.
8. Realized vs expected R comparison at TradeOutcome time — v7/docs/contracts/trade_outcome.md snapshots decision_expected_r_seen vs realized outcome R. This is the closed-loop prediction-error signal: (realized_R - expected_R) per action, usable as the primary offline-RL reward / critic training target. AlphaForge label_contract already stores long_R_net/short_R_net as ground truth.
9. NO_TRADE quality labels (saved_loss_score, missed_opportunity_score, no_trade_quality) — label_contract.md. Reward signal for critic learning when to suppress action.
10. gap_R / regret_R / best_R / path_quality_score — label fields (ai_summary section 7.x). Regret-based reward.

NOTE: bad_trade_probability and an explicit model_disagreement score are NOT currently defined as AlphaForge outputs. deterministic_disagreement_reason exists on V7's AnalysisResult (model-vs-deterministic-policy disagreement) and is the closest existing disagreement signal. A PolicyCritic would need to derive bad_trade_probability from calibration error + reliability_error + reconstruction_error + confidence_kind.

## Domain Boundary Constraints
Per CLAUDE.md domain boundaries and alphaforge/docs/ai_summary.md / handoff_to_v7.md:

- AlphaForge does NOT own final trade decisions. V7 owns policy acceptance. AlphaForge RECOMMENDS; V7 DECIDES. A PROMOTION_CANDIDATE recommendation is a suggestion, not a command; V7 may reject.
- AlphaForge does NOT invent labels. Simulation owns economic truth; AlphaForge consumes SimulationOutput and transforms it. Truth hierarchy: simulation > realized > contract > runtime > model.
- AlphaForge does NOT own portfolio/risk policy, runtime lifecycle, or exchange connectivity.
- AlphaForge must NOT allow model confidence to override V7 risk gates. Policy must not execute based on alpha score alone (ai_summary section 13).
- A PolicyCritic placed in this subsystem must NOT become a hidden trade-decision authority: it may modulate confidence/alpha_R, force confidence_kind=degraded, or recommend no-trade, but final accept/reject remains V7's. The critic must emit events/suggestions, not execute.
- Unsupervised context is allowed ONLY as a fold-scoped feature producer; it must NOT emit trade labels, execution permission, or a hidden veto (ai_summary section 8.5, 6A.1).
- Regime modifiers must NOT act as silent vetoes — any suppression must surface reason codes (regime_gate_forced_no_trade, etc.) and constraint levels (ADVISORY/SOFT_BLOCK/HARD_BLOCK) in both AnalysisResult and DecisionEvent (6A.2).
- Raw confidence must NOT be mislabeled as calibrated (confidence_kind must be honest). Calibration missing ⇒ confidence_kind=DEGRADED and policy may degrade gates.
- No new trading modes or actions may be added.

## Fields Produced/Consumed
- `p_long`
- `p_short`
- `p_no_trade`
- `calibrated_p_long`
- `calibrated_p_short`
- `calibrated_p_no_trade`
- `expected_R_long`
- `expected_R_short`
- `expected_cost_adjusted_R_long`
- `expected_cost_adjusted_R_short`
- `expected_drawdown_R_long`
- `expected_drawdown_R_short`
- `confidence`
- `calibrated_confidence`
- `confidence_kind`
- `classification_margin`
- `long_alpha_R`
- `short_alpha_R`
- `directional_edge_R`
- `recommended_alpha_action`
- `reliability_error`
- `action_bucket_realized_R`
- `reliability_artifact_id`
- `calibration_artifact_version`
- `model_artifact_version`
- `anomaly_score`
- `volume_anomaly_score`
- `liquidity_shock_score`
- `reconstruction_error`
- `isolation_forest_score`
- `regime_id`
- `context_regime_confidence`
- `deterministic_disagreement_reason`
- `calibration_degradation`
- `best_action_label`
- `long_R_net`
- `short_R_net`
- `saved_loss_score`
- `missed_opportunity_score`
- `no_trade_quality`
- `gap_R`
- `regret_R`
- `path_quality_score`
- `label_validity`

## Notes
Key finding: AlphaForge is entirely specification/contract at this point — alphaforge/src/ is an empty .gitkeep. There is NO implemented scorer, calibrator, label engine, or feature engine in the alphaforge/ tree. The implementation target is src/v7/alpha/{calibration,scoring,model,features,labels,anomaly,...} (ai_summary section 17), planned in phases P5/P6/P9, all status 'Planned / Not started'. So a PolicyCritic integration is being designed against contracts, not against live code.

Calibration approach (specified, not implemented): per-mode calibration via isotonic/platt/beta (method chosen per model family). Calibration slice = second half of validation; holdout tail untouched. Usability: CALIBRATED (ECE<0.05), UNCALIBRATED (ECE>=0.05), UNRELIABLE (ECE>0.10). Regression reliability = expected-R bucket vs realized avg R, sign correctness, adverse pressure reliability. If weak, policy must degrade expected-R gates explicitly.

Label engine (specified): consumes SimulationOutput, produces best_action_label via gap_R/ambiguity_gap/min_action_edge logic (ai_summary section 9.2). Regression targets: y_reg_long=long_R_net, y_reg_short=short_R_net, plus mae/adverse-pressure/cost-adjusted. Funding cost is DEFERRED — labels are fee+slippage only, valid for SPOT-equivalent.

Feature surface (specified): primary/context/refinement interval features + unsupervised context (anomaly_score, regime_id, reconstruction_error, isolation_forest_score). symbol_one_hot_v1 over 20-symbol universe (MVP). Fold-scoped anomaly fitting enforced (6A.1).

Existing signals relevant to critic: confidence_kind (calibrated/raw/degraded/unavailable) is the primary reliability flag; reliability_error and calibration_degradation (LOW/MEDIUM/HIGH in ValidationReport) are the offline calibration-health signals; reconstruction_error/anomaly_score/isolation_forest_score are the OOD signals; deterministic_disagreement_reason on V7 AnalysisResult is the closest model-disagreement signal. bad_trade_probability is NOT defined anywhere — a critic would have to synthesize it. Recent prediction error is available only closed-loop via TradeOutcome (decision_expected_r_seen vs realized_R), not as a live AlphaForge emit. P9 will add prediction/feature/anomaly drift monitoring but is not implemented.

Recommendation: a PolicyCritic should consume the alpha_prediction_row + unsupervised context features + reliability_error + confidence_kind, and emit a critic_score / critic_confidence_modifier / critic_force_no_trade flag into the V7 policy_bridge, positioned after P6.C scoring and before V7 hard risk gates. It must remain a suggester per domain rules.