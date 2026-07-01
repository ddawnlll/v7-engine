# AlphaForge Profitability v0.1 — Complete Run Report
Generated: 2026-07-01 21:45 UTC
Pipeline version: 0.2.0
Mode: SWING (4h bars)

---

## Run: SENTETİK DATA (2000 bars × 3 symbols)

### Pipeline Genel
| Metric | Value |
|--------|-------|
| Verdict | PASS |
| Steps executed | ? |
| Duration | 15.087071796999226s |
| Model size | 1,217,206 bytes |

### Data Profile
| Metric | Value |
|--------|-------|
| Total bars | 6000 |
| Symbols | 3 |
| Features | 60 |
| Valid rows (non-NaN) | 5959 |
| LONG_NOW | 2035 (34.2%) |
| SHORT_NOW | 1961 (32.9%) |
| NO_TRADE | 1963 (32.9%) |

### Feature List
   1. amihud_illiquidity_N 🆕
   2. atr_N
   3. atr_expansion_N
   4. atr_pct_N
   5. bb_position
   6. bb_width
   7. consecutive_dn_N 🆕
   8. consecutive_up_N 🆕
   9. cusum_negative 🆕
  10. cusum_positive 🆕
  11. cusum_signal 🆕
  12. depth_ratio_N 🆕
  13. doji_N 🆕
  14. engulfing_N
  15. gap_N 🆕
  16. garman_klass_vol_N
  17. hammer_N 🆕
  18. high_low_range_N
  19. highest_N 🆕
  20. hmm_vol_probability 🆕
  21. hmm_vol_state 🆕
  22. liquidity_vacuum_N 🆕
  23. log_return_1
  24. log_return_N
  25. lowest_N 🆕
  26. macd
  27. macd_histogram
  28. macd_signal
  29. marubozu_N
  30. microprice_N 🆕
  31. microstructure_noise_N 🆕
  32. momentum_N
  33. multi_level_obi_N 🆕
  34. obi
  35. obv_N
  36. ofi_N 🆕
  37. parkinson_vol_N
  38. price_impact_slope_N 🆕
  39. quoted_spread_N 🆕
  40. range_breakout_N
  41. realized_volatility_N
  42. return_volatility_N
  43. return_zscore_N
  44. roc_N 🆕
  45. roll_spread_N 🆕
  46. rsi_N
  47. serial_correlation_N 🆕
  48. spread_pct_N 🆕
  49. stoikov_micro_price_N 🆕
  50. trade_count_N 🆕
  51. trade_intensity_N 🆕
  52. vamp_N 🆕
  53. volatility_regime 🆕
  54. volume_concentration_hhi_N 🆕
  55. volume_imbalance_N 🆕
  56. volume_ratio_N
  57. volume_trend_N
  58. vpin_N 🆕
  59. vwap_deviation
  60. vwap_mid_deviation_N 🆕

### Walk-Forward Validation (WFV)
| Config | Value |
|--------|-------|
| Folds | 7 |
| Train window | 2000 bars |
| Test window | 500 bars |
| Purge | 20 bars |
| Embargo | 20 bars |

#### Kârlılık Metrikleri
| Metric | Value | Threshold | Status |
|--------|-------|-----------|--------|
| Avg Sharpe | -9.1397 | > 0.0 | ❌ FAIL |
| Avg Profit Factor | 0.6397 | > 1.0 | ❌ FAIL |
| Avg Win Rate | 0.3268 (32.68%) | — | — |
| Avg Max Drawdown | -38.21% | > -30% | ❌ FAIL |
| Folds Passing | 0/7 | > 50% | ❌ |
| Accuracy Gap | 0.2692 | < 0.15 | ❌ FAIL |
| Train Accuracy | 0.6388 | — | — |
| Val Accuracy | 0.3696 | — | — |
| Sharpe Std Dev | 2.7728 | — | — |
| Fold Stability | 0.6966 | — | — |
| Total OOS Trades | 1359 | — | — |
| Verdict | FAIL_OVERFIT | — | — |

#### Per-Fold Detay
| Fold | Train | Val | OOS | TrnAcc | ValAcc | Sharpe | WinRate | MaxDD | ProfitF | Trades |
|------|-------|-----|-----|--------|--------|--------|---------|-------|---------|--------|
| 0 | 2000 | 240 | 240 | 0.719 | 0.342 | -11.93 | 0.308 | -50% | 0.580 | 224 |
| 1 | 2520 | 240 | 240 | 0.652 | 0.433 | -8.08 | 0.314 | -31% | 0.597 | 118 |
| 2 | 3040 | 240 | 240 | 0.659 | 0.367 | -9.12 | 0.338 | -39% | 0.658 | 222 |
| 3 | 3560 | 240 | 240 | 0.631 | 0.379 | -4.22 | 0.380 | -21% | 0.817 | 205 |
| 4 | 4080 | 240 | 240 | 0.611 | 0.354 | -9.05 | 0.320 | -36% | 0.626 | 178 |
| 5 | 4600 | 240 | 240 | 0.643 | 0.358 | -8.84 | 0.332 | -39% | 0.650 | 199 |
| 6 | 5120 | 240 | 240 | 0.557 | 0.354 | -12.73 | 0.296 | -52% | 0.550 | 213 |

