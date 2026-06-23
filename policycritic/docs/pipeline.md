# Policy Critic Pipeline

> Status: Docs/Design Only — No implementation started
> Created: 2026-06-23 (adapted from old repo source material)

## Overview

The Policy Critic evolves through four staged versions, each requiring specific prerequisites, passing specific release gates, and operating under escalating authority restrictions.

```
V1: Rule-Based Shadow Critic     → heuristic, shadow-only, zero live influence
V2: Supervised Critic            → XGBoost model predicts expected return
V3: Offline RL / IQL Critic      → learned Q-function for risk scoring (distributional + conformal)
V4: Constrained Policy Optimizer → sizing/exit proposals within shield limits
```

**Each transition requires evidence, not ambition.**

---

## V1: Rule-Based Shadow Critic

### Description
Shadow-only heuristic critic that applies rule-based risk scoring. Records PolicyCriticReview audit records without influencing execution. Always passes through the proposed action.

### What It Does
- Scores risk using heuristic rules: volatility regime, anomaly score, confidence degradation, cost stress, regime-conditional thresholds
- Recommends NO_TRADE when risk exceeds calibrated thresholds
- Records PolicyCriticReview via ShadowPolicyRepository
- Always annotates but never blocks the proposed action
- Zero live influence — pure audit trail

### Inputs
| Input | Source |
|---|---|
| Canonical market state | AlphaForge snapshot builder (planned) / V6 adapter (interim) |
| Proposed action | AlphaForge scorer (planned) / V6 AnalysisResult (interim) |
| Regime label | Deterministic context |
| Confidence + confidence_kind | AlphaForge/V6 output |

### Outputs
| Output | Destination |
|---|---|
| PolicyCriticReview | `ShadowPolicyRepository` (`runtime/db/repos/shadow_policy_repo.py`) |
| Risk score (0.0–1.0) | Audit record metadata |
| Confidence multiplier (0.0–1.0) | Audit record metadata |

### Estimated Effort
1–2 weeks, ~200 lines of code

### Prerequisites
None beyond current infrastructure. Reuses:
- `ShadowPolicyRepository` for persistence
- Simulation engine for reward truth
- Existing contract patterns

### Release Gate
- Shadow burn-in: 30 days stable operation with no false-positive NO_TRADE recommendations exceeding 50% of decisions

---

## V2: Supervised Critic

### Description
XGBoost supervised model that predicts `realized_r` (expected return) from state features. Acts as an expected-value estimator trained on (state, action, reward) tuples from the replay buffer.

### What It Does
- Predicts `expected_value_r` for each proposed action (LONG_NOW, SHORT_NOW, NO_TRADE)
- Estimates `value_uncertainty` (standard error of prediction)
- Recommends NO_TRADE when expected_value_r < -0.2R
- Continues shadow-only operation (no live influence)

### Inputs
| Input | Source |
|---|---|
| State features | Canonical snapshot + AlphaForge/V6 features |
| Training labels (realized_r_net) | Replay buffer resolved outcomes from simulation engine |
| Regime labels | Deterministic context |

### Outputs
| Output | Destination |
|---|---|
| PolicyCriticReview (with expected_value_r) | ShadowPolicyRepository |
| Confidence multiplier (proportional to predicted return) | Audit record |
| Value uncertainty estimate | Audit record |

### Estimated Effort
4–6 weeks

### Prerequisites
- Replay buffer ≥ 1000 resolved outcomes covering 3+ market regimes
- Replay buffer includes all supported symbols
- DSR p < 0.05 after multiple-testing correction
- PBO < 0.10 (probability of backtest overfitting)
- Walk-forward consistency ≥ 4/5 folds
- Champion anti-regression: no safety degradation vs V1 baseline

### Release Gate
- DSR p < 0.05, PBO < 0.10, Walk-forward ≥ 4/5 folds
- Champion anti-regression pass
- 30-day shadow burn-in against V1 critic baseline
- Human approval

---

## V3: Offline RL / IQL Critic

### Description
IQL-trained critic that learns Q(s,a) and V(s) from offline trajectory data. Q-values provide risk scores; advantage A(s,a) = Q(s,a) - V(s) drives confidence adjustment. Distributional Q-head (16-32 quantiles) with conformal calibration.

### What It Does
- Learns V(s) via expectile regression on dataset actions
- Learns Q(s,a) only on in-sample actions (never queries unseen actions)
- Extracts policy via advantage-weighted regression
- Distributional Q-head provides calibrated lower-quantile risk scores
- IQL/CQL ensemble cross-check: disagreement → REQUIRE_REVIEW
- Operates in shadow mode (still advisory only)

