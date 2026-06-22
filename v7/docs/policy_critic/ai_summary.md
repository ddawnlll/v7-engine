# V7 Policy Critic — AI Summary

## What It Is

V7 Policy Critic is an **advisory offline-RL component** that sits between V7's hard gates and the final gate. It reviews the proposed action (LONG/SHORT from hard gates, scores from AlphaForge) using a learned value function and returns a verdict: ALLOW, DOWNWEIGHT_CONFIDENCE, VETO_TO_NO_TRADE, or REQUIRE_REVIEW.

The critic is the **lowest authority** in V7's truth hierarchy (simulation > realized > contract > runtime > model). It can **downgrade but never upgrade** execution — hard-gate failure always wins, and a critic ALLOW does not grant execution eligibility.

## RL Architecture (Core Design)

| Aspect | Decision |
|--------|----------|
| **Primary method** | Implicit Q-Learning (IQL) with distributional Q-head (16-32 quantiles) |
| **Model class** | Per-action gradient-boosted quantile/expectile regressor ensemble (XGBoost) |
| **Calibration** | Conformal prediction retrofit post-training on held-out realized net R |
| **Runner-up / cross-check** | Conservative Q-Learning (CQL) — IQL/CQL disagreement -> REQUIRE_REVIEW |
| **Training data** | (state, action, realized_r_net, mae_r, next_state) tuples from `/simulation` engine replay adapter |
| **Reward** | Decomposable mode-weighted: action_utility + drawdown penalty + NO_TRADE credit (saved_loss_r - 0.5*missed_opportunity_r) + overtrading penalty. NO_TRADE is first-class zero-cost baseline. |
| **Where it lives** | `v7/src/v7/alpha/policy_bridge/` (greenfield; v7/src/ empty today) |

## Three Q-Values

```
Q(s, LONG_NOW)  -- calibrated lower-quantile (e.g. 20th percentile) of return distribution for going long
Q(s, SHORT_NOW) -- same, for going short
Q(s, NO_TRADE)  -- same, for not trading (first-class action, zero-cost baseline)
```

## Critic I/O

**Inputs** (mapped to real V6/V7 fields -- see [codebase_maps/](codebase_maps/) for exact field names with file:line):
- symbol, mode, regime -> V6 AnalysisRequest / deterministic_context
- calibrated_head_scores {long, short, no_trade} -> inference_engine.py:248
- confidence_raw_score, confidence_final_score, confidence_kind -> inference_engine.py:280
- decision_margin -> inference_engine.py:429
- expected_return (single, V6) / expected_R_long/short (target, P6+)
- setup_score + components -> decision_modeling.py:3605
- deterministic_alignment, constraint_level -> inference_engine.py:327
- ml_conviction_score, final_hybrid_conviction -> inference_engine.py:395

**Outputs** (PolicyCriticReview contract):
- critic_value_LONG, critic_value_SHORT, critic_value_NO_TRADE
- critic_confidence_adjustment (multiplier in (0, 1])
- critic_veto_reason (enum: critic_calibrated_lower_bound_negative, critic_reliability_degraded, critic_ood_distance_high, critic_no_trade_dominant, etc.)
- critic_verdict: ALLOW | DOWNWEIGHT_CONFIDENCE | VETO_TO_NO_TRADE | REQUIRE_REVIEW
- is_advisory: true (non-negotiable)

## Action Mapping (Evaluated in Order)

1. **Hard gate fail** (V6 choose_action at decision_modeling.py:1461 + HARD_BLOCK at inference_engine.py:326) -> **NO_TRADE**. Critic NOT consulted.
2. **Hard gate produces LONG/SHORT** -> critic reviews:
   - ALLOW if calibrated_lower_bound(Q(s, a_gate)) > 0 AND Q(s, a_gate) >= Q(s, NO_TRADE)
   - DOWNWEIGHT_CONFIDENCE if positive but interval wide -> adjust confidence_final_score, re-trip confidence gate
   - VETO_TO_NO_TRADE if lower_bound <= 0 OR NO_TRADE dominates -> V7 policy enacts veto
   - REQUIRE_REVIEW if IQL vs CQL cross-check disagreement
3. **Final operational hard gate** (runtime execution_orchestrator.py) runs AFTER, unchanged.

## Staged Rollout

