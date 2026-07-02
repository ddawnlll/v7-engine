# v0.31A — Real-Data Model Failure Diagnostic Report

**Date:** 2026-07-02
**Config:** SCALP, 1h, BTC/ETH/SOL/BNB, 118K bars, 6-fold WFV, XGBoost depth=4/200trees
**Status:** DIAGNOSTIC_ONLY — No model config changed

---

## Executive Summary

| Question | Answer | Evidence |
|----------|--------|----------|
| Are labels meaningful? | ✅ YES | Mean net_R = +0.0065, balanced classes |
| Does the model learn? | ✅ YES | Raw OOS acc = 42.6% (beats 33% random, beats 42% majority) |
| Is confidence useful? | ❌ NO | Accuracy is flat across ALL thresholds (0.42-0.44) |
| Is NO_TRADE working? | ❌ NO | 0% accuracy on NO_TRADE — class collapsed |
| Is the threshold the problem? | ❌ NO | Threshold filter is a measurement artifact, not a fix |
| Is the model stable? | ✅ YES | Fold stability = 0.97, std = 1.3% across folds |

## Registered Hypothesis

```
HYP-031-001 — NO_TRADE class collapse reduces effective model capacity.

Evidence:
  - NO_TRADE accuracy = 0% (49/6121 correct)
  - Model predicts NO_TRADE only 0.5% of the time
  - Per-class accuracy oscillates between folds (89% SHORT ↔ 89% LONG)
  - Raw accuracy (42.6%) barely beats majority class (42.0%)

Interpretation:
  The 3-class softmax is effectively 2-class. NO_TRADE has no predictive 
  signal in 1h features at SCALP horizons, forcing the model to choose 
  LONG/SHORT on every bar. This causes the fold-level oscillation.

Action (if approved):
  Train as 2-class (drop NO_TRADE, or weight it at 0) and compare.

Acceptance criteria:
  - 2-class accuracy > 63% (adjusted majority baseline)
  - Per-class accuracy stable across folds
  - Net_R positive and fold-consistent
```

---

# v0.31A — Label Audit

## 1. Class Distribution
| Class | Count | % |
|-------|-------|---|
| LONG_NOW | 49130 | 41.6% |
| SHORT_NOW | 49658 | 42.0% |
| NO_TRADE | 19436 | 16.4% |

## 2. Economic Separability
| Metric | Value |
|--------|-------|
| Mean Gross R | 0.0072 |
| Mean Net R | 0.0065 |
| Cost drag | 0.0007 |

**Critical question:** Do LONG and SHORT labels have positive future net_R after costs?

## 3. Class Distribution Per Fold
| Fold | LONG | SHORT | NO_TRADE | Dominant % |
|------|------|-------|----------|------------|
| 1 | 2515 | 2709 | 1109 | 42.8% |
| 2 | 2722 | 2593 | 1018 | 43.0% |
| 3 | 2563 | 2681 | 1089 | 42.3% |
| 4 | 2696 | 2661 | 976 | 42.6% |
| 5 | 2555 | 2785 | 993 | 44.0% |
| 6 | 2648 | 2749 | 936 | 43.4% |

## 4. Baselines
| Baseline | Expected Accuracy |
|----------|-------------------|
| Random (uniform) | 33.3% |
| Majority class | 42.0% |
| Always LONG | 41.6% |
| Always SHORT | 42.0% |
| Always NO_TRADE | 16.4% |

## 5. Verdict

**PASS: Labels are balanced and carry positive net_R.** Model failure is not in the labels.

---

# v0.31A — Model Failure Analysis

## 1. Fold-by-Fold Performance
| Fold | Train Acc | OOS Acc | Gap | Active Trades | Low Conf % |
|------|-----------|---------|-----|---------------|------------|
| 1 | 0.6749 | 0.4173 | 0.2575 | 1216 | 80.8% |
| 2 | 0.5959 | 0.4341 | 0.1618 | 207 | 96.7% |
| 3 | 0.5654 | 0.4042 | 0.1612 | 1262 | 80.1% |
| 4 | 0.5427 | 0.4331 | 0.1095 | 450 | 92.9% |
| 5 | 0.5377 | 0.4221 | 0.1156 | 255 | 96.0% |
| 6 | 0.5275 | 0.4450 | 0.0826 | 12 | 99.8% |

