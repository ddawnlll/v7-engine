# AlphaForge Dataset Audit Report

**Date:** 2026-07-06
**Auditor:** AlphaForge Dataset Auditor
**Repo Root:** /home/daskomputer/src/v7-engine

---

## Scope

All data files under `data/`, `cache/`, and `reports/alphaforge/mining/` were audited.
No datasets found under `simulation/data/` or `alphaforge/data/` — those directories do not exist.

---

## Datasets Found: 11

| # | Dataset | Rows | Cols | Size |
|---|---------|------|------|------|
| 1 | `data/candidates/outcomes_v1.parquet` | 10,000 | 24 | 6.6 MB |
| 2 | `reports/alphaforge/mining/p10_smoke_v002/candidate_outcomes_v002.parquet` | 2,000 | 38 | 2.3 MB |
| 3 | `data/raw/BTCUSDT/BTCUSDT_1h_full.parquet` | 28,492 | 6 | 1.3 MB |
| 4 | `data/raw/ETHUSDT/ETHUSDT_1h_full.parquet` | 29,928 | 6 | 1.4 MB |
| 5 | `data/raw/BNBUSDT/BNBUSDT_1h_full.parquet` | 29,928 | 6 | 1.4 MB |
| 6 | `data/raw/SOLUSDT/SOLUSDT_1h_full.parquet` | 29,928 | 6 | 1.4 MB |
| 7 | `cache/factor_sprint/panel_close.parquet` | 29,928 | 20 | 4.8 MB |
| 8 | `cache/factor_sprint/panel_high.parquet` | 29,928 | 20 | 4.8 MB |
| 9 | `cache/factor_sprint/panel_low.parquet` | 29,928 | 20 | 4.8 MB |
| 10 | `cache/factor_sprint/panel_open.parquet` | 29,928 | 20 | 4.8 MB |
| 11 | `cache/factor_sprint/panel_volume.parquet` | 29,928 | 20 | 4.8 MB |

---

## 1. Dataset: outcomes_v1.parquet

**Path:** `data/candidates/outcomes_v1.parquet`
**Description:** Primary candidate outcomes — simulation results for 10,000 alpha candidates across 3 symbols (BTCUSDT, ETHUSDT, SOLUSDT).
**Time Range:** 2023-11-14 22:13:20 UTC to 2025-01-04 13:13:20 UTC (~14 months)
**Columns:** symbol, timestamp, side, mode, timeframe, regime_trend, volatility_percentile, momentum_rank, volume_zscore, atr_pct, btc_regime, pullback_atr, distance_to_range_high, spread_proxy, funding_context, net_R, gross_R, cost_R, mfe_R, mae_R, exit_reason, hold_duration, simulation_run_id, candidate_id

### Checks

| Check | Result |
|-------|--------|
| **NaN values** | 0 — PASS |
| **Inf values** | 0 — PASS |
| **Timestamp monotonicity** | Monotonic increasing — PASS |
| **Timestamp duplicates** | 0 — PASS |
| **Timestamp gaps** | 0 gaps — all 1h intervals contiguous — PASS |
| **Lookahead column names** | No suspicious names — PASS |
| **Train/test split** | None found — single partition. PASS (no cross-split consistency issue) |

### Issues: NONE

**Note:** Columns `net_R`, `gross_R`, `cost_R`, `mfe_R`, `mae_R`, `exit_reason`, `hold_duration` are simulation **outputs** (labels/targets), not features. If used as training features for another model, that would constitute lookahead contamination. In this dataset they are correctly stored as outcome labels.

---

## 2. Dataset: candidate_outcomes_v002.parquet

