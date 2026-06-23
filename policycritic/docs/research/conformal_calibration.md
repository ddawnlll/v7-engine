# Conformal Calibration — Uncertainty Quantification for Critics

## Abstract

Conformal prediction (CP) is a distribution-free framework for producing prediction intervals with guaranteed coverage: P(Y ∈ Γ_α(X)) ≥ 1-α. Split conformal prediction (SCP) computes nonconformity scores on a held-out calibration set and uses their empirical quantile to construct prediction intervals. The key assumption is **exchangeability** between calibration and test data — which time-series financial data systematically violates.

## Why It Matters for V7

The V3 IQL critic must produce calibrated confidence intervals. Without calibration, the critic cannot distinguish "confident +1.5R" from "uncertain +1.5R." Conformal prediction provides: (1) calibrated lower quantiles for veto decisions, (2) interval width as uncertainty signal for DOWNWEIGHT_CONFIDENCE, (3) distribution-free guarantees — no Gaussian assumptions on financial returns.

## What the Literature Says

### Standard Split Conformal Prediction

1. Split data: training set (model fitting) + calibration set (nonconformity scores) + test set
2. Define nonconformity score: s_i = |Y_i - f̂(X_i)| for regression
3. Compute q̂ = (1-α)(1+1/|cal|)-th empirical quantile of {s_i}
4. Prediction interval: [f̂(X_test) - q̂, f̂(X_test) + q̂]
5. Guarantee: P(Y_test ∈ interval) ≥ 1-α under exchangeability

### Exchangeability Violation in Time Series

Financial data is temporally dependent, autocorrelated, and non-stationary — all violate exchangeability. Standard CP then loses coverage guarantees. Solutions:

- **Weighted CP** (Tibshirani et al. 2019): Weight recent calibration points higher
- **NexCP** (Barber et al. 2023): Bound coverage gap by deviation from exchangeability measure
- **Adaptive CI** (Gibbs & Candès 2021): Online quantile tuning without fixed calibration set
- **Horizon-specific SCP**: Calibrate separately per forecast horizon (e.g., per holding period)

### Practical Finding (JMLR 2024)

"Standard split CP can still work reasonably well on financial data even when exchangeability is clearly violated, especially with quantile regression-based scores." Coverage may be approximate (~85-90% for nominal 90%) rather than exact, which is acceptable for advisory critic use.

## How It Applies to V7

1. **Post-training calibration**: Train IQL first, then calibrate Q-value quantiles against realized outcomes on held-out calibration set
2. **Coverage target**: 80-90% (lower bound of Q-distribution should cover realized outcome with this probability)
3. **Uncertainty signal**: Interval width → `confidence_adjustment_factor` (wider = more downweight)
4. **Time-aware variant**: Weight recent calibration points higher (recency-weighted CP)

## How It Can Fail

| Failure Mode | Mitigation |
|-------------|-----------|
| Coverage below nominal due to non-exchangeability | Accept approximate coverage; monitor coverage drift |
| Calibration set too small for tail quantiles | Minimum 500+ calibration points per regime |
| Regime shift invalidates calibration | Recalibrate periodically; per-regime calibration sets |
| Quantile crossing in calibrated outputs | Post-processing sort; non-crossing quantile regression |

## Business Implication

Conformal calibration transforms the critic from "probably useful" to "provably calibrated at confidence level X." This is essential for: (a) human operator trust, (b) regulatory/audit acceptance, (c) risk management sign-off.

## Decision: USE LATER (V3 calibration retrofit)

Conformal calibration is specified as a post-training retrofit for V3 IQL critic. Time-aware variant required due to exchangeability violation. Prerequisite: sufficient calibration data per regime.