## 2. Per-Class Accuracy (OOS, no threshold)
| Fold | LONG Acc | SHORT Acc | NO_TRADE Acc |
|------|----------|-----------|--------------|
| 1 | 0.0736 | 0.8933 | 0.0343 |
| 2 | 0.8924 | 0.1207 | 0.0069 |
| 3 | 0.7948 | 0.1940 | 0.0028 |
| 4 | 0.4611 | 0.5637 | 0.0000 |
| 5 | 0.5902 | 0.4183 | 0.0000 |
| 6 | 0.2088 | 0.8236 | 0.0011 |

## 3. Confusion Matrix (OOS, all folds)

| True \ Pred | LONG | SHORT | NO_TRADE |
|-------------|------|-------|----------|
| LONG       |   7955 |   7657 |     87 |
| SHORT      |   7905 |   8182 |     91 |
| NO_TRADE   |   3004 |   3068 |     49 |

**Column dominance:** The model's most-predicted class for each true label: {0: 0, 1: 1, 2: 1}
**Correct predictions:** 42.6%
**Off-diagonal (errors):** 57.4%

## 4. Fold Stability
| Metric | Value |
|--------|-------|
| Mean OOS acc | 0.4260 |
| Std OOS acc  | 0.0132 |
| Min OOS acc  | 0.4042 |
| Max OOS acc  | 0.4450 |
| Fold stability (1 - CV) | 0.9691 |

## 5. Diagnosis

**BORDERLINE:** Train (57.4%) > OOS (42.6%), gap=14.8%. May improve with regularization.

---

# v0.31A — Confidence Calibration

## 1. Bucket Analysis

| Confidence | Count | % of Total | Accuracy | LONG | SHORT | NO_TRADE |
|------------|-------|------------|----------|------|-------|----------|
| 0.30-0.35 | 66 | 0.2% | 0.3788 | 28 | 23 | 15 |
| 0.35-0.40 | 1485 | 3.9% | 0.3859 | 699 | 671 | 115 |
| 0.40-0.45 | 14109 | 37.1% | 0.4216 | 6206 | 7823 | 80 |
| 0.45-0.50 | 12317 | 32.4% | 0.4372 | 6016 | 6290 | 11 |
| 0.50-0.55 | 6619 | 17.4% | 0.4211 | 3964 | 2650 | 5 |
| 0.55-0.60 | 2551 | 6.7% | 0.4269 | 1522 | 1029 | 0 |
| 0.60-1.00 | 851 | 2.2% | 0.4442 | 429 | 421 | 1 |

## 2. Decision Rule Check

- Accuracy above 0.55: 0.4312 (3402 samples)
- Accuracy below 0.55: 0.4255 (34596 samples)
- **Verdict:** Confidence does NOT meaningfully predict accuracy. Threshold tuning would be blind.

---



---

# v0.31A — Feature-Family Ablation Plan

## 1. Current Feature Set
- **60 features** across all groups
- Feature names: ['amihud_illiquidity_N', 'atr_N', 'atr_expansion_N', 'atr_pct_N', 'bb_position', 'bb_width', 'consecutive_dn_N', 'consecutive_up_N', 'cusum_negative', 'cusum_positive', 'cusum_signal', 'depth_ratio_N', 'doji_N', 'engulfing_N', 'gap_N', 'garman_klass_vol_N', 'hammer_N', 'high_low_range_N', 'highest_N', 'hmm_vol_probability']

## 2. Proposed Families

| Family | Estimated Count | Hypothesis |
|--------|----------------|------------|
| Returns/Price Action | ~10 | Short-term mean reversion signal |
| Momentum | ~8 | Trend following on multiple horizons |
| Volatility/ATR | ~6 | Regime detection, position sizing |
| Volume | ~6 | Volume confirmation / divergence |
| Trend (MA/EMA) | ~8 | Directional bias on multiple resolutions |
| Regime | ~5 | Market regime classification |
| Candle Patterns | ~6 | Single-candle pattern recognition |
| Cross-symbol | ~4 | Lead-lag relationships |
| All Features | ~60 | Full set (current baseline) |
| Shuffled (null) | 60 | Permuted labels — control for data snooping |

## 3. Methodology

1. Train with each family ALONE using same config (6-fold WFV, SCALP 1h)
2. Record OOS accuracy, net_R, fold stability
3. Compare against null (shuffled labels) baseline
4. If NO family beats null → features are not predictive → back to feature engineering
5. If 1-2 families beat null → feature set reduction is the right path
6. If ALL families beat null but combined set does not → interference / multicollinearity

## 4. Stop Condition

Ablation concludes when we have a clear answer to:

> Does any feature family carry economically meaningful OOS signal?

If yes → feature reduction + regularization.
If no → feature engineering redesign.