#### SHAP Feature Importance (Top 20)
| Rank | Feature | Gain Score | New | Group |
|------|---------|-----------|-----|-------|
| 1 | atr_pct_N | 180.8 |    | — |
| 2 | realized_volatility_N | 176.0 |    | — |
| 3 | volume_concentration_hhi_N | 167.8 | 🆕 | — |
| 4 | macd_signal | 155.1 |    | — |
| 5 | quoted_spread_N | 143.6 | 🆕 | — |

#### Overfit Risk Flags
| Severity | Description |
|----------|-------------|
| HIGH | Fold 0: accuracy gap 0.3773 exceeds threshold 0.15. Train acc=0.7190, Val acc=0.3417 |
| MEDIUM | Fold 0: logloss gap 0.1282 exceeds threshold 0.1. Train ll=0.9697, Val ll=1.0979 |
| HIGH | Fold 1: accuracy gap 0.2190 exceeds threshold 0.15. Train acc=0.6524, Val acc=0.4333 |
| HIGH | Fold 2: accuracy gap 0.2919 exceeds threshold 0.15. Train acc=0.6586, Val acc=0.3667 |
| MEDIUM | Fold 2: logloss gap 0.1135 exceeds threshold 0.1. Train ll=0.9891, Val ll=1.1026 |
| HIGH | Fold 3: accuracy gap 0.2520 exceeds threshold 0.15. Train acc=0.6312, Val acc=0.3792 |
| HIGH | Fold 4: accuracy gap 0.2569 exceeds threshold 0.15. Train acc=0.6110, Val acc=0.3542 |
| HIGH | Fold 5: accuracy gap 0.2847 exceeds threshold 0.15. Train acc=0.6430, Val acc=0.3583 |
| HIGH | Fold 6: accuracy gap 0.2025 exceeds threshold 0.15. Train acc=0.5566, Val acc=0.3542 |

---

## Run: GERÇEK DATA (BTCUSDT, ETHUSDT • 2024-01/06)

### Pipeline Genel
| Metric | Value |
|--------|-------|
| Verdict | PASS |
| Steps executed | ? |
| Duration | 17.888669797001057s |
| Model size | 1,189,858 bytes |

### Data Profile
| Metric | Value |
|--------|-------|
| Total bars | 4000 |
| Symbols | 2 |
| Features | 60 |
| Valid rows (non-NaN) | 3959 |
| LONG_NOW | 1368 (34.6%) |
| SHORT_NOW | 1306 (33.0%) |
| NO_TRADE | 1285 (32.5%) |

### Feature List
   1. amihud_illiquidity_N 🆕
   2. atr_N
   3. atr_expansion_N
   4. atr_pct_N
   5. bb_position
   6. bb_width
   7. consecutive_dn_N 🆕
   8. consecutive_up_N 🆕
   9. cusum_negative 🆕
  10. cusum_positive 🆕
  11. cusum_signal 🆕
  12. depth_ratio_N 🆕
  13. doji_N 🆕
  14. engulfing_N
  15. gap_N 🆕
  16. garman_klass_vol_N
  17. hammer_N 🆕
  18. high_low_range_N
  19. highest_N 🆕
  20. hmm_vol_probability 🆕
  21. hmm_vol_state 🆕
  22. liquidity_vacuum_N 🆕
  23. log_return_1
  24. log_return_N
  25. lowest_N 🆕
  26. macd
  27. macd_histogram
  28. macd_signal
  29. marubozu_N
  30. microprice_N 🆕
  31. microstructure_noise_N 🆕
  32. momentum_N
  33. multi_level_obi_N 🆕
  34. obi
  35. obv_N
  36. ofi_N 🆕
  37. parkinson_vol_N
  38. price_impact_slope_N 🆕
  39. quoted_spread_N 🆕
  40. range_breakout_N
  41. realized_volatility_N
  42. return_volatility_N
  43. return_zscore_N
  44. roc_N 🆕
  45. roll_spread_N 🆕
  46. rsi_N
  47. serial_correlation_N 🆕
  48. spread_pct_N 🆕
  49. stoikov_micro_price_N 🆕
  50. trade_count_N 🆕
  51. trade_intensity_N 🆕
  52. vamp_N 🆕
  53. volatility_regime 🆕
  54. volume_concentration_hhi_N 🆕
  55. volume_imbalance_N 🆕
  56. volume_ratio_N
  57. volume_trend_N
  58. vpin_N 🆕
  59. vwap_deviation
  60. vwap_mid_deviation_N 🆕

### Walk-Forward Validation (WFV)
| Config | Value |
|--------|-------|
| Folds | 3 |
| Train window | 2000 bars |
| Test window | 500 bars |
| Purge | 20 bars |
| Embargo | 20 bars |

