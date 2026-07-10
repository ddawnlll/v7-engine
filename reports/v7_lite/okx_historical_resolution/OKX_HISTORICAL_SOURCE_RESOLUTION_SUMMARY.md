# OKX Historical Microstructure Source Resolution Summary

## Runtime
- started_at: 2026-07-09T12:25:37.384163+00:00
- ended_at: 2026-07-09T12:25:37.430806+00:00
- status: PARTIAL_WITH_FALLBACK_SOURCE_IDENTIFIED

## P2 coverage reality check
- p2_actual_coverage: ~1 hour per symbol
- p2_was_recent_only: True
- p2_conclusion: NOT historical. P2 uses recent OKX trades only.

## OKX source candidates
- static_archive: 404 (not available)
- rest_historical (trades): EXISTS but RECENT ONLY (~5 min window)
- history_candles: YES — 375 days for BTC/ETH/SOL
- funding_rate_history: YES — 33 days for all 3 symbols
- recent_api: Available (trades + funding)
- manual_download: Possible (Excel per month, but manual)

## Download attempts
- attempts_count: 14 probes + 3 symbols x 30 page pagination
- historical_trade_source_found: NO
- best_source (trades): OKX /v5/market/history-trades — RECENT ONLY
- best_source (funding): OKX /v5/public/funding-rate-history — 33 days
- best_source (OHLCV): OKX /v5/market/history-candles — 375 days

## Mini build
- built: Funding features only (199 rows per symbol, 33 days)
- symbols: BTCUSDT, ETHUSDT, SOLUSDT
- date_range: 2026-06-06 -> 2026-07-09
- coverage_days: 33 (funding), 375 (candles)
- feature_rows_funding: 597 (3 symbols × 199)
- output_files: 3 parquet files
- raw_evicted: 0 candle JSONs

## Timestamp/leakage
- timestamp_semantics: Trade execution time (no future data leak)
- asof_join_safe: YES
- unknown_delay_flags: true
- leakage_verdict: SAFE (no backfill/revise observed)

## Storage
- permanent_size_mb: 0.09
- staging_peak_mb: 0.15
- hard_stop_triggered: NO (disk at 16.19%)

## Decision
- OKX_HISTORICAL_1DAY_ONLY
- OKX public API does NOT support historical trade/tick downloads.
- Only candles (OHLCV) and funding (8h snapshots) are available historically.

## Impact on V7-Lite
- Can P2 scale build become true historical: NO (trade ticks unavailable)
- Can specialist scan be trusted: PARTIAL (funding+candles OK, trade features only recent)
- Should we proceed to alpha scan: NOT YET (need resolve historical trades)

## Exact next executable command
```
cd /teamspace/studios/this_studio/v7-engine
/commands/python3 scripts/v7_lite/smoke_test_okx_historical_resolution.py
```

## Forbidden next actions
- live trading
- revenue claim
- alpha scan on recent-only microstructure features
- model training before historical coverage is solved
- cost/risk mutation
