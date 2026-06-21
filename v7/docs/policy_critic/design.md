# V7 Policy Critic — Design Recommendation

## 1. Recommended RL Approach

PRIMARY: **Implicit Q-Learning (IQL)** with a distributional (quantile-regression) Q-head, conformal-calibrated post-training against realized net R. Train three per-action Q-functions Q(s, LONG_NOW), Q(s, SHORT_NOW), Q(s, NO_TRADE) via IQL expectile regression over ONLY in-sample logged actions, with each Q-head outputting a return distribution (16-32 quantiles).

RUNNER-UP: **Conservative Q-Learning (CQL)** as cross-check/ensemble member. IQL/CQL disagreement -> REQUIRE_REVIEW.

### Why IQL Over the Alternatives
1. Structurally never queries Q on out-of-distribution actions — OOD overestimation (the dominant offline-RL failure mode in finance) cannot arise by construction.
2. One effective hyperparameter (expectile tau), no generative model to fit, no large transformer.
3. In-sample-only updates are the most sample-efficient for the approx 10^4-10^6 transition scale of a single-instrument perp log.
4. Advantage-weighted regression for policy extraction keeps the extracted policy within the behavior support.

## 2. Why This Fits V7

The V7 reality: (a) v7/src/ is greenfield, (b) live decision path runs through V6 sibling repo, (c) data is small/single-instrument/OOD-prone, (d) simulation/ owns the only authoritative reward (realized_r_net), (e) critic must be the LOWEST authority. IQL fits each constraint.

## 3. Model Architecture

### Inputs (real V6 fields available now)
- symbol, mode, primary_interval — from AnalysisRequest
- regime — deterministic_context.regime_label
- calibrated_head_scores {long, short, no_trade} — inference_engine.py:248
- confidence_raw_score, confidence_final_score, confidence_kind — inference_engine.py:280
- decision_margin — inference_engine.py:429
- setup_score + components — decision_modeling.py:3605
- ml_conviction_score, final_hybrid_conviction — inference_engine.py:395
- deterministic_alignment, constraint_level — inference_engine.py:327
- expected_return (single V6 value) — analysis_result.py:113

### Simulation-side features (for training only)
- realized_r_net, realized_r_gross, fee_cost_r, slippage_cost_r, total_cost_r — ActionOutcome
- mae_r (drawdown proxy), mfe_r, path_quality_score — PathMetrics
- saved_loss_r, saved_loss_score, missed_opportunity_r, no_trade_quality, was_correct_skip, action_utility — NoTradeOutcome

### Target-only fields (P6+)
- calibrated_p_long/short/no_trade, expected_R_long/short, long_alpha_R/short_alpha_R, reliability_error
- anomaly_score, reconstruction_error, isolation_forest_score (unsupervised context)

### Fields the user spec identified that DO NOT YET EXIST
- no_trade_margin: a POLICY CONFIG KEY, not a produced/consumed field. Drop as input.
- bad_trade_probability: must be synthesized (v2+) from calibration + reliability + reconstruction errors.
- model_disagreement: closest existing signal is deterministic_disagreement_reason.
- recent_prediction_error: only available closed-loop via TradeOutcome. Offline training feature only.
- recent_drawdown (per-decision): use mae_r as proxy.
- cost_bps/slippage_estimate: live not available; use total_cost_r from simulation at training time.

### Outputs
- critic_value_LONG, critic_value_SHORT, critic_value_NO_TRADE: calibrated lower-quantile of IQL distributional Q-head
- critic_confidence_adjustment: multiplier in (0, 1] from conformal-calibrated interval width
- critic_veto_reason: enum from locked reason-code set
- critic_verdict: ALLOW | DOWNWEIGHT_CONFIDENCE | VETO_TO_NO_TRADE | REQUIRE_REVIEW

### Model Class
Ensemble of per-action gradient-boosted quantile/expectile regressors (XGBoost), NOT MLP. Rationale: (1) codebase is XGBoost-centric, (2) tree ensembles are far more sample-efficient and interpretable on approx 10^4-10^6 tabular transitions, (3) expectile regression is implementable as custom XGBoost objective, (4) quantile outputs feed conformal calibration directly. Keep shallow (depth 4-6, 200-500 trees).

## 4. Training Data Source

THE REPLAY BUFFER DOES NOT EXIST. Must be built. Each tuple requires:
- state: canonical market snapshot at decision time (UnifiedSnapshotBuilder)
- action: action taken by V6 engine from DecisionEvent
- reward: realized_r_net from /simulation engine.py (NOT runtime historical_simulation_engine.py)
- drawdown proxy: mae_r from PathMetrics
- next_state: snapshot at next decision point (same symbol/mode)
- terminal: from exit_reason (COMPLETE only; exclude UNRESOLVED/INVALIDATED)

Route through /simulation engine, not the runtime historical engine (which has separate fee/slippage — parity divergence).

## 5. Reward Function

Decomposable weighted reward with NO_TRADE as first-class zero-cost baseline:

