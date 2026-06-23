# Phase 3 — Offline Training and Evaluation

> Status: NOT STARTED
> Prerequisite: Phase 2 complete (≥ 1000 replay buffer tuples)
> Duration: 12-18 weeks estimated (sub-phases 3A, 3B, 3C)

## Goal

Train three generations of critic models — supervised (V2), IQL (V3), and constrained optimizer (V4) — each passing progressively stricter evidence gates. All training is offline on replay buffer data. Zero live influence.

## Sub-Phase 3A: V2 Supervised Critic (4-6 weeks)

### Goal
Train an XGBoost regressor that predicts `realized_r_net` from state features. Acts as an expected-value estimator.

### Deliverables
- `alphaforge/training/critic_supervised_v2.py` — Training script
- Trained XGBoost model artifact (per-mode)
- Calibration report (realized vs predicted r²)

### Exit Criteria
- DSR p < 0.05 after multiple-testing correction
- PBO < 0.10 (CSCV procedure)
- Walk-forward consistency ≥ 4/5 folds
- Realized vs predicted r² > 0.1 on held-out test
- ≥ 1000 training tuples

## Sub-Phase 3B: OPE Infrastructure (3-4 weeks)

### Goal
Implement Fitted Q-Evaluation (FQE) and integrate DSR/PBO validation into the evaluation pipeline.

### Deliverables
- `alphaforge/training/off_policy_evaluation.py` — FQE implementation
- DSR computation (from Bailey & Lopez de Prado 2014)
- PBO computation via CSCV (from Bailey et al. 2016)

### Exit Criteria
- FQE 95% CI computed for V2 critic
- CI width documented
- OPE protocol documented for reproducibility

## Sub-Phase 3C: V3 IQL Critic (8-12 weeks)

### Goal
Train a distributional IQL critic with conformal calibration. Learn Q(s, LONG_NOW), Q(s, SHORT_NOW), Q(s, NO_TRADE) via expectile regression on in-sample actions only. CQL ensemble as cross-check.

### Deliverables
- `alphaforge/training/critic_iql_v3.py` — IQL training with distributional Q-head (16-32 quantiles)
- `alphaforge/training/critic_calibration.py` — Conformal calibration retrofit
- `alphaforge/training/critic_ensemble.py` — IQL/CQL cross-check
- Trained model artifacts (per-mode, per-action Q-functions)
- Expectile τ sensitivity analysis

### Exit Criteria
- FQE 95% CI overlaps observed performance
- DSR p < 0.05 and PBO < 0.10 maintained
- Walk-forward ≥ 4/5 folds maintained
- IQL/CQL disagreement bounded (not diverging)
- Bellman error not monotonically increasing during training
- Champion anti-regression: no degradation vs V2 critic
- ≥ 10,000 training tuples
- Conformal coverage within tolerance of nominal
- Multi-regime coverage confirmed (≥ 3 regimes)

## Entry Criteria (for entire Phase 3)

- [ ] Phase 2 exit criteria met (replay buffer populated)
- [ ] ≥ 1000 tuples for 3A, ≥ 10000 for 3C
- [ ] Data split infrastructure validated
- [ ] Reward normalization scheme frozen
- [ ] Training hardware available

## Exit Criteria (for entire Phase 3)

- [ ] V2, OPE, and V3 sub-phase criteria all met
- [ ] All model artifacts versioned and stored
- [ ] Training lineage documented (data splits, hyperparameters, seeds)
- [ ] Evaluation reports generated for all sub-phases
- [ ] Human approval for V3→V4 transition consideration

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| IQL expectile τ requires extensive tuning | High | Schedule delay | Start with τ=0.7-0.8 range; sensitivity analysis early |
| Financial data violates IQL assumptions | Medium | Poor Q-function | CQL cross-check catches this; fall back to V2 |
| Conformal exchangeability violated by time series | High | Invalid coverage | Weighted/time-aware CP variant; accept approximate coverage |
| OPE overestimates true performance | Medium | False confidence | Compare FQE to realized during shadow burn-in |

## What Must NOT Be Implemented in This Phase

- ❌ Any runtime inference (training only)
- ❌ Any live influence on execution
- ❌ Any critic invocation in scan loop
- ❌ Any database migration for model storage (use file artifacts)

## Rollback Plan

Delete training artifacts. Revert training scripts. Replay buffer data unchanged.