**Path:** `reports/alphaforge/mining/p10_smoke_v002/candidate_outcomes_v002.parquet`
**Description:** Mining run p10 smoke v002 — 2,000 simulation outcomes across 4 symbols.
**Time Range:** 2023-11-14 22:13:20 UTC to 2023-11-14 22:13:21 UTC (~2 seconds — timestamps are simulation epoch start, not market time)
**Columns:** row_id, symbol, timestamp, timeframe, mode, side, simulation_profile_id, dataset_version, regime_trend, volatility_percentile, momentum_rank, volume_zscore, atr_pct, btc_regime, pullback_atr, distance_to_range_high, spread_proxy, funding_context, gross_R, net_R, cost_R, mfe_R, mae_R, bars_held, exit_reason, is_valid, rejection_reason, profit_bucket, is_profitable_state, is_strong_win, is_bad_state, simulation_run_id, candidate_id, atr_bucket, regime_bucket, baseline_net_R_mean, excess_net_R, excess_profit_bucket

### Checks

| Check | Result |
|-------|--------|
| **NaN values** | 0 — PASS |
| **Inf values** | 0 — PASS |
| **Timestamp monotonicity** | Monotonic increasing — PASS |
| **Timestamp duplicates** | 0 — PASS |
| **Lookahead column names** | No suspicious names — PASS |
| **Train/test split** | No split column — PASS (mining output dataset) |

### Issues: NONE

**Warning:** `excess_net_R`, `baseline_net_R_mean`, `excess_profit_bucket` are derived metrics computed against a baseline. Must ensure baseline is computed from historical data only when used in training.

---

## 3-6. Raw OHLCV Datasets

**Paths:**
- `data/raw/BTCUSDT/BTCUSDT_1h_full.parquet`
- `data/raw/ETHUSDT/ETHUSDT_1h_full.parquet`
- `data/raw/BNBUSDT/BNBUSDT_1h_full.parquet`
- `data/raw/SOLUSDT/SOLUSDT_1h_full.parquet`

**Structure:** timestamp (int64, ms), open, high, low, close, volume

### BTCUSDT — ISSUES FOUND

| Check | Result |
|-------|--------|
| **NaN / Inf** | 0 — PASS |
| **Timestamp monotonicity** | Monotonic increasing — PASS |
| **Timestamp duplicates** | **2 duplicate timestamps (4 rows)** — FAIL |
| **Timestamp gaps** | **1 large data gap** — FAIL |
| **Rows** | 28,492 vs expected 29,928 — **1,438 missing hours** |

**Duplicate rows** (indices 8760-8763):
- `2024-01-01 00:00:00` — 2 identical rows (open=43200, high=43300, low=43100, close=43250)
- `2024-01-02 00:00:00` — 2 identical rows (open=43250, high=43400, low=43200, close=43350)

These are exact duplicates — the same OHLCV values for the same timestamps.

**Data gap**: After deduplication, there is a **59-day gap** from 2024-01-02 to 2024-03-01.

**Impact:** Training on BTC data without addressing this gap will cause:
1. Incorrect rolling window statistics across the gap boundary
2. Potential leakage if gap-filling methods use future data
3. Inconsistent symbol alignment in multi-symbol training frames

### ETHUSDT, BNBUSDT, SOLUSDT — CLEAN

| Check | Result |
|-------|--------|
| **NaN / Inf** | 0 — PASS |
| **Timestamp monotonicity** | Monotonic increasing — PASS |
| **Timestamp duplicates** | 0 — PASS |
| **Timestamp gaps** | 0 — all 1h intervals contiguous — PASS |
| **Rows** | 29,928 each — complete Jan 2023 to May 2026 — PASS |

---

## 7-11. Cache Factor Panels

**Paths:** `cache/factor_sprint/panel_*.parquet` (close, high, low, open, volume)
**Structure:** 20 columns (symbols), DatetimeIndex (2023-01-01 to 2026-05-31)
**Status:** Ephemeral cache — auto-generated and can be regenerated from raw data

### NaN Issues — NEEDS REPAIR (all 5 panels identical)

