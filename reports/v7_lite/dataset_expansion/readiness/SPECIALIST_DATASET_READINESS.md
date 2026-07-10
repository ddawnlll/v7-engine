# Specialist Dataset Readiness Assessment

Generated: 2026-07-09T07:09:52Z

## Executive Summary

The expanded panel cache is now ready for specialist alpha discovery.
56 symbols at 1h timeframe with 2.1M rows per OHLCV field.

## Readiness Scores by Discovery Type

### 1. GLOBAL_GENERALIST_DISCOVERY

| Metric | Value |
|--------|-------|
| readiness_score_0_to_100 | 65 |
| available_symbols | 56 |
| available_clusters | 13 |
| available_timeframes | 1h |
| blocking_data_gaps | None — dataset is clean and complete for 1h |
| next_required_dataset_action | Run global factor scan across all 56 symbols |

**Assessment:** GOOD. The expanded panel provides broad coverage for global discovery.
Limitation: only 1h timeframe means scalp strategies may need higher resolution.

### 2. SYMBOL_SPECIALIST_DISCOVERY

| Metric | Value |
|--------|-------|
| readiness_score_0_to_100 | 80 |
| available_symbols | 56 |
| available_clusters | 13 |
| available_timeframes | 1h |
| blocking_data_gaps | None for 1h; missing 4h/15m for multi-timeframe |
| next_required_dataset_action | Run per-symbol alpha scan with cost model |

**Assessment:** GOOD. 56 symbols with 39k+ rows each is sufficient for symbol-specialist
discovery. The Truth V6 SOLUSDT result already proves symbol-specialist potential.

### 3. SYMBOL_CLUSTER_SPECIALIST_DISCOVERY

| Metric | Value |
|--------|-------|
| readiness_score_0_to_100 | 75 |
| available_symbols | 56 |
| available_clusters | 13 |
| available_timeframes | 1h |
| blocking_data_gaps | Cluster-specific derivatives data only for 19 symbols |
| next_required_dataset_action | Build cluster-aggregated factor signals, test per-cluster |

**Assessment:** GOOD. 13 clusters defined, 56 symbols mapped. The DERIVATIVES_RICH
cluster (19 symbols) has funding_rate data enabling basis/OI strategies.

### 4. REGIME_SPECIALIST_DISCOVERY

| Metric | Value |
|--------|-------|
| readiness_score_0_to_100 | 60 |
| available_symbols | 56 |
| available_clusters | 13 |
| available_timeframes | 1h |
| blocking_data_gaps | No regime labels in dataset; must be computed |
| next_required_dataset_action | Compute regime labels (trend/range/volatility) from OHLCV |

**Assessment:** PARTIAL. Dataset has enough data to compute regimes, but no regime
labels exist yet. Need to build regime detection pipeline.

### 5. SESSION_SPECIALIST_DISCOVERY

| Metric | Value |
|--------|-------|
| readiness_score_0_to_100 | 45 |
| available_symbols | 56 |
| available_clusters | 13 |
| available_timeframes | 1h |
| blocking_data_gaps | 1h resolution too coarse for session boundaries |
| next_required_dataset_action | Download 15m data for session boundary analysis |

**Assessment:** WEAK. 1h candles blur session boundaries (Asian/European/US).
Need 15m data for proper session analysis.

### 6. FILTER_ONLY_ALPHA_DISCOVERY

| Metric | Value |
|--------|-------|
| readiness_score_0_to_100 | 70 |
| available_symbols | 56 |
| available_clusters | 13 |
| available_timeframes | 1h |
| blocking_data_gaps | None — filters work on any OHLCV data |
| next_required_dataset_action | Run filter sweep across symbol × cluster matrix |

**Assessment:** GOOD. Filter-based strategies (volume filters, range filters,
volatility filters) work well with existing data.

## Overall Dataset Readiness

| Dimension | Score | Notes |
|-----------|-------|-------|
| Symbol coverage | 85 | 56 symbols across 13 clusters |
| Timeframe coverage | 40 | Only 1h; missing 4h/15m |
| Data quality | 95 | 67/91 PASS, 24 WARN_MINOR, 0 FAIL |
| Derivatives coverage | 37 | 19/56 symbols have funding_rate |
| Date range | 70 | 2021-2026 for most symbols |
| Panel cache completeness | 90 | 5 OHLCV fields, sorted, deduped |

**Composite readiness score: 70/100**

## Blocking Gaps

1. **No 4h timeframe** — limits swing strategy validation
2. **No 15m timeframe** — limits scalp/session strategy validation
3. **No regime labels** — must be computed from OHLCV
4. **Missing 7 target symbols** — SHIB, PEPE, FLOKI, FET, RENDER, OCEAN, WLD
5. **Derivatives only for 19 symbols** — limits basis/OI strategy scope

## Recommended Next Steps

1. **Immediate:** Run symbol-specialist alpha discovery on expanded panel
2. **Short-term:** Download 4h data via `scripts/download_binance.py`
3. **Medium-term:** Download 15m data for session analysis
4. **Medium-term:** Compute regime labels from OHLCV
5. **Long-term:** Fetch missing meme/AI tokens
