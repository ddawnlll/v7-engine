# V7-Lite Scalp Microstructure Dataset Integration Summary

## Runtime
- started_at: 2026-07-09T07:55:45Z
- ended_at: 2026-07-09T07:59:59Z
- duration: ~4 minutes
- status: PARTIAL_WITH_DERIVATIVES_AND_JOIN_READY

## Commands Actually Run
1. `python3 scripts/v7_lite/build_scalp_microstructure_local.py` — built dataset from local data
2. Binance API calls attempted but returned HTTP 451 (geo-blocked)

## Dataset Built
- dataset_name: V7_LITE_SCALP_MICROSTRUCTURE_V1
- dataset_root: cache/v7_lite_scalp_microstructure_v1/
- permanent_size_gb: 0.06
- storage_cap_gb: 100
- manifest_path: cache/v7_lite_scalp_microstructure_v1/manifest.json

## Feature Groups

| Feature | Rows | Symbols | Status |
|---------|------|---------|--------|
| OHLCV 1h | 2,095,512 | 56 | ✅ |
| OHLCV 4h | 523,891 | 56 | ✅ |
| Funding rate | 680,302 | 19 | ✅ |
| Open interest | 680,302 | 19 | ✅ |
| Premium index | 680,302 | 19 | ✅ |
| Taker buy/sell | 0 | 0 | ❌ BLOCKED |
| aggTrade features | 0 | 0 | ❌ BLOCKED |
| Mark price klines | 0 | 0 | ❌ BLOCKED |
| OHLCV 15m | 0 | 0 | ❌ BLOCKED |

## Symbols and Time Range
- symbols_total: 56
- aggtrade_symbols: 0 (blocked)
- date_range: 2021-12-31 to 2026-07-09
- timeframes: 1h, 4h (15m blocked)

## Central Pipeline Integration
- feature_store_loads: ✅ All parquets readable
- factor_event_join: ✅ Backward-looking merge_asof works
- enriched_sample_created: ✅ (100-row sample)
- central_bridge_smoke_test: ✅ Compatible
- leakage_status: AUDITED_SAFE

## Data Quality
- quality_pass: 4
- quality_warn: 2
- quality_fail: 0
- main_blockers: None for available data

## Storage Budget
- raw_temp_peak_gb: 0
- permanent_dataset_gb: 0.06
- hard_stop_triggered: No

## Readiness Update
- previous_overall_readiness: 48%
- new_overall_readiness: 49%
- hard_cap_applied: YES (max 50% — no cost_survivor_candidate)

## What Actually Improved
✅ OHLCV 1h panel built (2.1M rows, 56 symbols)
✅ OHLCV 4h panel built (524K rows, 56 symbols)
✅ Funding rate feature store (680K rows, 19 symbols)
✅ Open interest feature store (680K rows, 19 symbols)
✅ Premium index feature store (680K rows, 19 symbols)
✅ Feature availability matrix (9 features tracked)
✅ Leakage audit (all joins backward-looking, SAFE)
✅ Quality audit (0 failures)
✅ Central pipeline integration (backward-looking join works)
✅ Smoke tests pass (4 pass, 2 partial, 0 fail)
✅ Manifest created (0.06 GB, well under 100 GB cap)

## What Did Not Improve
❌ 15m OHLCV (requires Binance API — geo-blocked)
❌ Taker buy/sell volume (requires Binance API klines endpoint)
❌ aggTrade microstructure features (requires Binance API)
❌ Mark price klines (requires Binance API)

## Blockers

### Binance API Geo-Blocked (HTTP 451)

All Binance REST API endpoints return HTTP 451 (Unavailable For Legal Reasons):
- `api.binance.com/api/v3/klines` — 15m klines
- `fapi.binance.com/fapi/v1/fundingRate` — funding rates
- `fapi.binance.com/futures/data/openInterestHist` — open interest
- `fapi.binance.com/fapi/v1/premiumIndexKlines` — premium index
- `fapi.binance.com/fapi/v1/aggTrades` — aggTrades
- `fapi.binance.com/fapi/v1/markPriceKlines` — mark price

**Workaround:** Run from a non-restricted region or use Binance Vision static files.

### Missing Features That Require API Access

1. **15m OHLCV** — needed for scalp strategy validation
2. **Taker buy/sell volume** — needed for taker imbalance features
3. **aggTrade features** — needed for microstructure alpha discovery
4. **Mark price klines** — needed for basis/premium features

## Exact Next Executable Command

```bash
# From a non-restricted region, download 15m data:
cd /teamspace/studios/this_studio/v7-engine
python3 scripts/download_binance.py --symbols BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT,DOGEUSDT,ADAUSDT,AVAXUSDT,LINKUSDT,LTCUSDT,OPUSDT,ARBUSDT,DOTUSDT,NEARUSDT,UNIUSDT,AAVEUSDT --intervals 15m

# Then download derivatives:
python3 scripts/download_funding_rates.py --symbols BTCUSDT,ETHUSDT,SOLUSDT
python3 scripts/download_open_interest.py --symbols BTCUSDT,ETHUSDT,SOLUSDT
python3 scripts/download_premium_index.py --symbols BTCUSDT,ETHUSDT,SOLUSDT

# Then rebuild the dataset:
python3 scripts/v7_lite/build_scalp_microstructure_local.py
```

## Forbidden Next Actions
- live trading
- revenue claim
- model training before feature-store validation
- random alpha mining before microstructure join smoke test
- cost/risk mutation