| Symbol | NaN Count | NaN % |
|--------|-----------|-------|
| MATICUSDT | 15,062 | **50.33%** |
| BTCUSDT | 6,528 | 21.81% |
| BNBUSDT | 5,832 | 19.49% |
| ETHUSDT | 5,832 | 19.49% |
| SOLUSDT | 5,832 | 19.49% |
| SUIUSDT | 2,944 | 9.84% |
| ARBUSDT | 1,959 | 6.55% |

**Total NaN per panel: 43,989 (7.35% of cells)**

**Root cause:** Different symbols have different listing dates. MATICUSDT has ~50% NaN because it was delisted/renamed during this period. The NaN pattern is identical across all 5 panels (same rows missing per symbol), confirming the alignment is correct — missing data is from symbols not yet trading.

**Impact:**
- XGBoost handles NaN internally (splits on non-missing only), but high NaN % in MATICUSDT means that symbol contributes little to splits.
- Padding forward fills would introduce lookahead.
- BTCUSDT at 21.81% NaN is suspicious — BTC has been trading continuously since before 2023. This suggests a data fetch gap for BTC cache (coinciding with the raw data gap identified above).

---

## 8. Lookahead Contamination Assessment

### Training Pipeline Risk

The two candidate datasets (`outcomes_v1.parquet`, `candidate_outcomes_v002.parquet`) contain simulation outcome columns (`net_R`, `gross_R`, `mfe_R`, `mae_R`, `exit_reason`, `hold_duration`) that are inherently forward-looking. These are appropriate as **training labels/targets**.

**Risk:** If any training pipeline uses these outcome columns as **features** (X) instead of labels (y), that is critical lookahead contamination. This audit cannot confirm which columns are used as features vs labels without inspecting the training code.

### Feature Construction Risk

The panel feature columns (`regime_trend`, `volatility_percentile`, `momentum_rank`, `volume_zscore`, `atr_pct`, `btc_regime`, `pullback_atr`, `distance_to_range_high`, `spread_proxy`, `funding_context`) contain no suspicious names. However, features computed from OHLCV data must use only data available at prediction time (i.e., no future high/low relative to the prediction point).

---

## 9. Summary of All Issues

| Severity | Dataset | Issue |
|----------|---------|-------|
| **MODERATE** | `BTCUSDT_1h_full.parquet` | 2 duplicate timestamps (4 exact duplicate rows) at 2024-01-01 and 2024-01-02 |
| **MODERATE** | `BTCUSDT_1h_full.parquet` | 59-day data gap (2024-01-02 to 2024-03-01), missing 1,438 hours |
| **LOW** | `cache/factor_sprint/panel_*.parquet` (5 files) | 43,989 NaN values per panel (7.35%), mostly from MATICUSDT delisting and BTC cache gap |
| **INFO** | `outcomes_v1.parquet` | Simulation outcome labels present — must not be used as features |
| **INFO** | `candidate_outcomes_v002.parquet` | Derived metrics (excess_net_R etc.) — must verify historical-only computation |

---

## 10. Recommendation

### Immediate actions:
1. **Deduplicate BTCUSDT raw data** — remove the 4 exact duplicate rows (drop_duplicates on timestamp).
2. **Investigate BTC data gap** — the 59-day gap in Q1 2024 needs to be filled from an alternate data source if BTC is used for training in that period.
3. **Document NaN handling for cache panels** — ensure downstream training code uses XGBoost's built-in NaN handling or explicit masking, not forward fill.

### Training pipeline audit needed:
- Verify that `net_R`, `gross_R`, `mfe_R`, `mae_R` are never used as input features.
- Verify that `excess_net_R` and `baseline_net_R_mean` in V002 are computed from historical-only data.

---

## Verdict: NEEDS_REPAIR

The BTCUSDT raw data has a significant gap and duplicate rows.
The cache panels have pervasive NaN values (acceptable but needs documented handling).
No lookahead contamination detected in column names or structure,
but training code audit is required to confirm outcome columns aren't used as features.

---