### Inputs
| Input | Source |
|---|---|
| (s, a, r, s', terminal) tuples | Replay buffer from simulation engine |
| State (canonical market snapshot) | AlphaForge snapshot builder |
| Action (LONG_NOW/SHORT_NOW/NO_TRADE) | Behavioral policy (V6 or AlphaForge) |
| Reward (realized_r_net) | `simulation/engine/engine.py` ActionOutcome |
| Drawdown proxy (mae_r) | `simulation/engine/engine.py` PathMetrics |
| Next state | Next scheduled analysis snapshot |
| Terminal flag | End-of-episode signal |

### Outputs
| Output | Destination |
|---|---|
| Q(s, a) for proposed action (distributional) | Risk score in PolicyCriticReview |
| V(s) for current state | Baseline value in audit record |
| Advantage A(s,a) = Q(s,a) - V(s) | Confidence adjustment recommendation |
| Calibrated lower-quantile (e.g., 20th percentile) | Critic verdict |
| IQL/CQL disagreement flag | REQUIRE_REVIEW trigger |
| PolicyCriticReview | ShadowPolicyRepository |

### Estimated Effort
8–12 weeks

### Prerequisites
- Replay buffer ≥ 10,000 (s, a, r, s', terminal) tuples
- FQE validation: 95% CI on estimated value overlaps observed performance
- DSR p < 0.05, PBO < 0.10, Walk-forward ≥ 4/5 folds
- Champion anti-regression: no degradation vs V2 critic
- Multi-regime coverage confirmed
- V2 critic operating in shadow for ≥ 30 days with stable metrics

### Release Gate
- FQE 95% CI overlaps observed performance
- DSR p < 0.05, PBO < 0.10, Walk-forward ≥ 4/5 folds
- Champion anti-regression pass
- IQL/CQL disagreement bounded
- 30-day shadow burn-in against V2 critic baseline
- Human approval (required for any transition beyond V2)

---

## V4: Constrained Policy Optimizer

### Description
Critic proposes sizing adjustments and exit timing within explicit shield constraints. Operates within the existing authority hierarchy — cannot override gates, cannot open/close trades independently, cannot bypass risk limits.

### What It Does
- Proposes position size adjustments within gate size_multiplier bounds
- Recommends exit timing based on learned value function
- All proposals are advisory and subject to gate veto
- Operates under explicit formal shield compliance verification

### Estimated Effort
12–16 weeks

### Prerequisites
- All V3 prerequisites met and stable for ≥ 60 days
- Formal shield compliance verification complete
- Multi-regime validation across ≥ 5 distinct regimes
- Adversarial simulation: critic tested against worst-case market scenarios
- Stress testing: flash crashes, extreme volatility, liquidity crises
- Human approval (mandatory — no automation of V4 transition)

### Release Gate
- Formal shield compliance verified
- Multi-regime, adversarial, and stress test pass
- FQE CI overlap, DSR, PBO maintained
- Champion anti-regression maintained
- Human approval

---

## Release Gates Summary

| Gate | V1→V2 | V2→V3 | V3→V4 |
|---|---|---|---|
| Shadow burn-in (30 days) | ✅ | ✅ | ✅ |
| Replay buffer minimum | ≥ 1000 | ≥ 10000 | ≥ 10000 |
| DSR p < 0.05 | ✅ | ✅ | ✅ |
| PBO < 0.10 | ✅ | ✅ | ✅ |
| Walk-forward ≥ 4/5 folds | ✅ | ✅ | ✅ |
| Champion anti-regression | ✅ | ✅ | ✅ |
| FQE CI overlap | — | ✅ | ✅ |
| Formal shield compliance | — | — | ✅ |
| Multi-regime validation | — | ✅ | ✅ |
| IQL/CQL disagreement bounded | — | ✅ | ✅ |
| Human approval | ✅ | ✅ | ✅ |

## HOLD Conditions Summary

| Condition | Applies To | Action |
|---|---|---|
| Safety metric degradation | All versions | HOLD + investigate |
| Replay buffer insufficient | V1 → V2 | HOLD at V1 |
| Missing regime coverage | All versions | HOLD |
| PBO > 0.20 | All versions | HOLD + investigate |
| FQE CI does not overlap | V3 → V4 | HOLD + investigate |
| Shield compliance violation | V4 | HOLD + immediate rollback |
| Calibration failure | V2 → V4 | HOLD + recalibrate |
| Human approval not obtained | All transitions | HOLD |

---

## Current Status

**Today**: All versions are **NOT IMPLEMENTED**. The only active policy stack is:
- V6 inference engine (sibling repo) — live decision path
- V7 policy gates (docs only — `v7/docs/pipeline/policy.md`)
- AlphaForge scorer (spec only — P5/P6 not started)
- Simulation engine (implemented — produces authoritative reward surface)

**Next step**: Complete docs/design (this task), then implement V1 shadow rule-based critic when authorized.

## Related Documents

- [[policy_critic_design.md]] — Architecture and authority hierarchy
- [[rl_intro_for_v7.md]] — RL concepts for V7
- [[replay_buffer_design.md]] — Prerequisite infrastructure
- [[rollout_plan.md]] — Staged deployment with PR sequencing
- [[authority_and_boundaries.md]] — Detailed boundary specification
- `v7/docs/policy_critic/design.md` — Canonical design with staged rollout table
