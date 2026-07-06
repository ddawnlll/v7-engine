# Phase 4H: Feature Parity Harness Skeleton

**Status**: SKELETON — pending live feature engine implementation (blocked by #273)
**Date**: 2026-07-06
**Issue**: #275

---

## Overview

This document defines the feature parity harness skeleton for comparing batch (alphaforge) vs live (runtime) computation of the 16 locked Alpha1 features. The live feature engine does not exist yet — this skeleton establishes the contract, tolerances, and test structure so that parity verification can begin immediately upon live engine implementation.

---

## Per-Feature Mapping

| # | Feature | Batch Source | Formula | Tolerance | Type | Risk |
|---|---------|-------------|---------|-----------|------|------|
| 1 | `bb_position` | pipeline.py:1520 | `(close - lower) / (upper - lower)` | 0.0 | exact | CRITICAL |
| 2 | `ofi_N` | orderbook.py:1459 | `rolling_mean((up_vol - down_vol) / total_vol)` | 1e-6 | absolute | LOW |
| 3 | `atr_expansion_N` | pipeline.py:1122 | `ATR[t] / SMA(ATR, window)[t]` | 1e-6 | absolute | HIGH |
| 4 | `return_zscore_N` | pipeline.py:851 | `(r[t] - mean(r)) / std(r, ddof=1)` | 1e-6 | absolute | LOW |
| 5 | `vwap_mid_deviation_N` | orderbook.py:1676 | `(mid - vwap) / vwap` | 1e-6 | absolute | LOW |
| 6 | `trade_count_N` | orderbook.py:1758 | `rolling z-score: (vol - mean) / std(ddof=1)` | 1e-6 | absolute | LOW |
| 7 | `multi_level_obi_N` | orderbook.py:1273 | `exp-weighted sum of OBI at 5 levels` | 1e-6 | absolute | MEDIUM |
| 8 | `microprice_N` | orderbook.py:1001 | `low*(1-w) + high*w, w=up_vol/total` | 1e-6 | absolute | LOW |
| 9 | `log_return_1` | pipeline.py:806 | `ln(close[t] / close[t-1])` | 0.0 | exact | LOW |
| 10 | `garman_klass_vol_N` | pipeline.py:956 | `sqrt(rolling_mean(0.5*ln(H/L)^2 - (2ln2-1)*ln(C/O)^2))` | 1e-10 | absolute | LOW |
| 11 | `doji_N` | candle_pattern.py:52 | `rolling fraction where \|open-close\| / (high-low) <= 0.1` | 0.0 | exact | LOW |
| 12 | `hammer_N` | candle_pattern.py:137 | `rolling fraction: lower_shadow >= 2*body AND upper <= 0.3*body` | 0.0 | exact | LOW |
| 13 | `volume_trend_N` | pipeline.py:1355 | `rolling linear regression slope of volume` | 1e-10 | absolute | LOW |
| 14 | `cusum_positive` | regime.py:439 | `S_pos[t] = max(0, S[t-1] + r[t] - drift)` | 1e-10 | absolute | LOW |
| 15 | `rsi_N` | pipeline.py:1201 | `100 - 100/(1+avg_gain/avg_loss)` Wilder's | 1e-6 | absolute | HIGH |
| 16 | `parkinson_vol_N` | pipeline.py:1000 | `sqrt(rolling_sum(ln(H/L)^2) / (4*ln(2)*count))` | 1e-10 | absolute | LOW |

---

## Tolerance Rationale

### Exact (0.0)
Features with exact tolerance MUST be bit-identical between batch and live:
- **bb_position**: 97.3% feature dominance; any drift cascades to ALL predictions
- **log_return_1**: Single-bar computation; no smoothing to absorb rounding
- **doji_N / hammer_N**: Boolean threshold → fraction; floating-point would change which bars cross threshold

### Absolute 1e-6
Features where Wilder's smoothing or division introduces minor floating-point differences:
- **atr_expansion_N**, **rsi_N**: Stateful smoothing with warmup divergence risk
- **ofi_N**, **return_zscore_N**, **vwap_mid_deviation_N**, **trade_count_N**: Division-based z-scores

### Absolute 1e-10
Features where sqrt or OLS regression introduces negligible floating-point differences:
- **garman_klass_vol_N**, **parkinson_vol_N**: sqrt sensitivity
- **volume_trend_N**: OLS normal equations
- **cusum_positive**: Stateful accumulator with small drift

---

## Highest-Risk Mismatches

### 1. bb_position (CRITICAL)

**Risk**: 97.3% feature dominance — any bit-level drift cascades to every prediction.

**Root cause**: The denominator `(upper - lower)` approaches zero in low-volatility regimes, amplifying rounding errors. The batch implementation uses `std(ddof=1)` and `SMA(20)`; the live engine must use identical ddof and window semantics.

**Mitigation**: Tolerance=0.0 (bit-identical). Live engine must:
- Use ddof=1 (not ddof=0) for standard deviation
- Use exact SMA(20) window (no warmup tricks)
- Use the same close price source (no OHLCV-proxy substitutions)

### 2. atr_expansion_N (HIGH)

**Risk**: Ratio of two smoothed values diverges during warmup period.

**Root cause**: ATR warmup (<20 bars) uses partial-window normalization. Batch computes `ATR[t] / SMA(ATR, window)[t]` where SMA counts only available bars during warmup. Live engine may use a different warmup strategy.

**Mitigation**: Tolerance=1e-6. Live engine must:
- Replicate exact warmup behavior (partial-window SMA)
- Use identical ATR period and smoothing method
- Match Wilder's smoothing seed value

### 3. rsi_N (HIGH)

**Risk**: Wilder's smoothing is stateful; warmup path diverges if seed values differ.

**Root cause**: First RSI value depends on initial `avg_gain`/`avg_loss` seed. Batch seeds with the first-window mean of gains/losses. Live engine may seed differently (e.g., EMA-style seed).

**Mitigation**: Tolerance=1e-6. Live engine must:
- Seed `avg_gain` and `avg_loss` with the arithmetic mean of the first window's gains/losses
- Use Wilder's smoothing (not EMA) for subsequent updates
- Match the exact RSI period parameter

---

## Test Structure

The test file `runtime/tests/test_alpha1_feature_parity.py` contains:

1. **`test_feature_manifest_completeness`** — Verifies all 16 features are in the manifest with formulas, tolerances, and rationale
2. **`test_bb_position_is_exact_tolerance`** — Documents that bb_position MUST be bit-identical (0.0 tolerance)
3. **`test_remaining_features_have_documented_tolerance`** — Documents tolerance for each non-bb_position feature
4. **`test_high_risk_mismatches_documented`** — Verifies the 3 highest-risk mismatches are documented
5. **`test_parity_comparison_not_yet_implemented`** — Placeholder (skipped) for actual batch vs live comparison
6. **`test_parity_batch_live_comparison`** — Placeholder (skipped) for the core parity check

### Expansion Plan

When the live feature engine is implemented:
1. Add `compute_batch(feature, data)` and `compute_live(feature, data)` helpers
2. Load a representative historical sample (e.g., 1000 bars of BTCUSDT 4h)
3. Compute all 16 features via both paths
4. Assert `|batch - live| <= tolerance` for each feature
5. Flag any mismatches exceeding tolerance for investigation

---

## Constraints

- **Do NOT implement the live feature engine** (blocked by #273 design decision)
- **Do NOT touch alphaforge/ source files**
- **Do NOT touch simulation/ files**
- **Tests must PASS** — skeleton tests verify harness structure, not actual parity

---

## Next Steps

1. **#273**: Design decision for live feature engine architecture
2. **Post-#273**: Implement live feature engine
3. **Post-implementation**: Expand this harness with actual batch vs live comparison tests
4. **Validation**: Run full parity suite on representative historical sample
5. **Lock**: Document final tolerances after first empirical evidence