| Stage | What | Empirical Release Gate |
|-------|------|----------------------|
| **v1 -- Rule-based shadow** | Deterministic advisory (disagreement, degraded, cost sanity). No veto enactment. | Contract roundtrip pass; zero silent suppressions; shadow veto rate bounded away from 0 and 1. |
| **v2 -- Supervised critic** | (state -> is_good_decision) classifier. Conformal-calibrated. Advisory veto. | Conformal coverage holds; regret improvement vs baseline significant (Deflated Sharpe); baseline profit rate not degraded. |
| **v3 -- Offline RL critic** | IQL + distributional + conformal. Live veto in SWING only (LOCKED_INITIAL_BASELINE). SCALP/AGGRESSIVE shadow-only (HOLD). | IQL/CQL disagreement bounded; OPE approx equal to realized; SWING net expectancy >= baseline (Deflated Sharpe); veto rate bounded; no OOD exceedance. |
| **v4 -- Constrained policy optimizer** | Calibrated threshold adjustment per-regime via OPE-constrained optimization. SWING only. | OPE-estimated improvement survives Deflated Sharpe + PBO; live shadow confirms OPE approx equal to realized; monotone-smooth thresholds. |

## Domain Boundaries

| Rule | Compliance |
|------|-----------|
| Alpha discovery -> AlphaForge | Critic consumes existing evidence, never generates new alpha |
| Risk gates override model | Critic ALLOW not equal to execution eligibility; runtime hard gate runs after |
| Simulation owns economic truth | Critic reward = realized_r_net from `/simulation` engine, not runtime historical engine |
| V7 owns final trade decisions | Critic emits advisory verdict; V7 policy enacts veto |
| No bypass of deterministic hard block | Critic NOT consulted when hard gate fails |
| No new actions/modes | Action space locked {LONG, SHORT, NO_TRADE} (DEC-002) |
| No silent suppression | Every critic verdict visible in DecisionEvent.runtime_interpretation |
| SCALP/AGGRESSIVE thresholds HOLD | Live veto only in SWING |
| Funding DEFERRED | Critic spot-only-valid; perp blocked at G3 |

## Open HOLDs (Must Resolve Before Lock)

1. **Replay buffer does not exist** -- (state, action, realized_r_net, mae_r, next_state) tuple emitter must be built
2. **regret_r hardcoded to 0.0** in engine.py:168
3. **funding_cost_r DEFERRED** -- critic spot-only-valid, perp blocked
4. **Per-direction expected_R not in V6** -- train on simulation per-direction realized R, use V6 single expected_return as proxy
5. **bad_trade_probability, model_disagreement, recent_prediction_error don't exist live** -- must be synthesized (v2+) or wait for P9
6. **Per-decision portfolio drawdown doesn't exist** -- mae_r used as proxy
7. **Conformal exchangeability violated** by time-series -- which time-aware variant is implementable?
8. **Decision-event family contracts not registered** -- PolicyCriticReview can proceed independently
9. **v7/src greenfield** -- wire critic into runtime adapter (no V6 patch) for interim
10. **IQL expectile tau, conformal coverage** -- numeric thresholds not lockable without empirical evidence

## Doc Tree

| File | Purpose |
|------|---------|
| `ai_summary.md` | This file -- dense synthesis entry point |
| `README.md` | Navigation and reading order |
| `design.md` | Full design recommendation with all rationale |
| `codebase_maps/v7_pipeline_map.md` | V7/V6 decision flow, gate logic, exact field names |
| `codebase_maps/alphaforge_map.md` | AlphaForge scorer, calibration, field surface |
| `codebase_maps/simulation_map.md` | Simulation cost model, reward signals, replay infrastructure |
| `codebase_maps/contracts_runtime_map.md` | Contract registry, runtime wiring, PolicyCriticReview spec |
| `research/offline_rl_methods.md` | Offline RL literature (CQL, IQL, BCQ, TD3+BC, AWAC, DT) |
| `research/critic_calibration.md` | Critic/calibration methods (QR-DQN, conformal, FQE, Cal-QL) |
| `research/reward_design.md` | Reward design literature (cost-aware, drawdown, NO_TRADE) |
| `research/finance_rl_failures.md` | Finance RL failure modes (OOD, overfitting, guardrails) |

**Supplementary expanded docs**: `policycritic/docs/` contains the expanded partner-grade package with business plan, profitability calculation, 7 phase plans, 15 deep research docs, risk register, and quality scoring. See `policycritic/docs/README.md`.

## Reading Order

1. `ai_summary.md` (this file) -- dense summary
2. `design.md` -- full design with rationale
3. `codebase_maps/*` -- codebase grounding
4. `research/*` -- literature grounding (after design, as supporting evidence; see literature for source URLs)
