# Central Pipeline Integration Report

Generated: 2026-07-09T07:59:46.974461+00:00

## Feature Store

Dataset: `cache/v7_lite_scalp_microstructure_v1/`

### Available Features

| Feature | Parquet | Rows | Symbols | Status |
|---------|---------|------|---------|--------|
| OHLCV 1h | ohlcv/klines_1h.parquet | 2,095,512 | 56 | ✅ |
| OHLCV 4h | ohlcv/klines_4h.parquet | 523,891 | 56 | ✅ |
| Funding rate | derivatives/funding_rate.parquet | 680,302 | 19 | ✅ |
| Open interest | derivatives/open_interest.parquet | 680,302 | 19 | ✅ |
| Premium index | derivatives/premium_index_klines.parquet | 680,302 | 19 | ✅ |
| Taker volume | derivatives/taker_buy_sell_volume.parquet | 0 | 0 | ✅ |
| aggTrade features | — | 0 | 0 | ❌ BLOCKED |
| Mark price klines | — | 0 | 0 | ❌ BLOCKED |

### Loading

```python
import pandas as pd
ohlcv_1h = pd.read_parquet("cache/v7_lite_scalp_microstructure_v1/ohlcv/klines_1h.parquet")
funding = pd.read_parquet("cache/v7_lite_scalp_microstructure_v1/derivatives/funding_rate.parquet")
oi = pd.read_parquet("cache/v7_lite_scalp_microstructure_v1/derivatives/open_interest.parquet")
taker = pd.read_parquet("cache/v7_lite_scalp_microstructure_v1/derivatives/taker_buy_sell_volume.parquet")
```

### Join to Factor Events

Factor events path: /teamspace/studios/this_studio/v7-engine/reports/v7_lite/p0_primitives/factor_events/FACTOR_SIGNAL_EVENTS.csv
Available: ✅

```python
factor_events = pd.read_csv("/teamspace/studios/this_studio/v7-engine/reports/v7_lite/p0_primitives/factor_events/FACTOR_SIGNAL_EVENTS.csv")
enriched = pd.merge_asof(
    factor_events.sort_values("timestamp"),
    funding.sort_values("timestamp"),
    on="timestamp", by="symbol", direction="backward"
)
```

## Blockers

1. **Binance API geo-blocked (HTTP 451)** — all REST endpoints return 451
   - Affected: 15m klines, funding rate download, OI download, premium index,
     aggTrades, mark price klines
   - Workaround: Run from non-restricted region or use Binance Vision static files
2. **No 15m data** — requires API access or Binance Vision download
3. **No aggTrade features** — requires API access
4. **No mark price klines** — requires API access

## Recommendations

1. Download 15m data via `scripts/download_binance.py` from a non-restricted region
2. Run `scripts/download_funding_rates.py` from a non-restricted region
3. Build aggTrade features after API access is restored