#### Kârlılık Metrikleri
| Metric | Value | Threshold | Status |
|--------|-------|-----------|--------|
| Avg Sharpe | -9.7120 | > 0.0 | ❌ FAIL |
| Avg Profit Factor | 0.6115 | > 1.0 | ❌ FAIL |
| Avg Win Rate | 0.3198 (31.98%) | — | — |
| Avg Max Drawdown | -39.83% | > -30% | ❌ FAIL |
| Folds Passing | 0/3 | > 50% | ❌ |
| Accuracy Gap | 0.2961 | < 0.15 | ❌ FAIL |
| Train Accuracy | 0.6766 | — | — |
| Val Accuracy | 0.3806 | — | — |
| Sharpe Std Dev | 1.9905 | — | — |
| Fold Stability | 0.7950 | — | — |
| Total OOS Trades | 564 | — | — |
| Verdict | FAIL_OVERFIT | — | — |

#### Per-Fold Detay
| Fold | Train | Val | OOS | TrnAcc | ValAcc | Sharpe | WinRate | MaxDD | ProfitF | Trades |
|------|-------|-----|-----|--------|--------|--------|---------|-------|---------|--------|
| 0 | 2000 | 240 | 240 | 0.719 | 0.342 | -11.93 | 0.308 | -50% | 0.580 | 224 |
| 1 | 2520 | 240 | 240 | 0.652 | 0.433 | -8.08 | 0.314 | -31% | 0.597 | 118 |
| 2 | 3040 | 240 | 240 | 0.659 | 0.367 | -9.12 | 0.338 | -39% | 0.658 | 222 |

#### SHAP Feature Importance (Top 20)
| Rank | Feature | Gain Score | New | Group |
|------|---------|-----------|-----|-------|
| 1 | atr_pct_N | 305.5 |    | — |
| 2 | spread_pct_N | 302.0 | 🆕 | — |
| 3 | bb_width | 287.7 |    | — |
| 4 | multi_level_obi_N | 281.8 | 🆕 | — |
| 5 | volume_concentration_hhi_N | 265.2 | 🆕 | — |

#### Overfit Risk Flags
| Severity | Description |
|----------|-------------|
| HIGH | Fold 0: accuracy gap 0.3773 exceeds threshold 0.15. Train acc=0.7190, Val acc=0.3417 |
| MEDIUM | Fold 0: logloss gap 0.1282 exceeds threshold 0.1. Train ll=0.9697, Val ll=1.0979 |
| HIGH | Fold 1: accuracy gap 0.2190 exceeds threshold 0.15. Train acc=0.6524, Val acc=0.4333 |
| HIGH | Fold 2: accuracy gap 0.2919 exceeds threshold 0.15. Train acc=0.6586, Val acc=0.3667 |
| MEDIUM | Fold 2: logloss gap 0.1135 exceeds threshold 0.1. Train ll=0.9891, Val ll=1.1026 |

---

## A/B Comparison: Baseline vs New Features

| Metric | Baseline (26 feat) | New (60 feat) | Δ |
|--------|:------------------:|:-------------:|:-:|
| Val Accuracy | 0.6495 | **0.6893** | +6.1% ✅ |
| LONG Precision | 0.6362 | **0.6791** | +4.3% ✅ |
| SHORT Precision | 0.6656 | **0.7006** | +3.5% ✅ |
| NO_TRADE Precision | 0.0000 | **1.0000** | +inf ✅ |
| Overfit Gap | 0.0422 | 0.0456 | +8.1% ⚠️ |

**Not:** A/B comparison sentetik veride yapıldı. Gerçek kârlılık metrikleri WFV tablosunda.

## Executive Summary

### Implemented Features (14 new, 60 total)
- **OrderBook (7):** OBI, OBI_N, OFI, VAMP, quoted spread, VWAP-to-mid, micro-price, volume HHI
- **Regime (3):** CUSUM detection, HMM trend classification, volatility regime
- **Candle Pattern (10+):** Doji, hammer, gap, consecutive, highest/lowest, ROC
- **Labeling (2):** Triple-barrier labeling, Meta-labeling
- **Validation (2):** CPCV splitter, Purged CV for Optuna
- **Infra (2):** 20-symbol download, Feature caching

### Profitability Status
- **Accuracy:** +6.1% improvement (0.6495 → 0.6893)
- **Sharpe:** -9.71 (FAIL — overfit) → tuning required
- **Profit Factor:** 0.61 (FAIL — below 1.0)
- **Overfit:** HIGH — accuracy gap 0.30, 0/3 folds pass

### Root Causes
1. Default hyperparameters (no Optuna tuning yet)
2. Short data window (6 months → only 3 folds possible)
3. SWING mode + 4h bars = limited samples
4. No feature selection (60 features with default params = overfit)

### Recommended Next Steps
1. Run Optuna + CPCV hyperparameter tuning
2. Test SCALP mode (15m bars → 10x more samples)
3. Expand data to 2-3 years
4. Apply feature selection (top 20 SHAP)
5. Tune meta-labeling threshold (>60%)