```
BASE:        r_base = realized_r_net          (NO_TRADE: r_base = 0)
SHAPED:      r_shaped = action_utility         (mode-weighted composite)
DRAWDOWN:    r_drawdown = -lambda_dd * abs(mae_r)   (Sortino-style, downside only)
NO_TRADE:    r_no_trade = saved_loss_r - 0.5 * missed_opportunity_r
OVERTRADE:   r_overtrade = -lambda_ot * max(0, freq - freq_threshold(vol_regime))
FUNDING:     NOT INCLUDED (DEFERRED — spot-only)

R(s, LONG)  = r_shaped(long_outcome) + r_drawdown(long_outcome) + r_overtrade
R(s, SHORT) = r_shaped(short_outcome) + r_drawdown(short_outcome) + r_overtrade
R(s, NO_TRADE) = r_no_trade + correct_NO_TRADE_bonus_or_missed_opp_penalty
```

NO_TRADE is first-class: it earns saved_loss_r when a directional trade would have lost, and is penalized missed_opportunity_r when a directional trade would have won. The 0.5 coefficient is the simulation's existing anchor, not a new magic number.

Calibration anchor: lock (edge - cost) indifference point, not penalty magnitudes.

## 6. Action Mapping

1. HARD GATE FAIL (choose_action + HARD_BLOCK) -> NO_TRADE. Critic NOT consulted.
2. IF hard gate produces LONG/SHORT:
   - ALLOW if calibrated_lower_bound(Q(s,a_gate)) > 0 AND Q(s,a_gate) >= Q(s,NO_TRADE)
   - DOWNWEIGHT_CONFIDENCE if positive but interval wide -> adjust confidence, re-trip confidence gate
   - VETO_TO_NO_TRADE if lower_bound <= 0 OR NO_TRADE dominates -> V7 policy enacts veto
   - REQUIRE_REVIEW if IQL vs CQL cross-check disagrees
3. FINAL GATE (runtime operational) runs after, unchanged.

## 7. Integration Point

Inserts BETWEEN the hard gate (V6 choose_action) and the final gate (runtime execution_orchestrator). In V7-native target: after Alpha Score Builder (P6.C), before V7 policy gates.

**Contract needed:** PolicyCriticReview (V7-owned). Register per contracts/README.md 6-step procedure:
1. schema: verdict enum, confidence_adjustment_factor, critic_value_long/short/no_trade, critic_veto_reason, is_advisory=true
2. registry.json entry
3. compatibility.json pairs
4. mapping -> runtime_interpretation fields
5. fixture
6. integration test

**Runtime wiring:** PolicyCriticRegistryService (mirrors AnalyzerEngineRegistryService), POLICY_CRITIC_ACTIVE setting, bypass when unavailable (safe degrade). Invoked from analyzer_engine_adapter.py or new policy-stage step in scan_runtime. Verdict consumed into existing DecisionEvent.runtime_interpretation fields.

**Interim (v7/src empty):** Wire into runtime adapter path (analyzer_engine_adapter.py) that bridges V6 AnalysisResult to runtime normalized contract — no V6 patch needed.

## 8. Staged Rollout

See ai_summary.md table. Key empirical gates:
- v1->v2: contract roundtrip, zero silent suppressions, veto rate bounded away from 0 and 1
- v2->v3: conformal coverage holds, regret improvement significant (Deflated Sharpe)
- v3->v4: IQL/CQL disagreement bounded, OPE approx equal to realized, SWING net expectancy >= baseline (Deflated Sharpe)
- v4->PAPER_ELIGIBLE: Deflated Sharpe + PBO survive, live shadow confirms, monotone-smooth thresholds

SCALP/AGGRESSIVE_SCALP: live veto is HOLD until independent evidence. SWING is the LOCKED_INITIAL_BASELINE rollout target.

## 9. Key Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| OOD overestimation | IQL structurally prevents it; CQL cross-check; OOD-distance monitoring + auto-degrade |
| Conservative collapse | tau ~0.7-0.8 (not 0.9); veto rate bounded away from 1 gate; conformal scale calibration |
| State-distribution OOD (regime shift) | Continuous OOD monitoring + auto-degrade; walk-forward regime-split validation |
| Reward hacking | Decomposable multi-component reward; comparable NO_TRADE bonus/penalty magnitutes |
| Backtest overfitting | Deflated Sharpe + PBO; walk-forward + regime-split validation; offline pass != promotion evidence |
| Conformal exchangeability violation | Weighted/time-aware variant (COPP-IS); approximate coverage accepted |
| Sim-to-reality gap | Train on /simulation realized_r_net (not runtime); live shadow OPE vs realized compare |
| Funding model absent | Spot-only-valid artifact; perp G3 block; retrain when funding_cost_r lands |

## 10. Domain Boundary Compliance

See ai_summary.md "Domain Boundaries" section. All 12 CLAUDE.md rules mapped and respected.

## 11. Open Questions

Are HOLD — see ai_summary.md "Open HOLDs" section for the full list.
