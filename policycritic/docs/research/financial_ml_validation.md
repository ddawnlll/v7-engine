# Financial ML Validation — Walk-Forward, Purging, Embargo

## Abstract

Financial data violates the IID assumption of standard cross-validation. Lopez de Prado (2018, *Advances in Financial Machine Learning*) developed a suite of validation methods specific to finance: purged k-fold cross-validation removes training samples whose labels overlap temporally with test samples; embargo adds a gap after test periods to prevent information leakage; combinatorial purged cross-validation (CPCV) generates multiple backtest paths for robust performance estimation. These methods are essential for any ML model that will be deployed in live trading.

## Why It Matters for V7

The Policy Critic will be trained on financial time-series data where standard k-fold CV produces **dangerously optimistic** performance estimates. Without purging and embargo, the critic will appear to perform well in validation but fail in live trading. Walk-forward validation with purge+embargo is a non-negotiable evidence gate (≥ 4/5 folds required for all version transitions).

## What the Literature Says

### Why Standard CV Fails in Finance

1. **Serial correlation**: Adjacent observations are correlated → random train/test splits leak information
2. **Label overlap**: Labels (e.g., realized_r over next N bars) span multiple observations → training samples see test-label information
3. **Non-stationarity**: Distribution changes over time → random split trains on future-like data, tests on past-like data

### Purging

Remove from the training set any observation whose label's time window overlaps with a test set observation's label window. This prevents the model from learning, during training, information that will be used to evaluate it.

### Embargo

After purging, additionally remove a small gap of observations immediately following each test set. This prevents information leakage from test-label outcomes that may correlate with immediately subsequent training observations.

### Combinatorial Purged CV (CPCV)

Standard walk-forward provides only **one backtest path** → high variance in performance estimate. CPCV generates C(N,k) combinations of train/test splits, purges each, and produces a **distribution** of OOS performance metrics. This enables: (a) confidence intervals on performance, (b) PBO computation, (c) detection of path-dependent overfitting.

## How It Applies to V7

1. **Training**: CPCV with N=6 groups, k=2 test groups → 15 splits → 5 backtest paths
2. **Purging**: Remove training samples whose outcome window overlaps any test sample
3. **Embargo**: Small gap (e.g., 1% of data) after each test period
4. **Walk-forward requirement**: ≥ 4/5 folds must show consistent improvement direction

## Decision: USE NOW (mandatory evaluation infrastructure)

Purged walk-forward CV is required for all critic training and evaluation. Must be built as part of Phase 3 evaluation infrastructure.
